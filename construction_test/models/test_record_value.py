# -*- coding: utf-8 -*-
"""檢(試)驗紀錄的「試驗項目及數據」（新北契約附表11 每一項的合格值與試驗值）。

值一律存文字：規範值常寫成「≥280 kgf/cm²」「0.45 以下」，存成數字會丟資訊。
母表刪除時一起刪（ondelete='cascade'）——數據離開母表就沒有意義。
公司隔離靠 security.xml 的全域規則（規則不會從母表繼承）。
"""

from odoo import fields, models


class SupervisionTestRecordValue(models.Model):
    _name = 'supervision.test.record.value'
    _description = '檢(試)驗紀錄 試驗項目及數據'
    _order = 'record_id, sequence, id'

    record_id = fields.Many2one(
        'supervision.test.record', string='檢(試)驗紀錄',
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='record_id.company_id', store=True, index=True)
    sequence = fields.Integer(string='序號', default=10)
    item_name = fields.Char(string='試驗項目', required=True)
    standard_value = fields.Char(string='合格值')
    test_value = fields.Char(string='試驗值')
