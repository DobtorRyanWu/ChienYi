# -*- coding: utf-8 -*-
"""驗收紀錄與檢試驗記錄的樣板匯出。"""

from odoo import models


class AcceptanceFinal(models.Model):
    _name = 'acceptance.final'
    _inherit = ['acceptance.final', 'document.template.export.mixin']

    def action_export_acceptance_template(self):
        """匯出「驗收紀錄」樣板"""
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', 'acceptance_report'))


class SupervisionTestRecord(models.Model):
    _name = 'supervision.test.record'
    _inherit = ['supervision.test.record', 'document.template.export.mixin']

    def action_export_test_template(self):
        """匯出「材料試驗報告」送審函樣板"""
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', 'material_test'))
