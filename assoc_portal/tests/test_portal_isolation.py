"""前台隔離（計畫 P2、P6）：會員沒有任何 assoc.* 的 ACL，也不能自己改名冊欄位。"""

import base64
import re

from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_member import GUARD_LINK
from odoo.addons.assoc_base.tests.common import force_internal_user_on
from .common import PASSWORD, PortalCase, VALID_ID_2, index_cards, visible_card_urls

PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQ'
           'AAAABJRU5ErkJggg==')

# 會員專區併進 /my 之後，這些入口要以原生入口卡的形式直接排在 /my（與 Connection & Security 同一層）
MEMBER_ENTRY_URLS = {
    '/my/assoc/meetings', '/my/assoc/profile', '/my/assoc/pass', '/my/assoc/dues',
    '/my/assoc/gifts', '/my/assoc/proxies', '/my/assoc/credits',
}
CORE_SECURITY_URL = '/my/security'


@tagged('post_install', '-at_install')
class TestPortalIsolation(PortalCase):

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()

    def test_member_has_no_acl_on_assoc_models(self):
        """絆線：share 使用者對每一個 assoc.* 模型都不該有讀取權。

        只數 ir.model.access 的列數不夠——group_id 為空的 ACL 對所有人生效。
        """
        for model_name in self.env.registry:
            if not model_name.startswith('assoc.'):
                continue
            model = self.env[model_name].with_user(self.user)
            self.assertFalse(
                model.has_access('read'),
                '%s 不該開放給前台會員（前台一律走 sudo + _me()）' % model_name)

    def test_member_cannot_write_own_identity_fields(self):
        """核心讓使用者改自己的 name/image_1920/company_id/email，而且是 sudo 寫入。"""
        for field, value in (('name', '改名'),
                             ('image_1920', PNG_1PX),
                             ('company_id', self.other_company.id),
                             ('email', 'new@example.com')):
            with self.assertRaises(AccessError, msg='%s 應該被擋下' % field):
                self.user.with_user(self.user).write({field: value})

    def test_self_writeable_fields_follow_the_current_user(self):
        """`fields_get` 是 @api.model（self 為空集合，res_users.py:2153）。

        只看 `self` 的話，空集合會落回 super 的完整清單 →
        前台會員拿到的 metadata 會說姓名、照片可寫（前端據此畫出可編輯欄位，
        使用者填完才在 write 被擋），res_users.py:2158 的 readonly 標記也跟著失準。
        """
        member_view = self.env['res.users'].with_user(self.user)
        self.assertFalse(member_view)                      # 這就是 fields_get 當下的 self
        for field in ('name', 'image_1920', 'company_id', 'email'):
            self.assertNotIn(field, member_view.SELF_WRITEABLE_FIELDS,
                             '%s 不該出現在會員的可自寫清單' % field)
        internal = self.env['res.users'].sudo().create({
            'name': '內部（metadata）', 'login': 'm6_internal_meta',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertIn('name', self.env['res.users'].with_user(internal).SELF_WRITEABLE_FIELDS,
                      '內部使用者維持核心行為')

    def test_member_can_still_change_the_password(self):
        """改密碼不能被一起擋掉——而這件事要**做一次**才算驗過。

        這支原本叫 `test_member_keeps_core_preference_fields`，
        斷言的是 `lang`／`tz` 還在 `SELF_WRITEABLE_FIELDS` 裡，
        理由寫「改密碼是核心 /my/security 的功能」——**兩者根本無關**：
        改密碼走 `change_password()`，不經過 `SELF_WRITEABLE_FIELDS`。
        於是那支測試實際上是在把「不要擋過頭」這個意圖，
        釘在兩個剛好**該**被擋的欄位上（L2⑮：斷言要打在使用者看得到的結果上）。
        第十一輪紅隊實跑證明 `tz` 是真的攻擊面：改成 UTC+14 之後
        「會籍有效」與「已逾期」在到期當天可以被自己推移一天。
        """
        self.user.with_user(self.user).change_password(PASSWORD, PASSWORD + '-new')
        # **不要用 `authenticate()` 驗。** 它另開一個 cursor，看不到這個測試交易裡
        # 還沒 commit 的新密碼，於是一律 AccessDenied——為了錯的理由紅。
        # 在同一個交易裡證明「密碼真的換掉了」的方法是：拿舊密碼再改一次，
        # 必須被拒絕（`change_password` 會先驗舊密碼）。
        with self.assertRaises(AccessDenied):
            self.user.with_user(self.user).change_password(PASSWORD, PASSWORD + '-again')
        self.user.with_user(self.user).change_password(PASSWORD + '-new', PASSWORD)

    def test_internal_user_keeps_core_self_write(self):
        internal = self.env['res.users'].create({
            'name': '內部', 'login': 'm6_internal_self',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertIn('name', internal.with_user(internal).SELF_WRITEABLE_FIELDS)

    def test_archived_member_still_counts_as_a_member_account(self):
        """停權不能讓守衛失效。

        守衛問的是「這個帳號是不是會員帳號」，不是「這位會員還有效嗎」——
        用後者的話，會員一被停權查詢就回空，核心的帳號頁（partner.sudo().write）
        就對他開放，等於停權的人反而可以從前台改掉名冊姓名與 Email。
        """
        Member = self.env['assoc.member']
        self.assertTrue(Member._member_account_for_user(self.user))
        self.member.sudo().active = False
        self.assertFalse(Member._member_for_user(self.user), '停權後不提供前台服務')
        self.assertTrue(Member._member_account_for_user(self.user), '但仍然是會員帳號')

    def test_archived_member_reset_password_still_blocked(self):
        self.member.sudo().active = False
        with self.assertRaises(UserError):
            self.user.sudo().action_reset_password()

    def test_portal_state_filter_does_not_return_everyone(self):
        """非儲存 compute 沒有 search 時，篩選會靜默回傳整份名冊。"""
        Member = self.env['assoc.member'].sudo()
        other = self.new_member('M6041')
        self.assertEqual(other.portal_state, 'none')
        pending = Member.search([('portal_state', '=', 'pending')])
        self.assertIn(self.member, pending)
        self.assertNotIn(other, pending, '未開通的會員不該出現在「已印通知單」')
        none = Member.search([('portal_state', '=', 'none')])
        self.assertIn(other, none)
        self.assertNotIn(self.member, none)
        self.assertFalse(Member.search([('portal_state', '=', 'revoked')]) & self.member)

    def test_member_lookup_is_scoped_to_user(self):
        other = self.new_member('M6020', VALID_ID_2, 'm6020@example.com')
        self.grant(other)
        self.assertEqual(self.env['assoc.member']._member_for_user(self.user), self.member)
        self.assertEqual(
            self.env['assoc.member']._member_for_user(other.sudo().user_id), other)


@tagged('post_install', '-at_install')
class TestPortalPages(HttpCase, PortalCase):

    def test_first_login_with_a_browser_timezone_cookie_works(self):
        """帶 `tz` cookie 的**首次登入**必須成功。

        核心 `_login()` 做 `user = user.with_user(user)` 然後 `user.tz = tz`
        （`res_users.py:946-949`，條件 `not user.tz or not user.login_date`）
        ——那是 **self-write**，走的正是 `SELF_WRITEABLE_FIELDS`。
        我一度把 `tz` 加進 `MEMBER_LOCKED_FIELDS`，於是核心的 `for/else` 不 sudo、
        改走 ACL，而 portal 帳號對 `res.users` 沒有寫權 → `AccessError`。
        它不是 `AccessDenied`，`_login` 的 `except AccessDenied` 攔不到，
        cursor 整個回滾，`_update_last_login()` 永遠跑不到、`login_date` 永遠是空、
        下次條件還成立——**那個帳號永久登不進來**（實測回 403）。

        **`HttpCase.authenticate()` 抓不到這件事**：它直接呼叫
        `res.users.authenticate()`，沒有 request，`cookies.get('tz')` 恆為 None
        （L2⑫：測試釘死了唯一能讓 bug 不出現的那種幾何）。
        所以這支走真的 HTTP，而且先把帳號弄成「沒有 tz、沒登入過」。

        時區那件事的治本在 `tools.assoc_today()`（公會的事實釘死公會時區），
        不是鎖欄位——鎖欄位本來就攔不到核心自己的寫入。
        """
        self.user.partner_id.sudo().write({'tz': False})
        self.env.cr.flush()
        self.opener.cookies.set('tz', 'Pacific/Kiritimati')
        page = self.url_open('/web/login')
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        response = self.url_open('/web/login', data={
            'csrf_token': csrf, 'login': self.user.login,
            'password': PASSWORD, 'redirect': ''}, allow_redirects=False)
        self.assertIn(response.status_code, (302, 303),
                      '帶瀏覽器時區 cookie 的首次登入被擋下來了：%s' % response.status_code)

    def test_second_account_on_the_same_contact_is_kept_off_both_sides(self):
        """同一筆 partner 的第二個帳號：核心帳號頁要擋、前台服務也不能給。

        第十二輪 skeptic：`_assoc_member_accounts()` 改查 partner 之後，
        `/my/account` 與 `/my/deactivate_account` 的守衛（走
        `_member_account_for_user`）**沒有跟著改**，於是這個帳號不會被轉址，
        落到核心 `CustomerPortal.account()`——那支做的是 `partner.sudo().write()`，
        姓名竄改換一條路原封不動（L4②）。判準因此收成同一支 `_account_domain()`。

        反方向也要驗：判準放寬之後，`_member_for_user` 的
        `member.user_id.share` 問的是**會員自己**那個 share 帳號（恆為 True），
        少了 `member.user_id == user` 這一句，這個內部帳號反而拿得到前台。
        """
        member = self.member.sudo()
        twin = force_internal_user_on(self.env, member.partner_id, 'm6_twin_both_sides')
        twin.sudo().write({'password': PASSWORD})
        Member = self.env['assoc.member']
        self.assertTrue(Member._member_account_for_user(twin),
                        '擋核心帳號頁的那一側必須看得到它')
        self.assertFalse(Member._member_for_user(twin),
                         '提供前台服務的那一側必須看不到它')
        self.env.cr.flush()
        self.authenticate(twin.login, PASSWORD)
        self.assertEqual(self.url_open('/my/account', allow_redirects=False).status_code, 303,
                         '核心帳號頁要被轉址（不轉址就會落到 partner.sudo().write()）')
        self.assertEqual(self.url_open('/my/assoc').status_code, 404,
                         '前台服務不給它')

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.other = self.new_member('M6030', VALID_ID_2, 'm6030@example.com')
        self.grant(self.other)
        self.other_doc = self.env['assoc.member.document'].sudo().create({
            'member_id': self.other.id, 'doc_type': 'photo',
            'file': PNG_1PX, 'file_name': 'other.png'})
        self.env.cr.flush()

    def test_member_pages_render(self):
        self.authenticate(self.user.login, PASSWORD)
        home = self.url_open('/my')
        self.assertEqual(home.status_code, 200)
        self.assertIn('我的大會', home.text)
        profile = self.url_open('/my/assoc/profile')
        self.assertIn('A1******89', profile.text, '身分證要隱碼顯示')
        self.assertNotIn('A123456789', profile.text)

    def test_my_home_lists_member_entries_as_native_cards(self):
        """會員專區與 My account 同一層：入口卡直接排在 /my，不再經過「會員專區」那一行。"""
        self.authenticate(self.user.login, PASSWORD)
        home = self.url_open('/my')
        visible = visible_card_urls(home.text)
        self.assertLessEqual(MEMBER_ENTRY_URLS | {CORE_SECURITY_URL}, visible,
                             '缺少的入口：%s' % ((MEMBER_ENTRY_URLS | {CORE_SECURITY_URL}) - visible))
        self.assertNotIn('href="/my/assoc"', home.text, '不可以再多一層「會員專區」連結')
        cards = index_cards(home.text)
        for url in MEMBER_ENTRY_URLS:
            icon = cards[url][1]
            self.assertTrue(icon and icon.startswith('/assoc_portal/static/src/img/'),
                            '%s 要有自己的圖示（實際 %s）' % (url, icon))
            response = self.url_open(icon)
            self.assertEqual(response.status_code, 200, icon)
            self.assertIn('svg', response.headers.get('Content-Type', ''), icon)

    def test_non_member_my_home_has_no_member_entries(self):
        internal = self.env['res.users'].sudo().create({
            'name': '內部', 'login': 'm6_internal_home', 'password': PASSWORD,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env.cr.flush()
        self.authenticate(internal.login, PASSWORD)
        home = self.url_open('/my')
        self.assertEqual(home.status_code, 200)
        cards = index_cards(home.text)
        # 正向錨點：先證明這頁真的解析得出入口卡，下一行的「沒有」才有意義（否則解析失敗也會綠）
        self.assertIn(CORE_SECURITY_URL, cards)
        self.assertFalse(MEMBER_ENTRY_URLS & set(cards), '不是會員就不能看到會員入口')

    def test_archived_member_my_home_has_no_member_entries(self):
        """停權會員：入口跟各頁同一支判斷（`_member_for_user`，看 active）——不顯示一排點進去全是 404 的卡。
        改成 `_member_account_for_user`（不看 active）這支就會紅。"""
        self.member.sudo().active = False
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)
        cards = index_cards(self.url_open('/my').text)
        self.assertIn(CORE_SECURITY_URL, cards)
        self.assertFalse(MEMBER_ENTRY_URLS & set(cards), '停權會員不應看到會員入口')
        self.assertEqual(self.url_open('/my/assoc/meetings').status_code, 404, '各頁本來就擋')

    def test_old_member_home_url_redirects_to_my(self):
        """舊網址（書籤、紙本說明）導回 /my；非會員照樣 404（見 test_non_member_gets_404）。"""
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/assoc', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers['Location'].endswith('/my'), response.headers['Location'])

    def test_profile_page_has_documents_and_upload_form(self):
        """證明文件（清單＋上傳）搬到「我的資料」頁。"""
        self.authenticate(self.user.login, PASSWORD)
        profile = self.url_open('/my/assoc/profile')
        self.assertIn('證明文件', profile.text)
        self.assertIn('action="/my/assoc/documents/upload"', profile.text)

    def test_non_member_gets_404(self):
        internal = self.env['res.users'].sudo().create({
            'name': '內部', 'login': 'm6_internal_page', 'password': PASSWORD,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env.cr.flush()
        self.authenticate(internal.login, PASSWORD)
        self.assertEqual(self.url_open('/my/assoc').status_code, 404)

    def test_cannot_download_other_members_document(self):
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/assoc/documents/%s/file' % self.other_doc.id)
        self.assertEqual(response.status_code, 404)

    def test_own_document_downloads_as_attachment(self):
        doc = self.env['assoc.member.document'].sudo().create({
            'member_id': self.member.id, 'doc_type': 'photo',
            'file': PNG_1PX, 'file_name': 'me.png'})
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/assoc/documents/%s/file' % doc.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'image/png')
        # attachment 與白名單固定的 Content-Type 是我們自己的防線；
        # nosniff 核心本來就會加（http.py:2524），在這裡驗等於驗核心
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertNotIn('inline', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_archived_member_cannot_use_core_account_page(self):
        self.member.sudo().active = False
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/account', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/my/assoc/profile', response.headers['Location'])

    def test_account_page_redirects_to_readonly_profile(self):
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/account', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/my/assoc/profile', response.headers['Location'])

    def test_deactivate_account_is_blocked(self):
        """會員不能自行停用帳號（帶正確的 csrf_token，否則會被 CSRF 擋掉、驗不到守衛）。"""
        self.authenticate(self.user.login, PASSWORD)
        # /my/account 已轉址成唯讀資料頁，csrf 改從「我的資料」頁的上傳表單取
        page = self.url_open('/my/assoc/profile')
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        response = self.url_open('/my/deactivate_account', data={
            'csrf_token': csrf, 'validation': self.user.login, 'password': PASSWORD})
        self.assertNotIn('deactivated', response.text.lower())
        self.assertTrue(self.user.active, '帳號必須還在')


@tagged('post_install', '-at_install')
class TestMemberPass(HttpCase, PortalCase):
    """電子會員證＋動態報到 QR。"""

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()

    def test_pass_page_shows_rotating_qr(self):
        self.authenticate(self.user.login, PASSWORD)
        response = self.url_open('/my/assoc/pass')
        self.assertEqual(response.status_code, 200)
        self.assertIn('data:image/png;base64,', response.text)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertNotIn(self.member.sudo().barcode, response.text,
                         '前台永遠不顯示靜態卡號')

    def test_pass_tokens_endpoint_returns_two_windows(self):
        self.authenticate(self.user.login, PASSWORD)
        result = self.opener.post(
            self.base_url() + '/my/assoc/pass/tokens',
            json={'jsonrpc': '2.0', 'method': 'call', 'params': {}}).json()['result']
        self.assertEqual(len(result['codes']), 2, '只預取 2 窗（轉傳有效期最長 90 秒）')
        self.assertTrue(all(code.startswith('data:image/png;base64,') for code in result['codes']))

    def test_pass_requires_membership(self):
        internal = self.env['res.users'].sudo().create({
            'name': '內部', 'login': 'm6_internal_pass', 'password': PASSWORD,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env.cr.flush()
        self.authenticate(internal.login, PASSWORD)
        self.assertEqual(self.url_open('/my/assoc/pass').status_code, 404)


@tagged('post_install', '-at_install')
class TestInternalAccountCannotBeAMember(PortalCase):
    """**沒有任何人可以同時握有後台與前台。**

    正常流程擋得住：`action_grant_portal` 一律建 share 帳號、群組寫死 portal，
    而 share 使用者對 `assoc.*` 零 ACL。但 `member.user_id` 是可寫欄位——
    哨兵守衛擋得住 RPC，擋不住 `odoo shell` 與直接寫 DB（D6 的殘餘）。
    一旦有人把某位會員指到一個**內部**帳號，原本會同時打開兩扇門：
      ① `_member_for_user` 不濾 share → 前台服務照給
      ② `SELF_WRITEABLE_FIELDS` 用 `all(user.share)` 判斷 → 對非 share 不適用
         → P6 那個洞復活，他能用 call_kw 改自己 partner 的姓名，而那就是名冊姓名
    """

    def setUp(self):
        super().setUp()
        # 用哨兵把會員連到一個**內部**帳號，模擬 shell／DB 手動連結
        self.member.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = self.admin_user.id
        self.assertFalse(self.admin_user.share, '這一步要連到內部帳號才測得到東西')

    def test_internal_account_gets_no_portal_service(self):
        """前台一側：要求 share，所以這個連結拿不到前台。"""
        member_model = self.env['assoc.member']
        self.assertFalse(
            member_model._member_for_user(self.admin_user),
            '內部帳號即使被連結，也不可以拿到前台服務')
        # 而「這個帳號是不是綁著會員」那一側刻意維持寬鬆（擋核心行為要 fail-closed）
        self.assertTrue(
            member_model._member_account_for_user(self.admin_user),
            '擋核心行為的那一側必須看得到這個連結，否則守衛會放行')

    def test_second_account_on_the_same_contact_cannot_rename_the_roster(self):
        """**不必動 `user_id`**：同一筆聯絡人多開一個帳號就繞過去了。

        `res_users` 沒有 partner 唯一約束，所以系統管理員在
        設定→使用者 新增一個內部帳號、聯絡人挑會員那一筆即可——
        而要保護的資產（名冊姓名、報到照片）住的正是那一列 `res.partner`。
        第十一輪 skeptic 指出、主迴圈獨立複現：守衛看不到這個帳號（它只查
        `user_id`），`name` 留在 `SELF_WRITEABLE_FIELDS`，核心以 sudo 寫入，
        名冊姓名被換掉、照片被換掉，而公會管理員**改不回來**
        （`_partner_sudo()` 認定那是內部使用者而拒絕）。
        這是 L4① 的形狀：擋了鏡像欄位，來源端敞開。

        `setUp` 連的是 `admin_user`，這裡另外建一個**沒有**任何連結、
        只是共用同一筆 partner 的帳號——判準必須是 partner。
        """
        member = self.member.sudo()
        # ORM 那條路現在被 `_check_no_internal_account_on_a_roster_contact` 擋住了
        # （見 `test_roster_contact_cannot_back_an_internal_account`）。這一支驗的是
        # **萬一那個狀態還是成立了**（shell／直接寫 DB）底下那道防線還在，
        # 所以要硬安上去（L2⑯：新加一條更廣的檢查之後，舊的那條不能沒人守）。
        twin = force_internal_user_on(self.env, member.partner_id, 'm6_twin_on_same_partner')
        self.assertFalse(twin.share, '這一步要是內部帳號才測得到東西')
        self.assertNotEqual(member.user_id, twin, '它刻意不是 member.user_id')
        self.assertTrue(twin._assoc_member_accounts(),
                        '守衛要看得到「這個帳號寫到某位會員的名冊 partner 上」')
        before = member.name
        with self.assertRaises(AccessError):
            twin.with_user(twin).write({'name': '偽造 名冊姓名'})
        member.invalidate_recordset(['name'])
        self.assertEqual(member.name, before, '名冊姓名不可以被換掉')

    def test_roster_contact_cannot_back_an_internal_account(self):
        """名冊那筆聯絡人底下不可以有內部帳號——**在源頭擋**。

        只擋「寫得到」不夠，還要擋「改不回來」：第十二輪紅隊實跑，
        多開一個內部帳號之後公會管理員就改不動那位會員的姓名／照片／Email
        （四個 inverse 全走 `_partner_sudo()`），而 `action_revoke_portal`
        的復原分支條件是「`user_id` 指向內部帳號」，在這個形狀下 `user_id`
        仍是合法的 share 帳號，**永遠不會觸發**。
        """
        with self.assertRaises(ValidationError):
            self.env['res.users'].sudo().create({
                'login': 'm6_internal_on_roster', 'name': '想混進來的',
                'partner_id': self.member.sudo().partner_id.id,
                'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])]})

    def test_the_member_own_portal_account_is_not_caught_by_that_rule(self):
        """反向：會員自己的 share 帳號與純內部職員都不可以被這條誤擋。

        假警報比漏報更糟（L1⑨）——一條會擋住正常開通的約束，
        會讓公會直接放棄用這個系統開前台帳號。
        """
        self.member.sudo().user_id.write({'action_id': False})      # share，不該被擋
        plain = self.env['res.users'].sudo().create({
            'login': 'm6_plain_ok', 'name': '路人職員',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertTrue(plain.id)

    def test_a_plain_internal_account_is_not_locked(self):
        """反向：沒碰到名冊 partner 的一般內部帳號不該被誤鎖。

        守衛放寬成「查 partner」之後，最容易犯的錯是把全公司的人一起鎖住
        （假警報比漏報更糟，L1⑨）。
        """
        plain = self.env['res.users'].sudo().create({
            'name': '路人職員', 'login': 'm6_plain_staff',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.assertFalse(plain._assoc_member_accounts())
        self.assertIn('name', plain.with_user(plain).SELF_WRITEABLE_FIELDS)

    def test_internal_account_still_cannot_rename_the_roster(self):
        """核心一側：判準是「綁著會員嗎」，不是「是不是 share」。"""
        writeable = self.admin_user.with_user(self.admin_user).SELF_WRITEABLE_FIELDS
        for locked in ('name', 'image_1920', 'company_id', 'email'):
            self.assertNotIn(locked, writeable,
                             '綁著會員的帳號不可以自己改 %s（那是名冊姓名／報到照片）' % locked)
