# -*- coding: utf-8 -*-
"""檢試驗預警活動的指派對象（B20，2026-11-02）。

原本寫死指派 base.user_admin（有 TODO），工程設的「檢試驗負責人」完全沒用。
改走 project._get_activity_user('test')。
"""
from types import SimpleNamespace

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_test')
class TestWarningActivityAssignee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.assignee = cls.env['res.users'].create({
            'name': '檢試驗負責人（測試）', 'login': 'test_activity_assignee',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.project = cls.env['project.project'].create({
            'name': '檢試驗指派測試', 'code': 'TST-ASSIGN', 'company_id': cls.env.company.id,
            'activity_test_user_id': cls.assignee.id})
        cls.task = cls.env['project.task'].create({
            'name': '混凝土澆置', 'project_id': cls.project.id, 'planned_qty': 100.0})
        cls.standard = cls.env['supervision.test.standard'].create({
            'name': '混凝土抗壓強度', 'material': '預拌混凝土', 'project_id': cls.project.id})
        cls.Line = cls.env['daily.log.line']

    def _warning(self, warning_type):
        return self.env['supervision.test.warning'].create({
            'project_id': self.project.id, 'standard_id': self.standard.id,
            'task_id': self.task.id, 'warning_type': warning_type,
            'warning_date': fields.Date.today(), 'achievement_rate': 96.0,
            'next_threshold_qty': 100.0})

    def test_warning_activity_goes_to_project_test_user(self):
        for warning_type in ('frequency', 'completion'):
            warning = self._warning(warning_type)
            self.Line._create_warning_activity(warning, self.project)
            activities = self.env['mail.activity'].search([
                ('res_model', '=', 'supervision.test.warning'), ('res_id', '=', warning.id)])
            self.assertEqual(activities.user_id, self.assignee, warning_type)

    def test_custom_formula_reminder_goes_to_project_test_user(self):
        line = SimpleNamespace(work_item_id=self.task, daily_qty=1.0, cumulative_qty=2.0)
        self.Line._create_custom_formula_daily_notification(line, self.standard, self.project)
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'supervision.test.standard'), ('res_id', '=', self.standard.id)])
        self.assertTrue(activities, '測試前提：有建立活動')
        self.assertEqual(activities.user_id, self.assignee)
