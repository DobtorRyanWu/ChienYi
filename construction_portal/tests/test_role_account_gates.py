# -*- coding: utf-8 -*-
"""後台角色帳號（S1，2026-11-10）在前台的危險閘門與唯讀。

角色帳號（營造老闆／營造主管／監造老闆／監造主管）是內部帳號（share=False），沒有前台角色群組。
原本只看 share 或「內部、不是營造方、不是控台讀取」的閘門，會把它們當成監造方後台人員放行——
樣板管理、樣板 docx 上傳（套印引擎 docxtpl 的 Jinja2 沒有沙箱）、已提報缺失的定義欄位、工程師下拉。
這裡逐一驗四種角色帳號都被擋、監造方後台人員（代操作員）照常通過（反證）。
S2（2026-11-11）：手機寫入照同方別、同層級的舊前台帳號（能力矩陣在 construction_company_dashboard tests/test_role_phone.py）；
這裡留下「危險閘門照擋」與「範圍不合格（沒開 TOTP）＝手機什麼都不能寫」兩件事。

群組定義在 construction_company_dashboard；那個模組沒裝時整個類別略過（角色帳號不存在）。
用 website.tools.MockRequest 驅動真實路由方法（同 test_role_guards.py 的做法）。
"""
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import MANAGER_TOTP_SECRET, make_contractor

DASH = 'construction_company_dashboard'
CONTRACTOR_MARKER = f'{DASH}.group_contractor_manager'
ROLE_BOSS = f'{DASH}.group_role_boss'
ROLE_MANAGER = f'{DASH}.group_role_manager'
ROLE_SUPERVISION = f'{DASH}.group_role_supervision'
OPERATOR = 'construction_supervision_base.group_operator'
COMPANY_TYPE_SUPERVISION = 'supervision'
UNLOCK_DENIED = 'no_unlock_permission'


class _Docx:
    filename = 'role.docx'

    def read(self):
        return b'PK fake docx'


@tagged('post_install', '-at_install', 'construction_portal')
class TestRoleAccountGates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if not env.ref(ROLE_BOSS, raise_if_not_found=False):
            raise unittest.SkipTest('construction_company_dashboard 沒裝：沒有後台角色帳號')
        cls.ctrl = ConstructionPortal()
        cls.co_a = make_contractor(env, 'ROLE 前台 營造 A')
        cls.co_s = env['res.company'].create({'name': 'ROLE 前台 監造 S', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.project = cls._project('ROLE-FP', 'general', 'construction')
        cls.p_draft = cls._project('ROLE-FPD', 'general', 'draft')
        cls.r_project = cls._project('ROLE-FPR', 'reservation', 'construction')

        both = cls.co_a | cls.co_s
        cls.cb = cls._user('role_f_cb', [CONTRACTOR_MARKER, ROLE_BOSS], both, scope=cls.co_a)
        cls.cm = cls._user('role_f_cm', [CONTRACTOR_MARKER, ROLE_MANAGER], both, scope=cls.co_a)
        cls.sb = cls._user('role_f_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s)
        cls.sm = cls._user('role_f_sm', [ROLE_SUPERVISION, ROLE_MANAGER], cls.co_s)
        cls.roles = cls.cb | cls.cm | cls.sb | cls.sm
        for user in cls.roles:
            user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})   # 範圍合格（讀得到工程），閘門才擋得到下一層
            for project in (cls.project, cls.p_draft, cls.r_project):
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        # 監造方後台人員（反證用）：代操作員
        cls.operator = cls._user('role_f_operator', ['base.group_user', OPERATOR], cls.co_s)
        # 既有的營造廠主管（只帶營造方標記、沒有層級）：fix1-D 要它照舊出現在工地主任下拉
        cls.contractor_manager = cls._user('role_f_cmgr', [CONTRACTOR_MARKER], both, scope=cls.co_a)

        defect_vals = {'record_type': 'supervision', 'check_type': 'construction',
                       'defect_category': 'workmanship', 'defect_description': 'ROLE 缺失',
                       'defect_location': 'B1', 'source_type': 'daily_check', 'state': 'notified'}
        cls.general_defect = env['general.defect.improvement'].create(dict(defect_vals, project_id=cls.project.id))
        slip = env['reservation.notification.slip'].create({
            'project_id': cls.r_project.id, 'location': 'ROLE 地點', 'slip_no': 1})
        slip.sudo().write({'state': 'in_progress'})
        cls.reservation_defect = env['reservation.defect.improvement'].create(
            dict(defect_vals, project_id=cls.r_project.id, slip_id=slip.id))
        cls.itype = env['self.inspection.type'].create({
            'name': 'ROLE 樣板', 'code': 'ROLE-T', 'project_id': cls.project.id})
        employee = env['hr.employee'].create({'name': 'ROLE 填表人', 'company_id': cls.co_s.id})
        cls.log = env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id, 'company_id': cls.co_s.id,
            'employee_id': employee.id, 'log_date': fields.Date.today()})

    @classmethod
    def _project(cls, code, ptype, state):
        env = cls.env
        project = env['project.project'].create({
            'name': f'{code} 前台角色帳號測試', 'code': code, 'project_type': ptype, 'state': state,
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        return project

    @classmethod
    def _user(cls, login, groups, companies, scope=None):
        vals = {
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
            'company_id': cls.co_s.id, 'company_ids': [(6, 0, companies.ids)],
        }
        if scope:
            vals['dash_scope_company_id'] = scope.id
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    def _as(self, user):
        return MockRequest(self.env(user=user))

    # ── 判定 ─────────────────────────────────────────────────────────
    def test_not_supervision_side_nor_backend_staff(self):
        for user in self.roles:
            self.assertFalse(user.share, f'前提：{user.login} 是內部帳號')
            self.assertFalse(user._is_supervision_side(), user.login)
            self.assertFalse(user._is_backend_staff(), user.login)
        self.assertTrue(self.operator._is_supervision_side(), '反證：代操作員是監造方')

    def test_contractor_judgments_split(self):
        """受限（要過 ir.rule）的判斷四種都算；「營造方」的判斷只算營造方角色帳號（S1 只驗判斷函式本身）。"""
        for user in self.roles:
            with self._as(user):
                self.assertTrue(self.ctrl._dash_is_restricted(), f'{user.login}：前台讀取要以本人身分再過一次範圍規則')
                self.assertFalse(hasattr(self.ctrl, '_dash_is_contractor'), '舊名（意思顛倒）已刪除')
                contractor = user in (self.cb | self.cm)
                self.assertEqual(self.ctrl._dash_is_contractor_or_console(), contractor, user.login)
                if contractor:
                    with self.assertRaises(AccessError, msg=user.login):
                        self.ctrl._require_not_contractor()
                else:
                    self.ctrl._require_not_contractor()   # 監造方角色帳號不能被當成營造方擋下

    # ── 樣板管理與 docx 上傳 ──────────────────────────────────────────
    def test_cannot_manage_inspection_types(self):
        for user in self.roles:
            with self._as(user):
                self.assertFalse(self.ctrl._can_manage_inspection_types(), user.login)
        with self._as(self.operator):
            self.assertTrue(self.ctrl._can_manage_inspection_types(), '反證：代操作員可以管理樣板')

    def _save_with_upload(self, user):
        with self._as(user) as req:
            req.httprequest.files = MultiDict([('template_file', _Docx())])
            return self.ctrl.portal_inspection_type_save(type_id=str(self.itype.id), name=self.itype.name)

    def test_docx_upload_rejected_even_past_manage_guard(self):
        """把前一道「樣板管理」守衛拿掉（模擬它失效），docx 上傳那一道自己也要擋得住角色帳號（L2⑥：防線互相遮蔽）。"""
        with patch.object(ConstructionPortal, '_require_manage_inspection_types', lambda self: None):
            for user in self.roles:
                with self.assertRaises(AccessError, msg=user.login):
                    self._save_with_upload(user)
                self.assertFalse(self.itype.template_file, f'{user.login} 不可換掉樣板 docx')
            self._save_with_upload(self.operator)   # 反證：同一個 patch 下代操作員上傳得進去
        self.assertEqual(self.itype.template_filename, _Docx.filename)

    # ── 工程師下拉 ───────────────────────────────────────────────────
    def test_engineer_dropdown_excludes_role_accounts(self):
        captured = []
        with self._as(self.operator) as req:
            # 路由包裝要求回傳值是回應：記下 qcontext、回空字串
            req.render = lambda template, values=None, **kw: captured.append(values) or ''
            self.ctrl.portal_construction_project_edit(project_id=self.p_draft.id)
        self.assertEqual(len(captured), 1, '前提：編輯頁有渲染（草稿工程、代操作員讀得到）')
        values = captured[0]
        for key in ('all_users', 'supervision_users'):
            self.assertIn(self.operator, values[key], f'反證：{key} 列出代操作員')
        # 監造工程師下拉：只列監造方後台人員
        self.assertFalse(values['supervision_users'] & (self.roles | self.contractor_manager), '監造工程師下拉')
        # 工地主任、活動負責人等其他下拉（all_users）：照 S1 之前（所有內部帳號），既有營造廠主管要在（fix1-D）
        self.assertIn(self.contractor_manager, values['all_users'], '工地主任下拉照舊列出營造廠主管')

    def test_project_edit_page_requires_manage(self):
        """工程資訊編輯頁 GET 與存檔 POST 用同一把尺（fix1-F、fix3-T；S2 起照同方別同層級的舊前台帳號）。

        監造老闆：有管理權、不是營造方 → 打得開（舊前台監造老闆也打得開）；營造方：被「營造方不能改」擋下；
        主管讀不到未開始的工程（先被導回）。
        """
        for user in self.roles:
            rendered = []
            with self._as(user) as req:
                req.render = lambda template, values=None, **kw: rendered.append(template) or ''
                try:
                    self.ctrl.portal_construction_project_edit(project_id=self.p_draft.id)
                except AccessError as exc:
                    self.assertIn(user, self.cb | self.cm, f'{user.login}：只有營造方被擋')
                    self.assertIn('營造廠帳號不能修改', str(exc))
            self.assertEqual(bool(rendered), user == self.sb, f'{user.login}：編輯頁')

    # ── 已提報缺失的定義欄位鎖 ────────────────────────────────────────
    def test_defect_definition_lock(self):
        for defect in (self.general_defect, self.reservation_defect):
            self.assertNotEqual(defect.state, 'draft', '前提：缺失已離開草稿')
            for user in self.roles:
                with self.assertRaises(UserError, msg=f'{user.login} × {defect._name}'):
                    defect.with_user(user).sudo().write({'defect_description': 'ROLE 改寫'})
            self.assertEqual(defect.defect_description, 'ROLE 缺失')
            defect.with_user(self.operator).sudo().write({'defect_description': 'ROLE 監造方改寫'})
            self.assertEqual(defect.defect_description, 'ROLE 監造方改寫', '反證：監造方後台人員照常可改')

    # ── 手機寫入：S2 起照層級（範圍合格）；沒開 TOTP 一律拒 ─────────────────────
    def test_phone_write_guards_follow_level(self):
        """S2：角色帳號（範圍合格）過得了寫入守衛；解鎖日誌限監造方（營造方照擋）。"""
        pid = self.project.id
        for user in self.roles:
            with self._as(user):
                self.assertTrue(self.ctrl._document_check_access('project.project', pid), '前提：讀得到工程')
                self.ctrl._require_write()
                self.assertTrue(self.ctrl._can_manage(), f'{user.login}：老闆／主管有管理權')
                response = self.ctrl.portal_construction_daily_log_unlock(project_id=pid, log_id=self.log.id)
            contractor = user in (self.cb | self.cm)
            self.assertEqual(UNLOCK_DENIED in response.location, contractor, f'{user.login}：解鎖限監造方')
        with self._as(self.operator):
            self.ctrl._require_write()   # 反證：監造方後台人員通過寫入守衛

    # S2 fix2-Z：驗「強制兩步驟驗證時」（construction_company_dashboard 的 DASH_REQUIRE_TOTP 預設 False）
    @patch('odoo.addons.construction_company_dashboard.models.res_users_guard.DASH_REQUIRE_TOTP', True)
    def test_phone_write_routes_rejected_without_totp(self):
        """範圍不合格（沒開 TOTP）的角色帳號：手機寫入路由一律拒（S1 的唯讀保證，S2 縮成這個情境）。"""
        pid = self.project.id
        cases = [
            ('portal_construction_defect_create', {'project_id': str(pid)}),
            ('portal_construction_daily_log_create', {'project_id': str(pid)}),
            ('portal_construction_inspection_create', {'project_id': str(pid)}),
            ('portal_construction_photo_upload', {'project_id': str(pid)}),
            ('portal_construction_project_create', {'name': 'ROLE 沒開 TOTP 建的工程'}),
        ]
        for user in self.roles:
            user.sudo().write({'totp_secret': False})
            self.env.registry.clear_cache()
            with self._as(user):
                with self.assertRaises(AccessError, msg=f'{user.login}：_require_write'):
                    self.ctrl._require_write()
            for method, kw in cases:
                with self._as(user):
                    try:
                        response = getattr(self.ctrl, method)(**kw)
                    except AccessError:
                        continue
                self.assertIn('/my', response.location, f'{user.login} × {method}：讀不到工程就導回，不能寫')
            self.assertFalse(self.env['project.project'].search_count([('name', '=', 'ROLE 沒開 TOTP 建的工程')]))


@tagged('post_install', '-at_install', 'construction_portal')
class TestProjectEditButtonHttp(HttpCase):
    """fix2-O：工程資訊頁的「編輯」按鈕與編輯頁 GET 同一把尺（有管理權、而且不是營造方／控台讀取）。

    沒有管理權的既有內部監造人員：fix1 之後 GET 編輯頁從「打得開但存不了」變成 403，按鈕也一起藏起來。
    """

    PASSWORD = 'Role-edit-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if not env.ref(ROLE_BOSS, raise_if_not_found=False):
            raise unittest.SkipTest('construction_company_dashboard 沒裝：沒有後台角色帳號')
        cls.co_a = make_contractor(env, 'ROLE 編輯鈕 營造 A')
        cls.co_s = env['res.company'].create({'name': 'ROLE 編輯鈕 監造 S', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.project = env['project.project'].create({
            'name': 'ROLE-EB 編輯鈕測試', 'code': 'ROLE-EB', 'project_type': 'general', 'state': 'draft',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups):
            return Users.create({'name': login, 'login': login, 'password': cls.PASSWORD,
                                 'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                                 'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.sb = user('role_eb_sb', [ROLE_SUPERVISION, ROLE_BOSS])
        cls.sb.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        cls.staff = user('role_eb_staff', ['base.group_user', 'construction_supervision_base.group_supervisor_admin'])
        cls.operator = user('role_eb_operator', ['base.group_user', OPERATOR])

    def _login(self, user):
        # 已啟用 TOTP 的帳號：核心對非互動式登入只收 API 金鑰；HttpCase.authenticate 是非互動式，測試裡當互動式登入
        with patch.object(type(self.env['res.users']), '_rpc_api_keys_only', lambda self: False):
            self.authenticate(user.login, self.PASSWORD)

    def test_edit_button_matches_edit_page(self):
        edit_url = f'/construction/{self.project.id}/edit'
        # S2：監造老闆角色帳號照舊前台監造老闆（可以編輯）；沒有管理權的監造人員照舊不行
        for user, can_edit in ((self.sb, True), (self.staff, False), (self.operator, True)):
            self._login(user)
            page = self.url_open(f'/construction/{self.project.id}/info')
            self.assertEqual(page.status_code, 200, f'{user.login}：工程資訊頁打得開')
            self.assertEqual(edit_url in page.text, can_edit, f'{user.login}：編輯按鈕')
            status = self.url_open(edit_url).status_code
            self.assertEqual(status == 200, can_edit, f'{user.login}：編輯頁 GET（{status}）')

    def test_role_account_hides_entries_backend_denies(self):
        """r5 N1（2026-11-11）：入口顯示＝後端放行（真 HTTP）。

        * 水位監測：S2 起監造方角色帳號照舊前台監造帳號看得到（唯讀）——入口在、頁面 200。
        * 意見回饋：S2 fix2-W（使用者 11-11）起範圍合格的監造方角色帳號照舊前台監造帳號看得到（建單路由以 sudo 建本人的單）。
        * /my：角色帳號的 /my 首頁 S2 起跟前台帳號一樣是工程清單，沒有文件、試算表卡。
        監造方後台人員照常看得到（反證：證明這支測試看得到入口，不是頁面本來就沒有）。
        """
        water_url = f'/construction/{self.project.id}/water-level'
        docs_installed = bool(self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'dobtor_doc_editor'), ('state', '=', 'installed')]))
        for user, water, feedback, others in ((self.sb, True, True, False), (self.staff, True, True, True)):
            self._login(user)
            page = self.url_open(f'/construction/{self.project.id}/info')
            self.assertEqual(page.status_code, 200, f'{user.login}：工程資訊頁打得開')
            self.assertEqual(water_url in page.text, water, f'{user.login}：水位監測入口')
            self.assertEqual(self.url_open(water_url).status_code, 200, f'{user.login}：水位監測頁')
            self.assertEqual('意見回饋' in page.text, feedback, f'{user.login}：意見回饋入口')
            if docs_installed:
                home = self.url_open('/my')
                self.assertEqual(home.status_code, 200, f'{user.login}：/my 打得開')
                self.assertEqual('/my/documents' in home.text, others, f'{user.login}：/my 文件卡')
