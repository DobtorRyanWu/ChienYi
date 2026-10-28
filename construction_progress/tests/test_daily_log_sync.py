# -*- coding: utf-8 -*-
"""日誌的本日實際進度要同步到進度表——不只在改本日進度時。

2026-10-28 以前只有「改了本日進度的值」才同步，而同步只算已填寫／自動鎖定／已鎖定的日誌：
正常流程是新增（草稿）→ 標記已填寫（只改狀態）→ 14 天自動鎖定（只改狀態），被填的那張永遠不在它自己觸發的
同步裡，進度表、首頁進度 %、進度報告都不會動（r1 審查 F3；jt 10-28 實查 5,679 張日誌全是自動鎖定）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestDailyLogSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=12)
        cls.project = cls.env['project.project'].create({
            'name': '進度同步測試', 'code': 'PRG-SYNC', 'project_type': 'general',
            'state': 'construction', 'company_id': company.id})
        cls.schedule = cls.env['progress.schedule'].create(
            {'project_id': cls.project.id, 'change_date': cls.d0 - timedelta(days=1)})
        Line = cls.env['progress.schedule.line']
        cls.l1 = Line.create({'schedule_id': cls.schedule.id, 'sequence': 10, 'date_start': cls.d0,
                              'date_end': cls.d0 + timedelta(days=9), 'planned_progress': 10.0})
        cls.l2 = Line.create({'schedule_id': cls.schedule.id, 'sequence': 20, 'date_start': cls.d0 + timedelta(days=10),
                              'date_end': cls.d0 + timedelta(days=19), 'planned_progress': 20.0})
        cls.schedule.write({'state': 'active'})
        cls.employee = cls.env['hr.employee'].create({'name': '進度同步測試員工', 'company_id': company.id})

    def _sheet(self, day, **vals):
        return self.env['daily.log.sheet'].create(dict({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': day}, **vals))

    def test_state_change_syncs(self):
        sheet = self._sheet(self.d0 + timedelta(days=1), daily_actual_progress=1.5)    # 草稿：同步不算
        self.assertEqual(self.l1.actual_progress, 0.0)
        sheet.write({'state': 'filled'})                                               # 只改狀態
        self.assertEqual(self.l1.actual_progress, 1.5)
        sheet.write({'state': 'auto_locked'})
        self.assertEqual(self.l1.actual_progress, 1.5)

    def test_create_in_counted_state_syncs(self):
        self._sheet(self.d0 + timedelta(days=2), daily_actual_progress=2.0, state='locked')
        self.assertEqual(self.l1.actual_progress, 2.0)

    def test_moving_to_another_interval_resyncs_both(self):
        sheet = self._sheet(self.d0 + timedelta(days=3), daily_actual_progress=1.0, state='filled')
        self.assertEqual((self.l1.actual_progress, self.l2.actual_progress), (1.0, 0.0))
        sheet.write({'log_date': self.d0 + timedelta(days=12)})
        self.assertEqual((self.l1.actual_progress, self.l2.actual_progress), (0.0, 1.0))
