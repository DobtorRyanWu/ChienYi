# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：會議起因的情境走一次真實的前台路由。

情境：開口合約（預約式）沒有預定進度表、也沒做初始化設定。
修改前：開不了工（六項初始化未完成）；就算開了工，前台新增日誌也會被「尚未建立進度表」擋下；
        超過 14 天的日誌前台不能改（error=locked）。
修改後：直接開工 → 前台新增日誌成功 → 20 天前的日誌前台照樣能改。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（PJ-04、DL-01、DL-05）。
"""
import re
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import (
    ConstructionPortal, PROJECT_FIELDS_LOCKED_AFTER_START)
from odoo.addons.construction_portal.tests.dash_fixtures import (
    SUPERVISION_USER_VALS, contractor_project_vals, contractor_user_vals, make_contractor)
from odoo.addons.construction_portal.utils import defect_xlsm_parser

LEADER = 'construction_supervision_base.group_portal_leader'
BOSS = 'construction_supervision_base.group_portal_subscriber'    # 老闆：未開始的工程只有老闆看得到
CONTRACT_START = date(2026, 1, 5)
CONTRACT_END = date(2026, 3, 30)
NEGATIVE_EXTENSION_DAYS = -3
NEGATIVE_DAILY_QTY = -2.5


@tagged('post_install', '-at_install', 'construction_portal')
class TestEagleParityPortalScenario(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(cls.env, '回復原版前台營造')
        cls.project = cls.env['project.project'].create({
            'name': '回復原版開口合約', 'code': 'EP-PORTAL', 'project_type': 'reservation',
            'company_id': cls.env.company.id, **contractor_project_vals(cls.contractor)})
        cls.env['project.task'].create({'name': '回復原版開口工項', 'project_id': cls.project.id})
        cls.leader = cls.env['res.users'].create({
            'name': 'ep_portal_leader', 'login': 'ep_portal_leader',
            'groups_id': [(6, 0, [cls.env.ref(LEADER).id])], **contractor_user_vals(cls.contractor)})
        cls.env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': cls.leader.id})
        if not cls.env['hr.employee'].search([('user_id', '=', cls.leader.id)], limit=1):
            cls.env['hr.employee'].create({
                'name': '回復原版前台員工', 'company_id': cls.env.company.id, 'user_id': cls.leader.id})

    def _post(self, method, *args, **post):
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            return method(*args, **post).headers.get('Location', '')

    def _logs(self):
        return self.env['daily.log.sheet'].search([('supervision_project_id', '=', self.project.id)])

    def test_open_contract_without_schedule_end_to_end(self):
        project = self.project
        self.assertEqual(project.state, 'draft')
        self.assertFalse(project.all_init_done, '前提：初始化設定都沒做')
        self.assertFalse(self.env['progress.schedule'].search_count([('project_id', '=', project.id)]),
                         '前提：沒有進度表')
        project.action_approve()                                      # 直接開工
        self.assertEqual(project.state, 'construction')

        day = fields.Date.today() - timedelta(days=1)
        loc = self._post(self.ctrl.portal_construction_daily_log_create,
                         project_id=str(project.id), log_date=str(day))
        self.assertIn('message=created', loc)                         # 前台新增日誌
        log = self._logs()
        self.assertEqual((len(log), log.log_date), (1, day))

    def test_old_log_editable_from_portal(self):
        self.project.action_approve()
        employee = self.env['hr.employee'].search([('user_id', '=', self.leader.id)], limit=1)
        old = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': employee.id, 'log_date': fields.Date.today() - timedelta(days=20),
            'contractor_company_id': self.contractor.id})
        self.env.cr.execute(          # 模擬以前就建好的日誌
            "UPDATE daily_log_sheet SET create_date = create_date - interval '30 days' WHERE id = %s", [old.id])
        loc = self._post(self.ctrl.portal_construction_daily_log_update, self.project.id, old.id,
                         work_summary='20 天前的日誌從前台補記')
        self.assertNotIn('error=', loc)
        self.env.invalidate_all()
        self.assertEqual(old.work_summary, '20 天前的日誌從前台補記')


@tagged('post_install', '-at_install', 'construction_portal')
class TestEagleParityPortalFollowUp(TransactionCase):
    """前台跟著後台回復原版（使用者 2026-11-20：「前台也要跟著做」）。

    後台那六包拿掉的限制，前台另外寫了一份的有這幾處，逐條對一個「修改前會失敗」的案例：
    * PJ-09 工程資訊編輯只開放未開始的工程 → 開工後也能編輯（工程類型、契約金額、契約日期、展延、管理公司照後台維持鎖住）
    * PJ-12 存檔前預檢「契約完工日不得早於開工日」→ 不檢查
    * PG-12 工期展延天數不可為負數 → 可以
    * DL-14 日誌工項清單不列整包項 → 列（比例項照舊不列）
    * DL-16 今日數量輸入框 min="0" → 拿掉，負數存得進去
    * DF-01 「通知改善」的期限欄必填 → 可不填
    * DF-11 缺失匯入時期限早於發現日會被改成發現日 → 照原檔的值
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(env, '回復原版前台跟進營造')
        base = {'project_type': 'general', 'company_id': env.company.id,
                'contract_start_date': CONTRACT_START, 'contract_end_date': CONTRACT_END,
                **contractor_project_vals(cls.contractor)}
        cls.started = env['project.project'].create(dict(
            base, name='回復原版已開工工程', code='EP-PF-STARTED', state='construction'))
        cls.draft = env['project.project'].create(dict(
            base, name='回復原版未開始工程', code='EP-PF-DRAFT'))
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.started.id, 'supervision_prefix': 'EPQA', 'contractor_prefix': 'EPQR'})
        # 監造方前台主管：工程資訊、工期展延、通知改善都限監造方
        cls.leader = env['res.users'].create({
            'name': 'ep_follow_leader', 'login': 'ep_follow_leader',
            'groups_id': [(6, 0, [env.ref(LEADER).id])], **SUPERVISION_USER_VALS})
        cls.boss = env['res.users'].create({
            'name': 'ep_follow_boss', 'login': 'ep_follow_boss',
            'groups_id': [(6, 0, [env.ref(BOSS).id])], **SUPERVISION_USER_VALS})
        for project in (cls.started, cls.draft):
            env['supervision.project.member'].create({'project_id': project.id, 'user_id': cls.leader.id})
        if not env['hr.employee'].search([('user_id', '=', cls.leader.id)], limit=1):   # 有些庫建帳號時會自動建員工
            env['hr.employee'].create({'name': '回復原版前台跟進員工', 'company_id': env.company.id,
                                       'user_id': cls.leader.id})
        Task = env['project.task']
        cls.normal_task = Task.create({'name': '回復原版一般工項', 'project_id': cls.started.id,
                                       'unit': 'M', 'planned_qty': 100.0, 'unit_price': 10.0})
        cls.lump_task = Task.create({'name': '回復原版整包項', 'project_id': cls.started.id,
                                     'unit': '式', 'planned_qty': 1.0, 'xml_amount': 50000.0,
                                     'is_lump_sum': True})
        cls.rate_task = Task.create({'name': '回復原版比例項', 'project_id': cls.started.id,
                                     'unit': '式', 'planned_qty': 1.0, 'tax_misc_rate': 5.0})

    def _drive(self, method, *args, files=None, user=None, **kw):
        """監造方主管（或指定的 user）跑真實路由、模板真的渲染。
        回傳 (values, html)；路由回 redirect 時 values 為 None、html 為 Location。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user or self.leader)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = files or []
            req.httprequest.args = {}
            req.params = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        self.env.invalidate_all()
        return seen['vals'], html.decode() if isinstance(html, bytes) else str(html)

    @staticmethod
    def _tag(html, pattern):
        """取出第一個符合的整個標籤（屬性順序不固定，整個標籤拿來查有沒有 disabled／min／required）。"""
        found = re.search(pattern, html)
        return found.group(0) if found else None

    # ---- PJ-09：開工後也能編輯工程資訊 --------------------------------
    def test_info_page_has_edit_button_after_start(self):
        vals, html = self._drive(self.ctrl.portal_construction_project_info, self.started.id)
        self.assertIsNotNone(vals, html)
        self.assertIn(f'/construction/{self.started.id}/edit', html, '已開工的工程，工程資訊頁要有「編輯」')

    def test_edit_page_opens_after_start_with_locked_fields(self):
        vals, html = self._drive(self.ctrl.portal_construction_project_edit, self.started.id)
        self.assertIsNotNone(vals, f'已開工的工程編輯頁要打得開，實際被導到 {html}')
        self.assertTrue(vals['locked_after_start'])
        for name, tag in (('project_type', 'select'), ('contract_start_date', 'input'),
                          ('contract_end_date', 'input'), ('extension_duration', 'input'),
                          ('contract_amount', 'input'), ('company_id', 'select')):
            self.assertIn(name, PROJECT_FIELDS_LOCKED_AFTER_START)
            element = self._tag(html, r'<%s[^>]*name="%s"[^>]*>' % (tag, name))
            self.assertIsNotNone(element, f'編輯頁找不到 {name}')
            self.assertIn('disabled', element, f'{name} 開工後要停用')
        for name, tag in (('name', 'input'), ('location', 'input'), ('contract_no', 'input'),
                          ('year', 'select'), ('actual_start_date', 'input')):
            element = self._tag(html, r'<%s[^>]*name="%s"[^>]*>' % (tag, name))
            self.assertIsNotNone(element, f'編輯頁找不到 {name}')
            self.assertNotIn('disabled', element, f'{name} 開工後要能改')

    def test_edit_page_draft_has_no_locked_fields(self):
        vals, html = self._drive(self.ctrl.portal_construction_project_edit, self.draft.id, user=self.boss)
        self.assertIsNotNone(vals, html)
        self.assertFalse(vals['locked_after_start'])
        self.assertNotIn('disabled', self._tag(html, r'<input[^>]*name="contract_start_date"[^>]*>'))

    def test_update_after_start_writes_open_fields_and_ignores_locked(self):
        project = self.started
        vals, loc = self._drive(
            self.ctrl.portal_construction_project_update, project.id,
            name='回復原版開工後改名', location='新地點', contract_no='EP-C-999',
            # 下面四個是開工後鎖住的欄位：就算有人自己組請求送進來也不能寫
            project_type='reservation', contract_start_date='2020-01-01',
            contract_end_date='2020-12-31', extension_duration='99')
        self.assertIsNone(vals)
        self.assertIn('message=updated', loc, '開工後存檔要成功（修改前：error=not_draft）')
        self.assertEqual((project.name, project.location, project.contract_no),
                         ('回復原版開工後改名', '新地點', 'EP-C-999'))
        self.assertEqual((project.project_type, project.contract_start_date, project.contract_end_date,
                          project.extension_duration),
                         ('general', CONTRACT_START, CONTRACT_END, 0), '鎖住的欄位不能被改到')

    # ---- PJ-12：不再預檢契約日期先後 ----------------------------------
    def test_draft_update_accepts_end_before_start(self):
        project = self.draft
        _vals, loc = self._drive(self.ctrl.portal_construction_project_update, project.id, user=self.boss,
                                 contract_start_date='2026-12-31', contract_end_date='2026-01-01')
        self.assertIn('message=updated', loc, '完工日早於開工日也要存得進去（修改前：error=date_invalid）')
        self.assertEqual((project.contract_start_date, project.contract_end_date),
                         (date(2026, 12, 31), date(2026, 1, 1)))

    # ---- PG-12：展延天數可以是負數 ------------------------------------
    def test_schedule_extend_accepts_negative_days(self):
        schedule = self.env['progress.schedule'].create({
            'project_id': self.started.id, 'change_date': fields.Date.today()})
        self.assertEqual(schedule.state, 'draft', '前提')
        vals, html = self._drive(self.ctrl.portal_schedule_extend_page, self.started.id)
        self.assertIsNotNone(vals, html)
        self.assertNotIn('min=', self._tag(html, r'<input[^>]*name="current_extension"[^>]*>'))
        _vals, loc = self._drive(self.ctrl.portal_schedule_extend_submit, self.started.id, schedule.id,
                                 current_extension=str(NEGATIVE_EXTENSION_DAYS))
        self.assertIn('success=1', loc, '負的展延天數要收（修改前：error=negative）')
        self.assertEqual(schedule.current_extension, NEGATIVE_EXTENSION_DAYS)

    # ---- DL-14、DL-16：整包項可以填日誌、今日數量可以是負數 -----------
    def test_new_log_form_lists_lump_item_without_qty_floor(self):
        vals, html = self._drive(self.ctrl.portal_construction_daily_log_new, self.started.id)
        self.assertIsNotNone(vals, html)
        self.assertIn(self.lump_task, vals['tasks'], '整包項要列在工項清單（修改前不列）')
        self.assertIn(self.normal_task, vals['tasks'])
        self.assertNotIn(self.rate_task, vals['tasks'], '比例項照舊不列')
        self.assertNotIn('min=', self._tag(html, r'<input[^>]*name="line_daily_qty_0"[^>]*>'),
                         '今日數量輸入框不能再有 min="0"')

    def test_create_log_with_lump_item_and_negative_qty(self):
        day = fields.Date.today() - timedelta(days=1)
        _vals, loc = self._drive(
            self.ctrl.portal_construction_daily_log_create,
            project_id=str(self.started.id), log_date=str(day),
            line_entry_type_0='contract', line_work_item_id_0=str(self.lump_task.id), line_daily_qty_0='0.4',
            line_entry_type_1='contract', line_work_item_id_1=str(self.normal_task.id),
            line_daily_qty_1=str(NEGATIVE_DAILY_QTY))
        self.assertIn('message=created', loc)
        log = self.env['daily.log.sheet'].search([('supervision_project_id', '=', self.started.id)])
        got = {line.work_item_id: line.daily_qty for line in log.line_ids}
        self.assertEqual(got, {self.lump_task: 0.4, self.normal_task: NEGATIVE_DAILY_QTY})

    # ---- DF-01：通知改善的期限可不填 ----------------------------------
    def test_notify_form_deadline_not_required(self):
        defect = self.env['general.defect.improvement'].create({
            'project_id': self.started.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版前台通知改善',
            'defect_location': 'B1', 'source_type': 'daily_check', 'state': 'draft'})
        vals, html = self._drive(self.ctrl.portal_construction_defect_detail, defect.id)
        self.assertIsNotNone(vals, html)
        deadline_input = self._tag(html, r'<input[^>]*name="deadline"[^>]*>')
        self.assertIsNotNone(deadline_input, '前提：草稿缺失的詳情頁有期限欄')
        self.assertNotIn('required', deadline_input, '期限欄不能再是必填（修改前瀏覽器會擋住送出）')
        _vals, loc = self._drive(self.ctrl.portal_defect_notify, defect.id)
        self.assertNotIn('error=', loc)
        self.assertEqual((defect.state, defect.deadline), ('notified', False))

    # ---- DF-11：缺失匯入照原檔的期限 ----------------------------------
    def test_defect_import_keeps_deadline_before_found_date(self):
        found, deadline = date(2026, 5, 10), date(2026, 5, 1)
        rows = [{'register_no': 'EP-R-1', 'description': '回復原版匯入缺失（期限早於發現日）',
                 'found_date': found, 'deadline': deadline, 'improvement_date': None,
                 'defect_category': 'workmanship', 'sheet_name': 'QA'}]
        upload = MagicMock(filename='ep.xlsx')
        upload.read.return_value = b'x'
        with patch.object(defect_xlsm_parser, 'parse_defect_tracking_xlsx_verbose',
                          return_value=(rows, [])):
            _vals, loc = self._drive(self.ctrl.portal_construction_defects_import_submit,
                                     self.started.id, files=[upload])
        self.assertIn('imported=1', loc, loc)
        defect = self.env['general.defect.improvement'].search(
            [('project_id', '=', self.started.id), ('defect_description', '=', rows[0]['description'])])
        self.assertEqual(len(defect), 1)
        self.assertEqual((defect.found_date, defect.deadline), (found, deadline),
                         '期限要照原檔（修改前會被改成發現日）')


@tagged('post_install', '-at_install', 'construction_portal')
class TestEagleParityPortalClosedDefect(TransactionCase):
    """DF-07（使用者 2026-11-20 決定拿掉）：已驗證／結案的缺失，前台也能改改善內容、刪照片。

    舊系統的缺失任何成員隨時可改、照片隨時可刪。修改前：改善導回 error=improve_locked、
    刪照片導回 error=photo_locked，詳情頁在這兩個狀態也不顯示刪除鈕。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(env, '回復原版前台結案缺失營造')
        cls.project = env['project.project'].create({
            'name': '回復原版結案缺失工程', 'code': 'EP-PF-DF', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id, **contractor_project_vals(cls.contractor)})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'EPCA', 'contractor_prefix': 'EPCR'})
        cls.leader = env['res.users'].create({
            'name': 'ep_closed_leader', 'login': 'ep_closed_leader',
            'groups_id': [(6, 0, [env.ref(LEADER).id])], **SUPERVISION_USER_VALS})
        env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': cls.leader.id})

    def _defect(self, state):
        defect = self.env['general.defect.improvement'].create({
            'project_id': self.project.id, 'record_type': 'supervision', 'check_type': 'construction',
            'defect_category': 'workmanship', 'defect_description': '回復原版結案缺失',
            'defect_location': 'B1', 'source_type': 'daily_check', 'state': 'notified'})
        defect.sudo().write({'state': state, 'improvement_result': '原本的改善成果'})
        attachment = self.env['ir.attachment'].create({
            'name': 'ep-df.png', 'raw': b'ep', 'res_model': 'supervision.photo'})
        photo = self.env['supervision.photo'].create({
            'project_id': self.project.id, 'general_defect_id': defect.id, 'photo_stage': 'after',
            'attachment_id': attachment.id})
        return defect, photo

    def _drive(self, method, *args, **kw):
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=self.leader)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = {}
            req.params = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                self.env.invalidate_all()
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        self.env.invalidate_all()
        return seen['vals'], html.decode() if isinstance(html, bytes) else str(html)

    def test_detail_shows_photo_delete_button_when_closed(self):
        for state in ('verified', 'closed'):
            defect, photo = self._defect(state)
            vals, html = self._drive(self.ctrl.portal_construction_defect_detail, defect.id)
            self.assertIsNotNone(vals, html)
            self.assertIn('/construction/defect/%d/photo/%d/delete' % (defect.id, photo.id), html, state)

    def test_photo_can_be_deleted_when_closed(self):
        for state in ('verified', 'closed'):
            defect, photo = self._defect(state)
            _vals, loc = self._drive(self.ctrl.portal_construction_defect_photo_delete, defect.id, photo.id)
            self.assertIn('photo_deleted', loc, '%s：%s' % (state, loc))
            self.assertFalse(photo.exists(), state)

    def test_improvement_can_be_rewritten_when_closed(self):
        for state in ('verified', 'closed'):
            defect, _photo = self._defect(state)
            _vals, loc = self._drive(self.ctrl.portal_construction_defect_improve, defect.id,
                                     improvement_description='結案後補充的改善成果', corrective_action='補記矯正措施')
            self.assertNotIn('error=', loc, state)
            defect = defect.sudo()
            self.assertEqual(defect.state, state, '狀態不能被改動')
            self.assertEqual(defect.improvement_action, '補記矯正措施', state)
