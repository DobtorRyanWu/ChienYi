# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class DailyLogSheet(models.Model):
    """
    施工日誌表單擴展

    擴展 construction_daily_log 模組的 daily.log.sheet
    新增人機使用明細關聯欄位
    """
    _inherit = 'daily.log.sheet'

    # === 人機使用明細關聯 ===
    man_machine_detail_ids = fields.One2many(
        'daily.log.man.machine.detail',
        'daily_log_id',
        string='人機使用記錄',
        help='選擇人機項目並登記當日使用量')

    # === 人機統計 ===
    total_man_machine_hours = fields.Float(
        string='人機總時數',
        compute='_compute_man_machine_totals',
        store=True,
        help='當日所有人機使用的總時數')

    # === 舊版欄位（向後兼容，已廢棄） ===
    # 這些欄位保留以避免升級錯誤，但已不再使用
    man_machine_ids = fields.One2many(
        'daily.log.man.machine',
        compute='_compute_legacy_man_machine',
        string='人機記錄（已廢棄）',
        help='此欄位已廢棄，請使用 man_machine_detail_ids')

    man_machine_personnel_count = fields.Integer(
        string='人員總數（已廢棄）',
        compute='_compute_legacy_stats',
        help='此欄位已廢棄')

    man_machine_equipment_count = fields.Integer(
        string='機具總數（已廢棄）',
        compute='_compute_legacy_stats',
        help='此欄位已廢棄')

    man_machine_total_man_hours = fields.Float(
        string='總人時（已廢棄）',
        compute='_compute_legacy_stats',
        help='此欄位已廢棄')

    man_machine_total_equipment_hours = fields.Float(
        string='總機時（已廢棄）',
        compute='_compute_legacy_stats',
        help='此欄位已廢棄')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('man_machine_detail_ids.hours')
    def _compute_man_machine_totals(self):
        """計算人機使用統計"""
        for sheet in self:
            sheet.total_man_machine_hours = sum(
                sheet.man_machine_detail_ids.mapped('hours')
            )

    def _compute_legacy_man_machine(self):
        """舊版相容：提供空的 man_machine_ids"""
        for sheet in self:
            sheet.man_machine_ids = False

    def _compute_legacy_stats(self):
        """舊版相容：提供零值統計"""
        for sheet in self:
            sheet.man_machine_personnel_count = 0
            sheet.man_machine_equipment_count = 0
            sheet.man_machine_total_man_hours = 0.0
            sheet.man_machine_total_equipment_hours = 0.0
