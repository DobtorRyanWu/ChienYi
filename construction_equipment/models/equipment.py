# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionEquipment(models.Model):
    """
    機具設備

    設計參考: maintenance.equipment
    - 設備追蹤與序號管理
    - MTBF/MTTR 效能指標自動計算
    - 動態屬性 (Odoo 18 Properties)
    - 維護請求關聯
    """
    _name = 'supervision.equipment'
    _description = '機具設備'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # === 基本資料 ===
    name = fields.Char(
        string='設備名稱',
        required=True,
        tracking=True,
        index=True)

    active = fields.Boolean(
        string='啟用',
        default=True,
        tracking=True)

    # === 分類與識別 ===
    category_id = fields.Many2one(
        'supervision.equipment.category',
        string='設備分類',
        required=True,
        tracking=True,
        index=True)

    serial_no = fields.Char(
        string='機身號/序號',
        copy=False,
        tracking=True,
        index=True,
        help='設備唯一識別碼')

    model = fields.Char(
        string='型號',
        tracking=True)

    # === 動態屬性 (Odoo 18 Properties) ===
    equipment_properties = fields.Properties(
        string='設備規格',
        definition='category_id.equipment_properties_definition',
        copy=True,
        help='依據分類定義的動態屬性')

    # === 位置追蹤 ===
    location = fields.Char(
        string='目前位置',
        tracking=True,
        help='設備目前存放或使用位置')

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        tracking=True,
        index=True,
        help='目前使用此設備的工程')

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        default=lambda self: self.env.company,
        tracking=True,
        index=True)

    # === 擁有者資訊 ===
    owner_type = fields.Selection([
        ('own', '自有'),
        ('rent', '租賃'),
        ('subcontract', '協力廠商'),
    ], string='設備來源', default='own', tracking=True)

    owner_partner_id = fields.Many2one(
        'res.partner',
        string='擁有者/出租方',
        tracking=True,
        help='若為租賃或協力廠商設備，填寫擁有者')

    # === 技術規格 (相容舊系統欄位) ===
    capacity = fields.Char(
        string='容量/馬力',
        help='設備容量或馬力規格')

    operator_name = fields.Char(
        string='操作人員',
        help='指定操作人員姓名')

    # === 日期追蹤 ===
    effective_date = fields.Date(
        string='啟用日期',
        tracking=True,
        help='設備開始服役日期')

    warranty_date = fields.Date(
        string='保固到期日',
        tracking=True)

    scrap_date = fields.Date(
        string='報廢日期',
        tracking=True)

    # === 成本資訊 ===
    cost = fields.Float(
        string='設備成本/租金',
        tracking=True,
        help='購置成本或租賃費用')

    daily_rate = fields.Float(
        string='日租金',
        help='每日租賃費率')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        default=lambda self: self.env.company.currency_id)

    # === 維護相關 (參考 maintenance) ===
    technician_id = fields.Many2one(
        'res.users',
        string='負責技師',
        tracking=True,
        help='負責此設備維護的技師')

    maintenance_request_ids = fields.One2many(
        'supervision.equipment.request',
        'equipment_id',
        string='維護請求')

    maintenance_count = fields.Integer(
        string='維護次數',
        compute='_compute_maintenance_stats',
        store=True)

    open_maintenance_count = fields.Integer(
        string='進行中維護',
        compute='_compute_open_maintenance_count')

    # === 效能指標 (MTBF/MTTR) ===
    expected_mtbf = fields.Integer(
        string='預期 MTBF (天)',
        default=365,
        help='平均故障間隔時間 (Mean Time Between Failures)')

    mtbf = fields.Float(
        string='實際 MTBF (天)',
        compute='_compute_maintenance_stats',
        store=True,
        help='根據歷史維護記錄計算的實際平均故障間隔')

    mttr = fields.Float(
        string='MTTR (天)',
        compute='_compute_maintenance_stats',
        store=True,
        help='平均修復時間 (Mean Time To Repair)')

    estimated_next_failure = fields.Date(
        string='預計下次故障',
        compute='_compute_maintenance_stats',
        store=True,
        help='根據 MTBF 預測的下次故障日期')

    latest_failure_date = fields.Date(
        string='最近故障日期',
        compute='_compute_maintenance_stats',
        store=True)

    # === 使用統計 ===
    total_usage_hours = fields.Float(
        string='累計使用時數',
        compute='_compute_usage_stats',
        help='從施工日誌統計的累計使用時數')

    # === 狀態 ===
    equipment_state = fields.Selection([
        ('available', '可用'),
        ('in_use', '使用中'),
        ('maintenance', '維護中'),
        ('unavailable', '不可用'),
    ], string='設備狀態', default='available', tracking=True)

    # === 備註 ===
    note = fields.Html(
        string='備註')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('maintenance_request_ids.stage_id.done',
                 'maintenance_request_ids.close_date',
                 'maintenance_request_ids.request_date',
                 'maintenance_request_ids.maintenance_type')
    def _compute_maintenance_stats(self):
        """
        計算 MTBF/MTTR 效能指標

        參考 maintenance 模組計算邏輯：
        - MTBF = (最近故障日 - 啟用日) / 故障次數
        - MTTR = 總修復天數 / 故障次數
        """
        for equipment in self:
            # 只計算已完成的糾正性維護 (故障維修)
            done_requests = equipment.maintenance_request_ids.filtered(
                lambda r: r.maintenance_type == 'corrective' and r.stage_id.done
            )
            equipment.maintenance_count = len(done_requests)

            if done_requests:
                # 計算 MTTR (平均修復時間)
                total_repair_days = 0
                valid_repairs = 0
                for r in done_requests:
                    if r.close_date and r.request_date:
                        repair_days = (r.close_date - r.request_date).days
                        total_repair_days += max(repair_days, 1)  # 至少 1 天
                        valid_repairs += 1

                if valid_repairs > 0:
                    equipment.mttr = total_repair_days / valid_repairs
                else:
                    equipment.mttr = 0

                # 計算最近故障日期
                request_dates = [r.request_date for r in done_requests if r.request_date]
                if request_dates:
                    equipment.latest_failure_date = max(request_dates)
                else:
                    equipment.latest_failure_date = False

                # 計算 MTBF (平均故障間隔)
                if equipment.effective_date and equipment.latest_failure_date:
                    days_in_service = (equipment.latest_failure_date - equipment.effective_date).days
                    if days_in_service > 0:
                        equipment.mtbf = days_in_service / len(done_requests)
                        # 預計下次故障日期
                        equipment.estimated_next_failure = (
                            equipment.latest_failure_date + timedelta(days=equipment.mtbf)
                        )
                    else:
                        equipment.mtbf = 0
                        equipment.estimated_next_failure = False
                else:
                    equipment.mtbf = 0
                    equipment.estimated_next_failure = False
            else:
                equipment.mttr = 0
                equipment.mtbf = 0
                equipment.latest_failure_date = False
                equipment.estimated_next_failure = False

    def _compute_open_maintenance_count(self):
        """計算進行中的維護請求數量"""
        for equipment in self:
            equipment.open_maintenance_count = len(
                equipment.maintenance_request_ids.filtered(
                    lambda r: not r.stage_id.done
                )
            )

    def _compute_usage_stats(self):
        """從施工日誌計算使用統計"""
        ManMachine = self.env['daily.log.man.machine']
        for equipment in self:
            records = ManMachine.search([
                ('equipment_id', '=', equipment.id),
                ('record_type', '=', 'equipment'),
            ])
            equipment.total_usage_hours = sum(records.mapped('equipment_hours'))

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """分類變更時，設定預設負責技師"""
        if self.category_id and self.category_id.default_technician_id:
            if not self.technician_id:
                self.technician_id = self.category_id.default_technician_id

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """工程變更時，更新位置資訊"""
        if self.project_id:
            self.location = self.project_id.name

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('effective_date', 'scrap_date')
    def _check_dates(self):
        """驗證日期合理性"""
        for equipment in self:
            if equipment.effective_date and equipment.scrap_date:
                if equipment.scrap_date < equipment.effective_date:
                    raise ValidationError('報廢日期不得早於啟用日期')

    @api.constrains('expected_mtbf')
    def _check_expected_mtbf(self):
        """驗證預期 MTBF"""
        for equipment in self:
            if equipment.expected_mtbf < 0:
                raise ValidationError('預期 MTBF 不得為負數')

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    def unlink(self):
        """刪除前檢查"""
        for equipment in self:
            if equipment.maintenance_request_ids.filtered(lambda r: not r.stage_id.done):
                raise UserError(f'設備 {equipment.name} 仍有進行中的維護請求，無法刪除')
        return super().unlink()

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_view_maintenance_requests(self):
        """查看維護請求"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 維護請求',
            'res_model': 'supervision.equipment.request',
            'view_mode': 'kanban,list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {
                'default_equipment_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }

    def action_create_maintenance_request(self):
        """建立新維護請求"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '建立維護請求',
            'res_model': 'supervision.equipment.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_equipment_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
                'default_user_id': self.technician_id.id if self.technician_id else False,
            },
        }

    def action_set_available(self):
        """設為可用"""
        self.write({'equipment_state': 'available'})

    def action_set_in_use(self):
        """設為使用中"""
        self.write({'equipment_state': 'in_use'})

    def action_set_maintenance(self):
        """設為維護中"""
        self.write({'equipment_state': 'maintenance'})

    def action_set_unavailable(self):
        """設為不可用"""
        self.write({'equipment_state': 'unavailable'})

    # -------------------------------------------------------------------------
    # SQL Constraints
    # -------------------------------------------------------------------------

    _sql_constraints = [
        ('serial_no_unique',
         'UNIQUE(serial_no)',
         '機身號/序號不可重複！'),
    ]
