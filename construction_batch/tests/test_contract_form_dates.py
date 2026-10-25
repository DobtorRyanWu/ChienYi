# -*- coding: utf-8 -*-
"""報表／下載中心「契約附表」不能用到隱藏起來的舊截止日（2.10.0 程式審查 M1）。

契約附表不篩日期、畫面上把起訖日期藏起來；但使用者若先選施工日誌填了截止日、再切到
契約附表，欄位只是看不到、值還在。表頭的「填表日期」與「截至今天的進度」以截止日為準
（construction_template/mappings/project_header.py），於是會靜靜算在那個舊日期。
"""

from odoo.tests import Form, TransactionCase, tagged

from odoo.addons.construction_template.utils import record_filter


@tagged('post_install', '-at_install')
class TestContractFormDates(TransactionCase):

    def test_hidden_dates_are_not_exported(self):
        project = self.env['project.project'].create({
            'name': '契約附表日期測試', 'code': 'BATCH-CFDATE', 'company_id': self.env.company.id})
        form = Form(self.env['batch.download.wizard'])
        form.download_type = 'daily_log'
        form.date_from = '2026-01-01'
        form.date_to = '2026-01-31'
        form.download_type = 'contract_form'
        form.project_id = project
        wizard = form.save()
        ctx = wizard._export_context()
        self.assertFalse(ctx.get(record_filter.CTX_FROM))
        self.assertFalse(ctx.get(record_filter.CTX_TO))

    def test_filtered_types_keep_dates(self):
        wizard = self.env['batch.download.wizard'].create({
            'download_type': 'daily_log', 'date_from': '2026-01-01', 'date_to': '2026-01-31'})
        self.assertEqual(str(wizard._export_context()[record_filter.CTX_TO]), '2026-01-31')
