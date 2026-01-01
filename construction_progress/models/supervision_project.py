# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class SupervisionProjectProgress(models.Model):
    """
    擴展工程案件主檔 - 新增進度表相關欄位

    業務說明：
    - 在專案上顯示關聯的進度表
    - 提供快速存取使用中進度表的功能
    - 顯示目前進度狀態摘要
    """
    _inherit = 'supervision.project'

    # === 進度表關聯 ===
    schedule_ids = fields.One2many(
        'progress.schedule',
        'project_id',
        string='進度表',
    )
    schedule_count = fields.Integer(
        string='進度表數量',
        compute='_compute_schedule_count',
    )
    active_schedule_id = fields.Many2one(
        'progress.schedule',
        string='使用中進度表',
        compute='_compute_active_schedule',
        store=True,
    )

    # === 進度摘要 (從使用中進度表帶入) ===
    schedule_planned_progress = fields.Float(
        string='進度表預定進度 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )
    schedule_actual_progress = fields.Float(
        string='進度表實際進度 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )
    schedule_variance = fields.Float(
        string='進度差異 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )
    schedule_variance_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
    ], string='進度表狀態', compute='_compute_schedule_progress')

    @api.depends('schedule_ids')
    def _compute_schedule_count(self):
        for project in self:
            project.schedule_count = len(project.schedule_ids)

    @api.depends('schedule_ids.state')
    def _compute_active_schedule(self):
        for project in self:
            active = project.schedule_ids.filtered(lambda s: s.state == 'active')
            project.active_schedule_id = active[0] if active else False

    @api.depends('active_schedule_id', 'active_schedule_id.current_cumulative_planned',
                 'active_schedule_id.current_cumulative_actual',
                 'active_schedule_id.current_variance',
                 'active_schedule_id.current_variance_status')
    def _compute_schedule_progress(self):
        for project in self:
            if project.active_schedule_id:
                project.schedule_planned_progress = project.active_schedule_id.current_cumulative_planned
                project.schedule_actual_progress = project.active_schedule_id.current_cumulative_actual
                project.schedule_variance = project.active_schedule_id.current_variance
                project.schedule_variance_status = project.active_schedule_id.current_variance_status
            else:
                project.schedule_planned_progress = 0.0
                project.schedule_actual_progress = 0.0
                project.schedule_variance = 0.0
                project.schedule_variance_status = False

    # =========================================================================
    # 動作方法
    # =========================================================================

    def action_view_schedules(self):
        """查看進度表"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 進度表',
            'res_model': 'progress.schedule',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'search_default_filter_active': 1,
            },
        }

    def action_view_active_schedule(self):
        """查看使用中進度表"""
        self.ensure_one()
        if not self.active_schedule_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '提示',
                    'message': '此工程尚未建立使用中的進度表',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': self.active_schedule_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_schedule(self):
        """建立新進度表"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '建立進度表',
            'res_model': 'progress.schedule',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
            },
            'target': 'current',
        }
