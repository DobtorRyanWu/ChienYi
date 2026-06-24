# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class DailyLogAddItemsWizardExtra(models.TransientModel):
    """新增施工項目精靈 — 自填項目（純文字，不登記為契約工項）"""
    _name = 'daily.log.add.items.wizard.extra'
    _description = '新增施工項目精靈 - 自填項目'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'daily.log.add.items.wizard',
        string='精靈',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='排序', default=10)
    name = fields.Char(
        string='項目說明',
        required=True,
        help='自填項目名稱，如「工區復舊」',
    )
    location = fields.Char(string='位置')
    work_description = fields.Text(string='備註')
