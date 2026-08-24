# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class DailyLogSpecificItem(models.Model):
    """營造業特定項目 — 營造業專業工程特定施工項目使用狀況及數量等

    欄位結構與 daily.log.material（工地材料管理）一致，
    但兩者是施工日誌上兩個獨立的頁籤，不共用資料。
    """
    _name = 'daily.log.specific.item'
    _description = '營造業特定項目'
    _order = 'daily_log_id, sequence'

    sequence = fields.Integer('排序', default=10)
    daily_log_id = fields.Many2one(
        'daily.log.sheet', string='施工日誌',
        required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        related='daily_log_id.supervision_project_id', store=True)

    name = fields.Char(string='營造業專業工程特定施工項目', required=True)
    unit = fields.Char(string='單位')
    contract_qty = fields.Float(string='契約數量')
    daily_qty = fields.Float(string='本日完成數量')
    cumulative_qty = fields.Float(string='累計完成數量')
    note = fields.Text(string='備註')
