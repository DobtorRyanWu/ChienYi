# -*- coding: utf-8 -*-
"""回復原版（1118 會議 A2）：沒有進度表也能填施工日誌。

會議起因：開口合約（預約式）沒有預定進度表，新系統卻要求先有「使用中的進度表」才能建日誌。
舊系統其實也有類似檢查（新增日誌時沒有進度資料會跳提示，只做在前端），但會議明確交辦拿掉。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（編號 DL-01）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestEagleParityDailyLog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': '回復原版測試員工', 'company_id': cls.env.company.id})

    def _log_without_schedule(self, project_type):
        project = self.env['project.project'].create({
            'name': '回復原版 %s' % project_type, 'code': 'EP-LOG-%s' % project_type.upper(),
            'project_type': project_type, 'state': 'construction', 'company_id': self.env.company.id})
        self.assertFalse(self.env['progress.schedule'].search_count([('project_id', '=', project.id)]),
                         '前提：這個工程沒有任何進度表')
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today() - timedelta(days=1)})
        self.assertTrue(sheet.exists())
        self.assertFalse(sheet.active_progress_schedule_id)
        self.assertEqual(sheet.daily_planned_progress, 0.0, '沒有進度表時本日預定進度是 0，不能出錯')
        return sheet

    def test_reservation_project_log_without_schedule(self):
        """DL-01：預約式（開口合約）沒有進度表也能建日誌。"""
        self._log_without_schedule('reservation')

    def test_general_project_log_without_schedule(self):
        """DL-01：一般式沒有進度表也能建日誌（會議交辦兩種都拿掉）。"""
        self._log_without_schedule('general')

    def test_log_without_schedule_can_be_marked_filled(self):
        """沒有進度表的日誌標成已填寫時，同步進度那段不能出錯。"""
        sheet = self._log_without_schedule('reservation')
        sheet.write({'daily_actual_progress': 1.5, 'state': 'filled'})
        self.assertEqual(sheet.state, 'filled')


@tagged('post_install', '-at_install', 'construction_progress')
class TestEagleParityScheduleInput(TransactionCase):
    """PG-03、PG-05、PG-06、PG-07、PG-12：舊系統儲存進度表只檢查「變更時間有填、預定進度不能全部是 0」
    （前端 views/PC/Schedule.vue addSchedule），其他都不檢查。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.d0 = fields.Date.today() - timedelta(days=30)
        cls.project = cls.env['project.project'].create({
            'name': '回復原版進度表', 'code': 'EP-PG', 'project_type': 'general', 'state': 'draft',
            'company_id': cls.env.company.id,
            'contract_start_date': cls.d0, 'contract_end_date': cls.d0 + timedelta(days=59)})
        cls.schedule = cls.env['progress.schedule'].create({'project_id': cls.project.id, 'change_date': cls.d0})

    def _line(self, start_offset, end_offset, planned, sequence=10):
        return self.env['progress.schedule.line'].create({
            'schedule_id': self.schedule.id, 'sequence': sequence,
            'date_start': self.d0 + timedelta(days=start_offset),
            'date_end': self.d0 + timedelta(days=end_offset), 'planned_progress': planned})

    def test_overlapping_and_out_of_range_lines_allowed(self):
        self._line(0, 19, 30.0, 10)
        self._line(10, 29, 30.0, 20)                 # 跟上一段重疊
        self._line(-5, -1, 5.0, 30)                  # 早於開工日
        self._line(55, 70, 5.0, 40)                  # 晚於完工日
        self.env.flush_all()
        self.assertEqual(len(self.schedule.line_ids), 4)

    def test_line_end_before_start_over_100_and_negative_allowed(self):
        backwards = self._line(9, 0, 10.0, 10)       # 結束日早於開始日
        over = self._line(10, 19, 150.0, 20)         # 單一區間超過 100%
        negative = self._line(20, 29, -10.0, 30)     # 負數（沒有啟用校正）
        self.env.flush_all()
        self.assertLess(backwards.date_end, backwards.date_start)
        self.assertEqual((over.planned_progress, negative.planned_progress), (150.0, -10.0))

    def test_activate_wizard_opens_when_total_over_100(self):
        self._line(0, 29, 80.0, 10)
        self._line(30, 59, 80.0, 20)
        action = self.schedule.action_activate()
        self.assertEqual(action.get('type'), 'ir.actions.act_window', '總和超過 100% 也要開得出啟用視窗')

    def test_negative_cumulative_extension_allowed(self):
        self.schedule.write({'current_extension': -5})
        self.env.flush_all()
        self.assertLess(self.schedule.duration_extension, 0)

    def test_daily_log_on_overlapping_schedule_does_not_crash(self):
        """區間重疊時，日誌找「本日所屬區間」與本日預定進度不能出錯。"""
        self._line(0, 19, 30.0, 10)
        self._line(10, 29, 30.0, 20)
        self.schedule.write({'state': 'active'})
        self.project.write({'state': 'construction'})
        employee = self.env['hr.employee'].create({'name': '回復原版進度員工', 'company_id': self.env.company.id})
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': employee.id, 'log_date': self.d0 + timedelta(days=15)})
        self.assertTrue(sheet.progress_line_id)
        self.assertGreater(sheet.daily_planned_progress, 0.0)
