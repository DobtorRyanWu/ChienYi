# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ProjectTask(models.Model):
    """
    契約工項擴展

    擴展 project.task 支援：
    - 廠商分配 (assigned_company_id)
    - 預算追蹤 (planned_qty, unit_price, planned_amount)
    - 時間計畫 (planned_date_start, planned_date_end)
    - 實際執行追蹤 (actual_qty, actual_amount, completion_rate)
    """
    _inherit = 'project.task'

    # === 工項編號 ===
    item_no = fields.Char(
        string='工項編號', index=True,
        help='契約工項編號，如：1-1, 1-2, 2-1')

    # === 廠商分配 ===
    assigned_company_id = fields.Many2one(
        'res.company', string='承包廠商', index=True,
        domain="[('company_type', '=', 'contractor')]",
        tracking=True,
        help='此工項分配給哪家施工廠商執行')

    assignment_date = fields.Date(
        string='分配日期',
        help='工項分配給廠商的日期')

    assigned_by_id = fields.Many2one(
        'res.users', string='分配人',
        help='執行分配操作的使用者')

    # === 分配狀態 ===
    assignment_state = fields.Selection([
        ('unassigned', '未分配'),
        ('assigned', '已分配'),
        ('in_progress', '執行中'),
        ('completed', '已完成'),
        ('accepted', '已驗收'),
    ], string='分配狀態', default='unassigned',
       compute='_compute_assignment_state', store=True, tracking=True)

    @api.depends('assigned_company_id', 'stage_id', 'stage_id.is_acceptance_stage')
    def _compute_assignment_state(self):
        for task in self:
            if not task.assigned_company_id:
                task.assignment_state = 'unassigned'
            elif task.stage_id and task.stage_id.is_acceptance_stage:
                task.assignment_state = 'accepted'
            elif task.actual_date_end:
                task.assignment_state = 'completed'
            elif task.actual_date_start:
                task.assignment_state = 'in_progress'
            else:
                task.assignment_state = 'assigned'

    # === 預算欄位 (契約價量) ===
    planned_qty = fields.Float(
        string='契約數量', digits=(16, 4),
        help='契約預估數量 (預算)')

    unit = fields.Char(
        string='單位',
        help='計量單位，如：M, M2, M3, 式')

    unit_price = fields.Float(
        string='契約單價', digits=(16, 2),
        help='契約預估單價')

    planned_amount = fields.Float(
        string='契約金額',
        compute='_compute_planned_amount', store=True,
        help='planned_qty x unit_price (預算上限)')

    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        for task in self:
            task.planned_amount = task.planned_qty * task.unit_price

    # === 實際執行欄位 ===
    actual_qty = fields.Float(
        string='實際完成數量', digits=(16, 4),
        help='已核定的估驗數量彙總')

    actual_amount = fields.Float(
        string='實際請款金額',
        compute='_compute_actual_amount', store=True,
        help='actual_qty x unit_price')

    @api.depends('actual_qty', 'unit_price')
    def _compute_actual_amount(self):
        for task in self:
            task.actual_amount = task.actual_qty * task.unit_price

    # === 對比分析 ===
    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate', store=True,
        help='actual_amount / planned_amount x 100')

    qty_remaining = fields.Float(
        string='剩餘數量',
        compute='_compute_completion_rate', store=True,
        help='planned_qty - actual_qty')

    budget_status = fields.Selection([
        ('under', '低於預算'),
        ('on_budget', '符合預算'),
        ('over', '超出預算'),
    ], string='預算狀態',
       compute='_compute_completion_rate', store=True)

    @api.depends('planned_qty', 'planned_amount', 'actual_qty', 'actual_amount')
    def _compute_completion_rate(self):
        for task in self:
            task.qty_remaining = task.planned_qty - task.actual_qty

            if task.planned_amount:
                task.completion_rate = (task.actual_amount / task.planned_amount) * 100
                if task.completion_rate < 95:
                    task.budget_status = 'under'
                elif task.completion_rate <= 100:
                    task.budget_status = 'on_budget'
                else:
                    task.budget_status = 'over'
            else:
                task.completion_rate = 0.0
                task.budget_status = False

    # === 時間計畫欄位 ===
    planned_date_start = fields.Datetime(
        string='預定開始時間', tracking=True,
        help='工項預定開始時間')

    planned_date_end = fields.Datetime(
        string='預定完成時間', tracking=True,
        help='工項預定完成時間')

    planned_duration = fields.Float(
        string='預定工期(天)',
        compute='_compute_planned_duration', store=True)

    @api.depends('planned_date_start', 'planned_date_end')
    def _compute_planned_duration(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                delta = task.planned_date_end - task.planned_date_start
                task.planned_duration = delta.total_seconds() / 86400  # 轉換為天數
            else:
                task.planned_duration = 0.0

    # === 實際執行時間 ===
    actual_date_start = fields.Datetime(
        string='實際開始時間', tracking=True)

    actual_date_end = fields.Datetime(
        string='實際完成時間', tracking=True)

    actual_duration = fields.Float(
        string='實際工期(天)',
        compute='_compute_actual_duration', store=True)

    @api.depends('actual_date_start', 'actual_date_end')
    def _compute_actual_duration(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                delta = task.actual_date_end - task.actual_date_start
                task.actual_duration = delta.total_seconds() / 86400
            else:
                task.actual_duration = 0.0

    # === 時程對比分析 ===
    schedule_variance = fields.Float(
        string='時程差異(天)',
        compute='_compute_schedule_variance', store=True,
        help='負值=超前, 正值=落後')

    schedule_status = fields.Selection([
        ('ahead', '超前'),
        ('on_schedule', '正常'),
        ('delayed', '落後'),
    ], string='時程狀態',
       compute='_compute_schedule_variance', store=True)

    @api.depends('planned_date_end', 'actual_date_end', 'assignment_state')
    def _compute_schedule_variance(self):
        for task in self:
            if task.planned_date_end and task.actual_date_end:
                delta = (task.actual_date_end - task.planned_date_end).days
                task.schedule_variance = delta
                if delta < -1:
                    task.schedule_status = 'ahead'
                elif delta <= 1:
                    task.schedule_status = 'on_schedule'
                else:
                    task.schedule_status = 'delayed'
            elif task.planned_date_end and task.assignment_state == 'in_progress':
                # 執行中：與現在時間比較
                now = fields.Datetime.now()
                delta = (now - task.planned_date_end).days
                task.schedule_variance = delta if delta > 0 else 0
                task.schedule_status = 'delayed' if delta > 0 else 'on_schedule'
            else:
                task.schedule_variance = 0.0
                task.schedule_status = False

    # === 工程相關 ===
    supervision_project_id = fields.Many2one(
        'supervision.project', string='工程案件',
        compute='_compute_supervision_project', store=True,
        help='關聯的工程案件主檔')

    @api.depends('project_id')
    def _compute_supervision_project(self):
        SupervisionProject = self.env['supervision.project']
        for task in self:
            if task.project_id:
                supervision = SupervisionProject.search([
                    ('project_id', '=', task.project_id.id)
                ], limit=1)
                task.supervision_project_id = supervision.id if supervision else False
            else:
                task.supervision_project_id = False

    # === 備註 ===
    construction_notes = fields.Text(
        string='施工說明',
        help='工項施工注意事項或說明')

    specification = fields.Text(
        string='規格說明',
        help='工項規格或技術要求')

    # === 約束 ===
    @api.constrains('planned_date_start', 'planned_date_end')
    def _check_planned_dates(self):
        for task in self:
            if task.planned_date_start and task.planned_date_end:
                if task.planned_date_end < task.planned_date_start:
                    raise ValidationError('預定完成時間必須晚於預定開始時間')

    @api.constrains('actual_date_start', 'actual_date_end')
    def _check_actual_dates(self):
        for task in self:
            if task.actual_date_start and task.actual_date_end:
                if task.actual_date_end < task.actual_date_start:
                    raise ValidationError('實際完成時間必須晚於實際開始時間')

    @api.constrains('planned_qty', 'unit_price')
    def _check_positive_values(self):
        for task in self:
            if task.planned_qty < 0:
                raise ValidationError('契約數量不可為負數')
            if task.unit_price < 0:
                raise ValidationError('契約單價不可為負數')

    # === 動作方法 ===
    def action_assign_to_contractor(self):
        """開啟分配廠商精靈"""
        self.ensure_one()
        if not self.supervision_project_id:
            raise UserError('此工項未關聯工程案件，無法分配廠商')

        return {
            'type': 'ir.actions.act_window',
            'name': '分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': self.supervision_project_id.id,
            },
        }

    def action_start_work(self):
        """開始施工"""
        for task in self:
            if not task.assigned_company_id:
                raise UserError('請先分配廠商才能開始施工')
            if not task.actual_date_start:
                task.actual_date_start = fields.Datetime.now()

    def action_complete_work(self):
        """完成施工"""
        for task in self:
            if not task.actual_date_start:
                raise UserError('尚未開始施工，無法標記完成')
            if not task.actual_date_end:
                task.actual_date_end = fields.Datetime.now()

    def action_batch_assign(self):
        """批次分配工項"""
        if not self:
            raise UserError('請先選擇要分配的工項')

        # 檢查是否都屬於同一個專案
        projects = self.mapped('supervision_project_id')
        if len(projects) > 1:
            raise UserError('批次分配的工項必須屬於同一個工程案件')
        if not projects:
            raise UserError('選取的工項未關聯工程案件')

        return {
            'type': 'ir.actions.act_window',
            'name': '批次分配廠商',
            'res_model': 'task.assign.contractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_ids': [Command.set(self.ids)],
                'default_project_id': projects[0].id,
            },
        }

    def write(self, vals):
        """覆寫寫入方法以記錄分配資訊"""
        if 'assigned_company_id' in vals:
            if vals['assigned_company_id']:
                vals['assignment_date'] = fields.Date.today()
                vals['assigned_by_id'] = self.env.uid
            else:
                vals['assignment_date'] = False
                vals['assigned_by_id'] = False
        return super().write(vals)


class ProjectTaskType(models.Model):
    """專案階段擴展 - 增加工程相關屬性"""
    _inherit = 'project.task.type'

    is_construction_stage = fields.Boolean(
        string='施工階段',
        help='標記此階段為施工執行階段')

    is_acceptance_stage = fields.Boolean(
        string='驗收階段',
        help='標記此階段為驗收完成階段')
