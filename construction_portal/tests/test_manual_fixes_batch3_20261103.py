# -*- coding: utf-8 -*-
"""說明書修正第 3 批（2026-11-03）線 1：前台。

- B3-1 前台新增缺失日期壞掉：導回新增頁帶固定代碼，不跳 500、不建缺失
- B3-2 前台存日誌：只有真的重疊才說「已有日誌」，其他驗證錯誤顯示真正原因（走 session，不經網址）
- B3-3 日誌／缺失／檢查／通報單詳情頁不把網址 error 參數原樣印出
- B3-4 首頁自主檢查卡片文字（無指派概念，不可寫「已指派給你」）
- B3-5 刪除照片：只有上傳者本人與管理層級可刪（四條刪除路由；前台群組也不能直接 ORM unlink）
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

VIEWER = 'construction_supervision_base.group_portal_viewer'   # 定期閱覽者
FIELD = 'construction_supervision_base.group_portal_user'      # 現場人員
LEADER = 'construction_supervision_base.group_portal_leader'   # 主管
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
# 偽造的網址參數：若被原樣印出，畫面上就會出現這段字
FORGED_TEXT = '偽造的系統通知XYZ請匯款'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalManualFixesBatch3(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.project = env['project.project'].create({
            'name': 'B3 一般式工程', 'code': 'B3-GEN', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.res_project = env['project.project'].create({
            'name': 'B3 預約式工程', 'code': 'B3-RSV', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'B3QA',
            'contractor_prefix': 'B3QR'})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.res_project.id, 'supervision_prefix': 'B3RS',
            'contractor_prefix': 'B3RC'})
        env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.worker_a = cls._mk_user('b3_worker_a', FIELD)
        cls.worker_b = cls._mk_user('b3_worker_b', FIELD)
        cls.leader = cls._mk_user('b3_leader', LEADER)
        cls.observer = cls._mk_user('b3_observer', VIEWER)
        for u in (cls.worker_a, cls.worker_b, cls.leader, cls.observer):
            for p in (cls.project, cls.res_project):
                env['supervision.project.member'].create({
                    'project_id': p.id, 'user_id': u.id})
        cls.emp_a = cls._mk_employee(cls.worker_a)
        cls.emp_b = cls._mk_employee(cls.worker_b)
        cls.itype = env['self.inspection.type'].create({'name': 'B3 類型'})

    @classmethod
    def _mk_user(cls, login, group_xmlid):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])]})

    @classmethod
    def _mk_employee(cls, user):
        emp = cls.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        return emp or cls.env['hr.employee'].create({
            'name': user.login + '_emp', 'company_id': cls.env.company.id,
            'user_id': user.id})

    def _drive(self, user, method, *args, params=None, args_qs=None, **kw):
        """真實使用者跑真實路由；路由若 render 就把模板真的渲染成 HTML。
        回傳 (values, html)；路由回 redirect 時 values 為 None、html 為 Location。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = args_qs or {}
            req.params = params or {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    # ── 記錄工廠 ────────────────────────────────────────────────────────
    def _log(self, employee):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'company_id': self.env.company.id,
            'employee_id': employee.id,
            'log_date': fields.Date.today()})

    def _general_inspection(self):
        return self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'name': 'B3-INSP',
            'inspection_type_id': self.itype.id, 'sub_project_name': 'B3',
            'inspection_date': fields.Date.today()})

    def _slip(self):
        # 同一工程的通報單號有唯一約束：同一個測試裡建多張要自己給不同號
        self._slip_no = getattr(self, '_slip_no', 0) + 1
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.res_project.id, 'location': 'B3 地點',
            'slip_no': self._slip_no})
        slip.sudo().write({'state': 'in_progress'})
        return slip

    def _reservation_inspection(self):
        return self.env['reservation.self.inspection'].create({
            'slip_id': self._slip().id, 'inspection_type_id': self.itype.id,
            'sub_project_name': 'B3', 'inspection_date': fields.Date.today()})

    def _general_defect(self):
        return self.env['general.defect.improvement'].create({
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': 'B3 牆面裂縫', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': 'notified'})

    def _reservation_defect(self):
        return self.env['reservation.defect.improvement'].create({
            'project_id': self.res_project.id, 'slip_id': self._slip().id,
            'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': 'B3 預約缺失',
            'defect_location': 'B3', 'source_type': 'daily_check', 'state': 'notified'})

    def _photo(self, uploader, record, project):
        """以 uploader 的身分建一張掛在 record 上的照片（create_uid＝uploader，與前台上傳相同）。"""
        env_u = self.env(user=uploader)
        att = env_u['ir.attachment'].sudo().create({
            'name': 'b3.png', 'datas': PNG_B64, 'mimetype': 'image/png',
            'public': False, 'res_model': 'supervision.photo'})
        field = self.env['supervision.photo']._photo_source_field_map()[record._name]
        photo = env_u['supervision.photo'].sudo().create({
            'project_id': project.id, 'attachment_id': att.id, field: record.id})
        self.assertEqual(photo.create_uid, uploader, '前提：照片的建立者要是上傳者')
        return photo

    # ═══ B3-1 缺失新增日期 ═══════════════════════════════════════════════
    def test_b3_1_bad_dates_redirect_back_no_defect_created(self):
        Defect = self.env['general.defect.improvement']
        before = Defect.search_count([('project_id', '=', self.project.id)])
        for field_name in ('found_date', 'deadline'):
            post = {'project_id': str(self.project.id), 'description': 'B3 壞日期',
                    'location': 'B1', field_name: '2026-13-45'}
            vals, loc = self._drive(
                self.worker_a, self.ctrl.portal_construction_defect_create, **post)
            self.assertIsNone(vals)
            self.assertEqual(
                loc, f'/construction/{self.project.id}/defect/new?error=invalid_date',
                f'{field_name} 壞掉應導回新增頁並只帶固定代碼')
        self.assertEqual(
            Defect.search_count([('project_id', '=', self.project.id)]), before,
            '日期壞掉不可建出缺失')
        # 新增頁真的把提示畫出來
        vals, html = self._drive(
            self.worker_a, self.ctrl.portal_construction_defect_new,
            self.project.id, params={'error': 'invalid_date'})
        self.assertIn('日期格式不正確', html)

    def test_b3_1_good_dates_still_create(self):
        Defect = self.env['general.defect.improvement']
        before = Defect.search_count([('project_id', '=', self.project.id)])
        vals, loc = self._drive(
            self.worker_a, self.ctrl.portal_construction_defect_create,
            project_id=str(self.project.id), description='B3 好日期', location='B1',
            found_date='2026-11-03', deadline='2026-11-10')
        self.assertIn('/construction/defect/', loc)
        self.assertNotIn('error=', loc)
        self.assertEqual(
            Defect.search_count([('project_id', '=', self.project.id)]), before + 1)

    # ═══ B3-2 日誌存檔：重疊 vs 其他驗證錯誤 ═══════════════════════════════
    def test_b3_2_other_validation_error_shows_real_reason_not_duplicate(self):
        reason = 'B3 其他驗證原因QQQ'
        Sheet = type(self.env['daily.log.sheet'])

        def boom(self_, vals_list, *a, **k):
            raise ValidationError(reason)

        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=self.worker_a)
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.params = {}
            seen = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            with patch.object(Sheet, 'create', boom):
                res = self.ctrl.portal_construction_daily_log_create(
                    project_id=str(self.project.id),
                    log_date=fields.Date.today().isoformat())
            loc = res.headers.get('Location', '')
            self.assertNotIn('duplicate_log', loc, '沒有重疊日誌，不可說「已有日誌」')
            self.assertNotIn(reason, loc, '原因文字不可經網址')
            self.assertIn('error=flash', loc)
            # 同一個 session 接著開新增頁：看得到真正原因，且只顯示一次
            req.params = {'error': 'flash'}
            self.ctrl.portal_construction_daily_log_new(self.project.id, error='flash')
            html = env['ir.ui.view']._render_template(
                seen['tpl'], dict(seen['vals']))
            html = html.decode() if isinstance(html, bytes) else html
            self.assertIn(reason, html)
            seen.clear()
            self.ctrl.portal_construction_daily_log_new(self.project.id, error='flash')
            html2 = env['ir.ui.view']._render_template(
                seen['tpl'], dict(seen['vals']))
            html2 = html2.decode() if isinstance(html2, bytes) else html2
            self.assertNotIn(reason, html2, 'flash 訊息顯示後要清掉')

    def test_b3_2_same_employee_same_day_is_still_duplicate(self):
        self._log(self.emp_a)
        vals, loc = self._drive(
            self.worker_a, self.ctrl.portal_construction_daily_log_create,
            project_id=str(self.project.id), log_date=fields.Date.today().isoformat())
        self.assertIn('/daily-log/new?error=duplicate_log', loc)

    def test_b3_2_other_filler_same_day_is_allowed(self):
        """使用者決定：同工程同一天可有多張日誌（不同填表人），不可被當成重複。"""
        self._log(self.emp_a)
        before = self.env['daily.log.sheet'].search_count(
            [('supervision_project_id', '=', self.project.id)])
        vals, loc = self._drive(
            self.worker_b, self.ctrl.portal_construction_daily_log_create,
            project_id=str(self.project.id), log_date=fields.Date.today().isoformat())
        self.assertNotIn('error=', loc)
        self.assertEqual(self.env['daily.log.sheet'].search_count(
            [('supervision_project_id', '=', self.project.id)]), before + 1)

    # ═══ B3-3 error 參數不原樣印出 ═════════════════════════════════════════
    def _detail_pages(self):
        """(標籤, 路由, 位置參數) —— 每個印 error 區塊的詳情頁"""
        log = self._log(self.emp_a)
        insp = self._general_inspection()
        res_insp = self._reservation_inspection()
        defect = self._general_defect()
        slip = self._slip()
        return [
            ('日誌詳情', self.ctrl.portal_construction_daily_log_detail,
             (self.project.id, log.id)),
            ('缺失詳情', self.ctrl.portal_construction_defect_detail, (defect.id,)),
            ('檢查詳情', self.ctrl.portal_construction_inspection_detail, (insp.id,)),
            ('預約檢查詳情', self.ctrl.portal_construction_reservation_inspection_detail,
             (res_insp.id,)),
            ('通報單詳情', self.ctrl.portal_construction_slip_detail,
             (self.res_project.id, slip.id)),
        ]

    def test_b3_3_forged_error_param_is_not_echoed(self):
        for label, method, args in self._detail_pages():
            vals, html = self._drive(
                self.leader, method, *args,
                params={'error': FORGED_TEXT}, args_qs={})
            self.assertIsNotNone(vals, f'{label}：應渲染而不是被導走：{html}')
            self.assertNotIn(FORGED_TEXT, html, f'{label}：不可原樣印出網址的 error 參數')

    def test_b3_3_known_code_shows_fixed_message(self):
        log = self._log(self.emp_a)
        vals, html = self._drive(
            self.leader, self.ctrl.portal_construction_daily_log_detail,
            self.project.id, log.id, params={'error': 'locked'})
        self.assertIn('此日誌已鎖定，無法修改', html)

    def test_b3_3_review_action_error_goes_through_session_not_url(self):
        reason = 'B3 審核失敗原因RRR'

        class _Rec:
            # _run_review_action 一律以本人身分 sudo 執行（前台角色 ORM 寫入權已收回）
            def with_user(self_, user):
                return self_

            def sudo(self_):
                return self_

            def boom(self_):
                raise UserError(reason)

        self.env.flush_all()
        with MockRequest(self.env(user=self.leader)):
            res = self.ctrl._run_review_action(_Rec(), 'boom', '/ok', '/construction/1/x')
        loc = res.headers.get('Location', '')
        self.assertNotIn(reason, loc)
        self.assertEqual(loc, '/construction/1/x?error=flash')

    # ═══ B3-4 首頁卡片文字 ═══════════════════════════════════════════════
    def test_b3_4_home_card_does_not_claim_assignment(self):
        path = 'construction_portal/views/portal_templates.xml'
        with file_open(path) as f:
            src = f.read()
        self.assertNotIn('已指派給你', src)
        self.assertNotIn('自主檢查指派', src)

    # ═══ B3-5 刪除照片：上傳者本人或管理層級 ═══════════════════════════════
    def _delete_routes(self):
        """(標籤, 路由, 建立「記錄＋照片」的函式, 組路由參數的函式)。
        日誌／檢查三條以附件 id 指定照片；缺失以 supervision.photo id 指定。"""
        def mk_log(uploader):
            rec = self._log(self.emp_a)
            return self._photo(uploader, rec, self.project), {'log_id': rec.id}

        def mk_insp(uploader):
            rec = self._general_inspection()
            return self._photo(uploader, rec, self.project), {'inspection_id': rec.id}

        def mk_res_insp(uploader):
            rec = self._reservation_inspection()
            return self._photo(uploader, rec, self.res_project), {'inspection_id': rec.id}

        def mk_defect(uploader):
            rec = self._general_defect()
            return self._photo(uploader, rec, self.project), {'defect_id': rec.id}

        def mk_res_defect(uploader):
            rec = self._reservation_defect()
            return self._photo(uploader, rec, self.res_project), {'defect_id': rec.id}

        return [
            ('日誌', self.ctrl.portal_construction_daily_log_photo_delete, mk_log, 'att_id'),
            ('一般式檢查', self.ctrl.portal_construction_inspection_photo_delete, mk_insp, 'att_id'),
            ('預約式檢查', self.ctrl.portal_construction_reservation_inspection_photo_delete,
             mk_res_insp, 'att_id'),
            ('一般式缺失', self.ctrl.portal_construction_defect_photo_delete, mk_defect, 'line_id'),
            ('預約式缺失', self.ctrl.portal_construction_defect_photo_delete, mk_res_defect, 'line_id'),
        ]

    def _try_delete(self, user, method, kw, photo_arg, photo):
        kw = dict(kw)
        kw[photo_arg] = photo.attachment_id.id if photo_arg == 'att_id' else photo.id
        # 預約式缺失的 id 會與一般式撞號，路由靠 ?model=reservation 區分
        qs = {'model': 'reservation'} if 'defect_id' in kw and photo.reservation_defect_id else {}
        self._drive(user, method, args_qs=qs, **kw)

    def test_b3_5_uploader_can_delete_own_photo(self):
        for label, method, mk, arg in self._delete_routes():
            photo, kw = mk(self.worker_a)
            pid = photo.id
            self._try_delete(self.worker_a, method, kw, arg, photo)
            self.assertFalse(self.env['supervision.photo'].sudo().browse(pid).exists(),
                             f'{label}：上傳者本人應能刪掉自己的照片')

    def test_b3_5_field_worker_cannot_delete_others_photo(self):
        for label, method, mk, arg in self._delete_routes():
            photo, kw = mk(self.worker_a)
            with self.assertRaises(AccessError, msg=f'{label}：別人上傳的照片現場人員不可刪'):
                self._try_delete(self.worker_b, method, kw, arg, photo)
            self.assertTrue(photo.exists(), f'{label}：被擋之後照片還要在')

    def test_b3_5_manager_can_delete_others_photo(self):
        for label, method, mk, arg in self._delete_routes():
            photo, kw = mk(self.worker_a)
            pid = photo.id
            self._try_delete(self.leader, method, kw, arg, photo)
            self.assertFalse(self.env['supervision.photo'].sudo().browse(pid).exists(),
                             f'{label}：主管應能刪別人上傳的照片')

    def test_b3_5_viewer_cannot_delete(self):
        for label, method, mk, arg in self._delete_routes():
            photo, kw = mk(self.worker_a)
            with self.assertRaises(AccessError, msg=f'{label}：閱覽者不可刪'):
                self._try_delete(self.observer, method, kw, arg, photo)
            self.assertTrue(photo.exists())

    # ═══ 審查補充（11-03）═══════════════════════════════════════════════════
    def test_b3_5_rpc_unlink_of_others_photo_is_blocked(self):
        """刪照片的限制不能只裝在前台路由：前台帳號直接呼叫 ORM（/web/dataset/call_kw）
        刪照片也要被擋。前台刪照片一律走 sudo 路由，所以前台群組不需要 unlink 權。"""
        boss = self._mk_user('b3_boss', 'construction_supervision_base.group_portal_subscriber')
        log = self._log(self.emp_a)
        for user in (self.worker_b, self.leader, boss, self.worker_a):
            photo = self._photo(self.worker_a, log, self.project)
            with self.assertRaises(AccessError, msg=f'{user.login}：前台帳號不可直接 unlink 照片'):
                photo.with_user(user).unlink()
            self.assertTrue(photo.exists())

    def test_b3_2_edit_to_same_day_shows_duplicate_not_500(self):
        """編輯日誌把日期改成同填表人另一張日誌的日期：導回編輯頁提示重複（原本直接 500）。"""
        today = fields.Date.today()
        self._log(self.emp_a)
        other = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'company_id': self.env.company.id,
            'employee_id': self.emp_a.id,
            'log_date': today - timedelta(days=1)})
        vals, loc = self._drive(
            self.leader, self.ctrl.portal_construction_daily_log_update,
            self.project.id, other.id, log_date=today.isoformat())
        self.assertIn(f'/daily-log/{other.id}/edit?error=duplicate_log', loc)
        self.assertEqual(other.log_date, today - timedelta(days=1), '整筆不可存進去')

    # ═══ B3-10 日誌匯入：同一天已有日誌不再整份跳過（使用者 11-03 決定）═══════
    def _parsed(self, day, qty=2.0, note=''):
        """解析器的輸出（patch 掉真的 xlsm 解析，只測匯入路由怎麼處理同一天）。"""
        return {
            'log_date': day, 'weather_am': False, 'weather_pm': False,
            'actual_progress': 0.0, 'has_technician_requirement': False,
            'safety_pre_work_education': False, 'safety_labor_insurance_check': False,
            'safety_ppe_check': False, 'safety_other_matters': '',
            'sampling_test_record': '', 'subcontractor_notification': '',
            'important_matters': note,
            'line_rows': [{'name': 'B3 匯入工項', 'unit': '式', 'planned_qty': 10.0,
                           'daily_qty': qty, 'note': ''}],
            'material_rows': [],
        }

    def _import(self, user, parsed, same_day=None):
        """以 user 身分跑真實的匯入 POST 路由，回傳 (Location, 處理明細)。"""
        self.env.flush_all()
        self.env.invalidate_all()
        upload = MagicMock(filename='b3.xlsm')
        upload.read.return_value = b'xlsm'
        post = {'same_day': same_day} if same_day else {}
        with MockRequest(self.env(user=user)) as req, patch(
                'odoo.addons.construction_portal.utils.daily_log_xlsm_parser.parse_daily_log_xlsm',
                return_value=parsed):
            req.httprequest.files.getlist.return_value = [upload]
            res = self.ctrl.portal_construction_daily_logs_import_submit(self.project.id, **post)
            details = req.session.get('daily_log_import_failed_details', [])
        return res.headers.get('Location', ''), details

    def _day_sheets(self, day):
        return self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project.id), ('log_date', '=', day)])

    def test_b3_10_import_same_day_different_content_adds_sheet(self):
        """同一個人、同一天、內容不同：另建一張（原本整份跳過）。"""
        day = fields.Date.today()
        self._log(self.emp_a)
        loc, details = self._import(self.worker_a, self._parsed(day))
        self.assertIn('imported=1', loc, details)
        self.assertEqual(len(self._day_sheets(day)), 2)

    def test_b3_10_import_identical_content_is_skipped(self):
        day = fields.Date.today() - timedelta(days=2)
        self._import(self.worker_a, self._parsed(day))
        loc, details = self._import(self.worker_a, self._parsed(day))
        self.assertIn('imported=0', loc)
        self.assertIn('skipped=1', loc)
        self.assertEqual(len(self._day_sheets(day)), 1, '同一個檔再傳一次不可多一張')
        self.assertIn('相同的日誌', details[-1]['error'])

    def test_b3_10_import_replace_overwrites_that_day(self):
        day = fields.Date.today() - timedelta(days=2)
        self._import(self.worker_a, self._parsed(day, qty=2.0))
        sheet = self._day_sheets(day)
        loc, details = self._import(self.leader, self._parsed(day, qty=5.0), same_day='replace')
        self.assertIn('replaced=1', loc, details)
        self.assertEqual(self._day_sheets(day), sheet, '取代＝覆蓋同一張，不可多建')
        self.assertEqual(sheet.line_ids.mapped('daily_qty'), [5.0], '明細要換成檔案內容、舊的不留')

    def test_b3_10_import_replace_refuses_others_log_for_field_worker(self):
        day = fields.Date.today() - timedelta(days=2)
        self._import(self.worker_a, self._parsed(day, qty=2.0))
        sheet = self._day_sheets(day)
        loc, details = self._import(self.worker_b, self._parsed(day, qty=5.0), same_day='replace')
        self.assertIn('failed=1', loc)
        self.assertIn('只能取代自己的日誌', details[-1]['error'])
        self.assertEqual(sheet.line_ids.mapped('daily_qty'), [2.0], '被擋時原日誌不可被改')

    # ── 審查補充（匯入同日） ─────────────────────────────────────────────
    def test_b3_10_reimport_with_progress_decimals_is_skipped(self):
        """實際進度欄只存 2 位小數、解析器給 4 位：同一個檔再傳一次仍要判成相同（不可多一張讓數量加倍）。"""
        day = fields.Date.today() - timedelta(days=2)
        parsed = dict(self._parsed(day), actual_progress=4.0712)
        self._import(self.worker_a, parsed)
        for mode in (None, 'replace'):
            loc, details = self._import(self.worker_a, parsed, same_day=mode)
            self.assertIn('skipped=1', loc, (mode, details))
        self.assertEqual(len(self._day_sheets(day)), 1)

    def test_b3_10_add_mode_skips_same_quantities_even_if_text_was_added(self):
        """既有那張後來被補過文字：預設「另建一張」下，工項與數量相同仍跳過，不可讓累計加倍。"""
        day = fields.Date.today() - timedelta(days=2)
        self._import(self.worker_a, self._parsed(day))
        self._day_sheets(day).write({'important_matters': '事後補充'})
        loc, details = self._import(self.worker_a, self._parsed(day))
        self.assertIn('skipped=1', loc, details)
        self.assertEqual(len(self._day_sheets(day)), 1)

    def test_b3_10_replace_with_text_change_replaces_and_leaves_a_note(self):
        day = fields.Date.today() - timedelta(days=2)
        self._import(self.worker_a, self._parsed(day))
        sheet = self._day_sheets(day)
        loc, details = self._import(self.leader, self._parsed(day, note='修正後'), same_day='replace')
        self.assertIn('replaced=1', loc, details)
        self.assertEqual(sheet.important_matters, '修正後')
        self.assertTrue(any('取代日誌內容' in (m.body or '') for m in sheet.message_ids),
                        '主管取代別人的日誌要留下紀錄')

    def test_b3_10_edit_after_same_day_import_still_saves(self):
        """匯入補傳讓同一人同一天有兩張後，前台編輯其中一張（日期沒改）不可被當成重複。"""
        day = fields.Date.today()
        first = self._log(self.emp_a)
        self._import(self.worker_a, self._parsed(day))
        self.assertEqual(len(self._day_sheets(day)), 2, '前提：同一人同一天兩張')
        vals, loc = self._drive(
            self.leader, self.ctrl.portal_construction_daily_log_update,
            self.project.id, first.id, log_date=day.isoformat(), work_summary='編輯後')
        self.assertNotIn('error=', loc)
        self.assertEqual(first.work_summary, '編輯後')

    def test_b3_10_replace_keeps_linked_key_material_rows(self):
        """取代只換人工材料列；連到契約材料清單的重要材料列（含已填數量）要留著。"""
        self.env['construction.contract.material'].create({
            'project_id': self.project.id, 'name': 'B3 重要材料', 'unit': 'm3', 'is_key': True})
        sheet = self._log(self.emp_a)
        linked = sheet.material_ids.filtered('catalog_item_id')
        self.assertEqual(len(linked), 1, '前提：建日誌時自動帶入一列重要材料')
        linked.daily_qty = 3.0
        parsed = dict(self._parsed(fields.Date.today()), material_rows=[{
            'name': '檔案裡的材料', 'unit': 'kg', 'contract_qty': 0.0, 'daily_qty': 1.0,
            'cumulative_qty': 1.0, 'note': ''}])
        loc, details = self._import(self.leader, parsed, same_day='replace')
        self.assertIn('replaced=1', loc, details)
        self.assertTrue(linked.exists(), '重要材料列不可被刪')
        self.assertEqual(linked.daily_qty, 3.0)
        self.assertIn('檔案裡的材料', sheet.material_ids.mapped('name'))
