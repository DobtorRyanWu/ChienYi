# -*- coding: utf-8 -*-
"""H1（稽核 M0.5）回歸測試 — 前台唯讀角色不得建立 / 上傳 / 改專案主檔。

背景：前台 create / upload 路由多走 .sudo() 寫入（繞過 ir.rule / ir.model.access），
唯讀的「定期閱覽者」(group_portal_viewer) 仍可 POST 進來寫入 → 越權（H1）。
修法：在 controller 於 _document_check_access 後加 _require_write guard
（viewer 擋、現場人員以上放行）；專案主檔異動加 _require_manage。

驗證策略：以 website.tools.MockRequest 驅動「真實路由方法」+「真實角色群組使用者」，
斷言 viewer 被 AccessError 擋、現場人員/主管通過 guard 決策。純 TransactionCase —
本環境 HttpCase 於替代埠不穩，故用 MockRequest 直接注入 request 上下文。
"""

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

VIEWER = 'construction_supervision_base.group_portal_viewer'   # 定期閱覽者（唯讀）
FIELD = 'construction_supervision_base.group_portal_user'      # 現場人員
LEADER = 'construction_supervision_base.group_portal_leader'   # 主管
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalRoleGuards(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.project = cls.env['project.project'].create({
            'name': 'H1 Guard 測試工程',
            'code': 'H1-GUARD',
            'state': 'construction',  # 非 draft/terminated → 成員可讀
            'company_id': cls.env.company.id,
        })
        cls.observer = cls._mk_user('h1_observer', VIEWER)
        cls.field = cls._mk_user('h1_field', FIELD)
        cls.leader = cls._mk_user('h1_leader', LEADER)
        # 純內部使用者（監造單位員工）：無任何前台角色群組，仍應可寫入（放寬後）
        cls.internal = cls._mk_user('h1_internal', 'base.group_user')
        # 三人皆設為專案參與成員 → 滿足 read ir.rule（member_user_ids in [user.id]）
        for u in (cls.observer, cls.field, cls.leader):
            cls.env['supervision.project.member'].create({
                'project_id': cls.project.id,
                'user_id': u.id,
            })

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })

    # ── 前置健全性：viewer 確實「可讀但不可直接寫」專案 ──────────────
    def test_setup_viewer_can_read_but_not_write_project(self):
        proj = self.project.with_user(self.observer)
        # 可讀（成員 + construction 狀態）
        self.assertTrue(proj.name, 'viewer 應可讀取所屬專案')
        # 直接寫入被 ACL/rule 擋（證明前台 sudo 寫入才是越權破口）
        with self.assertRaises(AccessError):
            proj.write({'name': 'hacked'})

    # ── Part A：guard 決策邏輯（真實群組成員）─────────────────────────
    def _guard_verdict(self, user):
        with MockRequest(self.env(user=user)):
            try:
                self.ctrl._require_write()
                writable = True
            except AccessError:
                writable = False
            can_manage = self.ctrl._can_manage()
        return writable, can_manage

    def test_guard_decision_by_role(self):
        obs_write, obs_manage = self._guard_verdict(self.observer)
        self.assertFalse(obs_write, 'H1：viewer 不應可寫入單據')
        self.assertFalse(obs_manage, 'viewer 不應可管理')

        fld_write, fld_manage = self._guard_verdict(self.field)
        self.assertTrue(fld_write, '現場人員應可寫入單據')
        self.assertFalse(fld_manage, '現場人員不應可管理（審核/建案/改主檔）')

        ldr_write, ldr_manage = self._guard_verdict(self.leader)
        self.assertTrue(ldr_write, '主管應可寫入單據')
        self.assertTrue(ldr_manage, '主管應可管理')

        # 放寬：純內部使用者（無前台角色）應可寫入，但不因此取得「管理」權
        int_write, int_manage = self._guard_verdict(self.internal)
        self.assertTrue(int_write, '內部使用者應可寫入（放寬後）')
        self.assertFalse(int_manage, '純內部使用者不應自動具管理權')

    # ── Part B：真實路由已 wired，viewer 端到端被擋 ──────────────────
    def _call_route(self, user, method_name, **post):
        with MockRequest(self.env(user=user)):
            return getattr(self.ctrl, method_name)(**post)

    def test_observer_blocked_on_real_write_routes(self):
        pid = str(self.project.id)
        cases = [
            ('portal_construction_defect_create', {'project_id': pid}),
            ('portal_construction_daily_log_create', {'project_id': pid}),
            ('portal_construction_inspection_create', {'project_id': pid}),
            ('portal_construction_photo_upload', {'project_id': pid}),
            # 既有漏洞：update 路由原本沒擋 viewer（_is_field_only 對 viewer 回 False）
            ('portal_construction_daily_log_update',
             {'project_id': self.project.id, 'log_id': 0}),
        ]
        for method, kw in cases:
            with self.assertRaises(AccessError,
                                   msg=f'H1：{method} 應擋下 viewer 的寫入'):
                self._call_route(self.observer, method, **kw)

    def test_observer_blocked_on_project_master_edit(self):
        """改工程編號（JSON 路由）viewer 應收到 success=False（非管理者）。"""
        with MockRequest(self.env(user=self.observer)):
            res = self.ctrl.portal_construction_project_code_update(
                self.project.id, code='ZZZ-999')
        self.assertFalse(res.get('success'),
                         'H1：viewer 不應能改工程編號')
        # 現場人員同樣不可（改主檔限老闆/主管）
        with MockRequest(self.env(user=self.field)):
            res2 = self.ctrl.portal_construction_project_code_update(
                self.project.id, code='ZZZ-888')
        self.assertFalse(res2.get('success'),
                         '現場人員不應能改工程編號（限老闆/主管）')


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalRoleGuardsTable(TransactionCase):
    """第 2 批 P5／P6／P7：表驅動，逐路由驗「定期閱覽者被擋、現場人員通過守衛」。

    列舉式測試只證明列到的那幾條，所以守衛要新增就加進 GUARD_TABLE 一列。
    需要真實記錄的路由（刪除照片：記錄不存在會先被導走，守衛根本沒機會跑）
    由 _ctx() 先建好。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        env = cls.env
        cls.project = env['project.project'].create({
            'name': 'P7 表驅動工程', 'code': 'P7-TBL', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.res_project = env['project.project'].create({
            'name': 'P7 表驅動工程（預約式）', 'code': 'P7-TBL-R', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        cls.observer = cls._mk_user('p7_observer', VIEWER)
        cls.field = cls._mk_user('p7_field', FIELD)
        cls.leader = cls._mk_user('p7_leader', LEADER)
        for u in (cls.observer, cls.field, cls.leader):
            for p in (cls.project, cls.res_project):
                env['supervision.project.member'].create({
                    'project_id': p.id, 'user_id': u.id})
        # 施工日誌要有使用中的進度表才建得起來
        cls.schedule = env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()})
        cls.schedule.write({'state': 'active'})
        emp = env['hr.employee'].create({'name': 'p7_emp', 'company_id': env.company.id})
        cls.log = env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id, 'company_id': env.company.id,
            'employee_id': emp.id, 'log_date': fields.Date.today()})
        itype = env['self.inspection.type'].create({'name': 'P7 類型'})
        cls.insp = env['general.self.inspection'].create({
            'project_id': cls.project.id, 'name': 'P7-INSP',
            'inspection_type_id': itype.id, 'sub_project_name': 'P7',
            'inspection_date': fields.Date.today()})
        slip = env['reservation.notification.slip'].create({
            'project_id': cls.res_project.id, 'location': 'P7 地點'})
        slip.sudo().write({'state': 'in_progress'})
        cls.res_insp = env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': itype.id,
            'sub_project_name': 'P7', 'inspection_date': fields.Date.today()})

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])]})

    def _table(self):
        """(標籤, 路由方法, 參數 dict, 通過守衛所需的最低角色 'write'／'manage')"""
        pid = self.project.id
        pid_s = str(self.project.id)
        return [
            # P5：工期展延 GET／POST（老闆／主管）
            ('P5 展延 GET', 'portal_schedule_extend_page', {'project_id': pid}, 'manage'),
            ('P5 展延 POST', 'portal_schedule_extend_submit',
             {'project_id': pid, 'schedule_id': self.schedule.id,
              'current_extension': '1'}, 'manage'),
            # P6：新增專案 GET
            ('P6 新增專案 GET', 'portal_construction_project_new', {}, 'manage'),
            # P7：照片上傳
            ('P7 檢試驗照片', 'portal_construction_test_photo_upload',
             {'project_id': pid, 'test_id': 0}, 'write'),
            ('P7 通報單照片', 'portal_construction_slip_photo_upload',
             {'project_id': pid, 'slip_id': 0}, 'write'),
            # P7：刪除照片（記錄要真的存在）
            ('P7 日誌照片刪除', 'portal_construction_daily_log_photo_delete',
             {'log_id': self.log.id, 'att_id': 0}, 'write'),
            ('P7 檢查照片刪除', 'portal_construction_inspection_photo_delete',
             {'inspection_id': self.insp.id, 'att_id': 0}, 'write'),
            ('P7 預約檢查照片刪除', 'portal_construction_reservation_inspection_photo_delete',
             {'inspection_id': self.res_insp.id, 'att_id': 0}, 'write'),
            # P7：檔案與批次匯入（GET 頁與 POST 都守）
            ('P7 檔案上傳', 'portal_construction_document_upload',
             {'project_id': pid}, 'write'),
            ('P7 日誌匯入 GET', 'portal_construction_daily_logs_import',
             {'project_id': pid}, 'write'),
            ('P7 日誌匯入 POST', 'portal_construction_daily_logs_import_submit',
             {'project_id': pid}, 'write'),
            ('P7 缺失匯入 GET', 'portal_construction_defects_import',
             {'project_id': pid}, 'write'),
            ('P7 缺失匯入 POST', 'portal_construction_defects_import_submit',
             {'project_id': pid}, 'write'),
            ('P7 缺失 docx 匯入 GET', 'portal_construction_defects_import_docx',
             {'project_id': pid}, 'write'),
            ('P7 缺失 docx 匯入 POST', 'portal_construction_defects_import_docx_submit',
             {'project_id': pid}, 'write'),
            ('P7 檢查匯入 GET', 'portal_construction_inspections_import',
             {'project_id': pid}, 'write'),
            ('P7 檢查匯入 POST', 'portal_construction_inspections_import_submit',
             {'project_id': pid}, 'write'),
        ]

    def _call(self, user, method, kw):
        # 建立資料時超級使用者已把值讀進共用快取，不清掉的話前台帳號讀快取會繞過權限檢查
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=user)) as req:
            req.httprequest.files.getlist.return_value = []
            req.render = lambda *a, **k: '<render>'
            return getattr(self.ctrl, method)(**kw)

    def test_observer_blocked_everywhere(self):
        for label, method, kw, _level in self._table():
            with self.assertRaises(AccessError, msg=f'{label}：定期閱覽者應被擋'):
                self._call(self.observer, method, kw)

    def test_field_worker_passes_write_routes_blocked_on_manage_routes(self):
        for label, method, kw, level in self._table():
            if level == 'manage':
                with self.assertRaises(AccessError, msg=f'{label}：現場人員應被擋（限老闆／主管）'):
                    self._call(self.field, method, kw)
            else:
                try:
                    self._call(self.field, method, kw)
                except AccessError as e:
                    self.fail(f'{label}：現場人員不該被擋：{e}')

    def test_leader_passes_every_route(self):
        for label, method, kw, _level in self._table():
            try:
                self._call(self.leader, method, kw)
            except AccessError as e:
                self.fail(f'{label}：主管不該被擋：{e}')

    def test_photo_upload_ajax_json_route(self):
        """json 路由不丟例外，回 success=False／error=access_denied（比照同路由的存取失敗寫法）。"""
        kw = {'project_id': self.project.id, 'photo_data': PNG_B64, 'filename': 'a.png'}
        res = self._call(self.observer, 'portal_construction_photo_upload_ajax', kw)
        self.assertEqual(res, {'success': False, 'error': 'access_denied'},
                         '定期閱覽者不可經 ajax 上傳照片')
        res = self._call(self.field, 'portal_construction_photo_upload_ajax', kw)
        self.assertNotEqual(res.get('error'), 'access_denied', '現場人員應通過守衛')
