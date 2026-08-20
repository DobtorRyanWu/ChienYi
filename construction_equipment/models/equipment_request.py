# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionEquipmentRequest(models.Model):
    """
    設備維護請求

    設計參考: maintenance.request
    - 糾正性維護 (corrective) / 預防性維護 (preventive)
    - 看板工作流程
    - 循環維護排程
    """
    _name = 'supervision.equipment.request'
    _description = '設備維護請求'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
    _order = 'priority desc, schedule_date asc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='維護主題',
        required=True,
        tracking=True)

    # === 設備關聯 ===
    equipment_id = fields.Many2one(
        'supervision.equipment',
        string='設備',
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True)

    category_id = fields.Many2one(
        related='equipment_id.category_id',
        string='設備分類',
        store=True,
        index=True)

    project_id = fields.Many2one(
        related='equipment_id.project_id',
        string='所屬工程',
        store=True,
        index=True)

    company_id = fields.Many2one(
        related='equipment_id.company_id',
        string='管理公司',
        store=True,
        index=True)

    # === 維護類型 ===
    maintenance_type = fields.Selection([
        ('corrective', '糾正性維護'),
        ('preventive', '預防性維護'),
    ], string='維護類型', default='corrective', required=True, tracking=True,
       help='糾正性維護：故障後維修\n預防性維護：定期保養預防')

    # === 日期 ===
    request_date = fields.Date(
        string='請求日期',
        default=fields.Date.today,
        tracking=True,
        index=True)

    schedule_date = fields.Datetime(
        string='排定時間',
        tracking=True,
        help='預定執行維護的時間')

    close_date = fields.Date(
        string='完成日期',
        readonly=True,
        tracking=True)

    duration = fields.Float(
        string='預計耗時 (小時)',
        help='預估維護所需時間')

    actual_duration = fields.Float(
        string='實際耗時 (小時)',
        help='實際維護使用時間')

    # === 優先級與狀態 ===
    priority = fields.Selection([
        ('0', '低'),
        ('1', '一般'),
        ('2', '高'),
        ('3', '緊急'),
    ], string='優先級', default='1', tracking=True)

    stage_id = fields.Many2one(
        'supervision.equipment.request.stage',
        string='階段',
        default=lambda self: self._default_stage_id(),
        tracking=True,
        group_expand='_group_expand_stage_ids',
        index=True)

    kanban_state = fields.Selection([
        ('normal', '正常'),
        ('blocked', '阻擋'),
        ('done', '完成'),
    ], string='看板狀態', default='normal', tracking=True)

    color = fields.Integer(
        string='顏色',
        compute='_compute_color')

    # === 指派 ===
    user_id = fields.Many2one(
        'res.users',
        string='負責技師',
        tracking=True,
        index=True)

    owner_user_id = fields.Many2one(
        'res.users',
        string='請求者',
        default=lambda self: self.env.uid,
        tracking=True)

    # === 描述與內容 ===
    description = fields.Html(
        string='問題描述',
        help='詳細描述問題或維護需求')

    diagnosis = fields.Html(
        string='診斷結果',
        help='維護診斷與分析結果')

    repair_notes = fields.Html(
        string='維修記錄',
        help='維修過程與結果記錄')

    # === 循環維護 (預防性專用) ===
    recurring_maintenance = fields.Boolean(
        string='循環維護',
        default=False,
        help='啟用定期循環維護排程')

    repeat_interval = fields.Integer(
        string='重複間隔',
        default=1)

    repeat_unit = fields.Selection([
        ('day', '天'),
        ('week', '週'),
        ('month', '月'),
        ('year', '年'),
    ], string='重複單位', default='month')

    repeat_until = fields.Date(
        string='重複至',
        help='循環維護的結束日期')

    # === 成本資訊 ===
    parts_cost = fields.Float(
        string='零件費用',
        tracking=True)

    labor_cost = fields.Float(
        string='人工費用',
        tracking=True)

    total_cost = fields.Float(
        string='總費用',
        compute='_compute_total_cost',
        store=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='company_id.currency_id')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'equipment_request_attachment_rel',
        'request_id', 'attachment_id',
        string='相關附件')

    def _attachment_default_category(self):
        """機具申請附件 → 11-工程資料 / 06-廠商資料"""
        return self.env.ref(
            'construction_supervision_base.cat_11_06',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_default_folder(self):
        """機具申請附件 → 11-工程資料 / 06-廠商資料 / 機具申請 / <這張申請單>

        多墊一層「機具申請」：06-廠商資料 底下還有證照、保險等其他廠商文件，
        不先分一層的話，一堆申請單會跟其他文件混在同一層。
        """
        return self._attachment_category_folder(['機具申請', self._attachment_folder_label()])

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    # -------------------------------------------------------------------------
    # Default Methods
    # -------------------------------------------------------------------------

    def _default_stage_id(self):
        """取得預設階段"""
        return self.env['supervision.equipment.request.stage'].search([], limit=1)

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('priority', 'kanban_state')
    def _compute_color(self):
        """計算看板顏色"""
        for request in self:
            if request.kanban_state == 'blocked':
                request.color = 1  # 紅色
            elif request.kanban_state == 'done':
                request.color = 10  # 綠色
            elif request.priority == '3':
                request.color = 2  # 橙色
            elif request.priority == '2':
                request.color = 3  # 黃色
            else:
                request.color = 0  # 預設

    @api.depends('parts_cost', 'labor_cost')
    def _compute_total_cost(self):
        """計算總費用"""
        for request in self:
            request.total_cost = request.parts_cost + request.labor_cost

    @api.depends('schedule_date', 'stage_id.done')
    def _compute_overdue(self):
        """計算是否逾期"""
        now = fields.Datetime.now()
        for request in self:
            if request.stage_id.done:
                request.is_overdue = False
            elif request.schedule_date:
                request.is_overdue = request.schedule_date < now
            else:
                request.is_overdue = False

    # -------------------------------------------------------------------------
    # Group Expand Methods
    # -------------------------------------------------------------------------

    @api.model
    def _group_expand_stage_ids(self, stages, domain, order):
        """看板視圖顯示所有階段"""
        return stages.search([], order=order)

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        """設備變更時，設定預設負責技師"""
        if self.equipment_id:
            if self.equipment_id.technician_id and not self.user_id:
                self.user_id = self.equipment_id.technician_id
            # 更新設備狀態為維護中
            if self.maintenance_type == 'corrective':
                self.equipment_id.equipment_state = 'maintenance'

    @api.onchange('maintenance_type')
    def _onchange_maintenance_type(self):
        """維護類型變更時，調整相關設定"""
        if self.maintenance_type == 'preventive':
            self.recurring_maintenance = True
        else:
            self.recurring_maintenance = False

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立維護請求"""
        requests = super().create(vals_list)
        # 更新設備狀態
        for request in requests:
            if request.maintenance_type == 'corrective' and request.equipment_id:
                request.equipment_id.equipment_state = 'maintenance'
        return requests

    def write(self, vals):
        """更新維護請求"""
        # 處理階段完成
        if 'stage_id' in vals:
            new_stage = self.env['supervision.equipment.request.stage'].browse(vals['stage_id'])
            if new_stage.done:
                vals['close_date'] = fields.Date.today()
                vals['kanban_state'] = 'normal'
                # 處理循環維護
                for request in self.filtered(lambda r: r.recurring_maintenance):
                    request._create_next_recurring_request()
                # 恢復設備狀態
                for request in self:
                    if request.equipment_id:
                        request.equipment_id.equipment_state = 'available'

        return super().write(vals)

    def unlink(self):
        """刪除維護請求前檢查"""
        for request in self:
            if request.stage_id.done:
                raise UserError('已完成的維護請求無法刪除')
        return super().unlink()

    # -------------------------------------------------------------------------
    # Business Methods
    # -------------------------------------------------------------------------

    def _create_next_recurring_request(self):
        """建立下一個循環維護請求"""
        self.ensure_one()
        if not self.recurring_maintenance:
            return

        # 計算下次日期
        if self.repeat_unit == 'day':
            delta = relativedelta(days=self.repeat_interval)
        elif self.repeat_unit == 'week':
            delta = relativedelta(weeks=self.repeat_interval)
        elif self.repeat_unit == 'month':
            delta = relativedelta(months=self.repeat_interval)
        else:  # year
            delta = relativedelta(years=self.repeat_interval)

        next_date = fields.Date.today() + delta

        # 檢查是否超過結束日期
        if self.repeat_until and next_date > self.repeat_until:
            return

        # 建立新請求
        self.copy({
            'request_date': next_date,
            'schedule_date': fields.Datetime.now() + delta,
            'close_date': False,
            'stage_id': self._default_stage_id().id,
            'kanban_state': 'normal',
        })

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_mark_done(self):
        """標記完成"""
        done_stage = self.env['supervision.equipment.request.stage'].search([
            ('done', '=', True)
        ], limit=1)
        if not done_stage:
            raise UserError('請先設定完成階段')
        self.write({'stage_id': done_stage.id})

    def action_mark_blocked(self):
        """標記阻擋"""
        self.write({'kanban_state': 'blocked'})

    def action_mark_normal(self):
        """標記正常"""
        self.write({'kanban_state': 'normal'})

    def action_assign_to_me(self):
        """指派給自己"""
        self.write({'user_id': self.env.uid})

    def action_send_notification(self):
        """發送通知給負責技師"""
        for request in self:
            if request.user_id:
                request.message_post(
                    body=f'維護請求 {request.name} 已指派給您，請儘速處理。',
                    partner_ids=request.user_id.partner_id.ids,
                    message_type='notification',
                )

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('repeat_interval')
    def _check_repeat_interval(self):
        """驗證重複間隔"""
        for request in self:
            if request.recurring_maintenance and request.repeat_interval <= 0:
                raise ValidationError('重複間隔必須大於 0')

    @api.constrains('schedule_date', 'request_date')
    def _check_dates(self):
        """驗證日期"""
        for request in self:
            if request.schedule_date and request.request_date:
                if request.schedule_date.date() < request.request_date:
                    raise ValidationError('排定時間不得早於請求日期')
