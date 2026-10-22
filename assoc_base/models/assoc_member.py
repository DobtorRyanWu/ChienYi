import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .. import tools_pii
from ..tools import assoc_today, check_guild_admin, guarded, qr_data_uri

# 會員卡條碼：64 bit 十進位字串（同 event.registration 的做法，USB 掃碼槍相容性最好）
BARCODE_BITS = 64
CARD_QR_SIZE_PX = 240
ADMIN_GROUP = 'assoc_base.group_assoc_admin'
SYSTEM_GROUP = 'base.group_system'
IMPORT_TEMPLATE = '/assoc_base/static/xls/assoc_member.xlsx'
# 只能由系統流程寫入的欄位（create 不查欄位 groups，要自己擋）
SYSTEM_WRITE_FIELDS = frozenset({
    'national_id_enc', 'national_id_hmac', 'national_id_masked', 'national_id_kind', 'barcode'})
GUARD_SYSTEM = 'assoc_member_system'
# 算出來的欄位：**沒有 inverse 的 stored compute 仍然寫得進去**，
# 而且寫進去的值會留著直到某個依賴變動才重算。
# 「會費繳至」決定誰在選舉人名冊上，所以要明確擋掉直接寫入。
# （compute 自己刷新走的是 `_write_multi`，不經過 `write()`，不受影響。）
COMPUTED_ONLY_FIELDS = frozenset({'fee_paid_until', 'coverage_from'})


class AssocMember(models.Model):
    _name = 'assoc.member'
    _description = '公會會員'
    _inherit = ['mail.thread']
    _order = 'company_id, member_no'
    _rec_names_search = ['name', 'member_no']

    partner_id = fields.Many2one(
        'res.partner', string='聯絡人', required=True, ondelete='restrict', tracking=True)
    name = fields.Char(
        string='姓名', compute='_compute_name', inverse='_inverse_name',
        store=True, readonly=False, tracking=True)
    email = fields.Char(string='Email', compute='_compute_contact', inverse='_inverse_email',
                        search='_search_email')
    mobile = fields.Char(string='手機', compute='_compute_contact', inverse='_inverse_mobile',
                         search='_search_mobile')
    image_128 = fields.Image(string='照片（小）', related='partner_id.image_128')
    image_1920 = fields.Image(
        string='照片', max_width=1920, max_height=1920,
        compute='_compute_image_1920', inverse='_inverse_image_1920',
        help='報到台核對本人用。會員自行上傳的照片要經文件審核才會套用到這裡。')
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, tracking=True,
        default=lambda self: self.env.company)
    member_no = fields.Char(string='會員編號', required=True, tracking=True)
    barcode = fields.Char(
        string='會員卡條碼', readonly=True, copy=False, index=True,
        default=lambda self: self._new_barcode(), groups=ADMIN_GROUP,
        help='印在會員卡上供報到台掃描。遺失時用「換發會員卡」讓舊卡失效。\n'
             '只有公會管理員讀得到：能讀條碼就能複製會員卡代人報到。')
    active = fields.Boolean(string='有效', default=True, tracking=True)
    fee_paid_opening = fields.Date(
        string='期初繳至',
        help='系統啟用前就已經繳到的日期（例如從舊名冊搬過來）。'
             '裝了繳費模組之後，系統會從這一天接著往後算。')
    fee_paid_until = fields.Date(
        string='會費繳至', compute='_compute_fee_coverage', store=True, readonly=True,
        tracking=True,
        help='算出來的，不能直接改：要調整請改「期初繳至」或處理應繳。')
    coverage_from = fields.Date(
        string='會籍起算', compute='_compute_fee_coverage', store=True, readonly=True,
        help='目前這段連續繳清是從哪一天開始的。空白代表沿用期初繳至。')
    is_voter_eligible = fields.Boolean(
        string='具選舉權', compute='_compute_is_voter_eligible', search='_search_is_voter_eligible',
        help='會籍有效且會費繳至今日（含）以後。選舉名冊於「凍結名冊」當下依此快照。')

    # ------------------------------------------------------------------
    # 身分證字號（明文不落地，見 tools_pii）
    # ------------------------------------------------------------------
    national_id = fields.Char(
        string='身分證字號', compute='_compute_national_id', inverse='_inverse_national_id',
        store=False, groups=ADMIN_GROUP, copy=False,
        help='唯一的寫入口。存檔後只保留密文、查詢索引與隱碼；讀回來一律是空白，'
             '要看明文請按「顯示身分證」（會留存取軌跡）。')
    national_id_enc = fields.Char(
        string='身分證（密文）', readonly=True, copy=False, groups=SYSTEM_GROUP)
    national_id_hmac = fields.Char(
        string='身分證（查詢索引）', readonly=True, copy=False, index=True, groups=SYSTEM_GROUP)
    national_id_masked = fields.Char(string='身分證字號（隱碼）', readonly=True, copy=False)
    national_id_kind = fields.Selection(
        [('tw_id', '國民身分證'), ('arc_new', '新式居留證'), ('arc_old', '舊式居留證')],
        string='證號類別', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # 技師資料（積分名冊用）
    # ------------------------------------------------------------------
    engineer_field = fields.Char(string='技師科別')
    engineer_cert_no = fields.Char(string='技師證書字號')
    join_date = fields.Date(string='入會日期')
    document_ids = fields.One2many('assoc.member.document', 'member_id', string='證明文件')

    _sql_constraints = [
        ('member_no_company_uniq', 'unique(company_id, member_no)', '同一公會內會員編號不可重複'),
        ('barcode_uniq', 'unique(barcode)', '會員卡條碼重複，請重新產生'),
        ('national_id_company_uniq', 'unique(company_id, national_id_hmac)',
         '同一公會內身分證字號不可重複'),
    ]

    @api.model
    def _new_barcode(self):
        return str(secrets.randbits(BARCODE_BITS))

    # ------------------------------------------------------------------
    # 聯絡人欄位：受控 sudo（取代 Contact Creation 群組）
    # ------------------------------------------------------------------
    # 給公會管理員 base.group_partner_manager 等於給他改任何聯絡人的權限，
    # 包含內部使用者的 partner（partner_share=False 對所有公會都看得到），
    # 日後一開寄信就能藉「重設密碼」劫持帳號。改成只在這裡以 sudo 寫，
    # 並且限定「同公會、且不是內部使用者」的聯絡人。
    @api.model
    def _partner_is_internal(self, partner):
        """這個聯絡人是不是（含已封存的）內部使用者。

        不用 `partner_share`：它是 compute，對已封存的內部使用者會回 True，
        等於把「改內部使用者的 email」這條劫持路徑放行。
        """
        users = partner.sudo().with_context(active_test=False).user_ids
        return bool(users.filtered(lambda user: not user.share))

    def _partner_sudo(self):
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            raise UserError(_('請先指定聯絡人。'))
        # 一律要求同公會：res.partner.company_id 多數是 NULL，
        # 寫成 `company_id and company_id != …` 會讓這道檢查對大多數聯絡人失效。
        if partner.company_id != self.company_id:
            raise AccessError(_('此聯絡人不屬於本公會，不能從會員資料修改。'))
        if self._partner_is_internal(partner):
            raise AccessError(_('此聯絡人是內部使用者，請由系統管理員維護。'))
        return partner.sudo()

    @api.depends('partner_id.name')
    def _compute_name(self):
        for member in self:
            member.name = member.partner_id.name

    def _inverse_name(self):
        for member in self:
            if member.name:
                member._partner_sudo().name = member.name

    @api.depends('partner_id.email', 'partner_id.mobile')
    def _compute_contact(self):
        for member in self:
            member.email = member.partner_id.email
            member.mobile = member.partner_id.mobile

    def _inverse_email(self):
        for member in self:
            member._partner_sudo().email = member.email

    def _inverse_mobile(self):
        for member in self:
            member._partner_sudo().mobile = member.mobile

    # 非儲存的 compute 欄位一定要給 search：Odoo 18 搜不到 search method 時
    # 只寫一行 ERROR 就把那個條件當恆真，篩選會靜默回傳全部名冊。
    def _search_email(self, operator, value):
        return [('partner_id.email', operator, value)]

    def _search_mobile(self, operator, value):
        return [('partner_id.mobile', operator, value)]

    def _search_is_voter_eligible(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('「具選舉權」只支援等於 True／False 的篩選。'))
        today = assoc_today(self)
        eligible = [
            ('active', '=', True),
            ('fee_paid_until', '>=', today),
            # 預繳未來期的人今天還不算有效
            '|', ('coverage_from', '=', False), ('coverage_from', '<=', today),
        ]
        if (operator == '=') == value:
            return eligible
        # **不能用 `['!', ...]` 取補集**：Odoo 把 '!' 直接編成 `NOT (...)`
        # （`osv/expression.py`），而 `fee_paid_until IS NULL` 會讓整段變成
        # NULL → `NOT NULL` 還是 NULL → 那一列被 WHERE 丟掉。
        # 結果是「沒繳過任何費的人」在 `=False` 的篩選裡查不到，
        # 與 compute 的答案相反。所以明寫補集，把 NULL 那一支列出來。
        return [
            '|', ('active', '=', False),
            '|', ('fee_paid_until', '=', False),
            '|', ('fee_paid_until', '<', today),
            '&', ('coverage_from', '!=', False), ('coverage_from', '>', today),
        ]

    @api.depends('partner_id.image_1920')
    def _compute_image_1920(self):
        for member in self:
            member.image_1920 = member.partner_id.image_1920

    def _inverse_image_1920(self):
        for member in self:
            member._partner_sudo().image_1920 = member.image_1920

    @api.model_create_multi
    def create(self, vals_list):
        # 欄位的 groups 只在 write() 檢查（models.py:4724），create() 不查——
        # 非 system 的管理員一次 create 就能把明文塞進 national_id_masked、
        # 或自己指定 barcode。這裡自己擋 vals，並清掉 context 的 default_*；
        # 真正的把關是 _check_pii_consistency（驗結果，§16 通則 1）。
        record = self
        if not guarded(self.env, GUARD_SYSTEM):
            for vals in vals_list:
                bad = SYSTEM_WRITE_FIELDS & set(vals)
                if bad:
                    raise AccessError(_('這些欄位不能直接指定：%s', ', '.join(sorted(bad))))
            stripped = {key: value for key, value in self.env.context.items()
                        if not (key.startswith('default_') and key[8:] in SYSTEM_WRITE_FIELDS)}
            record = self.with_context(stripped)

        # 複製一份再改：匯入（load）遇到錯誤會回滾到 savepoint 後用同一批 vals 重試，
        # 若把聯絡人 id 寫回呼叫端的 dict，重試時會指到已被回滾掉的聯絡人（FK 錯誤）。
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            self._validate_national_id(vals.get('national_id'), vals.get('member_no'))
            if not vals.get('partner_id'):
                vals['partner_id'] = record._create_member_partner(vals).id
        return super(AssocMember, record).create(vals_list)

    def write(self, vals):
        if 'national_id' in vals:
            self._validate_national_id(vals['national_id'], self[:1].member_no)
        computed = COMPUTED_ONLY_FIELDS & set(vals)
        if computed:
            raise AccessError(_('這些欄位是算出來的，不能直接指定：%s（請改「期初繳至」'
                                '或處理應繳）', ', '.join(sorted(computed))))
        return super().write(vals)

    @api.model
    def _validate_national_id(self, value, member_no=None):
        """寫入前先驗格式與檢查碼。

        不能只靠 inverse：inverse 是整批 insert 之後才跑，一列壞資料會讓整批回滾，
        而 load() 重試時會把錯誤歸到第一列（實測：沒填身分證的那列被報「檢查碼不正確」）。
        訊息帶會員編號讓操作員找得到是哪一列，但**不回顯身分證本身**。
        """
        if not value or not value.strip():
            return
        _norm, kind, checksum = tools_pii.validate(value)
        if not checksum and kind != 'arc_old':
            raise UserError(_('身分證字號檢查碼不正確%(where)s，請確認後重新輸入。',
                              where=_('（會員編號 %s）', member_no) if member_no else ''))

    @api.constrains('partner_id', 'company_id')
    def _check_partner_company(self):
        """聯絡人必須屬於本公會、且不是內部使用者（受控 sudo 的前提，P3）。"""
        for member in self:
            partner = member.partner_id
            if partner.company_id != member.company_id:
                raise ValidationError(_('會員的聯絡人必須屬於同一個公會。'))
            if self._partner_is_internal(partner):
                raise ValidationError(_('不能把內部使用者的聯絡人指定為會員。'))

    @api.constrains('national_id_enc', 'national_id_hmac', 'national_id_masked', 'national_id_kind')
    def _check_pii_consistency(self):
        """身分證四個欄位必須彼此一致，而且密文要能用本列的 AAD 解開。

        驗結果不驗輸入：create 不查欄位 groups、sudo 路徑也繞得過 write 的檢查，
        只要有人直接塞值（例如把明文塞進職員看得到的隱碼欄），這裡就會擋下。
        """
        for member in self:
            data = member.sudo()
            if not data.national_id_enc:
                if any([data.national_id_hmac, data.national_id_masked, data.national_id_kind]):
                    raise ValidationError(_('身分證資料不一致，請用表單重新輸入。'))
                continue
            try:
                plain = tools_pii.decrypt(data.national_id_enc, member._pii_aad())
            except UserError as exc:
                # 解不開＝密文被搬過來或被改壞；約束要回 ValidationError 而不是解密層的錯誤
                raise ValidationError(_('身分證資料不一致，請用表單重新輸入。')) from exc
            kind = tools_pii.detect_kind(plain)
            if (data.national_id_hmac != tools_pii.index_hmac(plain)
                    or data.national_id_masked != tools_pii.mask(plain)
                    or data.national_id_kind != kind):
                raise ValidationError(_('身分證資料不一致，請用表單重新輸入。'))

    @api.model
    def _create_member_partner(self, vals):
        """沒給聯絡人時自動建一個（匯入與後台新增都會走這裡）。"""
        if not vals.get('name'):
            raise UserError(_('請填姓名或指定既有聯絡人。'))
        company_id = vals.get('company_id') or self.env.company.id
        return self.env['res.partner'].sudo().create({
            'name': vals['name'],
            'company_id': company_id,
            'email': vals.get('email'),
            'mobile': vals.get('mobile'),
            'type': 'contact',
        })

    @api.model
    def get_import_templates(self):
        return [{'label': _('會員名冊匯入範本'), 'template': IMPORT_TEMPLATE}]

    @api.depends('member_no', 'name')
    def _compute_display_name(self):
        for member in self:
            member.display_name = ' '.join(filter(None, [member.member_no, member.name]))

    @api.depends('fee_paid_opening')
    def _compute_fee_coverage(self):
        """基礎版：繳至＝期初值。

        裝了繳費模組（assoc_portal）之後會被覆寫成「一期一期往後接」。
        **不得依賴 today**：stored compute 依賴今天的話，跨過午夜不會自己重算
        （沒有任何欄位變動），「會籍有效」會停在昨天的答案。
        所以這裡只算「繳到哪一天」，資格在查詢時才判斷（`_fee_is_current`）。
        """
        for member in self:
            member.fee_paid_until = member.fee_paid_opening
            member.coverage_from = False

    def _fee_is_current(self, today=None):
        """會籍在指定日期是否有效。

        兩個條件：繳到今天（含）以後，而且這段涵蓋**已經開始**——
        只預繳明年那期的人，今天還不算有效。
        """
        self.ensure_one()
        today = today or assoc_today(self)
        return bool(self.fee_paid_until and self.fee_paid_until >= today
                    and (not self.coverage_from or self.coverage_from <= today))

    @api.depends('active', 'fee_paid_until', 'coverage_from')
    def _compute_is_voter_eligible(self):
        today = assoc_today(self)
        for member in self:
            member.is_voter_eligible = bool(member.active and member._fee_is_current(today))

    # ------------------------------------------------------------------
    # 身分證字號
    # ------------------------------------------------------------------
    def _pii_aad(self):
        """AES-GCM 的 AAD：把密文綁在這一列，搬到別人名下會解不開。"""
        self.ensure_one()
        return '%s:%s' % (self._name, self.id)

    def _compute_national_id(self):
        # 永遠回空白：明文不經由一般讀取路徑外流（要看明文走 action_reveal_national_id）
        for member in self:
            member.national_id = ''

    def _inverse_national_id(self):
        for member in self:
            value = member.national_id
            if not value or not value.strip():
                # 空值 no-op：匯出再匯入時空白儲存格會被轉成 False 寫回來（ir_fields.py:123-125），
                # 不能因此把已存的密文清掉。要清除請用「清除身分證字號」。
                continue
            norm, kind, _checksum = tools_pii.validate(value)
            member.sudo().write({
                'national_id_enc': tools_pii.encrypt(norm, member._pii_aad()),
                'national_id_hmac': tools_pii.index_hmac(norm),
                'national_id_masked': tools_pii.mask(norm),
                'national_id_kind': kind,
            })

    def _check_admin(self):
        check_guild_admin(self)   # 訊息＝預設值，不重複寫一次

    def _national_id_plain(self):
        """解出明文。**呼叫端自己負責寫軌跡**——單筆顯示寫 `reveal_pii`、
        整批匯出寫一筆 `export_pii`（否則一次匯出會灌進幾百筆 reveal_pii）。
        """
        self.ensure_one()
        # 先過 record rule：sudo 與非 sudo 共用同一份快取，
        # 少了這道，他公會的管理員打 RPC 就能讀到別人的身分證。
        self.check_access('read')
        self._check_admin()
        enc = self.sudo().national_id_enc
        if not enc:
            raise UserError(_('這位會員沒有身分證字號資料。'))
        return tools_pii.decrypt(enc, self._pii_aad())

    def action_reveal_national_id(self):
        """顯示明文一次，並留下存取軌跡（辦公室要用來登錄工程會積分）。"""
        self.ensure_one()
        plain = self._national_id_plain()
        self.env['assoc.audit.log']._log('reveal_pii', records=self, company=self.sudo().company_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('身分證字號'),
                'message': plain,
                'sticky': True,
                'type': 'warning',
            },
        }

    def action_clear_national_id(self):
        """清除身分證資料（例如誤植到別人身上）。"""
        self.check_access('write')
        self._check_admin()
        for member in self:
            member.sudo().write({
                'national_id_enc': False,
                'national_id_hmac': False,
                'national_id_masked': False,
                'national_id_kind': False,
            })
            self.env['assoc.audit.log']._log('clear_national_id', records=member,
                                             company=member.sudo().company_id)
        return True

    def action_rotate_barcode(self):
        """會員卡遺失時換發條碼：舊卡立即失效。"""
        for member in self:
            member.barcode = self._new_barcode()
            member.message_post(body=_('會員卡條碼已換發，舊卡失效'))
        return True

    def _card_qr_data_uri(self):
        self.ensure_one()
        return qr_data_uri(self.env, self.barcode, CARD_QR_SIZE_PX)
