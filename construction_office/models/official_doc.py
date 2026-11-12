# -*- coding: utf-8 -*-
"""公文登錄與搜尋（淞源 2026-11-10 會議 C10）。

淞源技師：只要很基本的——能用時間或關鍵字找到公文，在外面用手機也找得到，不用一個個點半天。
老闆：就是一個搜尋功能加總表，原則上按標案分開；簽辦不做（50 人以上再說）。

所以這裡只做「登錄＋搜尋」：收文／發文、公文日期、機關、文號、主旨、附件，另有選填的辦理期限與狀態
（給之後的期限提醒用）。沒有簽辦流程、沒有電子公文交換。

誰看得到（重點）
----------------
公文是「某一家公司的」（company_id，所屬公司），不是工程上每一方都能看：
* 同一個工程上的監造與營造廠，彼此看不到對方的公文——要給外人看，走參觀帳號逐份指定。
* 營造方帳號建立的公文，所屬公司一律是它自己的範圍公司（不管傳入什麼值），之後也不能改。
* 前台成員只看得到自己參與工程的公文；沒掛工程的（公司共通的）只有老闆與後台人員看得到。
規則在 security/office_rules.xml；受限帳號（營造方、角色帳號）另由 construction_company_dashboard 的
rule_scope 收窄成「所屬公司＝自己的公司」。

附件
----
附件就是掛在這筆公文上的 ir.attachment（res_model／res_id），attachment_ids 是唯讀的計算欄位。
刻意不做成可寫的 Many2many：那樣呼叫端可以把別人單據的附件 id 塞進來，再從前台下載端點把檔案拿走。
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

DIRECTION_INCOMING = 'incoming'
DIRECTION_OUTGOING = 'outgoing'
DIRECTION_SELECTION = [
    (DIRECTION_INCOMING, '收文'),
    (DIRECTION_OUTGOING, '發文'),
]
STATE_PENDING = 'pending'
STATE_DONE = 'done'
STATE_FILED = 'filed'
STATE_SELECTION = [
    (STATE_PENDING, '待辦'),
    (STATE_DONE, '已辦'),
    (STATE_FILED, '存查'),
]
# 關鍵字要比對的欄位（主旨、文號、機關）
KEYWORD_FIELDS = ('subject', 'doc_number', 'organization')


class ConstructionOfficialDoc(models.Model):
    _name = 'construction.official.doc'
    _description = '公文'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'doc_date desc, id desc'
    _rec_name = 'subject'

    active = fields.Boolean(string='啟用', default=True)
    subject = fields.Char(string='主旨', required=True, index='trigram', tracking=True)
    direction = fields.Selection(
        DIRECTION_SELECTION, string='收／發文', required=True, default=DIRECTION_INCOMING, index=True, tracking=True)
    doc_date = fields.Date(
        string='公文日期', required=True, default=lambda self: local_today(), index=True, tracking=True,
        help='公文上的發文日期')
    receive_date = fields.Date(string='收文日期', help='我方實際收到的日期（收文才填）')
    organization = fields.Char(
        string='機關／單位', index='trigram', tracking=True,
        help='收文＝來文機關；發文＝受文者')
    doc_number = fields.Char(string='文號', index='trigram', tracking=True, help='發文字號')
    project_id = fields.Many2one(
        'project.project', string='所屬工程', index=True, ondelete='restrict', tracking=True,
        help='這份公文屬於哪個工程；公司共通的公文可以不填')
    company_id = fields.Many2one(
        'res.company', string='所屬公司', required=True, index=True, ondelete='restrict',
        default=lambda self: self.env.company, tracking=True,
        help='這份公文是哪一家公司的。只有這家公司的帳號看得到；營造方帳號建立的一律是它自己的公司。')
    summary = fields.Text(string='說明')
    note = fields.Text(string='備註')

    # 辦理：選填。有辦理期限的公文會出現在期限待辦裡
    reply_deadline = fields.Date(string='辦理期限', index=True, tracking=True)
    state = fields.Selection(
        STATE_SELECTION, string='辦理狀態', required=True, default=STATE_FILED, index=True, tracking=True,
        help='存查＝不需要辦理；有填辦理期限的新公文預設是待辦')
    responsible_user_id = fields.Many2one(
        'res.users', string='承辦人', ondelete='set null', tracking=True)
    is_overdue = fields.Boolean(
        string='已逾期', compute='_compute_deadline_status', search='_search_is_overdue',
        help='待辦且辦理期限已過（不儲存：每次讀都以今天計算，不會過期）')
    days_left = fields.Integer(
        string='剩餘天數', compute='_compute_deadline_status',
        help='待辦公文距離辦理期限的天數；負數＝已逾期幾天')

    attachment_ids = fields.Many2many(
        'ir.attachment', string='附件', compute='_compute_attachment_ids', compute_sudo=True,
        help='掛在這筆公文上的檔案（後台在下方對話區用迴紋針上傳；手機在新增公文時上傳）')
    attachment_count = fields.Integer(string='附件數', compute='_compute_attachment_ids', compute_sudo=True)

    # ── 計算 ──────────────────────────────────────────────────────────────
    @api.depends('reply_deadline', 'state')
    def _compute_deadline_status(self):
        today = local_today()
        for doc in self:
            pending = doc.state == STATE_PENDING and doc.reply_deadline
            doc.days_left = (doc.reply_deadline - today).days if pending else 0
            doc.is_overdue = bool(pending and doc.reply_deadline < today)

    @api.model
    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise ValidationError('「已逾期」只能用「是／不是」篩選。')
        overdue = [('state', '=', STATE_PENDING), ('reply_deadline', '<', local_today())]
        if (operator == '=') == value:
            return overdue
        return ['|', '|', ('state', '!=', STATE_PENDING), ('reply_deadline', '=', False),
                ('reply_deadline', '>=', local_today())]

    def _compute_attachment_ids(self):
        Attachment = self.env['ir.attachment']
        groups = {}
        if self.ids:
            for attachment in Attachment.search(
                    [('res_model', '=', self._name), ('res_id', 'in', self.ids)], order='id'):
                groups.setdefault(attachment.res_id, Attachment.browse())
                groups[attachment.res_id] |= attachment
        for doc in self:
            doc.attachment_ids = groups.get(doc.id, Attachment.browse())
            doc.attachment_count = len(doc.attachment_ids)

    # ── 建立／寫入 ────────────────────────────────────────────────────────
    @api.model
    def _acting_contractor_company(self):
        """目前使用者是營造方時，回傳它的範圍公司（判定用 env.user，sudo 也一樣）；不是營造方回 None。
        營造方但範圍不合格 → 拒絕（不能替不知道是哪家的公司建公文）。"""
        user = self.env.user
        if not user._dash_is_contractor_side():
            return None
        scope = user.sudo().dash_scope_company_id
        if not scope:
            raise AccessError('帳號的範圍公司未設定，不能建立公文。')
        return scope

    @api.model_create_multi
    def create(self, vals_list):
        scope = self._acting_contractor_company()
        for vals in vals_list:
            if scope is not None:
                vals['company_id'] = scope.id       # 營造方建立的一律是自己的公司
            if vals.get('reply_deadline') and 'state' not in vals:
                vals['state'] = STATE_PENDING       # 有辦理期限的新公文預設待辦
        docs = super().create(vals_list)
        # 核心在建立時會把沒給值的多筆關聯欄位先快取成「空的」，連這個計算欄位也是；同一個交易裡緊接著
        # 掛上的附件（手機新增公文就是這樣）會因此讀不到。清掉，下次讀才現查
        docs.invalidate_recordset(['attachment_ids', 'attachment_count'])
        return docs

    def write(self, vals):
        if 'company_id' in vals and self._acting_contractor_company() is not None:
            raise AccessError('營造方帳號不能更改公文的所屬公司。')
        return super().write(vals)

    @api.constrains('doc_date', 'receive_date')
    def _check_dates(self):
        for doc in self:
            if doc.receive_date and doc.doc_date and doc.receive_date < doc.doc_date:
                raise ValidationError('收文日期不能早於公文日期。')

    # ── 動作 ──────────────────────────────────────────────────────────────
    def action_mark_done(self):
        self.write({'state': STATE_DONE})

    def action_mark_pending(self):
        self.write({'state': STATE_PENDING})

    def action_mark_filed(self):
        self.write({'state': STATE_FILED})

    # ── 搜尋（後台總表與手機頁共用一份條件）────────────────────────────────
    @api.model
    def _search_domain(self, keyword=None, date_from=None, date_to=None, direction=None, state=None):
        """搜尋條件：關鍵字（主旨、文號、機關任一含有；空白隔開的多個詞要全部符合）、公文日期起迄、收發文、辦理狀態。"""
        domain = []
        for word in (keyword or '').split():
            domain += ['|'] * (len(KEYWORD_FIELDS) - 1)
            domain += [(name, 'ilike', word) for name in KEYWORD_FIELDS]
        if date_from:
            domain.append(('doc_date', '>=', date_from))
        if date_to:
            domain.append(('doc_date', '<=', date_to))
        if direction in dict(DIRECTION_SELECTION):
            domain.append(('direction', '=', direction))
        if state in dict(STATE_SELECTION):
            domain.append(('state', '=', state))
        return domain
