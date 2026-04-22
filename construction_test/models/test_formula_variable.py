# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re


class TestFormulaVariable(models.Model):
    """自訂公式變數"""
    _name = 'supervision.test.formula.variable'
    _description = '自訂公式變數'
    _order = 'sequence, id'

    standard_id = fields.Many2one(
        'supervision.test.standard',
        string='檢試驗項目',
        required=True,
        ondelete='cascade',
        index=True)

    sequence = fields.Integer(
        string='排序',
        default=10)

    name = fields.Char(
        string='變數名稱',
        required=True,
        help='在公式中使用的變數名稱（英文字母、數字和底線，不可以數字開頭）')

    value = fields.Float(
        string='數值',
        digits=(16, 4),
        required=True)

    description = fields.Char(
        string='說明',
        help='此變數的用途說明')

    @api.constrains('name')
    def _check_variable_name(self):
        """檢查變數名稱是否合法"""
        reserved = {'cumulative_qty'}
        for rec in self:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', rec.name):
                raise ValidationError(
                    f'變數名稱「{rec.name}」不合法，'
                    '只能使用英文字母、數字和底線，且不可以數字開頭')
            if rec.name in reserved:
                raise ValidationError(
                    f'「{rec.name}」為系統保留變數，請使用其他名稱')
