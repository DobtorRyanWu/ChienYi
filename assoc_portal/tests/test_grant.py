"""開通、停用、跨公會衝突（計畫 P4、P16）。"""

from odoo.addons.assoc_base import tools_pii
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_member import GUARD_LINK
from odoo.tests import tagged
from psycopg2.errors import UniqueViolation as IntegrityError

from odoo.tools import mute_logger

from .common import PASSWORD, PortalCase, VALID_ID, VALID_ID_2


@tagged('post_install', '-at_install')
class TestGrant(PortalCase):

    def test_grant_creates_share_user(self):
        user = self.grant()
        self.assertTrue(user.share, '會員帳號必須是 share（portal）')
        self.assertEqual(user.login, 'm6001@example.com')
        self.assertEqual(user.company_ids, self.company)
        self.assertEqual(user.groups_id, self.env.ref('base.group_portal'))
        self.assertEqual(self.member.portal_state, 'pending')

    def test_grant_writes_unusable_pbkdf2_hash(self):
        """不能留空雜湊：核心對空雜湊 0 秒回絕，會變成反向計時預言。"""
        user = self.grant()
        self.env.cr.execute("SELECT password FROM res_users WHERE id = %s", [user.id])
        hashed = self.env.cr.fetchone()[0]
        self.assertTrue(hashed.startswith('$pbkdf2-sha512$'), hashed[:20])

    def test_login_falls_back_when_email_taken(self):
        self.env['res.users'].create({'name': '撞號', 'login': 'dup@example.com',
                                      'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        member = self.new_member('M6002', email='dup@example.com')
        user = self.grant(member)
        self.assertEqual(user.login, 'm%s-M6002' % self.company.id)

    def test_member_without_email_gets_fallback_login(self):
        member = self.new_member('M6003')
        self.assertEqual(self.grant(member).login, 'm%s-M6003' % self.company.id)

    def test_numeric_member_no_does_not_produce_an_unusable_login(self):
        """**數字會員編號**產生的後備帳號不可以長得像身分證。

        `m1-001234` 是 9 碼含 7 個數字，正好落在登入頁判定「使用者在打身分證」
        的區間——那種帳號永遠登不進來（登入頁不會把它交給核心），
        而 `_check_login_not_id_shaped` 會在開通時就 raise，
        訊息還叫承辦「請改用 Email」，但這個 login 是系統自己產的。
        示範資料的編號一律帶字母（T001、M6003）所以一直沒中；
        公會的實際編號多半是純數字。
        """
        for member_no in ('001234', '0012345', '123456'):
            member = self.new_member(member_no)
            login = self.grant(member).login       # 產不出合法 login 就會在這裡 raise
            self.assertFalse(tools_pii.looks_like_id_attempt(login),
                             '帳號 %s 會被登入頁當成身分證' % login)
            self.assertIn(member_no, login, '帳號仍然要看得出是誰')

    def test_fallback_login_never_collides(self):
        """後備帳號撞號時要自己讓開，不能丟原始的 DB 例外。

        `UNIQUE(login)` 是全庫的：編號 `00123456`（純數字→加 `-portal` 後綴）
        與另一位編號字面就是 `00123456-portal` 的會員會算出同一個 login，
        撞到時第二位永遠開通失敗、承辦看到的是 psycopg2 的 UniqueViolation
        （抗辯實跑複現）。真實編號多半帶字母所以機率低，但那是運氣不是設計。
        """
        # 先讓那個 login 被別人佔走（login 的命名空間是全庫共用的，
        # 管理員自己建的帳號、或另一位編號字面以 `-portal` 收尾的會員都會佔到）
        member = self.new_member('00123456')
        squatter = 'm%s-00123456-portal' % self.company.id
        self.env['res.users'].create({'name': '佔位帳號', 'login': squatter})

        user = self.grant(member)            # 沒讓開的話這裡會丟 UniqueViolation
        self.assertNotEqual(user.login, squatter)
        self.assertIn('00123456', user.login, '帳號仍然要看得出是誰')
        self.assertFalse(tools_pii.looks_like_id_attempt(user.login), user.login)

    def test_same_national_id_in_other_company_is_refused(self):
        """一個身分證只能有一個前台帳號；訊息不分原因並留軌跡。

        衝突的軌跡走獨立交易（`_log_independent`）：接下來的 UserError 會把主交易
        整個回滾，寫在主交易等於沒寫。
        """
        # 先讓他公會的同一人開通，再由本公會嘗試（呼叫方是已存在的公司，
        # 獨立交易才看得到——測試裡新建的公司還沒 commit）
        twin = self.new_member('X001', VALID_ID, company=self.other_company)
        admin_other = self.env['res.users'].create({
            'name': '他公會管理員', 'login': 'm6_admin_other',
            'company_id': self.other_company.id, 'company_ids': [(6, 0, self.other_company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_admin').id])]})
        twin.with_user(admin_other).with_company(self.other_company).action_grant_portal()

        with self.assertRaises(UserError) as err:
            self.member.with_user(self.admin_user).action_grant_portal()
        self.assertNotIn(VALID_ID, str(err.exception))
        self.assertFalse(self.member.sudo().user_id)
        # 註：軌跡走獨立交易（`_log_independent`），而測試交易是 REPEATABLE READ，
        # 看不到別的連線剛 commit 的列——「UserError 回滾後軌跡仍在」這條性質
        # 在 M6 的 E2E 用 psql 驗（tools/e2e/e2e_m6_portal.py）。

    def test_unique_index_blocks_direct_second_link(self):
        """Python 約束擋不住兩個公會同時開通（改的是不同列）→ 用 partial unique index。"""
        user = self.grant()
        twin = self.new_member('X002', VALID_ID, company=self.other_company)
        # 一定要收斂成 IntegrityError：寫成 Exception 的話，
        # 哨兵守衛的 AccessError 也會被接住，SQL 根本沒送出去、索引等於 0 覆蓋
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                twin.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = user.id
                self.env.flush_all()

    def test_revoke_then_grant_reuses_account(self):
        """停用後再開通要重用同一個帳號：login 全庫唯一，連封存的也算。"""
        user = self.grant()
        self.member.with_user(self.admin_user).action_revoke_portal()
        self.assertFalse(user.active)
        self.assertEqual(self.member.portal_state, 'revoked')
        self.member.with_user(self.admin_user).action_grant_portal()
        self.assertTrue(user.active)
        self.assertEqual(self.member.sudo().user_id, user)

    def test_revoke_clears_pending_notice(self):
        self.grant()
        self.print_notice()
        self.assertTrue(self.member.sudo().activation_nonce_hash)
        self.member.with_user(self.admin_user).action_revoke_portal()
        self.assertFalse(self.member.sudo().activation_nonce_hash)

    def test_other_company_admin_cannot_grant(self):
        other_member = self.new_member('X003', VALID_ID_2, company=self.other_company)
        with self.assertRaises(AccessError):
            other_member.with_user(self.admin_user).action_grant_portal()

    def test_staff_cannot_grant(self):
        staff = self.env['res.users'].create({
            'name': '職員', 'login': 'm6_staff',
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])]})
        with self.assertRaises(AccessError):
            self.member.with_user(staff).action_grant_portal()

    def test_core_reset_password_blocked_for_members(self):
        """核心的重設密碼信不會寄出，卻顯示「已寄出」——會員帳號一律走通知單。"""
        user = self.grant()
        with self.assertRaises(UserError):
            user.action_reset_password()

    def test_user_link_cannot_be_written_by_rpc(self):
        """公會管理員不能用 RPC 把會員指到別的帳號。

        `readonly=True` 在 Odoo 只是 UI 限制，write() 不檢查——少了哨兵守衛，
        管理員可以把自己公會的會員指到系統管理員帳號，再用停用／重新開通
        把對方封存並改掉密碼（第 1 輪 red-team 實際打出來的路徑）。
        """
        self.grant()
        system_user = self.env.ref('base.user_admin')
        with self.assertRaises(AccessError):
            self.member.with_user(self.admin_user).write({'user_id': system_user.id})
        with self.assertRaises(AccessError):
            self.member.sudo().write({'activation_nonce_hash': 'x' * 64})
        self.assertNotEqual(self.member.sudo().user_id, system_user)

    def test_user_link_cannot_be_set_on_create(self):
        """create 不檢查欄位 groups，也不看 readonly——要驗產出的紀錄。"""
        partner = self.env['res.partner'].create({
            'name': '建立時塞帳號', 'company_id': self.company.id})
        with self.assertRaises(ValidationError):
            self.env['assoc.member'].create({
                'partner_id': partner.id, 'member_no': 'M6050',
                'user_id': self.env.ref('base.user_admin').id})

    def _plant_bad_link(self, share=False):
        """在資料庫裡種一個「指到別人」的連結（舊資料、手動改過的情境）。"""
        other_partner = self.env['res.partner'].create({
            'name': '別人', 'company_id': self.company.id})
        group = 'base.group_portal' if share else 'base.group_user'
        stranger = self.env['res.users'].sudo().create({
            'name': '別人的帳號', 'login': 'm6_stranger_%s' % ('share' if share else 'int'),
            'partner_id': other_partner.id, 'active': False,
            'groups_id': [(6, 0, [self.env.ref(group).id])]})
        self.member.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = stranger.id
        return stranger

    def test_grant_refuses_mismatched_account(self):
        """壞連結若指到內部使用者，重新開通會把對方解封存並改掉密碼。

        停用那條路徑本來就有 `_linked_user()` 擋，開通這條原本沒有——
        防線不對稱的話，攻擊者走沒擋的那一條就好。
        """
        stranger = self._plant_bad_link(share=False)
        self.env.cr.execute('SELECT password FROM res_users WHERE id = %s', [stranger.id])
        before = self.env.cr.fetchone()[0]
        with self.assertRaises(AccessError):
            self.member.with_user(self.admin_user).action_grant_portal()
        self.assertFalse(stranger.active, '別人的帳號不能被解封存')
        self.env.cr.execute('SELECT password FROM res_users WHERE id = %s', [stranger.id])
        self.assertEqual(self.env.cr.fetchone()[0], before, '別人的密碼不能被改掉')

    def test_print_notice_refuses_mismatched_account(self):
        """列印通知單同樣要走 `_linked_user()`：否則會替別人的帳號產開通碼。"""
        self._plant_bad_link(share=True)
        with self.assertRaises(AccessError):
            self.member.with_user(self.admin_user).action_print_activation()
        self.assertFalse(self.member.sudo().activation_nonce_hash, '不該產生開通碼')

    def test_revoke_refuses_mismatched_account(self):
        """資料庫裡若留有錯誤的連結，停用不能拿它動到別人的帳號。"""
        self.grant()
        other_partner = self.env['res.partner'].create({
            'name': '別人', 'company_id': self.company.id})
        stranger = self.env['res.users'].sudo().create({
            'name': '別人的帳號', 'login': 'm6_stranger', 'partner_id': other_partner.id,
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.member.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = stranger.id
        with self.assertRaises(AccessError):
            self.member.with_user(self.admin_user).action_revoke_portal()
        self.assertTrue(stranger.active, '別人的帳號不能被封存')


@tagged('post_install', '-at_install')
class TestPasswordPolicy(PortalCase):
    """核心的 `_change_password` 只擋空字串，而 `auth_password_policy` 沒有安裝。"""

    def setUp(self):
        super().setUp()
        self.user = self.grant()

    def test_member_cannot_set_a_one_character_password(self):
        with self.assertRaises(UserError):
            self.user.sudo()._change_password('a')

    def test_member_can_set_a_long_enough_password(self):
        self.user.sudo()._change_password(PASSWORD)

    def test_internal_user_keeps_core_behaviour(self):
        internal = self.env['res.users'].sudo().create({
            'name': '內部（密碼）', 'login': 'm6_internal_pw',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        internal._change_password('short')      # 核心只擋空字串，不該被我們攔

    def test_public_reset_password_does_not_reveal_membership(self):
        """匿名的 /web/reset_password 走 `reset_password()`。

        不能讓它看到「會員帳號請改用…」：那句話只對會員帳號出現，
        一比就知道這個 Email 是不是會員（匿名可用的枚舉預言）。
        """
        with self.assertRaises(Exception) as member_err:
            self.env['res.users'].sudo().reset_password(self.user.login)
        with self.assertRaises(Exception) as unknown_err:
            self.env['res.users'].sudo().reset_password('nobody@example.com')
        self.assertEqual(str(member_err.exception), str(unknown_err.exception))
        self.assertNotIn('會員', str(member_err.exception))


@tagged('post_install', '-at_install')
class TestFormActions(PortalCase):
    """按鈕的可見條件：每個前台狀態都要有路可走。"""

    PORTAL_BUTTONS = ('action_grant_portal', 'action_revoke_portal', 'action_print_activation')

    def _visible_buttons(self, portal_state):
        """把前台那三顆按鈕的 invisible 條件，對給定的 portal_state 算一次。

        其他欄位一律當成 False（header 上還有 assoc_base 的按鈕會引用別的欄位）。
        """
        from lxml import etree
        from odoo.tools.safe_eval import safe_eval
        arch = etree.fromstring(
            self.env['assoc.member'].with_user(self.admin_user).get_view(
                self.env.ref('assoc_portal.assoc_member_view_form_portal').id, 'form')['arch'])
        context = {name: False for name in self.env['assoc.member']._fields}
        context.update(id=1, portal_state=portal_state)
        visible = []
        for button in arch.xpath('//header/button[@name]'):
            if button.get('name') not in self.PORTAL_BUTTONS:
                continue
            condition = button.get('invisible')
            if condition and safe_eval(condition, dict(context)):
                continue
            visible.append(button.get('name'))
        return visible

    def test_no_portal_state_is_a_dead_end(self):
        """停用的會員如果一顆按鈕都沒有，公會就只能進 shell 救人。

        `test_revoke_then_grant_reuses_account` 直接呼叫 method，所以它是綠的
        也不代表產品裡有路徑按得到。
        """
        for state in dict(self.env['assoc.member']._fields['portal_state'].selection):
            self.assertTrue(self._visible_buttons(state),
                            '%s 狀態下一顆按鈕都沒有' % state)

    def test_revoked_member_can_be_granted_again(self):
        self.assertIn('action_grant_portal', self._visible_buttons('revoked'))
