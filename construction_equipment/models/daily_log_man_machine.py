# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DailyLogManMachine(models.Model):
    """
    人機項目主檔 - 工程級設定

    每個工程建立可用的人員/機具項目，設定單價
    施工日誌中選擇這些項目登記使用量
    """
    _name = 'daily.log.man.machine'
    _description = '人機項目主檔'
    _order = 'project_id, record_type, sequence'

    # === 基本資料 ===
    sequence = fields.Integer(
        string='排序',
        default=10)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        help='此人機項目所屬的工程')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True)

    # === 記錄類型 ===
    record_type = fields.Selection([
        ('personnel', '人員'),
        ('equipment', '機具'),
    ], string='記錄類型', required=True, default='personnel')

    # === 人員/機具設定 ===
    personnel_type_id = fields.Many2one(
        'personnel.type',
        string='人員機具設定',
        required=True,
        domain="[('record_type', '=', record_type)]")

    # === 計價資訊 ===
    unit_price = fields.Float(
        string='單價',
        help='每小時或每天的單價')

    unit = fields.Selection([
        ('hour', '小時'),
        ('day', '天'),
        ('time', '次'),
    ], string='計價單位', default='hour')

    # === 使用統計（累計自使用明細） ===
    usage_detail_ids = fields.One2many(
        'daily.log.man.machine.detail',
        'man_machine_id',
        string='使用明細記錄')

    total_quantity = fields.Float(
        string='總數量',
        compute='_compute_totals',
        store=True,
        help='累計使用數量/人次')

    total_hours = fields.Float(
        string='總時數',
        compute='_compute_totals',
        store=True,
        help='累計使用時數')

    # === 備註 ===
    note = fields.Text('備註')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('usage_detail_ids.quantity',
                 'usage_detail_ids.hours')
    def _compute_totals(self):
        """從使用明細累計總量"""
        for record in self:
            record.total_quantity = sum(record.usage_detail_ids.mapped('quantity'))
            record.total_hours = sum(record.usage_detail_ids.mapped('hours'))

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('record_type', 'personnel_type_id')
    def _check_record_data(self):
        """驗證記錄資料完整性"""
        for record in self:
            if not record.personnel_type_id:
                raise ValidationError('必須選擇人員機具設定')

    # -------------------------------------------------------------------------
    # Display Name
    # -------------------------------------------------------------------------

    @api.depends('personnel_type_id', 'personnel_type_id.name', 'record_type', 'unit_price', 'unit')
    def _compute_display_name(self):
        """Odoo 18 使用 _compute_display_name 取代 name_get"""
        for record in self:
            name = record.personnel_type_id.name if record.personnel_type_id else ('人員' if record.record_type == 'personnel' else '機具')
            if record.unit_price:
                name = f'{name} ({record.unit_price}元/{record.unit})'
            record.display_name = name
