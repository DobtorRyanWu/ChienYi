# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class DailyLogMaterial(models.Model):
    """工地材料管理 — 含約定之重要材料使用狀況及數量等"""
    _name = 'daily.log.material'
    _description = '工地材料管理'
    _order = 'daily_log_id, sequence'

    sequence = fields.Integer('排序', default=10)
    daily_log_id = fields.Many2one(
        'daily.log.sheet', string='施工日誌',
        required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        related='daily_log_id.supervision_project_id', store=True)

    name = fields.Char(string='施工項目', required=True)
    unit = fields.Char(string='單位')
    contract_qty = fields.Float(string='契約數量')
    daily_qty = fields.Float(string='本日完成數量')
    cumulative_qty = fields.Float(string='累計完成數量')
    note = fields.Text(string='備註')
