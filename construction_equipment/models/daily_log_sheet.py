# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class DailyLogSheet(models.Model):
    """
    施工日誌表單擴展

    擴展 construction_daily_log 模組的 daily.log.sheet
    新增人機記錄關聯欄位
    """
    _inherit = 'daily.log.sheet'

    # === 人機記錄關聯 ===
    man_machine_ids = fields.One2many(
        'daily.log.man.machine',
        'daily_log_id',
        string='人機記錄',
        help='施工日誌的人員與機具使用記錄')

    # === 人機統計 ===
    man_machine_personnel_count = fields.Integer(
        string='人員總數',
        compute='_compute_man_machine_totals',
        store=True,
        help='所有人員類型的總人數')

    man_machine_equipment_count = fields.Integer(
        string='機具總數',
        compute='_compute_man_machine_totals',
        store=True,
        help='所有機具的總數量')

    man_machine_total_man_hours = fields.Float(
        string='總人時',
        compute='_compute_man_machine_totals',
        store=True,
        help='所有人員的總工時')

    man_machine_total_equipment_hours = fields.Float(
        string='總機時',
        compute='_compute_man_machine_totals',
        store=True,
        help='所有機具的總使用時數')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('man_machine_ids.record_type',
                 'man_machine_ids.personnel_count',
                 'man_machine_ids.total_man_hours',
                 'man_machine_ids.equipment_count',
                 'man_machine_ids.total_equipment_hours')
    def _compute_man_machine_totals(self):
        """計算人機記錄統計"""
        for sheet in self:
            personnel_records = sheet.man_machine_ids.filtered(
                lambda r: r.record_type == 'personnel'
            )
            equipment_records = sheet.man_machine_ids.filtered(
                lambda r: r.record_type == 'equipment'
            )

            sheet.man_machine_personnel_count = sum(
                personnel_records.mapped('personnel_count')
            )
            sheet.man_machine_total_man_hours = sum(
                personnel_records.mapped('total_man_hours')
            )
            sheet.man_machine_equipment_count = sum(
                equipment_records.mapped('equipment_count')
            )
            sheet.man_machine_total_equipment_hours = sum(
                equipment_records.mapped('total_equipment_hours')
            )
