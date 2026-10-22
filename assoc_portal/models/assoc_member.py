"""會員與前台帳號的連結、開通與重設通知單（計畫 P4、P5、P16）。

三個硬規則：
1. **一個帳號只對應一位會員**（`unique(user_id)`）。跨公會共用帳號的話，
   任一連結公會的管理員印一張通知單就能接管整個帳號（抗辯第 3 輪的 high）。
2. **同一身分證在任何公會已經開通 → 拒絕**，訊息不分原因並寫 audit。
   跨公會會員在第二家公會不開前台，用實體會員卡與辦公室代辦。
3. **開通與重設一律走紙本一次性通知單**：nonce 只在按鈕產生、用過即失效、重印即作廢。
   不用核心的 signup token——它在首次登入前可以重複使用，而且期限只有 4 或 144 小時。
"""

import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import hash_sign

from odoo.addons.assoc_base import tools_pii
from odoo.addons.assoc_base.tools import ASSOC_TZ, GUARD, check_created, guarded

ADMIN_GROUP = 'assoc_base.group_assoc_admin'
PORTAL_GROUP = 'base.group_portal'
TOKEN_SCOPE = 'assoc-activate'
ACTIVATION_HOURS = 72          # 紙本通知單被偷拍的有效窗要短 (H)
NONCE_BITS = 128
LOGIN_FALLBACK = 'm%s-%s'      # 沒有 Email 時的登入帳號：m<公會id>-<會員編號>
# 後備帳號撞到「看起來像身分證」時改用的形狀。加 7 個字元一定會把長度推出
# `ID_ATTEMPT_LENGTH`（9–11）的區間，所以這一個分支不需要再遞迴檢查一次。
LOGIN_FALLBACK_LONG = 'm%s-%s-portal'
GUARD_LINK = 'assoc_portal_link'
# 只能由開通／停用流程寫的欄位。readonly=True 在 Odoo 只是 UI 限制，write() 不檢查：
# 少了這道守衛，公會管理員可以用 RPC 把自己公會的會員指到「系統管理員」的帳號，
# 再按停用／重新開通把對方封存並改掉密碼。
LINK_FIELDS = frozenset({'user_id', 'activation_nonce_hash'})


class AssocMember(models.Model):
    _inherit = 'assoc.member'

    user_id = fields.Many2one(
        'res.users', string='前台帳號', readonly=True, index=True, copy=False,
        help='會員自助頁的登入帳號。一個帳號只對應一位會員。')
    activation_nonce_hash = fields.Char(
        string='開通碼雜湊', readonly=True, copy=False, groups='base.group_system')
    portal_state = fields.Selection(
        [('none', '未開通'), ('pending', '已印通知單'), ('active', '已啟用'), ('revoked', '已停用')],
        string='前台狀態', compute='_compute_portal_state', search='_search_portal_state')

    _sql_constraints = [
        ('user_uniq', 'unique(user_id)', '一個前台帳號只能對應一位會員'),
    ]

    def init(self):
        # 跨公會互斥：同一身分證只能有一個前台帳號。
        # 用 partial unique index 而不是 Python 約束——兩個公會同時開通時，
        # 改的是不同的列，RR 下不會撞在一起（write skew）。
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS assoc_member_one_account
                ON assoc_member (national_id_hmac)
             WHERE user_id IS NOT NULL AND national_id_hmac IS NOT NULL
        """)

    def write(self, vals):
        if LINK_FIELDS & set(vals) and not guarded(self.env, GUARD_LINK):
            raise AccessError(_('前台帳號的連結只能由開通／停用動作變更。'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        check_created(members, {'user_id': False, 'activation_nonce_hash': False}, GUARD_LINK)
        return members

    @api.depends('user_id', 'user_id.active', 'user_id.login_date', 'activation_nonce_hash')
    def _compute_portal_state(self):
        for member in self:
            user = member.sudo().user_id
            if not user:
                member.portal_state = 'none'
            elif not user.active:
                member.portal_state = 'revoked'
            elif user.login_date:
                member.portal_state = 'active'
            else:
                member.portal_state = 'pending'

    def _search_portal_state(self, operator, value):
        """非儲存 compute 沒有 search 時，任何篩選都靜默回傳**整份名冊**
        （只在 log 留一行 `Non-stored field ... cannot be searched`）。
        這個欄位在表單上看得到，使用者可以自建篩選器。
        """
        if operator not in ('=', '!=', 'in', 'not in'):
            raise UserError(_('前台狀態只支援等於／不等於的篩選。'))
        wanted = set(value if isinstance(value, (list, tuple)) else [value])
        if operator in ('!=', 'not in'):
            wanted = set(dict(self._fields['portal_state'].selection)) - wanted
        users = self.env['res.users'].sudo().with_context(active_test=False)
        # 逐狀態組出「哪些 user_id 算這一狀態」，再轉回會員的 domain
        active_users = users.search([('share', '=', True), ('active', '=', True)])
        domains = []
        if 'none' in wanted:
            domains.append([('user_id', '=', False)])
        if 'revoked' in wanted:
            revoked = users.search([('share', '=', True), ('active', '=', False)])
            domains.append([('user_id', 'in', revoked.ids)])
        if 'pending' in wanted:
            domains.append([('user_id', 'in',
                             active_users.filtered(lambda u: not u.login_date).ids)])
        if 'active' in wanted:
            domains.append([('user_id', 'in',
                             active_users.filtered('login_date').ids)])
        if not domains:
            return [('id', '=', False)]
        combined = domains[0]
        for extra in domains[1:]:
            combined = ['|'] + combined + extra
        return combined

    # ------------------------------------------------------------------
    # 開通與停用
    # ------------------------------------------------------------------
    def _assert_company_admin(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_('只有公會管理員可以執行這個動作。'))

    def _portal_login(self):
        """Email 可用就用 Email，否則用 m<公會id>-<會員編號>（login 全庫唯一）。"""
        self.ensure_one()
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        email = (self.email or '').strip()
        if email and not Users.search_count([('login', '=', email)]):
            return email
        login = LOGIN_FALLBACK % (self.company_id.id, self.member_no)
        taken = Users.search_count([('login', '=', login)])
        if tools_pii.looks_like_id_attempt(login) or taken:
            # **會員編號是數字時很容易中**：`m1-001234` 就是 9 碼含 7 個數字，
            # 正好落在「看起來像在打身分證」的區間。那種帳號**永遠登不進來**——
            # 登入頁對這個形狀一律走身分證路徑、不交給核心（P1）——而且
            # `_check_login_not_id_shaped` 會在開通時就擋下來，
            # 錯誤訊息還叫承辦「請改用 Email」，但這個 login 是系統自己產的。
            # 示範資料的編號帶字母（T001）所以一直沒中。
            # 加後綴之後仍可能撞號：會員編號 `00123456`（數字→加後綴）與
            # 另一位編號字面就是 `00123456-portal` 的會員會算出同一個 login，
            # 而 `UNIQUE(login)` 是全庫的——撞到時第二位永遠開通失敗，
            # 承辦看到的是原始的 DB 例外（抗辯實跑複現）。所以撞了就往後編號。
            login = LOGIN_FALLBACK_LONG % (self.company_id.id, self.member_no)
            suffix = 1
            while Users.search_count([('login', '=', login)]):
                suffix += 1
                login = '%s-%s' % (
                    LOGIN_FALLBACK_LONG % (self.company_id.id, self.member_no), suffix)
        return login

    def _same_person_user(self):
        """同一身分證在任何公會的既有帳號（含已停用）。"""
        self.ensure_one()
        data = self.sudo()
        if not data.national_id_hmac:
            return self.env['res.users'].browse()
        twin = self.sudo().with_context(active_test=False).search([
            ('national_id_hmac', '=', data.national_id_hmac),
            ('user_id', '!=', False),
            ('id', '!=', self.id),
        ], limit=1)
        return twin.user_id

    def action_grant_portal(self):
        """開通前台帳號（不寄信；密碼由紙本通知單設定）。"""
        self.ensure_one()
        self._assert_company_admin()
        audit = self.env['assoc.audit.log']
        if self._same_person_user():
            # 訊息不分原因：否則管理員可以拿任意身分證來探測「這個人是不是他公會的會員」。
            # 軌跡要寫在獨立交易：接下來的 UserError 會把主交易整個回滾。
            audit._log_independent('grant_conflict', company=self.company_id,
                                   res_model=self._name, res_ids=self.ids)
            raise UserError(_('無法開通，已通知系統管理員。'))
        if self.sudo().user_id:
            # 要和 action_revoke_portal 走同一道檢查：壞掉的連結（舊資料、手動改過）
            # 若指到內部使用者，這裡會把對方解封存並改掉密碼
            user = self._linked_user()
            if not user.active:
                # 停用過的帳號重新啟用：login 被舊帳號佔著，不能再建一個
                user.write({'active': True, 'password': self._random_password()})
                audit._log('grant_portal', records=self, detail={'reused': True})
            return self._notify(_('此會員已有前台帳號。'))

        partner = self._partner_sudo()
        user = self.env['res.users'].sudo().with_context(
            no_reset_password=True,   # 不要觸發核心的「設定密碼」邀請信
        ).create({
            'name': self.name,
            'login': self._portal_login(),
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'company_ids': [(6, 0, self.company_id.ids)],
            'groups_id': [(6, 0, [self.env.ref(PORTAL_GROUP).id])],
            # **一定要設時區**：不設的話會沿用 portal 範本 partner 的值
            # （示範庫裡那是 `Europe/Brussels`），於是後台與前台所有
            # datetime 都差好幾個小時，而且看起來完全正常（第十輪 skeptic）。
            'tz': ASSOC_TZ,
            'password': self._random_password(),
        })
        self.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = user.id
        audit._log('grant_portal', records=self)
        return self._notify(_('已開通，請列印開通通知單交給會員。'))

    def action_revoke_portal(self):
        """停用前台帳號：封存帳號、清掉未用的開通碼，但保留連結（重新開通會重用同一個帳號）。"""
        self.ensure_one()
        self._assert_company_admin()
        user = self.sudo().user_id
        if not user:
            raise UserError(_('此會員沒有前台帳號。'))
        if user.partner_id != self.sudo().partner_id:
            # 指到**別人**的帳號：不能動，動了會傷到無辜的第三人。
            raise AccessError(_('此會員的前台帳號資料不正確，請洽系統管理員。'))
        if not user.share:
            # 指到一個**內部**帳號——這正是「同一個人同時握有後台與前台」的那種
            # 壞連結（哨兵擋得住 RPC，擋不住 shell 與直接寫 DB）。原本這裡會
            # 直接 raise，於是公會管理員**連停用都執行不了**，只能求助 DB
            # superuser，而該帳號在那段期間照樣登得進後台（第十一輪紅隊）。
            # 斷連結就夠：前台服務認的是 `user_id`（`_member_for_user`）。
            # **刻意不封存那個內部帳號**——那超出公會管理員的權限範圍，
            # 而且會把一位職員鎖在後台外面；要不要停用那個帳號是系統管理員的事。
            self.sudo().with_context(**{GUARD_LINK: GUARD}).write({
                'user_id': False, 'activation_nonce_hash': False})
            self.env['assoc.audit.log']._log(
                'revoke_portal', records=self, detail={'irregular': 'internal_account'})
            return self._notify(_('此會員的前台帳號連結指向一個內部帳號，已解除連結；'
                                  '那個帳號本身請洽系統管理員處理。'))
        user.write({'active': False})
        self.sudo().with_context(**{GUARD_LINK: GUARD}).activation_nonce_hash = False
        self.env['assoc.audit.log']._log('revoke_portal', records=self)
        return self._notify(_('已停用前台帳號。'))

    def _linked_user(self):
        """取這位會員的前台帳號，並確認它真的是「這位會員的 share 帳號」。

        萬一資料庫裡留有錯誤的連結（舊資料、手動改過），停用與重新開通都不能拿它動別人的帳號。
        """
        self.ensure_one()
        user = self.sudo().user_id
        if not user:
            return user
        if not user.share or user.partner_id != self.sudo().partner_id:
            raise AccessError(_('此會員的前台帳號資料不正確，請洽系統管理員。'))
        return user

    @api.model
    def _random_password(self):
        """開通時先寫一組沒人知道的密碼。

        不能留空：核心對空密碼雜湊是 0 秒回絕（`res_users.py:484`），
        會變成「回應很快 = 這個身分證是已開通未啟用的會員」的反向計時預言。
        """
        return secrets.token_urlsafe(32)

    # ------------------------------------------------------------------
    # 一次性通知單（開通／重設共用）
    # ------------------------------------------------------------------
    def action_print_activation(self):
        """產生一次性開通碼並列印通知單。重印會換碼，舊通知單立即失效。"""
        self.ensure_one()
        self._assert_company_admin()
        user = self._linked_user()
        if not user:
            raise UserError(_('請先開通前台帳號。'))
        is_reset = bool(user.login_date)
        if self.env['ir.actions.report'].get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            raise UserError(_('PDF 產生器目前不可用，請洽系統管理員後再列印通知單。'))
        nonce = secrets.token_urlsafe(NONCE_BITS // 8)
        self.sudo().with_context(**{GUARD_LINK: GUARD}).activation_nonce_hash = \
            hashlib.sha256(nonce.encode()).hexdigest()
        token = hash_sign(self.env(su=True), TOKEN_SCOPE, [self.id, user.id, nonce],
                          expiration_hours=ACTIVATION_HOURS)
        self.env['assoc.audit.log']._log(
            'print_reset' if is_reset else 'print_activation', records=self)
        # token 走報表的 data（前端是 POST /report/download），不進網址列也不進 access log
        return self.env.ref('assoc_portal.action_report_activation_notice').report_action(
            self, data={'token': token, 'member_id': self.id, 'is_reset': is_reset})

    @api.model
    def _member_from_token(self, token):
        """驗簽 → 取回 (member, user, nonce)；任何一關不過都回三個 False。"""
        from odoo.tools import verify_hash_signed
        try:
            payload = verify_hash_signed(self.env(su=True), TOKEN_SCOPE, token)
        except Exception:      # noqa: BLE001  壞 token 不該變成 500
            payload = None
        if not payload or len(payload) != 3:
            return False, False, False
        member_id, user_id, nonce = payload
        member = self.sudo().browse(member_id).exists()
        if not member or not member.active or member.user_id.id != user_id:
            return False, False, False
        expected = hashlib.sha256(str(nonce).encode()).hexdigest()
        if not member.activation_nonce_hash or member.activation_nonce_hash != expected:
            return False, False, False       # 已經用過、或被重印換掉了
        return member, member.user_id, nonce

    def _consume_activation(self, password):
        """設定密碼並讓這張通知單失效（同一交易內完成，不需要 commit）。"""
        self.ensure_one()
        user = self.sudo().user_id
        user.write({'password': password})
        self.sudo().with_context(**{GUARD_LINK: GUARD}).activation_nonce_hash = False
        self.env['assoc.audit.log']._log('activate_ok', records=self,
                                         company=self.sudo().company_id)
        return user

    # ------------------------------------------------------------------
    # 前台身分
    # ------------------------------------------------------------------
    @api.model
    def _member_for_user(self, user=None):
        """登入者對應的**有效**會員：決定「要不要提供前台服務」。

        停權的會員在這裡回空集合（前台頁面一律 404），但**不要拿它當守衛**——
        守衛要問的是「這個帳號是不是會員帳號」，見 `_member_account_for_user`。

        **而且必須是 share 帳號。** `action_grant_portal` 一律建 share 帳號、
        群組寫死 portal，所以正常流程不會有例外；但 `user_id` 是可寫欄位
        （哨兵守衛擋得住 RPC，擋不住 `odoo shell` 與直接寫 DB），一旦有人把某位
        會員指到一個**內部**帳號，這支原本會照樣把前台服務端給他——
        於是同一個人同時握有後台與前台。這裡補上 share 條件，讓那種連結
        **拿不到前台**（而「擋核心行為」那一側刻意維持寬鬆，見下一支）。
        """
        user = user or self.env.user
        # **`member.user_id == user` 這一句不能少。** `_account_domain` 現在也比對
        # partner，所以同一筆 partner 的**第二個**帳號（內部職員）也會命中；
        # 少了這一句，`member.user_id.share` 問的是**會員自己**那個 share 帳號
        # （當然是 True），於是那個內部帳號反而拿得到前台服務——
        # 擋核心那一側要放寬、提供服務這一側要收緊，兩邊方向相反。
        return self._member_account_for_user(user).filtered(
            lambda member: member.active and member.user_id == user and member.user_id.share)

    @api.model
    def _account_domain(self, users):
        """守衛的**唯一**判準：這些帳號會不會寫到某位會員的名冊 partner 上。

        兩個子句都要，互相不涵蓋：
          * `user_id`：連結可能指向一個 partner **不同**的帳號（壞連結），
            那種帳號照樣要被擋核心自助寫入。
          * `partner_id`：`res_users` 沒有 partner 唯一約束，所以在
            設定→使用者新增一個內部帳號、聯絡人挑會員那一筆，`user_id` 查不到它
            ——而名冊姓名與報到照片住的正是那一列 `res.partner`。

        **判準只能有一份。** 第十二輪 skeptic 實跑：`_assoc_member_accounts()`
        改成查 partner 之後，`/my/account` 與 `/my/deactivate_account` 的守衛
        （走這一支）**沒有跟著改**，於是同一筆 partner 的第二個帳號不會被轉址，
        落到核心 `CustomerPortal.account()`——那支做的是 `partner.sudo().write()`，
        姓名竄改換一條路原封不動（L4②：同一效果有別的動作）。
        同一個判準寫在兩個地方，就是遲早只改到一邊。
        """
        return ['|', ('user_id', 'in', users.ids), ('partner_id', 'in', users.partner_id.ids)]

    @api.model
    def _member_account_for_user(self, user=None):
        """這個登入者會不會寫到某位會員的名冊 partner 上（**含已停權的會員**）。

        擋核心行為（帳號頁、自行停用、重設密碼信）一律用這個：
        用「有效會員」去判斷的話，一停權查詢就回空 → 守衛以為對方不是會員 → 放行核心。
        """
        user = user or self.env.user
        if not user or user._is_public():
            return self.browse()
        return self.sudo().with_context(active_test=False).search(
            self._account_domain(user), limit=1)

    @api.model
    def _user_by_national_id(self, raw_value):
        """身分證字號 → 唯一的 share 帳號；查不到、非 share、多於一個都回空。

        用一條 SQL 取完：走 ORM 的話，命中會多出 m2o prefetch 與 filtered 的查詢
        （實測 miss 1 次、hit 3 次），查詢次數本身就是一種時間差。
        """
        hmac_value = tools_pii.index_hmac(raw_value)
        Users = self.env['res.users']
        if not hmac_value:
            return Users.browse()
        # 走 raw SQL 就看不到還在快取裡的寫入（剛開通的 user_id、剛停用的 active）
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT u.id
              FROM assoc_member m
              JOIN res_users u ON u.id = m.user_id
             WHERE m.national_id_hmac = %s AND m.active AND u.active AND u.share
             LIMIT 2
        """, [hmac_value])
        rows = self.env.cr.fetchall()
        return Users.browse(rows[0][0]) if len(rows) == 1 else Users.browse()

    def _notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('會員前台'), 'message': message, 'type': 'success'},
        }
