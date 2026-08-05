# -*- coding: utf-8 -*-
"""估驗計價 → 工程估驗計價單樣板匯出。"""

from odoo import models

TEMPLATE_TYPE = 'estimate_report'


class PaymentEstimate(models.Model):
    _name = 'payment.estimate'
    _inherit = ['payment.estimate', 'document.template.export.mixin']

    def action_export_estimate_template(self):
        """把本張估驗的資料填進「工程估驗計價單」樣板並下載。"""
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', TEMPLATE_TYPE))
