# -*- coding: utf-8 -*-
"""計畫送審、材料送審的單筆表單匯出（新北市政府工程契約附表6-2、附表7，2026-10-25）。

匯出邏輯在 construction_template 的 document.template.export.mixin；這兩個模型屬於
construction_review，而 construction_template 不依賴它，所以掛在同時依賴兩邊的這個模組。
"""

from odoo import models


class SupervisionPlanControl(models.Model):
    _name = 'supervision.plan.control'
    _inherit = ['supervision.plan.control', 'document.template.export.mixin']

    def action_export_plan_review_stamp(self):
        """附表6-2 計畫送審核章表（裝訂於計畫首頁）"""
        self.ensure_one()
        return self._export_document_template('plan_review_stamp')


class SupervisionReviewApplication(models.Model):
    _name = 'supervision.review.application'
    _inherit = ['supervision.review.application', 'document.template.export.mixin']

    def action_export_material_review_record(self):
        """附表7 材料設備申請及審查紀錄表"""
        self.ensure_one()
        return self._export_document_template('material_review_record')
