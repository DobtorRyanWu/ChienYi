# -*- coding: utf-8 -*-
"""帳號設定（線 A1'，合約 §2、§3.1、§13-6）：伺服器動作、群組允許清單、允許公司同步、
兩步驟驗證、session 旗標、重新帶入營造廠歸屬。

斷言打在使用者看得到的結果（群組集合、允許公司、筆數、被拒＋訊息）。
"""
import base64
import time

from odoo.addons.website.tools import MockRequest
from odoo.addons.auth_totp.models.totp import hotp
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .test_scope_rules import (
    EXPECT_FRAMEWORK, MANAGER_GROUP, TOTP_FIXTURE_SECRET, DashScopeCase, require_totp,
)

ENGINEERING_MANAGER = 'construction_supervision_base.group_engineering_manager'
# dev 預設使用者範本帶的高權限群組（合約 §3.1）
TEMPLATE_GROUPS = (
    'hr.group_hr_manager', 'project.group_project_manager',
    'base.group_sanitize_override', 'base.group_allow_export',
)
TOTP_TIMESTEP = 30
INBOX_GROUP = 'mail.group_mail_notification_type_inbox'
MULTI_COMPANY_GROUP = 'base.group_multi_company'   # 多家允許公司時核心自動補
OLD_PASSWORD = 'Old-pass-12345'
NEW_PASSWORD = 'New-pass-67890'
TOTP_HINT = '兩步驟驗證'
SESSION_SID = 's' * 42   # 測試用 session id（長度同核心）
BROWSER_TZ = 'Asia/Taipei'   # 瀏覽器登入時前端寫的 tz cookie（核心第一次登入會用它設使用者時區）


def _totp_code(secret_b32):
    """依 secret 算現在的 6 位數驗證碼（與 auth_totp 的 TOTP.match 同一公式）。"""
    key = base64.b32decode(secret_b32.replace(' ', ''))
    return '%06d' % hotp(key, int(time.time()) // TOTP_TIMESTEP)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestAccountSetup(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # 第二家監造公司與只在它底下的工程；C 營造廠的兩個工程（一個在 S、一個在 S2）→ 平手取 id 小的
        cls.co_s2 = env['res.company'].create({'name': 'DASH 監造 S2', 'company_type': 'supervision'})
        cls.p_s2 = cls._project_in('DASH-PS2', cls.co_s2, cls.co_a)
        cls.p_c_s = cls._project_in('DASH-PCS', cls.co_s, cls.co_c)
        cls.p_c_s2 = cls._project_in('DASH-PCS2', cls.co_s2, cls.co_c)
        cls.eng = cls._user('dash_eng', [ENGINEERING_MANAGER], company=cls.co_s, companies=cls.co_s)

    @classmethod
    def _project_in(cls, code, supervision, contractor):
        project = cls._project(code, 'general', [(6, 0, contractor.ids)])
        project.write({'company_id': supervision.id})
        return project

    def _fresh_candidate(self, login, scope=None, extra_groups=()):
        """建一個「像 dev 預設使用者範本」的內部帳號：帶一堆高權限群組。"""
        groups = [self.env.ref('base.group_user').id] + [self.env.ref(x).id for x in (*TEMPLATE_GROUPS, *extra_groups)]
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, groups)],
                'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)]}
        if scope:
            vals['dash_scope_company_id'] = scope.id
        return self.env['res.users'].with_context(no_reset_password=True).create(vals)

    # ── 伺服器動作 ──────────────────────────────────────────────────────
    def test_action_sets_groups_companies_main(self):
        """群組重設成只有營造廠主管＋隱含群組；允許公司＝範圍公司＋所有相關監造公司；主公司＝工程最多的。"""
        user = self._fresh_candidate('dash_cand_a', scope=self.co_a)
        for xmlid in TEMPLATE_GROUPS:
            self.assertTrue(user.has_group(xmlid), f'前提：範本帶 {xmlid}')
        user.with_user(self.eng).action_set_contractor_manager()
        manager = self.env.ref(MANAGER_GROUP)
        allowed = manager | manager.trans_implied_ids | self.env.ref(INBOX_GROUP) | self.env.ref(MULTI_COMPANY_GROUP)
        self.assertEqual(user.groups_id, allowed, "群組應恰好是營造廠主管＋隱含群組＋通知/介面群組")
        for xmlid in TEMPLATE_GROUPS:
            self.assertFalse(user.has_group(xmlid), f'{xmlid} 應被拿掉')
        # A 的工程：P、PA、R（監造 S，共 3）＋PS2（監造 S2，1）
        self.assertEqual(user.company_ids, self.co_a | self.co_s | self.co_s2)
        self.assertEqual(user.company_id, self.co_s, '主公司＝承攬工程最多的監造公司（S：3 個，S2：1 個）')

    def test_action_main_tie_takes_lowest_id(self):
        user = self._fresh_candidate('dash_cand_c', scope=self.co_c)
        user.with_user(self.eng).action_set_contractor_manager()
        self.assertEqual(user.company_ids, self.co_c | self.co_s | self.co_s2)
        self.assertEqual(user.company_id, min(self.co_s, self.co_s2, key=lambda c: c.id))

    def test_action_without_projects_scope_only(self):
        """沒有承攬工程：允許公司只有範圍公司（之後補工程由自動同步補上，見 test_sync_*）。"""
        lonely = self.env['res.company'].create({'name': 'DASH 營造 孤', 'company_type': 'contractor'})
        user = self._fresh_candidate('dash_cand_lonely', scope=lonely)
        user.with_user(self.eng).action_set_contractor_manager()
        self.assertEqual(user.company_ids, lonely)
        self.assertEqual(user.company_id, lonely)

    def test_action_requires_scope(self):
        user = self._fresh_candidate('dash_cand_noscope')
        with self.assertRaises(UserError) as ctx:
            user.with_user(self.eng).action_set_contractor_manager()
        # 要是動作自己的檢查（「尚未填」），不是後面群組約束的訊息（約束也會提到範圍公司，會遮蔽這道檢查）
        self.assertIn('尚未填', str(ctx.exception))
        self.assertTrue(user.has_group('hr.group_hr_manager'), '失敗時不可動到群組')

    def test_action_rejects_non_contractor_scope(self):
        """範圍公司被改成非營造廠（繞過約束：SQL）→ 動作也要擋（動作自己的檢查）。"""
        user = self._fresh_candidate('dash_cand_badscope', scope=self.co_a)
        self.env.cr.execute('UPDATE res_users SET dash_scope_company_id = %s WHERE id = %s',
                            [self.co_s.id, user.id])
        user.invalidate_recordset(['dash_scope_company_id'])
        with self.assertRaises(UserError) as ctx:
            user.with_user(self.eng).action_set_contractor_manager()
        self.assertIn('不是營造廠', str(ctx.exception))

    def test_action_engineering_manager_only(self):
        user = self._fresh_candidate('dash_cand_perm', scope=self.co_a)
        with self.assertRaises(AccessError):
            user.with_user(self.sup).action_set_contractor_manager()
        self.assertTrue(user.has_group('hr.group_hr_manager'))

    def test_action_not_on_self(self):
        self.eng.sudo().write({'dash_scope_company_id': self.co_a.id})
        with self.assertRaises(UserError):
            self.eng.with_user(self.eng).action_set_contractor_manager()
        self.assertTrue(self.eng.has_group(ENGINEERING_MANAGER), '不可把自己的管理權重設掉')

    # ── 群組允許清單約束 ─────────────────────────────────────────────────
    def test_allowlist_blocks_template_groups_on_users_side(self):
        for xmlid in TEMPLATE_GROUPS:
            with self.subTest(group=xmlid), self.assertRaises(ValidationError) as ctx:
                with self.env.cr.savepoint():
                    self._fresh_candidate('dash_bad_' + xmlid.split('.')[1], scope=self.co_a, extra_groups=[MANAGER_GROUP])
            self.assertIn('不可再帶其他群組', str(ctx.exception))

    def test_allowlist_blocks_extra_group_added_later(self):
        mgr = self.mgr_a
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                mgr.write({'groups_id': [(4, self.env.ref('project.group_project_manager').id)]})
        console = self.console
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                console.write({'groups_id': [(4, self.env.ref('hr.group_hr_manager').id)]})

    def test_allowlist_blocks_group_side(self):
        """從群組表單加人（res.groups.users）也擋。"""
        hr_manager = self.env.ref('hr.group_hr_manager')
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                hr_manager.write({'users': [(4, self.mgr_a.id)]})
        self.assertNotIn(self.mgr_a, hr_manager.users)

    def test_allowlist_allows_closure_and_notification(self):
        """放行的方向：隱含群組閉包＋通知群組照常；監造方帳號可帶任意群組（不受影響）。"""
        user = self._fresh_candidate('dash_ok_user', scope=self.co_a)
        user.with_user(self.eng).action_set_contractor_manager()
        user.write({'groups_id': [(4, self.env.ref(INBOX_GROUP).id)]})
        self.assertTrue(user.has_group(INBOX_GROUP))
        self.sup.write({'groups_id': [(4, self.env.ref('hr.group_hr_manager').id)]})
        self.assertTrue(self.sup.has_group('hr.group_hr_manager'))

    def test_manager_requires_qualified_scope(self):
        """營造廠主管必須有範圍公司且是營造廠；清掉範圍公司被擋。"""
        with self.assertRaises(ValidationError) as ctx:
            with self.env.cr.savepoint():
                self._user('dash_mgr_noscope', [MANAGER_GROUP], company=self.co_s, companies=self.co_s)
        self.assertIn('範圍公司', str(ctx.exception))
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.mgr_a.write({'dash_scope_company_id': False})

    # ── 允許公司自動同步 ─────────────────────────────────────────────────
    def _manager_a(self):
        user = self._fresh_candidate('dash_sync_a', scope=self.co_a)
        user.with_user(self.eng).action_set_contractor_manager()
        user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        return user

    def test_sync_contractor_added_and_removed(self):
        user = self._manager_a()
        extra = self.env['res.company'].create({'name': 'DASH 監造 S3', 'company_type': 'supervision'})
        project = self._project_in('DASH-PS3', extra, self.co_b)
        self.assertNotIn(extra, user.company_ids, '前提：B 的工程不影響 A 的主管')
        project.write({'contractor_company_ids': [(4, self.co_a.id)]})
        self.assertIn(extra, user.company_ids, '工程加上營造廠 A → A 的主管自動多一家監造公司')
        project.write({'contractor_company_ids': [(3, self.co_a.id)]})
        self.assertNotIn(extra, user.company_ids, '拿掉營造廠 A → 自動收回')
        self.assertEqual(user.company_ids, self.co_a | self.co_s | self.co_s2)

    def test_sync_project_company_change_and_unlink(self):
        user = self._manager_a()
        project = self.p_s2
        project.write({'company_id': self.co_s.id})
        self.assertNotIn(self.co_s2, user.company_ids, '工程改到別家監造公司 → S2 不再相關')
        project.write({'company_id': self.co_s2.id})
        self.assertIn(self.co_s2, user.company_ids)
        # 已開始施工的工程不能刪（核心守衛）；刪草稿工程驗證 unlink 也會同步
        draft = self.env['project.project'].create({
            'name': 'DASH 草稿工程', 'code': 'DASH-DRAFT', 'project_type': 'general', 'state': 'draft',
            'company_id': self.co_s2.id, 'contractor_company_ids': [(6, 0, self.co_a.ids)]})
        project.write({'company_id': self.co_s.id})
        self.assertIn(self.co_s2, user.company_ids, '草稿工程讓 S2 相關')
        draft.unlink()
        self.assertNotIn(self.co_s2, user.company_ids, '工程刪除 → 收回')

    def test_sync_new_project_and_main_company_repair(self):
        user = self._manager_a()
        # 主公司被移出允許公司（S 的工程全部換到 S2）→ 主公司自動改到仍相關的監造公司
        for project in (self.p_shared, self.p_a, self.r_shared):
            project.write({'company_id': self.co_s2.id})
        self.assertNotIn(self.co_s, user.company_ids)
        self.assertEqual(user.company_id, self.co_s2)
        # 新建工程帶上營造廠 A、監造公司 S → 自動加入
        self._project_in('DASH-NEW', self.co_s, self.co_a)
        self.assertIn(self.co_s, user.company_ids)

    def test_sync_keeps_valid_main_company(self):
        """自動同步不推翻仍有效的主公司（使用者在偏好裡選的）。"""
        user = self._manager_a()
        user.sudo().write({'company_id': self.co_s2.id})
        self._project_in('DASH-NEW2', self.co_s, self.co_a)
        self.assertEqual(user.company_id, self.co_s2)

    def test_sync_ignores_other_scope_managers(self):
        user = self._manager_a()
        other = self._fresh_candidate('dash_sync_b', scope=self.co_b)
        other.with_user(self.eng).action_set_contractor_manager()
        before = other.company_ids
        extra = self.env['res.company'].create({'name': 'DASH 監造 S4', 'company_type': 'supervision'})
        self._project_in('DASH-PS4', extra, self.co_a)
        self.assertIn(extra, user.company_ids)
        self.assertEqual(other.company_ids, before, 'B 的主管不受 A 的工程影響')

    # ── 兩步驟驗證 ───────────────────────────────────────────────────────
    def _fresh_manager(self, login):
        user = self._fresh_candidate(login, scope=self.co_a)
        user.with_user(self.eng).action_set_contractor_manager()
        user.sudo().write({'password': OLD_PASSWORD})
        return user

    def _sheet_count(self, user):
        env = self.env(user=user, context={'active_test': False, 'allowed_company_ids': user.sudo().company_ids.ids})
        return env['daily.log.sheet'].search_count([])

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_totp_required_for_data(self):
        """沒啟用 TOTP＝什麼都看不到（訊息指向「帳戶安全性」）；啟用後同一程序立即看得到；停用又回到 0。"""
        user = self._fresh_manager('dash_totp_user')
        self.assertFalse(user.totp_enabled)
        self.assertEqual(self._sheet_count(user), 0, '沒啟用兩步驟驗證 → 什麼都看不到')
        with self.assertRaises(AccessError) as ctx:
            self.docs_a_sheet().with_user(user).read(['log_date'])
        self.assertIn(TOTP_HINT, str(ctx.exception))
        self.assertIn('帳戶安全性', str(ctx.exception))   # fix1-I：提示指向實際的選單與分頁
        expected = self._sheet_count(self.mgr_a)
        self.assertTrue(expected)
        user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        self.assertEqual(self._sheet_count(user), expected, '啟用後立即與已啟用的同範圍主管看到一樣多')
        user.sudo().write({'totp_secret': False})
        self.assertEqual(self._sheet_count(user), 0, '停用後回到什麼都看不到')

    def docs_a_sheet(self):
        return self.docs[('daily.log.sheet', self.co_a)][:1]

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_totp_missing_manager_logs_in_but_reads_no_business_data(self):
        """合約 §0b-16（線 C、D 真瀏覽器實證：未啟用 TOTP 的營造廠主管一登入就 403，提示永遠看不到）：
        ① 走核心登入（瀏覽器帶 tz cookie：核心 _login 以本人身分讀 user.tz／login_date）不被擋；
        ② session_info 完成、dash_totp_missing 為真；
        ③ 讀得到自己的使用者與聯絡人，別人的讀不到；
        ④ 框架以外的業務資料一筆都看不到（列舉全部模型）；啟用 TOTP 後同一套列舉數得到東西（防恆真）。"""
        user = self._fresh_manager('dash_login_user')
        self.assertTrue(user._dash_totp_missing(), '前提：未啟用 TOTP')
        self.assertNotEqual(user.tz, BROWSER_TZ, '前提：時區還不是瀏覽器的（登入後改成它，才證明 tz 那段真的跑過）')
        # ① 核心登入：開新 cursor（測試模式共用本交易），與瀏覽器同一條路
        self.env.flush_all()
        self.registry.enter_test_mode(self.cr)
        self.addCleanup(self.registry.leave_test_mode)
        with MockRequest(self.env(user=user)) as req:
            req.cookies = {'tz': BROWSER_TZ}
            auth = self.env['res.users']._login(
                self.env.cr.dbname, {'login': user.login, 'password': OLD_PASSWORD, 'type': 'password'},
                {'interactive': True})
        self.assertEqual(auth['uid'], user.id)
        self.env.invalidate_all()
        self.assertEqual(user.tz, BROWSER_TZ, '核心第一次登入依 tz cookie 設了時區（讀本人 res.users 沒被擋）')
        # ② session_info
        info = self._session_info(user)
        self.assertEqual(info['uid'], user.id)
        self.assertTrue(info['dash_totp_missing'])
        # ③ 本人的使用者與聯絡人
        env = self._env_of(user)
        own = env['res.users'].browse(user.id).read(['name', 'tz', 'login_date', 'partner_id', 'company_id'])
        self.assertEqual(own[0]['partner_id'][0], user.partner_id.id)
        self.assertEqual(env['res.partner'].browse(user.partner_id.id).read(['name'])[0]['name'], user.name)
        self.assertEqual(set(env['res.users'].search([]).ids), {user.id})
        # S2-D：內部受限帳號另外讀得到 OdooBot 的聯絡人（核心第一次打開後台要讀它，rule_scope._dash_with_odoobot）
        self.assertEqual(set(env['res.partner'].search([]).ids),
                         {user.partner_id.id, self.env.ref('base.partner_root').id})
        same_scope = self.mgr_a   # 同範圍公司的另一個主管：範圍合格時看得到，未啟用 TOTP 時看不到
        for other in (same_scope, self.sup):
            with self.assertRaises(AccessError):
                env['res.users'].browse(other.id).read(['name'])
            with self.assertRaises(AccessError):
                env['res.partner'].browse(other.partner_id.id).read(['name'])
        # ④ 業務資料：框架與本人兩個模型以外全部 0
        nonzero, errors = self._other_counts(user, EXPECT_FRAMEWORK | {'res.users', 'res.partner'})
        self.assertEqual((nonzero, errors), ({}, {}), '未啟用 TOTP：業務資料一筆都不能看到')
        user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        nonzero, errors = self._other_counts(user, EXPECT_FRAMEWORK | {'res.users', 'res.partner'})
        self.assertEqual(errors, {})
        self.assertIn('project.project', nonzero, '啟用後同一套列舉要數得到工程（否則上面的 0 可能是沒跑到）')
        self.assertIn(same_scope.id, set(env['res.users'].search([]).ids), '啟用後回到一般的個資收窄')

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_totp_not_required_for_other_users(self):
        """監造方、前台營造帳號不要求 TOTP（只對營造廠主管）：筆數不受影響。"""
        self.assertFalse(self.sup.totp_enabled)
        self.assertTrue(self._sheet_count(self.sup))
        self.assertFalse(self.portal_a.totp_enabled)
        self.assertTrue(self.portal_a._dash_scope_ok())

    def test_manager_self_service_works_under_deny_rules(self):
        """營造廠主管在拒寫規則下（含未啟用 TOTP 的當下）仍能：啟用 TOTP、改密碼、改語言時區。"""
        user = self._fresh_manager('dash_self_user')
        self.assertFalse(user.totp_enabled)
        env_user = user.with_user(user)
        # 改語言、時區（核心 SELF_WRITEABLE_FIELDS 走 sudo）
        env_user.write({'lang': 'zh_TW', 'tz': 'Asia/Taipei'})
        self.assertEqual((user.lang, user.tz), ('zh_TW', 'Asia/Taipei'))
        self.assertEqual(env_user.read(['lang', 'tz'])[0]['tz'], 'Asia/Taipei')
        # 改密碼＋啟用 TOTP：核心兩者都要求 request（MockRequest）
        with MockRequest(self.env(user=user)) as req:
            req.session['identity-check-last'] = time.time()
            req.session.sid = SESSION_SID   # 核心啟用 TOTP 時用 sid 算 session token
            env_user.change_password(OLD_PASSWORD, NEW_PASSWORD)
            action = env_user.action_totp_enable_wizard()
            wizard = self.env['auth_totp.wizard'].with_user(user).browse(action['res_id'])
            wizard.write({'code': _totp_code(wizard.secret)})
            wizard.enable()
        self.assertTrue(user.totp_enabled, '營造廠主管能自己啟用 TOTP')
        self.assertEqual(self._sheet_count(user), self._sheet_count(self.mgr_a),
                         '啟用後立即看得到資料（規則快取已更新）')
        # 啟用後再改一次語言時區仍可
        env_user.write({'tz': 'UTC'})
        self.assertEqual(user.tz, 'UTC')
        # 業務資料照樣不能寫（拒寫規則沒被繞開）
        with self.assertRaises(AccessError):
            self.docs_a_sheet().with_user(user).write({'notes': '不可寫'})

    # ── session 旗標 ─────────────────────────────────────────────────────
    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_session_flags(self):
        user = self._fresh_manager('dash_sess_user')
        info = self._session_info(user)
        self.assertTrue(info['dash_show_all_allowed_companies'])
        self.assertTrue(info['dash_totp_missing'])
        user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        info = self._session_info(user)
        self.assertTrue(info['dash_show_all_allowed_companies'])
        self.assertFalse(info['dash_totp_missing'])
        for other in (self.sup, self.portal_a, self.console):
            info = self._session_info(other)
            self.assertFalse(info['dash_show_all_allowed_companies'], other.login)
            self.assertFalse(info['dash_totp_missing'], other.login)

    def _session_info(self, user):
        with MockRequest(self.env(user=user)) as req:
            req.session.uid = user.id
            return self.env(user=user)['ir.http'].session_info()

    # ── 重新帶入營造廠歸屬 ──────────────────────────────────────────────
    def test_refill_attribution(self):
        project = self._project('DASH-RF', 'general', [])
        sheet = self.env['daily.log.sheet'].create(self._doc_vals('daily.log.sheet', project))
        self.assertFalse(sheet.contractor_company_id, '前提：工程沒有營造廠，歸屬空白')
        project.write({'contractor_company_ids': [(6, 0, self.co_a.ids)]})
        self.assertFalse(sheet.contractor_company_id, '前提：補了營造廠之後既有單據不會自動補')
        project.with_user(self.sup).action_dash_refill_attribution()
        self.assertEqual(sheet.contractor_company_id, self.co_a)

    def test_refill_attribution_leaves_filled_and_ambiguous(self):
        project = self._project('DASH-RF2', 'general', [(6, 0, (self.co_a | self.co_b).ids)])
        filled = self.env['daily.log.sheet'].create(
            dict(self._doc_vals('daily.log.sheet', project), contractor_company_id=self.co_b.id))
        blank = self.env['daily.log.sheet'].create(self._doc_vals('daily.log.sheet', project))
        self.assertFalse(blank.contractor_company_id)
        project.with_user(self.sup).action_dash_refill_attribution()
        self.assertEqual(filled.contractor_company_id, self.co_b, '已有值的不動')
        self.assertFalse(blank.contractor_company_id, '多家營造廠無法判定 → 仍空白，交監造方指定')

    def test_refill_attribution_supervision_only(self):
        project = self._project('DASH-RF3', 'general', [(6, 0, self.co_a.ids)])
        for user in (self.mgr_a, self.portal_a):
            with self.assertRaises(AccessError):
                project.with_user(user).action_dash_refill_attribution()
