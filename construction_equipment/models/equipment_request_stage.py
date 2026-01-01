# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class EquipmentRequestStage(models.Model):
    """
    維護請求階段

    設計參考: maintenance.stage
    - 看板階段管理
    - 完成標記支援 MTBF/MTTR 計算
    """
    _name = 'supervision.equipment.request.stage'
    _description = '維護請求階段'
    _order = 'sequence, id'

    # === 基本資料 ===
    name = fields.Char(
        string='階段名稱',
        required=True,
        translate=True)

    sequence = fields.Integer(
        string='排序',
        default=20)

    # === 看板設定 ===
    fold = fields.Boolean(
        string='看板摺疊',
        default=False,
        help='在看板視圖中是否預設摺疊')

    # === 完成標記 ===
    done = fields.Boolean(
        string='完成標記',
        default=False,
        help='標記此階段代表維護已完成，用於 MTBF/MTTR 計算')

    # === 請求統計 ===
    request_count = fields.Integer(
        string='請求數量',
        compute='_compute_request_count')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    def _compute_request_count(self):
        """計算此階段的請求數量"""
        Request = self.env['supervision.equipment.request']
        for stage in self:
            stage.request_count = Request.search_count([
                ('stage_id', '=', stage.id)
            ])

    # -------------------------------------------------------------------------
    # SQL Constraints
    # -------------------------------------------------------------------------

    _sql_constraints = [
        ('name_unique',
         'UNIQUE(name)',
         '階段名稱不可重複！'),
    ]
