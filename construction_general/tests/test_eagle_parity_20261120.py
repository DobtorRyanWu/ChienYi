# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：進度報告期間的結束日可以早於開始日。

舊系統（EAGLE）對這些輸入沒有檢查：只檢查有沒有選期間（前端 views/PC/ProgressReport.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（GN-02）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_general')
class TestEagleParityProgressReport(TransactionCase):

    def test_period_end_before_start_allowed(self):
        project = self.env['project.project'].create({
            'name': '回復原版進度報告', 'code': 'EP-GN', 'project_type': 'general', 'state': 'construction',
            'company_id': self.env.company.id})
        today = fields.Date.today()
        report = self.env['general.progress.report'].create({
            'project_id': project.id, 'period_start': today, 'period_end': today - timedelta(days=3)})
        self.env.flush_all()
        self.assertLess(report.period_end, report.period_start)
