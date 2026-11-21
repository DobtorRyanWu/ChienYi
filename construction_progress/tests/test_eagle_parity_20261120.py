# -*- coding: utf-8 -*-
"""回復原版（1118 會議 A2）：沒有進度表也能填施工日誌。

會議起因：開口合約（預約式）沒有預定進度表，新系統卻要求先有「使用中的進度表」才能建日誌。
舊系統其實也有類似檢查（新增日誌時沒有進度資料會跳提示，只做在前端），但會議明確交辦拿掉。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（編號 DL-01）。
"""

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


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
    """舊系統儲存進度表只檢查「變更時間有填、預定進度不能全部是 0」（前端 views/PC/Schedule.vue addSchedule）。
    2026-11-20 照 1118 會議把新系統多的檢查全部拿掉；2026-11-22 使用者對照鈺鈞的意見表逐條決定後：
      維持拿掉：加總超過 100%（PG-03）、區間超出工期（PG-05）、單一區間超過 100% 或負數（PG-07 的後兩項）
      加回：結束日不早於開始日（PG-07）、累計展延不可負（PG-12）
      放寬加回：區間不重疊（PG-06），上一段結束日＝下一段開始日不算重疊"""

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

    def test_out_of_range_lines_allowed(self):
        """PG-05：區間早於開工日、晚於完工日不擋。"""
        self._line(-5, -1, 5.0, 30)                  # 早於開工日
        self._line(55, 70, 5.0, 40)                  # 晚於完工日
        self.env.flush_all()
        self.assertEqual(len(self.schedule.line_ids), 2)

    def test_lines_sharing_boundary_day_allowed(self):
        """PG-06：上一段結束日＝下一段開始日不算重疊（舊系統 2021 年的工程每月一段都這樣填）；
        開始日＝結束日、落在交界日上的校正列也不算。"""
        self._line(0, 19, 30.0, 10)
        self._line(19, 39, 30.0, 20)                 # 第 19 天同時是上一段的結束、這一段的開始
        self._line(39, 39, 0.0, 30)                  # 單日列落在交界日
        self._line(39, 59, 40.0, 40)
        self.env.flush_all()
        self.assertEqual(len(self.schedule.line_ids), 4)

    def test_truly_overlapping_lines_blocked(self):
        """PG-06：真的重疊（共用超過一個交界日）要擋，新增與修改都一樣。"""
        first = self._line(0, 19, 30.0, 10)
        with self.assertRaises(ValidationError):
            self._line(10, 29, 30.0, 20)             # 第 10～19 天重疊
        with self.assertRaises(ValidationError):
            self._line(5, 5, 0.0, 30)                # 單日列落在別的區間中間
        second = self._line(20, 39, 30.0, 20)
        with self.assertRaises(ValidationError):
            second.write({'date_start': first.date_start + timedelta(days=18)})

    def test_line_end_before_start_blocked(self):
        """PG-07：結束日早於開始日要擋；同一天不擋。"""
        self._line(5, 5, 10.0, 10)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._line(19, 10, 10.0, 20)
            self.env.flush_all()                     # 資料庫層的 CHECK 約束在 flush 時才會擋

    def test_line_over_100_and_negative_allowed(self):
        """PG-07 的後兩項維持拿掉：單一區間超過 100%、負數（沒有啟用校正）都存得進去。"""
        over = self._line(10, 19, 150.0, 20)
        negative = self._line(20, 29, -10.0, 30)
        self.env.flush_all()
        self.assertEqual((over.planned_progress, negative.planned_progress), (150.0, -10.0))

    def test_activate_wizard_opens_when_total_over_100(self):
        self._line(0, 29, 80.0, 10)
        self._line(30, 59, 80.0, 20)
        action = self.schedule.action_activate()
        self.assertEqual(action.get('type'), 'ir.actions.act_window', '總和超過 100% 也要開得出啟用視窗')

    def test_negative_cumulative_extension_blocked(self):
        """PG-12：累計展延不可為負數；0 與正數照常。"""
        self.schedule.write({'current_extension': 5})
        self.schedule.write({'current_extension': 0})
        with self.assertRaises(ValidationError):
            self.schedule.write({'current_extension': -5})

    def test_daily_log_on_boundary_day_does_not_crash(self):
        """兩段共用交界日時，那一天的日誌找「本日所屬區間」與本日預定進度不能出錯。"""
        self._line(0, 15, 30.0, 10)
        self._line(15, 29, 30.0, 20)
        self.schedule.write({'state': 'active'})
        self.project.write({'state': 'construction'})
        employee = self.env['hr.employee'].create({'name': '回復原版進度員工', 'company_id': self.env.company.id})
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': employee.id, 'log_date': self.d0 + timedelta(days=15)})
        self.assertTrue(sheet.progress_line_id)
        self.assertGreater(sheet.daily_planned_progress, 0.0)


@tagged('post_install', '-at_install', 'construction_progress')
class TestEagleParityActivate(TransactionCase):
    """PG-04：啟用進度表時不再檢查「區間要從開工日排到完工日、中間不能有空檔」。
    舊系統「自訂」模式可以任意排區間，儲存時不檢查涵蓋範圍。
    PG-12（累計展延是負數不能啟用）2026-11-22 使用者決定加回。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.d0 = fields.Date.today() - timedelta(days=30)
        cls.project = cls.env['project.project'].create({
            'name': '回復原版啟用進度表', 'code': 'EP-PG-A', 'project_type': 'general', 'state': 'draft',
            'company_id': cls.env.company.id,
            'contract_start_date': cls.d0, 'contract_end_date': cls.d0 + timedelta(days=59)})
        cls.schedule = cls.env['progress.schedule'].create({'project_id': cls.project.id, 'change_date': cls.d0})
        Line = cls.env['progress.schedule.line']
        # 第 5～14 天、第 30～39 天：沒有從開工日開始、沒有排到完工日、中間有空檔
        Line.create({'schedule_id': cls.schedule.id, 'sequence': 10, 'planned_progress': 40.0,
                     'date_start': cls.d0 + timedelta(days=5), 'date_end': cls.d0 + timedelta(days=14)})
        Line.create({'schedule_id': cls.schedule.id, 'sequence': 20, 'planned_progress': 60.0,
                     'date_start': cls.d0 + timedelta(days=30), 'date_end': cls.d0 + timedelta(days=39)})

    def test_activate_with_gaps_and_partial_coverage(self):
        self.schedule._do_activate()
        self.assertEqual(self.schedule.state, 'active')

    def test_activate_with_negative_cumulative_extension_blocked(self):
        """存檔時就會擋負數；這裡用 SQL 直接寫，模擬 11-20～11-22 之間已經存進去的負數，啟用時也要擋。"""
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE progress_schedule SET current_extension = -3, duration_extension = -3 WHERE id = %s',
            (self.schedule.id,))
        self.schedule.invalidate_recordset()
        self.assertLess(self.schedule.duration_extension, 0, '前提：累計展延是負數')
        with self.assertRaises(UserError):
            self.schedule._do_activate()
        self.assertNotEqual(self.schedule.state, 'active')
