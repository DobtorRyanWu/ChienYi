# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ProjectTaskTimeline(models.Model):
    """
    契約工項時程擴展 - Timeline 視圖與計時器功能

    此模組擴展 project.task 以支援：
    1. Timeline 甘特圖視圖所需欄位
    2. 繼承 hr.timesheet.time.control.mixin 計時器功能
    3. 進階時程差異分析

    參考設計：
    - OCA project_timeline: Timeline 視圖支援
    - OCA project_timesheet_time_control: 計時器功能
    """
    _inherit = ['project.task', 'hr.timesheet.time.control.mixin']
    _name = 'project.task'

    # === Timeline 視圖欄位 ===
    # 注意：planned_date_start/end 已在 construction_supervision_base 定義
    # 這裡新增 Timeline 視圖需要的額外欄位

    date_start = fields.Datetime(
        string='開始日期',
        related='planned_date_start',
        readonly=False,
        store=True,
        help='Timeline 視圖使用的開始日期')

    date_end = fields.Datetime(
        string='結束日期',
        related='planned_date_end',
        readonly=False,
        store=True,
        help='Timeline 視圖使用的結束日期')

    # === 時程顏色標記 ===
    timeline_color = fields.Integer(
        string='Timeline 顏色',
        compute='_compute_timeline_color',
        help='根據時程狀態決定顏色')

    color_index = fields.Integer(
        string='顏色索引',
        default=0,
        help='手動設定的顏色索引')

    @api.depends('schedule_status', 'assignment_state')
    def _compute_timeline_color(self):
        """
        根據狀態計算 Timeline 顏色
        - 綠色 (10): 超前或正常
        - 黃色 (3): 執行中
        - 紅色 (1): 落後
        - 灰色 (0): 未分配
        """
        for task in self:
            if task.schedule_status == 'delayed':
                task.timeline_color = 1  # 紅色
            elif task.schedule_status == 'ahead':
                task.timeline_color = 10  # 綠色
            elif task.assignment_state == 'in_progress':
                task.timeline_color = 3  # 黃色
            elif task.assignment_state == 'unassigned':
                task.timeline_color = 0  # 灰色
            else:
                task.timeline_color = 4  # 藍色 (預設)

    # === 時程依賴關係 ===
    depend_on_ids = fields.Many2many(
        'project.task',
        'project_task_dependency_rel',
        'task_id',
        'depend_on_id',
        string='前置工項',
        domain="[('project_id', '=', project_id), ('id', '!=', id)]",
        help='此工項必須等待這些前置工項完成才能開始')

    dependent_ids = fields.Many2many(
        'project.task',
        'project_task_dependency_rel',
        'depend_on_id',
        'task_id',
        string='後續工項',
        help='依賴此工項的後續工項')

    has_dependency = fields.Boolean(
        string='有前置依賴',
        compute='_compute_has_dependency',
        store=True)

    @api.depends('depend_on_ids')
    def _compute_has_dependency(self):
        for task in self:
            task.has_dependency = bool(task.depend_on_ids)

    # === 關鍵路徑分析 ===
    is_critical_path = fields.Boolean(
        string='關鍵路徑',
        default=False,
        help='標記此工項是否在專案關鍵路徑上')

    slack_days = fields.Float(
        string='浮動時間(天)',
        compute='_compute_slack_days',
        store=True,
        help='此工項可延遲的天數而不影響專案完成日期')

    @api.depends('planned_date_end', 'dependent_ids.planned_date_start')
    def _compute_slack_days(self):
        """計算浮動時間"""
        for task in self:
            if task.planned_date_end and task.dependent_ids:
                # 找最早的後續工項開始時間
                earliest_dependent = min(
                    task.dependent_ids.filtered('planned_date_start').mapped('planned_date_start'),
                    default=None
                )
                if earliest_dependent:
                    delta = earliest_dependent - task.planned_date_end
                    task.slack_days = delta.total_seconds() / 86400
                else:
                    task.slack_days = 0.0
            else:
                task.slack_days = 0.0

    # === 實作 hr.timesheet.time.control.mixin ===
    @api.model
    def _relation_with_timesheet_line(self):
        """回傳與 account.analytic.line 的關聯欄位"""
        return 'task_id'

    def _get_timesheet_defaults(self):
        """覆寫以新增工程相關預設值"""
        self.ensure_one()
        vals = super()._get_timesheet_defaults()
        vals.update({
            'task_id': self.id,
            'project_id': self.project_id.id,
            'employee_id': self.env.user.employee_id.id if self.env.user.employee_id else False,
            'name': f'{self.item_no or ""} - {self.name}',
        })
        # Odoo 18: account_id 已被移除，改用 analytic distribution 系統
        return vals

    def button_start_work(self):
        """
        覆寫開始施工計時方法

        除了建立工時記錄外，還會：
        1. 設定實際開始時間（如果尚未設定）
        2. 更新分配狀態為「執行中」
        """
        self.ensure_one()

        # 檢查前置工項是否都已完成
        incomplete_deps = self.depend_on_ids.filtered(
            lambda t: t.assignment_state not in ('completed', 'accepted')
        )
        if incomplete_deps:
            raise UserError(
                f'前置工項尚未完成：{", ".join(incomplete_deps.mapped("name"))}'
            )

        # 設定實際開始時間
        if not self.actual_date_start:
            self.actual_date_start = fields.Datetime.now()

        # 呼叫 Mixin 的開始計時方法
        return super().button_start_work()

    def button_end_work(self):
        """
        覆寫結束施工計時方法

        結束計時後會：
        1. 設定實際結束時間
        2. 重新計算時程差異
        """
        self.ensure_one()

        result = super().button_end_work()

        # 設定實際結束時間
        if not self.actual_date_end:
            self.actual_date_end = fields.Datetime.now()

        return result

    # === 進階時程差異分析 ===
    schedule_variance_hours = fields.Float(
        string='時程差異(小時)',
        compute='_compute_schedule_variance_detail',
        store=True,
        help='預定工期與實際工期的差異（小時）')

    duration_variance = fields.Float(
        string='工期差異(天)',
        compute='_compute_schedule_variance_detail',
        store=True,
        help='預定工期與實際工期的差異（天）')

    efficiency_rate = fields.Float(
        string='效率比率 (%)',
        compute='_compute_schedule_variance_detail',
        store=True,
        help='預定工期 / 實際工期 * 100')

    @api.depends('planned_duration', 'actual_duration', 'planned_date_end', 'actual_date_end')
    def _compute_schedule_variance_detail(self):
        """計算詳細的時程差異"""
        for task in self:
            # 工期差異（天）
            task.duration_variance = task.planned_duration - task.actual_duration

            # 時程差異（小時）
            task.schedule_variance_hours = task.duration_variance * 24

            # 效率比率
            if task.actual_duration > 0:
                task.efficiency_rate = (task.planned_duration / task.actual_duration) * 100
            else:
                task.efficiency_rate = 100.0

    # === 時程警示 ===
    schedule_alert = fields.Selection([
        ('none', '無'),
        ('warning', '警示'),
        ('critical', '嚴重'),
    ], string='時程警示',
       compute='_compute_schedule_alert',
       store=True)

    schedule_alert_message = fields.Char(
        string='警示訊息',
        compute='_compute_schedule_alert_message')

    @api.depends('planned_date_end', 'assignment_state', 'schedule_variance')
    def _compute_schedule_alert(self):
        """計算時程警示等級 (stored)"""
        today = fields.Datetime.now()
        for task in self:
            task.schedule_alert = 'none'

            if task.assignment_state in ('completed', 'accepted'):
                continue

            if not task.planned_date_end:
                continue

            # 計算距離預定完成日的天數
            days_remaining = (task.planned_date_end - today).days

            if days_remaining < 0:
                # 已逾期
                task.schedule_alert = 'critical'
            elif days_remaining <= 3:
                # 即將到期
                task.schedule_alert = 'warning'
            elif task.schedule_variance > 5:
                # 進度落後超過 5 天
                task.schedule_alert = 'warning'

    @api.depends('planned_date_end', 'assignment_state', 'schedule_variance')
    def _compute_schedule_alert_message(self):
        """計算警示訊息 (non-stored)"""
        today = fields.Datetime.now()
        for task in self:
            task.schedule_alert_message = ''

            if task.assignment_state in ('completed', 'accepted'):
                continue

            if not task.planned_date_end:
                continue

            # 計算距離預定完成日的天數
            days_remaining = (task.planned_date_end - today).days

            if days_remaining < 0:
                task.schedule_alert_message = f'已逾期 {abs(days_remaining)} 天'
            elif days_remaining <= 3:
                task.schedule_alert_message = f'剩餘 {days_remaining} 天'
            elif task.schedule_variance > 5:
                task.schedule_alert_message = f'進度落後 {task.schedule_variance:.1f} 天'

    # === 動作方法 ===
    def action_set_today_start(self):
        """設定今天為預定開始日"""
        for task in self:
            task.planned_date_start = fields.Datetime.now().replace(
                hour=8, minute=0, second=0, microsecond=0
            )

    def action_set_today_end(self):
        """設定今天為預定完成日"""
        for task in self:
            task.planned_date_end = fields.Datetime.now().replace(
                hour=17, minute=0, second=0, microsecond=0
            )

    def action_auto_schedule(self):
        """
        自動排程

        根據前置工項的完成時間自動設定此工項的預定開始時間
        """
        for task in self:
            if not task.depend_on_ids:
                continue

            # 找所有前置工項中最晚的預定完成時間
            latest_end = max(
                task.depend_on_ids.filtered('planned_date_end').mapped('planned_date_end'),
                default=None
            )
            if latest_end:
                # 設定開始時間為前置工項完成後的下一個工作天開始
                task.planned_date_start = latest_end + timedelta(days=1)
                task.planned_date_start = task.planned_date_start.replace(
                    hour=8, minute=0, second=0, microsecond=0
                )

    def action_view_timeline(self):
        """開啟 Timeline 視圖"""
        return {
            'type': 'ir.actions.act_window',
            'name': '工項時程',
            'res_model': 'project.task',
            'view_mode': 'timeline,tree,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {
                'default_project_id': self.project_id.id,
            },
        }

    def action_view_gantt(self):
        """開啟甘特圖視圖"""
        return {
            'type': 'ir.actions.act_window',
            'name': '工項甘特圖',
            'res_model': 'project.task',
            'view_mode': 'gantt,tree,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {
                'default_project_id': self.project_id.id,
            },
        }

    # === 約束 ===
    @api.constrains('depend_on_ids')
    def _check_dependency_cycle(self):
        """檢查是否存在循環依賴"""
        for task in self:
            if task._has_dependency_cycle():
                raise ValidationError(
                    f'工項「{task.name}」存在循環依賴關係，請檢查前置工項設定'
                )

    def _has_dependency_cycle(self, visited=None):
        """遞迴檢查循環依賴"""
        if visited is None:
            visited = set()

        if self.id in visited:
            return True

        visited.add(self.id)

        for dep in self.depend_on_ids:
            if dep._has_dependency_cycle(visited.copy()):
                return True

        return False
