# -*- coding: utf-8 -*-
"""11-16 六件 low 的回歸：已鎖定／自動鎖定的日誌不能被標成「已填寫」（否則等於繞過鎖定）。"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

LOCKED_STATES = ('locked', 'auto_locked')


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestMarkFilledBlockedWhenLocked(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.project = env['project.project'].create({
            'name': '標已填鎖定測試工程', 'code': 'DL-MF', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.employee = env['hr.employee'].create({'name': '標已填測試員工', 'company_id': env.company.id})
        env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})

    def _sheet(self, state='draft', days_ago=0):
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today() - timedelta(days=days_ago)})
        if state != 'draft':
            sheet.write({'state': state})
        return sheet

    def test_locked_sheet_cannot_be_marked_filled(self):
        """修前：鎖定的日誌被標成已填寫（狀態直接被改掉）。"""
        for days_ago, state in enumerate(LOCKED_STATES, start=1):   # 同一天不能有兩張日誌
            sheet = self._sheet(state, days_ago)
            with self.assertRaises(UserError, msg=state):
                sheet.action_mark_filled()
            self.assertEqual(sheet.state, state, '狀態不可被改掉')

    def test_draft_sheet_can_still_be_marked_filled(self):
        """正常案例：編輯中的日誌照樣能標已填寫。"""
        sheet = self._sheet('draft')
        sheet.action_mark_filled()
        self.assertEqual(sheet.state, 'filled')
