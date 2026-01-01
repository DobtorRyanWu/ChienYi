# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, Command
from odoo.exceptions import ValidationError


class DailyLogManMachine(models.Model):
    """
    施工日誌 - 人機管理

    對應舊系統: dailyRecord.manMachineItems / manMachineUsage
    - 人員記錄：各類型施工人員出工統計
    - 機具記錄：設備使用時數與數量統計
    """
    _name = 'daily.log.man.machine'
    _description = '施工日誌人機管理'
    _order = 'daily_log_id, record_type, sequence'

    # === 關聯欄位 ===
    daily_log_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌',
        required=True,
        ondelete='cascade',
        index=True)

    project_id = fields.Many2one(
        related='daily_log_id.project_id',
        string='所屬工程',
        store=True,
        index=True)

    company_id = fields.Many2one(
        related='daily_log_id.company_id',
        string='施工廠商',
        store=True)

    date = fields.Date(
        related='daily_log_id.date_start',
        string='日期',
        store=True)

    sequence = fields.Integer(
        string='排序',
        default=10)

    # === 記錄類型 ===
    record_type = fields.Selection([
        ('personnel', '人員'),
        ('equipment', '機具'),
    ], string='記錄類型', required=True, default='personnel')

    # === 人員欄位 ===
    personnel_type = fields.Selection([
        ('supervisor', '監造人員'),
        ('site_manager', '工地主任'),
        ('safety_officer', '安衛人員'),
        ('quality_officer', '品管人員'),
        ('skilled_worker', '技術工人'),
        ('general_worker', '一般工人'),
        ('equipment_operator', '機具操作員'),
        ('other', '其他'),
    ], string='人員類型')

    personnel_count = fields.Integer(
        string='人數',
        default=0,
        help='該類型人員出工人數')

    work_hours = fields.Float(
        string='工時',
        default=8.0,
        help='平均工作時數')

    total_man_hours = fields.Float(
        string='總人時',
        compute='_compute_total_man_hours',
        store=True,
        help='人數 x 工時')

    # === 機具欄位 ===
    equipment_id = fields.Many2one(
        'supervision.equipment',
        string='機具設備',
        domain="[('project_id', '=', project_id)]",
        help='從設備主檔選擇')

    equipment_name = fields.Char(
        string='機具名稱',
        help='若未建檔可手填設備名稱')

    equipment_display_name = fields.Char(
        string='設備顯示名稱',
        compute='_compute_equipment_display_name',
        store=True)

    equipment_capacity = fields.Char(
        string='規格容量',
        help='設備規格或容量說明')

    equipment_count = fields.Integer(
        string='數量',
        default=1,
        help='設備使用數量')

    equipment_hours = fields.Float(
        string='使用時數',
        default=0.0,
        help='設備使用總時數')

    total_equipment_hours = fields.Float(
        string='總機時',
        compute='_compute_total_equipment_hours',
        store=True,
        help='數量 x 使用時數')

    # === 操作人員 ===
    operator_name = fields.Char(
        string='操作人員',
        help='設備操作人員姓名')

    # === 備註 ===
    note = fields.Text(
        string='備註')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('personnel_count', 'work_hours')
    def _compute_total_man_hours(self):
        """計算總人時"""
        for record in self:
            record.total_man_hours = record.personnel_count * record.work_hours

    @api.depends('equipment_count', 'equipment_hours')
    def _compute_total_equipment_hours(self):
        """計算總機時"""
        for record in self:
            record.total_equipment_hours = record.equipment_count * record.equipment_hours

    @api.depends('equipment_id', 'equipment_name')
    def _compute_equipment_display_name(self):
        """計算設備顯示名稱"""
        for record in self:
            if record.equipment_id:
                record.equipment_display_name = record.equipment_id.name
            else:
                record.equipment_display_name = record.equipment_name or ''

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        """設備變更時，自動帶入相關資訊"""
        if self.equipment_id:
            self.equipment_name = self.equipment_id.name
            self.equipment_capacity = self.equipment_id.capacity
            if self.equipment_id.operator_name:
                self.operator_name = self.equipment_id.operator_name

    @api.onchange('record_type')
    def _onchange_record_type(self):
        """記錄類型變更時，清除不相關欄位"""
        if self.record_type == 'personnel':
            self.equipment_id = False
            self.equipment_name = False
            self.equipment_capacity = False
            self.equipment_count = 0
            self.equipment_hours = 0.0
        else:
            self.personnel_type = False
            self.personnel_count = 0
            self.work_hours = 8.0

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('record_type', 'personnel_type', 'equipment_id', 'equipment_name')
    def _check_record_data(self):
        """驗證記錄資料完整性"""
        for record in self:
            if record.record_type == 'personnel':
                if not record.personnel_type:
                    raise ValidationError('人員記錄必須選擇人員類型')
            else:  # equipment
                if not record.equipment_id and not record.equipment_name:
                    raise ValidationError('機具記錄必須選擇設備或填寫機具名稱')

    @api.constrains('personnel_count')
    def _check_personnel_count(self):
        """驗證人數"""
        for record in self:
            if record.record_type == 'personnel' and record.personnel_count < 0:
                raise ValidationError('人數不得為負數')

    @api.constrains('equipment_count')
    def _check_equipment_count(self):
        """驗證設備數量"""
        for record in self:
            if record.record_type == 'equipment' and record.equipment_count < 0:
                raise ValidationError('設備數量不得為負數')

    @api.constrains('work_hours', 'equipment_hours')
    def _check_hours(self):
        """驗證時數"""
        for record in self:
            if record.work_hours < 0 or record.equipment_hours < 0:
                raise ValidationError('時數不得為負數')

    # -------------------------------------------------------------------------
    # Name Methods
    # -------------------------------------------------------------------------

    def name_get(self):
        """顯示名稱"""
        result = []
        for record in self:
            if record.record_type == 'personnel':
                name = dict(self._fields['personnel_type'].selection).get(
                    record.personnel_type, '人員'
                )
                name = f'{name} ({record.personnel_count}人)'
            else:
                name = record.equipment_display_name or '機具'
                name = f'{name} ({record.equipment_count}台)'
            result.append((record.id, name))
        return result
