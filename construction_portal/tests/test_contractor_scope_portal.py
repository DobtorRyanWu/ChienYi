# -*- coding: utf-8 -*-
"""前台路由的營造方範圍與寫入矩陣（公司儀表板合約 §3.6，線 A2）。

前台 controller 大量用 sudo 列出、取出、寫入營造廠層級紀錄，sudo 不走 ir.rule，營造廠範圍規則
（construction_company_dashboard/models/rule_scope.py）就被繞過。這裡逐條驗：

* 共用工程 P（營造廠 A＋B）、預約式共用工程 R（A＋B）、只有 B 的工程 PB；單據 A、B 各一份。
* A 的前台帳號（老闆／主管／現場／閱覽）讀不到、改不到、刪不到 B 的；營造廠主管（後台唯讀）前台寫入全被拒；
* 寫入矩陣（缺失驗證結案、工程主檔、工程編號、工期展延、通報單確認結案、自主檢查結案）營造方被拒、監造方可以；
  自主檢查「確認」營造方可以（限自家）；
* 監造方前台與後台帳號原本能做的照樣能做；範圍公司空白的營造方前台帳號：清單是空的、不報錯；
* rule_scope 線 A2 加的白名單（三個工程層級、九個營造廠層級子表）：A 只看得到自家、監造方兩家都看得到。

斷言打在使用者看得到的結果：被拒（AccessError＋訊息）、導回哪裡、看得到哪幾筆、資料有沒有被改。
"""
import base64
from datetime import timedelta
from unittest import SkipTest
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import NotFound

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    MANAGER_TOTP_SECRET, SUPERVISION_USER_VALS, contractor_project_vals, contractor_user_vals,
    make_contractor)

MANAGER_GROUP = 'construction_company_dashboard.group_contractor_manager'
BOSS = 'construction_supervision_base.group_portal_subscriber'
LEADER = 'construction_supervision_base.group_portal_leader'
FIELD = 'construction_supervision_base.group_portal_user'
VIEWER = 'construction_supervision_base.group_portal_viewer'
OPERATOR = 'construction_supervision_base.group_operator'
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
# 日誌超過這麼多天就鎖定（construction_daily_log：LOCK_DAYS = 14），測試用更舊的日期
LOCKED_LOG_AGE_DAYS = 20
# 地圖測試照片的座標（台北附近；只要不是 0）
LAT, LNG = 25.03, 121.56
DENIED_MSG = '營造廠帳號不能'
PARSER = 'odoo.addons.construction_portal.utils.'


@tagged('post_install', '-at_install', 'construction_portal')
class TestContractorScopePortal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if not env.ref(MANAGER_GROUP, raise_if_not_found=False):
            # 營造方範圍規則與營造廠主管群組在 construction_company_dashboard；沒裝就沒有可驗的東西
            raise SkipTest('construction_company_dashboard 沒裝：營造方範圍測試不能跑（不是通過）')
        cls.ctrl = ConstructionPortal()
        cls.sup_company = env.company
        cls.co_a = make_contractor(env, 'A2 營造 A')
        cls.co_b = make_contractor(env, 'A2 營造 B')
        both = cls.co_a | cls.co_b
        cls.p = cls._project('A2-P', 'general', both)
        cls.r = cls._project('A2-R', 'reservation', both)
        cls.pb = cls._project('A2-PB', 'general', cls.co_b)
        cls.projects = cls.p | cls.r | cls.pb

        # 帳號：A 的前台四個角色、B 的前台現場、範圍空白的營造方前台、A 的營造廠主管（後台）、監造方前台主管、
        # 監造方後台員工、監造方代操
        cls.boss_a = cls._user('a2_boss_a', [BOSS], contractor_user_vals(cls.co_a))
        cls.leader_a = cls._user('a2_leader_a', [LEADER], contractor_user_vals(cls.co_a))
        cls.field_a = cls._user('a2_field_a', [FIELD], contractor_user_vals(cls.co_a))
        cls.observer_a = cls._user('a2_observer_a', [VIEWER], contractor_user_vals(cls.co_a))
        cls.field_b = cls._user('a2_field_b', [FIELD], contractor_user_vals(cls.co_b))
        cls.blank = cls._user('a2_blank', [LEADER], {'is_contractor_org': True})
        cls.mgr_a = cls._user('a2_mgr_a', [MANAGER_GROUP], {'dash_scope_company_id': cls.co_a.id},
                              companies=cls.sup_company | cls.co_a)
        # 夾具：營造廠主管要啟用兩步驟驗證才看得到資料（合約 §0b-8）。沒啟用時進不了工程、
        # 路由在讀取那一步就導回，測不到寫入守衛（整合後 14 支紅的原因）；期望值不變
        cls.mgr_a.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
        cls.sup_leader = cls._user('a2_sup_leader', [LEADER], SUPERVISION_USER_VALS)
        cls.sup_internal = cls._user('a2_sup_internal', ['base.group_user'], {})
        cls.sup_operator = cls._user('a2_sup_operator', ['base.group_user', OPERATOR], {})
        for user in (cls.leader_a, cls.field_a, cls.observer_a, cls.field_b, cls.blank, cls.sup_leader):
            for project in cls.projects:
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})

        cls.emp = env['hr.employee'].create({'name': 'A2 填表人', 'company_id': cls.sup_company.id})
        cls.itype = env['self.inspection.type'].create({'name': 'A2 檢查類型'})
        cls.block = env['self.inspection.type.measure'].create({
            'type_id': cls.itype.id, 'name': 'A2 量測', 'template': '丈量___位置'})
        cls.today = fields.Date.today()
        cls._day = 0
        cls._slip_no = 0

        # 單據：A、B 各一份（歸屬明寫，不靠自動帶入）
        cls.log_a, cls.log_b = cls._log(cls.co_a), cls._log(cls.co_b)
        cls.photo_a, cls.photo_b = cls._photo(cls.co_a, cls.log_a), cls._photo(cls.co_b, cls.log_b)
        cls.def_a = cls._defect(cls.co_a, 'QA-A-001', 'A2 A 的缺失')
        cls.def_b = cls._defect(cls.co_b, 'QA-B-001', 'A2 B 的缺失')
        cls.insp_a, cls.insp_b = cls._inspection(cls.co_a), cls._inspection(cls.co_b)
        cls.res_insp_a, cls.res_insp_b = cls._res_inspection(cls.co_a), cls._res_inspection(cls.co_b)

    # ── 資料工廠 ────────────────────────────────────────────────────────
    @classmethod
    def _project(cls, code, ptype, contractors):
        project = cls.env['project.project'].create({
            'name': f'{code} 前台範圍測試工程', 'code': code, 'project_type': ptype,
            'state': 'construction', 'company_id': cls.env.company.id,
            **contractor_project_vals(contractors)})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        return project

    @classmethod
    def _user(cls, login, groups, side_vals, companies=None):
        vals = {'name': login, 'login': login,
                'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])], **side_vals}
        if companies:
            vals.update(company_id=cls.env.company.id, company_ids=[(6, 0, companies.ids)])
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    @classmethod
    def _log(cls, company, project=None, days_ago=None):
        if days_ago is None:
            cls._day += 1
            days_ago = cls._day
        return cls.env['daily.log.sheet'].create({
            'supervision_project_id': (project or cls.p).id, 'company_id': cls.env.company.id,
            'employee_id': cls.emp.id, 'log_date': cls.today - timedelta(days=days_ago),
            'contractor_company_id': company.id})

    @classmethod
    def _photo(cls, company, log=None, **extra):
        att = cls.env['ir.attachment'].create({
            'name': 'a2.png', 'datas': PNG_B64, 'mimetype': 'image/png', 'public': False,
            'res_model': 'supervision.photo'})
        vals = {'project_id': cls.p.id, 'attachment_id': att.id, 'contractor_company_id': company.id,
                'latitude': LAT, 'longitude': LNG, **extra}
        if log:
            vals['daily_log_id'] = log.id
        return cls.env['supervision.photo'].create(vals)

    @classmethod
    def _defect(cls, company, reg, desc, state='notified'):
        return cls.env['general.defect.improvement'].create({
            'project_id': cls.p.id, 'record_type': 'contractor', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': desc, 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': state, 'source_description': reg,
            'found_date': cls.today - timedelta(days=3), 'contractor_company_id': company.id})

    @classmethod
    def _inspection(cls, company, location='A2 L1'):
        insp = cls.env['general.self.inspection'].create({
            'project_id': cls.p.id, 'name': 'A2-INSP', 'inspection_type_id': cls.itype.id,
            'sub_project_name': 'A2', 'inspection_date': cls.today, 'inspection_location': location,
            'contractor_company_id': company.id})
        cls.env['general.self.inspection.item'].create({'inspection_id': insp.id, 'check_item': 'A2 項目'})
        return insp

    @classmethod
    def _slip(cls):
        cls._slip_no += 1
        slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.r.id, 'location': 'A2 地點', 'slip_no': cls._slip_no})
        task = cls.env['project.task'].create({'name': 'A2 契約工項', 'project_id': cls.r.id})
        cls.env['reservation.notification.slip.line'].create({
            'slip_id': slip.id, 'task_id': task.id, 'item_no': '1', 'unit': '式'})
        return slip

    @classmethod
    def _res_inspection(cls, company):
        slip = cls._slip()
        slip.sudo().write({'state': 'in_progress'})
        return cls.env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': cls.itype.id, 'sub_project_name': 'A2',
            'inspection_date': cls.today, 'contractor_company_id': company.id})

    # ── 驅動真實路由 ────────────────────────────────────────────────────
    def _call(self, user, method, *args, files=None, args_qs=None, patches=(), before=None, render=False, **kw):
        """以 user 身分跑真實路由。回傳 (render 的 values, Location 或 json 回傳值, session)。

        render=True：路由 render 時把模板真的渲染，第二個值改回傳 HTML（同一個請求裡渲染，與實際相同）。
        before：路由執行前在同一個請求裡先跑（例：先用 sudo 讀一次欄位，驗快取不會帶過去）。
        """
        self.env.flush_all()
        self.env.invalidate_all()
        seen = {}
        env = self.env(user=user)
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = files or []
            req.httprequest.args = args_qs or {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            for p in patches:
                p.start()
            try:
                if before:
                    before()
                res = method(*args, **kw)
                if render and 'tpl' in seen:
                    html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
                    seen['html'] = html.decode() if isinstance(html, bytes) else str(html)
            finally:
                for p in patches:
                    p.stop()
            session = dict(req.session)
        if 'tpl' in seen:
            return seen['vals'], seen.get('html'), session
        if hasattr(res, 'headers'):
            return None, res.headers.get('Location', ''), session
        return None, res, session

    def _location(self, user, method, *args, **kw):
        return self._call(user, method, *args, **kw)[1]

    def _assert_denied(self, user, method, *args, **kw):
        with self.assertRaises(AccessError, msg=f'{user.login}：{method.__name__} 應被拒') as ctx:
            self._call(user, method, *args, **kw)
        return str(ctx.exception)

    @staticmethod
    def _upload(name='a2.bin'):
        upload = MagicMock(filename=name, mimetype='image/png')
        upload.read.return_value = b'a2'
        return upload

    def _domain_ids(self, user, model='project.project'):
        with MockRequest(self.env(user=user)):
            domain = self.env[model].with_user(user)._get_portal_projects_domain(user.partner_id)
        return set(self.env[model].sudo().search(domain + [('id', 'in', self.projects.ids)]).ids)

    # ═══ 工程清單：_get_portal_projects_domain／_user_can_see_project ══════════
    def test_project_domain_contractor_scope(self):
        """營造方：依角色的條件 AND 工程營造廠含範圍公司；PB（只有 B）A 看不到，B 看得到。"""
        a_projects = set((self.p | self.r).ids)
        self.assertEqual(self._domain_ids(self.boss_a), a_projects, '老闆原本看全庫，現在只看 A 承攬的')
        self.assertEqual(self._domain_ids(self.field_a), a_projects, '成員也要 AND 營造廠範圍')
        self.assertEqual(self._domain_ids(self.mgr_a), a_projects, '營造廠主管（後台）同樣只看 A 承攬的')
        self.assertEqual(self._domain_ids(self.field_b), set(self.projects.ids), 'B 承攬三個都看得到')
        with MockRequest(self.env(user=self.field_a)):
            self.assertFalse(self.ctrl._user_can_see_project(self.pb))
            self.assertTrue(self.ctrl._user_can_see_project(self.p))

    def test_project_domain_supervision_unchanged(self):
        """監造方：與原本依角色的條件完全相同（後台員工、前台主管）。"""
        for user in (self.sup_internal, self.sup_leader, self.sup_operator):
            Project = self.env['project.project'].with_user(user)
            with MockRequest(self.env(user=user)):
                self.assertEqual(Project._get_portal_projects_domain(user.partner_id),
                                 Project._get_portal_projects_domain_by_role(user), user.login)
        self.assertEqual(self._domain_ids(self.sup_leader), set(self.projects.ids))

    def test_blank_scope_sees_empty_list_without_error(self):
        """範圍公司空白的營造方前台帳號：清單是空的、不報錯；進工程被導回。
        含一個沒填承攬廠商的工程（dev 有 247 個這種工程）：範圍空白也不可因此看得到。"""
        no_contractor = self.env['project.project'].create({
            'name': 'A2 沒填營造廠的工程', 'code': 'A2-NONE', 'state': 'construction',
            'company_id': self.env.company.id})
        self.env['supervision.project.member'].create({'project_id': no_contractor.id, 'user_id': self.blank.id})
        self.projects |= no_contractor
        self.assertEqual(self._domain_ids(self.blank), set())
        vals, _loc, _s = self._call(self.blank, self.ctrl.portal_my_construction_projects, view='list')
        self.assertIsNotNone(vals, '應渲染列表頁（空狀態），不是報錯或導走')
        self.assertFalse(vals['projects'])
        self.assertEqual(self._location(self.blank, self.ctrl.portal_construction_project_detail, self.p.id),
                         '/my')

    # ═══ 取圖、照片列表與地圖 API ══════════════════════════════════════════
    def test_photo_serve_only_own(self):
        with MockRequest(self.env(user=self.field_a)):
            self.assertIsNotNone(self.ctrl.portal_construction_photo_serve(self.photo_a.attachment_id.id))
            with self.assertRaises(NotFound, msg='A 不可取得 B 的照片'):
                self.ctrl.portal_construction_photo_serve(self.photo_b.attachment_id.id)
        with MockRequest(self.env(user=self.sup_leader)):
            for photo in (self.photo_a, self.photo_b):
                self.assertIsNotNone(self.ctrl.portal_construction_photo_serve(photo.attachment_id.id))

    def test_photo_map_api_only_own(self):
        def marker_ids(user):
            _v, res, _s = self._call(user, self.ctrl.portal_photos_map_markers, self.p.id)
            return {m['id'] for m in res['markers']}, res['total']

        def area_ids(user):
            bounds = {'north': LAT + 1, 'south': LAT - 1, 'east': LNG + 1, 'west': LNG - 1}
            _v, res, _s = self._call(user, self.ctrl.portal_photos_map_area, self.p.id, bounds=bounds)
            return {p['id'] for p in res['photos']}, res['total']

        self.assertEqual(marker_ids(self.field_a), ({self.photo_a.id}, 1))
        self.assertEqual(marker_ids(self.sup_leader), ({self.photo_a.id, self.photo_b.id}, 2))
        self.assertEqual(area_ids(self.field_a), ({self.photo_a.id}, 1))
        self.assertEqual(area_ids(self.sup_leader), ({self.photo_a.id, self.photo_b.id}, 2))
        vals_a, _l, _s = self._call(self.field_a, self.ctrl.portal_construction_photos_map, self.p.id)
        vals_s, _l, _s = self._call(self.sup_leader, self.ctrl.portal_construction_photos_map, self.p.id)
        self.assertEqual((vals_a['total_photos'], vals_a['gps_photos']), (1, 1))
        self.assertEqual((vals_s['total_photos'], vals_s['gps_photos']), (2, 2))

    def test_photo_grid_signboard_only_own(self):
        sb_a = self._photo(self.co_a, signboard_project_id=self.p.id)
        sb_b = self._photo(self.co_b, signboard_project_id=self.p.id)

        def img(photo):
            return '/construction/img/%d"' % photo.attachment_id.id

        def page(user):
            # 真的渲染模板（模板讀 project.signboard_photo_ids）；路由前先用 sudo 讀一次，驗快取不會帶過去
            vals, html, _s = self._call(user, self.ctrl.portal_construction_photos, self.p.id, render=True,
                                        before=lambda: self.p.sudo().signboard_photo_ids.ids)
            return vals, html

        vals, html = page(self.field_a)
        self.assertIn(img(sb_a), html)
        self.assertNotIn(img(sb_b), html, 'A 的告示牌照片區不可出現 B 的照片')
        self.assertEqual(set(vals['photos'].ids), {self.photo_a.id, sb_a.id}, '照片列表只列自家的')
        _v, html = page(self.sup_leader)
        self.assertIn(img(sb_a), html)
        self.assertIn(img(sb_b), html, '監造方兩家的告示牌照片都看得到')

    # ═══ 文件下載與列表 ═════════════════════════════════════════════════════
    def test_documents_only_own_sources(self):
        Att = self.env['ir.attachment']

        def doc(name, **vals):
            return Att.create({'name': name, 'datas': PNG_B64, 'mimetype': 'application/pdf',
                               'supervision_project_id': self.p.id, 'public': False, **vals})
        att_a = doc('A 日誌附件.pdf', res_model='daily.log.sheet', res_id=self.log_a.id)
        att_b = doc('B 日誌附件.pdf', res_model='daily.log.sheet', res_id=self.log_b.id)
        att_p = doc('工程文件.pdf')
        with MockRequest(self.env(user=self.field_a)):
            self.assertIsNotNone(self.ctrl.portal_construction_document_serve(att_a.id))
            self.assertIsNotNone(self.ctrl.portal_construction_document_serve(att_p.id))
            with self.assertRaises(NotFound, msg='A 不可下載 B 日誌上的附件'):
                self.ctrl.portal_construction_document_serve(att_b.id)
        ours = att_a | att_b | att_p
        vals_a, _l, _s = self._call(self.field_a, self.ctrl.portal_construction_documents, self.p.id)
        vals_s, _l, _s = self._call(self.sup_leader, self.ctrl.portal_construction_documents, self.p.id)
        self.assertEqual(set(vals_a['attachments'].ids) & set(ours.ids), {att_a.id, att_p.id})
        self.assertEqual(set(vals_s['attachments'].ids) & set(ours.ids), set(ours.ids))

    # ═══ 預約式檢查檢視與照片 ═══════════════════════════════════════════════
    def test_reservation_inspection_detail_only_own(self):
        method = self.ctrl.portal_construction_reservation_inspection_detail
        self.assertEqual(self._location(self.field_a, method, self.res_insp_b.id), '/my', 'A 不可看 B 的檢查')
        vals, _l, _s = self._call(self.field_a, method, self.res_insp_a.id)
        self.assertEqual(vals['inspection'], self.res_insp_a)
        vals, _l, _s = self._call(self.sup_leader, method, self.res_insp_b.id)
        self.assertEqual(vals['inspection'], self.res_insp_b, '監造方照常看得到')

    def test_reservation_inspection_photo_upload_delete_not_others(self):
        photo = self._photo(self.co_b, reservation_inspection_id=self.res_insp_b.id)
        before = self.res_insp_b.photo_ids
        loc = self._location(self.leader_a, self.ctrl.portal_construction_reservation_inspection_photo_upload,
                             self.res_insp_b.id, files=[self._upload()])
        self.assertEqual(loc, '/my')
        self.assertEqual(self.res_insp_b.photo_ids, before, 'A 不可在 B 的檢查加照片')
        loc = self._location(self.leader_a, self.ctrl.portal_construction_reservation_inspection_photo_delete,
                             self.res_insp_b.id, photo.attachment_id.id)
        self.assertEqual(loc, '/my')
        self.assertTrue(photo.exists(), 'A 不可刪 B 檢查上的照片')
        loc = self._location(self.sup_leader, self.ctrl.portal_construction_reservation_inspection_photo_delete,
                             self.res_insp_b.id, photo.attachment_id.id)
        self.assertIn('message=photo_deleted', loc)
        self.assertFalse(photo.exists(), '監造方主管照常刪得掉')

    def test_reservation_inspection_create_under_slip_is_own(self):
        """在通報單底下建自主檢查：建出來歸 A，B 看不到。"""
        slip = self._slip()
        slip.sudo().write({'state': 'in_progress'})
        loc = self._location(self.field_a, self.ctrl.portal_construction_reservation_inspection_create,
                             slip_id=str(slip.id), inspection_type_id=str(self.itype.id))
        new = self.env['reservation.self.inspection'].search([('slip_id', '=', slip.id)])
        self.assertEqual(len(new), 1, loc)
        self.assertEqual(new.contractor_company_id, self.co_a)
        self.assertEqual(self._location(self.field_b, self.ctrl.portal_construction_reservation_inspection_detail,
                                        new.id), '/my', 'B 看不到 A 建的檢查')

    # ═══ 日誌：材料累計、編輯、照片、解鎖、匯入 ═════════════════════════════
    def test_material_cumulative_only_own(self):
        item = self.env['construction.contract.material'].create({
            'project_id': self.p.id, 'code': 'A2M', 'name': 'A2 預拌混凝土', 'unit': 'M3',
            'contract_qty': 500.0, 'is_key': True})
        log_b = self._log(self.co_b, days_ago=10)
        log_a = self._log(self.co_a, days_ago=5)
        for log, qty in ((log_a, 3.0), (log_b, 5.0)):
            log.material_ids.filtered(lambda m: m.catalog_item_id == item).write({'daily_qty': qty})
        row_a = log_a.material_ids.filtered(lambda m: m.catalog_item_id == item)
        self.assertEqual(row_a.cumulative_qty, 8.0, '前提：存的累計含 B 較早的 5')

        def form_total(user, method, *args):
            vals, _l, _s = self._call(user, method, *args)
            return [m.cumulative_qty for m in vals['form_materials'] if m.name == item.name]

        self.assertEqual(form_total(self.leader_a, self.ctrl.portal_construction_daily_log_new, self.p.id), [3.0])
        self.assertEqual(form_total(self.sup_leader, self.ctrl.portal_construction_daily_log_new, self.p.id), [8.0])
        self.assertEqual(form_total(self.leader_a, self.ctrl.portal_construction_daily_log_edit,
                                    self.p.id, log_a.id), [3.0], '編輯頁同一套：只算自家')
        for user in (self.leader_a, self.mgr_a):
            # 後台營造廠主管沒有材料列的讀取權：累計用日誌判定範圍，頁面照樣開得起來
            vals, _l, _s = self._call(user, self.ctrl.portal_construction_daily_log_detail, self.p.id, log_a.id)
            self.assertEqual([m.cumulative_qty for m in vals['log_materials'] if m.name == item.name], [3.0],
                             user.login)
        vals, _l, _s = self._call(self.sup_leader, self.ctrl.portal_construction_daily_log_detail,
                                  self.p.id, log_a.id)
        self.assertEqual([m.cumulative_qty for m in vals['log_materials'] if m.name == item.name], [8.0],
                         '監造方照舊顯示存的累計')

    def test_daily_log_update_not_others(self):
        method = self.ctrl.portal_construction_daily_log_update
        loc = self._location(self.leader_a, method, self.p.id, self.log_b.id, work_summary='A 改 B')
        self.assertEqual(loc, f'/construction/{self.p.id}/daily-logs', '看不到就當作不存在')
        self.assertNotEqual(self.log_b.work_summary, 'A 改 B')
        loc = self._location(self.leader_a, method, self.p.id, self.log_a.id, work_summary='A 改自己')
        self.assertIn('message=updated', loc)
        self.assertEqual(self.log_a.work_summary, 'A 改自己')

    def test_daily_log_photo_upload_delete_not_others(self):
        before = self.log_b.photo_ids
        loc = self._location(self.leader_a, self.ctrl.portal_construction_daily_log_photo_upload,
                             self.log_b.id, files=[self._upload()])
        self.assertEqual(loc, '/my')
        self.assertEqual(self.log_b.photo_ids, before, 'A 不可在 B 的日誌加照片')
        loc = self._location(self.boss_a, self.ctrl.portal_construction_daily_log_photo_delete,
                             self.log_b.id, self.photo_b.attachment_id.id)
        self.assertEqual(loc, '/my')
        self.assertTrue(self.photo_b.exists(), 'A 的老闆不可刪 B 日誌上的照片')
        loc = self._location(self.sup_leader, self.ctrl.portal_construction_daily_log_photo_delete,
                             self.log_b.id, self.photo_b.attachment_id.id)
        self.assertIn('message=photo_deleted', loc)
        self.assertFalse(self.photo_b.exists(), '監造方主管照常刪得掉')

    def test_daily_log_unlock_contractor_denied(self):
        log = self._log(self.co_a, days_ago=LOCKED_LOG_AGE_DAYS)
        self.assertTrue(log._is_edit_locked(), '前提：日誌已鎖定')
        loc = self._location(self.boss_a, self.ctrl.portal_construction_daily_log_unlock, self.p.id, log.id)
        self.assertIn('error=no_unlock_permission', loc)
        self.assertTrue(log._is_edit_locked(), '營造方不能解鎖')
        loc = self._location(self.sup_leader, self.ctrl.portal_construction_daily_log_unlock, self.p.id, log.id)
        self.assertIn('message=unlocked', loc)
        self.assertFalse(log._is_edit_locked(), '監造方主管照常解得開')

    def test_daily_log_import_replace_never_touches_others(self):
        """取代模式：那天只有 B 一張時，A 匯入不可覆蓋 B 的（改成另建 A 自己的一張）。"""
        # 夾具：契約工項由監造方先建好（營造方匯入不會自動補建，合約 §0b-12）
        self.env['project.task'].create({'name': 'A2 匯入工項', 'project_id': self.p.id})
        day = self.log_b.log_date
        parsed = {
            'log_date': day, 'weather_am': False, 'weather_pm': False, 'actual_progress': 0.0,
            'has_technician_requirement': False, 'safety_pre_work_education': False,
            'safety_labor_insurance_check': False, 'safety_ppe_check': False,
            'safety_other_matters': '', 'sampling_test_record': '', 'subcontractor_notification': '',
            'important_matters': 'A 的匯入',
            'line_rows': [{'name': 'A2 匯入工項', 'unit': '式', 'planned_qty': 10.0, 'daily_qty': 0.2,
                           'note': ''}],
            'material_rows': []}
        mock = patch(PARSER + 'daily_log_xlsm_parser.parse_daily_log_xlsm', return_value=parsed)
        _v, loc, session = self._call(self.leader_a, self.ctrl.portal_construction_daily_logs_import_submit,
                                      self.p.id, files=[self._upload('a.xlsm')], patches=[mock],
                                      same_day='replace')
        self.assertIn('imported=1', loc, session.get('daily_log_import_failed_details'))
        self.assertIn('replaced=0', loc)
        self.assertNotEqual(self.log_b.important_matters, 'A 的匯入', 'B 的日誌不可被 A 取代')
        new = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.p.id), ('log_date', '=', day), ('id', '!=', self.log_b.id)])
        self.assertEqual(new.contractor_company_id, self.co_a)

    # ═══ 缺失：補充、匯入 ═══════════════════════════════════════════════════
    def test_defect_enrich_only_own(self):
        rows = [{'filename': 'b.docx', 'match_keys': ['QA-B-001'], 'register_no': 'QA-B-001',
                 'improvement': '改 B'},
                {'filename': 'a.docx', 'match_keys': ['QA-A-001'], 'register_no': 'QA-A-001',
                 'improvement': '改 A', 'close_comment': 'A 寫的結案說明'}]

        def run(user):
            mock = patch(PARSER + 'defect_docx_parser.parse_defect_zip', return_value=rows)
            _v, loc, session = self._call(user, self.ctrl.portal_construction_defects_enrich_submit, self.p.id,
                                          files=[self._upload('a.zip')], patches=[mock])
            return loc, session.get('defect_enrich_failed_details', [])

        loc, details = run(self.field_a)
        self.assertIn('updated=1', loc)
        self.assertIn('unmatched=1', loc)
        self.assertFalse(self.def_b.improvement_result, 'A 不可補 B 的缺失')
        self.assertEqual(self.def_a.improvement_result, '改 A')
        self.assertFalse(self.def_a.close_comment, '結案說明屬監造方，營造方匯入時略過')
        self.assertTrue(any('結案說明' in d['error'] for d in details), details)
        loc, _d = run(self.sup_leader)
        self.assertIn('updated=2', loc)
        self.assertEqual(self.def_b.improvement_result, '改 B')
        self.assertEqual(self.def_a.close_comment, 'A 寫的結案說明', '監造方照常寫結案說明')

    def _xlsx_rows(self, improvement_date=None, description='A2 B 的缺失'):
        return [{'register_no': '', 'description': description, 'found_date': self.def_b.found_date,
                 'deadline': None, 'improvement_date': improvement_date, 'defect_category': 'workmanship',
                 'note': '', 'sheet_name': None}]

    def _import_xlsx(self, user, rows):
        mock = patch(PARSER + 'defect_xlsm_parser.parse_defect_tracking_xlsx_verbose', return_value=(rows, []))
        _v, loc, session = self._call(user, self.ctrl.portal_construction_defects_import_submit, self.p.id,
                                      files=[self._upload('a.xlsx')], patches=[mock])
        return loc, session.get('defect_import_failed_details', [])

    def test_defect_import_duplicate_check_only_own(self):
        """與 B 的缺失同日同說明：A 照樣建自己的一筆（不因 B 的跳過、也不回報 B 的 id）；監造方跳過。"""
        loc, details = self._import_xlsx(self.field_a, self._xlsx_rows())
        self.assertIn('imported=1', loc)
        self.assertFalse(any(str(self.def_b.id) in d['error'] for d in details), details)
        loc, _d = self._import_xlsx(self.sup_leader, self._xlsx_rows(description='A2 A 的缺失'))
        self.assertIn('skipped=1', loc, '監造方看得到全部，同日同說明照舊跳過')

    def test_defect_import_closed_rows_contractor_denied(self):
        Defect = self.env['general.defect.improvement']
        rows = self._xlsx_rows(improvement_date=self.today, description='A2 已改善的缺失')
        loc, details = self._import_xlsx(self.field_a, rows)
        self.assertIn('failed=1', loc)
        self.assertFalse(Defect.search([('defect_description', '=', 'A2 已改善的缺失')]))
        self.assertTrue(any(DENIED_MSG in d['error'] for d in details), details)
        loc, _d = self._import_xlsx(self.sup_leader, rows)
        self.assertIn('imported=1', loc)
        self.assertEqual(Defect.search([('defect_description', '=', 'A2 已改善的缺失')]).state, 'closed')

    def _import_docx(self, user, rows):
        mock = patch(PARSER + 'defect_docx_parser.parse_defect_zip', return_value=rows)
        _v, loc, session = self._call(user, self.ctrl.portal_construction_defects_import_docx_submit, self.p.id,
                                      files=[self._upload('a.zip')], patches=[mock])
        return loc, session.get('defect_create_docx_failed_details', [])

    def test_defect_import_docx_duplicate_and_closed(self):
        Defect = self.env['general.defect.improvement']
        dup = [{'filename': 'b.docx', 'register_no': None, 'found_date': self.def_b.found_date,
                'description': 'A2 B 的缺失', 'defect_category': 'workmanship'}]
        loc, details = self._import_docx(self.field_a, dup)
        self.assertIn('imported=1', loc, details)
        loc, _d = self._import_docx(self.sup_leader, [dict(dup[0], description='A2 A 的缺失')])
        self.assertIn('skipped=1', loc)
        closed = [{'filename': 'c.docx', 'register_no': None, 'found_date': self.today,
                   'description': 'A2 docx 已結案', 'defect_category': 'workmanship',
                   'close_comment': '已改善完成'}]
        loc, details = self._import_docx(self.field_a, closed)
        self.assertIn('failed=1', loc)
        self.assertFalse(Defect.search([('defect_description', '=', 'A2 docx 已結案')]))
        self.assertTrue(any(DENIED_MSG in d['error'] for d in details), details)
        loc, _d = self._import_docx(self.sup_leader, closed)
        self.assertIn('imported=1', loc)
        self.assertEqual(Defect.search([('defect_description', '=', 'A2 docx 已結案')]).state, 'closed')

    def test_inspection_import_duplicate_check_only_own(self):
        rows = [{'type_name': self.itype.name, 'inspection_date': self.insp_b.inspection_date,
                 'location': self.insp_b.inspection_location, 'note': '', 'sheet_label': 'A2'}]

        def run(user):
            mock = patch(PARSER + 'inspection_xlsm_parser.parse_inspection_summary_xlsm', return_value=rows)
            return self._location(user, self.ctrl.portal_construction_inspections_import_submit, self.p.id,
                                  files=[self._upload('a.xlsx')], patches=[mock])

        self.env['general.self.inspection'].browse(self.insp_a.id).write({'inspection_location': 'A2 L-A'})
        self.assertIn('imported=1', run(self.field_a), 'B 的同一筆不可讓 A 跳過')
        self.assertIn('skipped=1', run(self.sup_leader), '監造方照舊跳過重複')

    # ═══ 寫入矩陣：審核類營造方拒、監造方可以 ════════════════════════════════
    def test_defect_verify_and_close_contractor_denied(self):
        self.def_a.sudo().write({'state': 'improved'})
        msg = self._assert_denied(self.boss_a, self.ctrl.portal_defect_verify, self.def_a.id)
        self.assertIn(DENIED_MSG, msg)
        self._assert_denied(self.mgr_a, self.ctrl.portal_defect_verify, self.def_a.id)
        self.assertEqual(self.def_a.state, 'improved')
        self.assertIn('msg=reviewed', self._location(self.sup_leader, self.ctrl.portal_defect_verify, self.def_a.id))
        self.assertEqual(self.def_a.state, 'verified')
        self._assert_denied(self.boss_a, self.ctrl.portal_defect_close, self.def_a.id)
        self.assertEqual(self.def_a.state, 'verified')
        self.assertIn('msg=reviewed', self._location(self.sup_leader, self.ctrl.portal_defect_close, self.def_a.id))
        self.assertEqual(self.def_a.state, 'closed')

    def test_project_master_contractor_denied(self):
        project = self.p
        self.assertIn(DENIED_MSG, self._assert_denied(
            self.boss_a, self.ctrl.portal_construction_project_update, project.id, name='A 改工程'))
        self._assert_denied(self.boss_a, self.ctrl.portal_construction_project_edit, project.id)
        self._assert_denied(self.boss_a, self.ctrl.portal_construction_project_new)
        self._assert_denied(self.boss_a, self.ctrl.portal_construction_project_create, name='A 建的工程')
        _v, res, _s = self._call(self.boss_a, self.ctrl.portal_construction_project_code_update,
                                 project.id, code='A2-HACK')
        self.assertFalse(res['success'])
        self.assertIn(DENIED_MSG, res['error'])
        self.assertEqual(project.code, 'A2-P')
        self.assertFalse(self.env['project.project'].search([('name', '=', 'A 建的工程')]))
        # 監造方前台主管：照常可以
        _v, res, _s = self._call(self.sup_leader, self.ctrl.portal_construction_project_code_update,
                                 project.id, code='A2-P2')
        self.assertTrue(res['success'], res)
        self.assertIn('error=not_draft', self._location(
            self.sup_leader, self.ctrl.portal_construction_project_update, project.id, name='改'),
            '守衛放行，接著才是「只有草稿可改」的既有檢查')
        loc = self._location(self.sup_leader, self.ctrl.portal_construction_project_create, name='監造建的工程')
        self.assertTrue(self.env['project.project'].search([('name', '=', '監造建的工程')]), loc)

    def test_schedule_extension_contractor_denied(self):
        # 展延要有契約起訖日才算得出來（同 test_portal_orm_readonly 的展延測試）
        project = self.env['project.project'].create({
            'name': 'A2 展延工程', 'code': 'A2-EXT', 'project_type': 'general', 'state': 'construction',
            'company_id': self.env.company.id, **contractor_project_vals(self.co_a | self.co_b),
            'contract_start_date': fields.Date.to_date('2026-01-05'),
            'contract_end_date': fields.Date.to_date('2026-03-30')})
        for user in (self.leader_a, self.sup_leader):
            self.env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        schedule = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': self.today})
        self.assertEqual(schedule.state, 'draft', '前提')
        self._assert_denied(self.boss_a, self.ctrl.portal_schedule_extend_page, project.id)
        self._assert_denied(self.leader_a, self.ctrl.portal_schedule_extend_submit, project.id, schedule.id,
                            current_extension='9')
        self.assertFalse(schedule.current_extension)
        vals, _l, _s = self._call(self.sup_leader, self.ctrl.portal_schedule_extend_page, project.id)
        self.assertEqual(vals['schedule'], schedule)
        loc = self._location(self.sup_leader, self.ctrl.portal_schedule_extend_submit, project.id, schedule.id,
                             current_extension='9')
        self.assertIn('success=1', loc)
        self.assertEqual(schedule.current_extension, 9)

    def test_slip_confirm_and_close_contractor_denied(self):
        slip = self._slip()
        self._assert_denied(self.boss_a, self.ctrl.portal_slip_confirm, self.r.id, slip.id)
        self.assertEqual(slip.state, 'draft')
        self.assertIn('msg=reviewed', self._location(self.sup_leader, self.ctrl.portal_slip_confirm,
                                                     self.r.id, slip.id))
        self.assertEqual(slip.state, 'not_started')
        slip.sudo().write({'state': 'in_progress'})
        slip.detail_line_ids.sudo().write({'actual_qty': 1.0})
        self._assert_denied(self.leader_a, self.ctrl.portal_slip_close, self.r.id, slip.id)
        self.assertEqual(slip.state, 'in_progress')
        self.assertIn('msg=reviewed', self._location(self.sup_leader, self.ctrl.portal_slip_close,
                                                     self.r.id, slip.id))
        self.assertEqual(slip.state, 'closed')

    def test_inspection_confirm_allowed_close_denied(self):
        insp = self.insp_a
        insp.sudo().write({'state': 'inspected'})
        self.assertEqual(self._location(self.boss_a, self.ctrl.portal_inspection_confirm, self.insp_b.id), '/my',
                         'A 不可確認 B 的檢查')
        self.assertIn('msg=reviewed', self._location(self.boss_a, self.ctrl.portal_inspection_confirm, insp.id),
                      '自主檢查確認：營造方可以（限自家）')
        self.assertEqual(insp.state, 'confirmed')
        self.assertIn(DENIED_MSG, self._assert_denied(self.boss_a, self.ctrl.portal_inspection_close, insp.id))
        self.assertEqual(insp.state, 'confirmed')
        self.assertIn('msg=reviewed', self._location(self.sup_leader, self.ctrl.portal_inspection_close, insp.id))
        self.assertEqual(insp.state, 'closed')

    def test_inspect_requires_write(self):
        """/inspect 先過 _require_write：定期閱覽者、營造廠主管不能改狀態（合約 §3.6、§13-8）。"""
        insp = self.insp_a
        self.assertEqual(insp.state, 'draft', '前提')
        self._assert_denied(self.observer_a, self.ctrl.portal_inspection_inspect, insp.id)
        self._assert_denied(self.mgr_a, self.ctrl.portal_inspection_inspect, insp.id)
        self.assertEqual(insp.state, 'draft')
        self.assertIn('msg=inspected', self._location(self.leader_a, self.ctrl.portal_inspection_inspect, insp.id))
        self.assertEqual(insp.state, 'inspected')

    def test_water_level_contractor_denied(self):
        self.assertIn('水位', self._assert_denied(self.field_a, self.ctrl.portal_construction_water_level,
                                                 self.p.id))
        self._assert_denied(self.field_a, self.ctrl.portal_water_level_export_csv, self.p.id)
        _v, res, _s = self._call(self.field_a, self.ctrl.portal_water_level_data, self.p.id)
        self.assertEqual(res, {'error': 'Access denied'})
        vals, _l, _s = self._call(self.sup_leader, self.ctrl.portal_construction_water_level, self.p.id)
        self.assertIn('devices', vals, '監造方照常看得到水位頁')
        _v, res, _s = self._call(self.sup_leader, self.ctrl.portal_water_level_data, self.p.id)
        self.assertIn('devices', res)

    # ═══ 營造廠主管（後台唯讀）：前台寫入全拒 ════════════════════════════════
    def test_manager_frontend_writes_all_denied(self):
        pid, spid = str(self.p.id), self.p.id
        slip = self._slip()
        cases = [
            (self.ctrl.portal_construction_daily_log_create, (), {'project_id': pid}),
            (self.ctrl.portal_construction_daily_log_update, (spid, self.log_a.id), {}),
            (self.ctrl.portal_construction_defect_create, (), {'project_id': pid}),
            (self.ctrl.portal_construction_defect_improve, (self.def_a.id,), {}),
            (self.ctrl.portal_construction_inspection_create, (), {'project_id': pid}),
            (self.ctrl.portal_construction_photo_upload, (), {'project_id': pid}),
            (self.ctrl.portal_construction_daily_log_photo_upload, (self.log_a.id,), {}),
            (self.ctrl.portal_construction_document_upload, (spid,), {}),
            (self.ctrl.portal_construction_daily_logs_import_submit, (spid,), {}),
            (self.ctrl.portal_slip_set_geo, (self.r.id, slip.id), {}),
        ]
        for method, args, kw in cases:
            with self.subTest(route=method.__name__):
                self._assert_denied(self.mgr_a, method, *args, **kw)
        with MockRequest(self.env(user=self.mgr_a)):
            with self.assertRaises(AccessError):
                self.ctrl._require_write()
            with self.assertRaises(AccessError):
                self.ctrl._require_photo_deleter(self.photo_a)
            self.assertFalse(self.ctrl._can_manage_inspection_types())

    def test_supervision_side_guards_unchanged(self):
        """監造方後台員工：寫入與刪照片守衛照舊放行；代操照舊能管樣板。"""
        with MockRequest(self.env(user=self.sup_internal)):
            self.ctrl._require_write()
            self.ctrl._require_photo_deleter(self.photo_a)
        with MockRequest(self.env(user=self.sup_operator)):
            self.assertTrue(self.ctrl._can_manage_inspection_types())

    def test_contractor_internal_operator_cannot_manage_inspection_types(self):
        """營造方的內部帳號就算帶代操群組（設定錯誤的帳號）也不能改全域樣板。"""
        # 內部帳號不能勾營造組織（會帶前台群組）；範圍公司是營造廠就是營造方
        op_a = self._user('a2_op_a', ['base.group_user', OPERATOR], {'dash_scope_company_id': self.co_a.id})
        with MockRequest(self.env(user=op_a)):
            self.assertTrue(self.ctrl._can_manage(), '前提：代操群組讓 _can_manage 成立')
            self.assertFalse(self.ctrl._can_manage_inspection_types())

    # ═══ rule_scope 線 A2 加的白名單 ════════════════════════════════════════
    def _children(self):
        """九個營造廠層級子表：{模型: (A 的子表, B 的子表)}。"""
        env = self.env
        ptype = env['personnel.type'].create({'name': 'A2 技工', 'record_type': 'personnel'})
        est = {}
        for company in (self.co_a, self.co_b):
            self._day += 1
            est[company] = env['payment.estimate'].create({
                'project_id': self.p.id, 'contractor_company_id': company.id,
                'estimate_date': self.today - timedelta(days=self._day)})
        extra_item = env['payment.estimate.extra.item'].create({
            'project_id': self.p.id, 'code': 'A2X', 'name': 'A2 額外項'})
        makers = {
            'daily.log.material': lambda c: {'daily_log_id': self._doc('log', c).id, 'name': 'A2 材料'},
            'daily.log.specific.item': lambda c: {'daily_log_id': self._doc('log', c).id, 'name': 'A2 特定項'},
            'daily.log.man.machine.detail': lambda c: {
                'daily_log_id': self._doc('log', c).id, 'personnel_type_id': ptype.id, 'hours': 8.0},
            'general.self.inspection.item': lambda c: {
                'inspection_id': self._doc('insp', c).id, 'check_item': 'A2 子項目'},
            'general.self.inspection.measure.line': lambda c: {
                'inspection_id': self._doc('insp', c).id, 'block_id': self.block.id,
                'template': self.block.template, 'result': 'pass'},
            'reservation.self.inspection.item': lambda c: {
                'inspection_id': self._doc('res', c).id, 'check_item': 'A2 子項目'},
            'reservation.self.inspection.measure.line': lambda c: {
                'inspection_id': self._doc('res', c).id, 'block_id': self.block.id,
                'template': self.block.template, 'result': 'pass'},
            'payment.estimate.extra.line': lambda c: {
                'estimate_id': est[c].id, 'extra_item_id': extra_item.id, 'name': 'A2 額外項'},
        }
        children = {model: tuple(env[model].create(make(c)) for c in (self.co_a, self.co_b))
                    for model, make in makers.items()}
        # daily.log.weather 的 ORM 建立會壞（既有 bug：_check_date_in_sheet_range 讀不存在的
        # sheet_id.date_start → AttributeError），用 SQL 放資料，只驗讀取範圍
        weather = env['daily.log.weather']
        for sheet in (self.log_a, self.log_b):
            env.cr.execute('INSERT INTO daily_log_weather (sheet_id, date) VALUES (%s, %s) RETURNING id',
                           [sheet.id, sheet.log_date])
            weather |= weather.browse(env.cr.fetchone()[0])
        children['daily.log.weather'] = (weather[0], weather[1])
        return children

    def _doc(self, kind, company):
        own = company == self.co_a
        return {'log': self.log_a if own else self.log_b, 'insp': self.insp_a if own else self.insp_b,
                'res': self.res_insp_a if own else self.res_insp_b}[kind]

    def _seen(self, user, records):
        self.env.flush_all()
        self.env.invalidate_all()
        return set(self.env[records._name].with_user(user).search([('id', 'in', records.ids)]).ids)

    def test_scope_child_tables_follow_parent(self):
        children = self._children()
        self.assertEqual(len(children), 9)
        for model, (own, other) in children.items():
            with self.subTest(model=model):
                both = own | other
                self.assertEqual(self._seen(self.field_a, both), {own.id}, f'{model}：A 只看得到自家父單的子表')
                self.assertEqual(self._seen(self.field_b, both), {other.id}, f'{model}：B 同理')
                self.assertEqual(self._seen(self.sup_leader, both), set(both.ids), f'{model}：監造方兩家都看得到')

    def test_scope_project_level_additions(self):
        """合約 §0b-6：資料夾、檢試驗標準、變更單歸工程層級——工程的營造廠含我就看得到。"""
        env = self.env
        cases = {
            'supervision.folder': lambda p: {'name': 'A2 資料夾', 'project_id': p.id},
            'supervision.test.standard': lambda p: {'name': 'A2 標準', 'material': 'A2 材料', 'project_id': p.id},
            'contract.change.order': lambda p: {'project_id': p.id},
        }
        for model, make in cases.items():
            if model not in env:
                continue
            with self.subTest(model=model):
                on_p, on_pb = env[model].create(make(self.p)), env[model].create(make(self.pb))
                both = on_p | on_pb
                self.assertEqual(self._seen(self.field_a, both), {on_p.id}, f'{model}：只看得到 A 承攬的工程')
                self.assertEqual(self._seen(self.field_b, both), set(both.ids), f'{model}：B 兩個工程都有承攬')
                self.assertEqual(self._seen(self.sup_leader, both), set(both.ids), model)

    # ═══ 線 A3：合約 §0b-10 工程文件、§0b-11 照片跟著單據、§0b-12 寫入矩陣補充 ══════════
    def _document(self, project, category):
        """工程文件＋掛在它上面的附件（附件的來源單據＝文件；前台下載與列表依來源單據判定）。"""
        att = self.env['ir.attachment'].create({
            'name': f'{project.code}.pdf', 'datas': PNG_B64, 'mimetype': 'application/pdf',
            'public': False, 'res_model': 'supervision.document'})
        doc = self.env['supervision.document'].create({
            'name': f'{project.code} 合約', 'project_id': project.id,
            'document_category_id': category.id, 'upload_attachment_ids': [(4, att.id)]})
        self.assertEqual((att.res_model, att.res_id), ('supervision.document', doc.id), '前提：附件的來源是文件')
        return doc, att

    def test_supervision_document_project_level(self):
        """合約 §0b-10：工程文件歸工程層級——A 只看得到自己承攬工程的（A 是兩個工程的成員也一樣），
        B 兩個都看得到；營造廠主管有讀取 ACL、同樣只看 A 承攬的；監造方不變。前台下載與列表同一套。"""
        category = self.env['supervision.document.category'].create({'name': 'A3 文件分類'})
        doc_p, att_p = self._document(self.p, category)
        doc_pb, att_pb = self._document(self.pb, category)
        both = doc_p | doc_pb
        self.assertEqual(self._seen(self.field_a, both), {doc_p.id}, '少不得：自己承攬工程的文件看得到')
        self.assertEqual(self._seen(self.mgr_a, both), {doc_p.id}, '營造廠主管：同上，讀取不報錯')
        self.assertEqual(self._seen(self.field_b, both), set(both.ids), 'B 兩個工程都有承攬')
        self.assertEqual(self._seen(self.sup_leader, both), set(both.ids), '監造方兩個都看得到')
        with MockRequest(self.env(user=self.field_a)):
            self.assertIsNotNone(self.ctrl.portal_construction_document_serve(att_p.id))
            with self.assertRaises(NotFound, msg='A 不可下載只有 B 承攬的工程的文件'):
                self.ctrl.portal_construction_document_serve(att_pb.id)
        vals, _l, _s = self._call(self.field_a, self.ctrl.portal_construction_documents, self.p.id)
        self.assertIn(att_p.id, vals['attachments'].ids, '前台檔案管理列得出工程文件上的附件')

    def test_manager_reads_whitelist_additions(self):
        """合約 §0b-10：線 A2 加進白名單的模型，營造廠主管都有讀取 ACL——讀取不報 AccessError，
        且只看得到自家（子表跟父單、工程層級跟工程）。"""
        for model, (own, other) in self._children().items():
            with self.subTest(model=model):
                self.assertEqual(self._seen(self.mgr_a, own | other), {own.id}, f'{model}：只看得到自家父單的子表')
        cases = {
            'supervision.folder': lambda p: {'name': 'A3 資料夾', 'project_id': p.id},
            'supervision.test.standard': lambda p: {'name': 'A3 標準', 'material': 'A3 材料', 'project_id': p.id},
            'contract.change.order': lambda p: {'project_id': p.id},
        }
        for model, make in cases.items():
            with self.subTest(model=model):
                on_p, on_pb = self.env[model].create(make(self.p)), self.env[model].create(make(self.pb))
                self.assertEqual(self._seen(self.mgr_a, on_p | on_pb), {on_p.id}, f'{model}：只看得到 A 承攬的工程')

    @staticmethod
    def _png_upload(name='a3.png'):
        upload = MagicMock(filename=name, mimetype='image/png')
        upload.read.return_value = base64.b64decode(PNG_B64)
        return upload

    def test_photo_on_document_follows_document_attribution(self):
        """合約 §0b-11：共用工程上監造方傳到 A 日誌的照片歸 A——A 看得到、取得到圖，B 看不到。
        （依工程判斷的話，工程有兩家營造廠、上傳者是監造方 → 留空 → A 也看不到。）"""
        before = self.log_a.photo_ids
        loc = self._location(self.sup_leader, self.ctrl.portal_construction_daily_log_photo_upload,
                             self.log_a.id, files=[self._png_upload()])
        self.assertIn('message=photo_added', loc)
        new = self.log_a.photo_ids - before
        self.assertEqual(len(new), 1, '前提：監造方上傳了一張')
        self.assertEqual(new.contractor_company_id, self.co_a, '照片跟著日誌歸 A')
        self.assertEqual(self._seen(self.field_a, new), {new.id}, 'A 看得到')
        self.assertEqual(self._seen(self.field_b, new), set(), 'B 看不到')
        with MockRequest(self.env(user=self.field_a)):
            self.assertIsNotNone(self.ctrl.portal_construction_photo_serve(new.attachment_id.id))
        with MockRequest(self.env(user=self.field_b)):
            with self.assertRaises(NotFound, msg='B 不可取得 A 日誌上的照片'):
                self.ctrl.portal_construction_photo_serve(new.attachment_id.id)

    def test_defect_notify_contractor_denied(self):
        """合約 §0b-12：通知改善（草稿 → 已通知）＝監造通知乙方限期改善 → 營造方老闆、主管被拒
        （含先寫期限的分支：被拒時期限也不可寫進去）；監造方前台主管可以。"""
        defect = self._defect(self.co_a, 'QA-A-003', 'A3 草稿缺失', state='draft')
        for user, kw in ((self.boss_a, {}), (self.leader_a, {'deadline': '2099-12-31'})):
            self.assertIn(DENIED_MSG, self._assert_denied(user, self.ctrl.portal_defect_notify, defect.id, **kw))
        self.assertEqual(defect.state, 'draft')
        self.assertFalse(defect.deadline, '被拒時期限不可先寫進去')
        loc = self._location(self.sup_leader, self.ctrl.portal_defect_notify, defect.id, deadline='2099-12-31')
        self.assertIn('msg=reviewed', loc)
        self.assertEqual(defect.state, 'notified')
        self.assertEqual(str(defect.deadline), '2099-12-31')

    def _import_log(self, user, parsed):
        mock = patch(PARSER + 'daily_log_xlsm_parser.parse_daily_log_xlsm', return_value=parsed)
        _v, loc, session = self._call(user, self.ctrl.portal_construction_daily_logs_import_submit, self.p.id,
                                      files=[self._upload('a.xlsm')], patches=[mock])
        return loc, session.get('daily_log_import_failed_details', [])

    def test_daily_log_import_no_task_stub_for_contractor(self):
        """合約 §0b-12：營造方匯入日誌不自動補建契約工項——缺的工項全部列出、說「請監造方補建」、整個檔不匯入；
        監造方照舊自動補建。"""
        Task, Log = self.env['project.task'], self.env['daily.log.sheet']
        day = self.today - timedelta(days=LOCKED_LOG_AGE_DAYS + 10)
        names = ['A3 沒有的工項甲', 'A3 沒有的工項乙']
        self.env['project.task'].create({'name': 'A3 已有的工項', 'project_id': self.p.id})
        parsed = {
            'log_date': day, 'weather_am': False, 'weather_pm': False, 'actual_progress': 0.0,
            'has_technician_requirement': False, 'safety_pre_work_education': False,
            'safety_labor_insurance_check': False, 'safety_ppe_check': False,
            'safety_other_matters': '', 'sampling_test_record': '', 'subcontractor_notification': '',
            'important_matters': 'A3 匯入',
            'line_rows': [{'name': n, 'unit': '式', 'planned_qty': 10.0, 'daily_qty': 1.0, 'note': ''}
                          for n in ['A3 已有的工項'] + names],
            'material_rows': []}
        task_domain = [('project_id', '=', self.p.id), ('name', 'in', names)]
        log_domain = [('supervision_project_id', '=', self.p.id), ('log_date', '=', day)]
        loc, details = self._import_log(self.leader_a, parsed)
        self.assertIn('imported=0', loc)
        self.assertIn('failed=1', loc)
        errors = [d['error'] for d in details]
        self.assertTrue(any(all(n in e for n in names) and '請監造方補建' in e for e in errors), errors)
        self.assertFalse(any('A3 已有的工項' in e for e in errors), '已有的工項不列')
        self.assertFalse(Task.search(task_domain), '營造方匯入不可補建工項')
        self.assertFalse(Log.search(log_domain), '缺工項＝整個檔不匯入')
        loc, details = self._import_log(self.sup_leader, parsed)
        self.assertIn('imported=1', loc, details)
        self.assertEqual(sorted(Task.search(task_domain).mapped('name')), sorted(names), '監造方照舊自動補建')
        self.assertEqual(len(Log.search(log_domain)), 1)

    def test_inspection_import_no_type_stub_for_contractor(self):
        """合約 §0b-12：營造方匯入自主檢查不自動補建檢查類型（樣板）——那一列列出原因、不匯入；
        已有的類型照常匯入；監造方照舊自動補建。"""
        Type, Insp = self.env['self.inspection.type'], self.env['general.self.inspection']
        missing = 'A3 沒有的檢查類型'
        rows = [{'type_name': missing, 'inspection_date': self.today, 'location': 'A3 L1', 'note': '',
                 'sheet_label': 'A3'},
                {'type_name': self.itype.name, 'inspection_date': self.today, 'location': 'A3 L2', 'note': '',
                 'sheet_label': 'A3'}]

        def run(user):
            mock = patch(PARSER + 'inspection_xlsm_parser.parse_inspection_summary_xlsm', return_value=rows)
            _v, loc, session = self._call(user, self.ctrl.portal_construction_inspections_import_submit,
                                          self.p.id, files=[self._upload('a.xlsx')], patches=[mock])
            return loc, session.get('inspection_import_failed_details', [])

        loc, details = run(self.field_a)
        self.assertIn('imported=1', loc, details)
        self.assertIn('failed=1', loc)
        self.assertTrue(any(missing in d['error'] and '請監造方補建' in d['error'] for d in details), details)
        self.assertFalse(Type.search([('name', '=', missing)]), '營造方匯入不可補建檢查類型')
        self.assertFalse(Insp.search([('project_id', '=', self.p.id), ('inspection_location', '=', 'A3 L1')]))
        loc, details = run(self.sup_leader)
        self.assertIn('imported=1', loc, details)
        self.assertEqual(len(Type.search([('name', '=', missing)])), 1, '監造方照舊自動補建')
