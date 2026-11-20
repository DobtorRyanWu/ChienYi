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
