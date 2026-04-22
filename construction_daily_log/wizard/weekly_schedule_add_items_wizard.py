# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError


class WeeklyScheduleAddItemsWizard(models.TransientModel):
    """施工排程新增工項精靈"""
    _name = 'weekly.schedule.add.items.wizard'
    _description = '施工排程新增工項'

    schedule_id = fields.Many2one(
        'construction.weekly.schedule',
        string='排程',
        required=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        related='schedule_id.project_id',
        string='專案',
        readonly=True,
    )

    line_ids = fields.One2many(
        'weekly.schedule.add.items.wizard.line',
        'wizard_id',
        string='可選工項',
    )

    available_item_count = fields.Integer(
        string='可選工項數',
        compute='_compute_available_item_count',
    )

    @api.depends('line_ids')
    def _compute_available_item_count(self):
        for wizard in self:
            wizard.available_item_count = len(wizard.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            if not wizard.line_ids and wizard.schedule_id:
                schedule = wizard.schedule_id
                # 直接從 supervision_project_id 取得 project_id，避免 related 欄位未同步
                project = schedule.supervision_project_id.project_id
                if not project:
                    continue
                # 已在排程中的工項
                existing_items = schedule.line_ids.mapped('task_id')
                # 所有末端工項
                all_leaf_items = self.env['project.task'].search([
                    ('project_id', '=', project.id),
                    ('is_summary_item', '=', False),
                    ('active', '=', True),
                ])
                available = all_leaf_items - existing_items
                line_vals = [
                    {'wizard_id': wizard.id, 'task_id': task.id}
                    for task in available
                ]
                if line_vals:
                    self.env['weekly.schedule.add.items.wizard.line'].create(line_vals)
        return wizards

    def action_add_selected(self):
        """新增勾選的工項"""
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.selected)
        if not selected:
            raise UserError('請至少勾選一個工項！')

        schedule = self.schedule_id
        existing_seqs = schedule.line_ids.mapped('sequence')
        max_seq = max(existing_seqs) if existing_seqs else 0

        vals_list = []
        for idx, wiz_line in enumerate(selected, start=1):
            vals_list.append({
                'schedule_id': schedule.id,
                'task_id': wiz_line.task_id.id,
                'sequence': max_seq + (idx * 10),
            })

        self.env['construction.weekly.schedule.line'].create(vals_list)
        return {'type': 'ir.actions.act_window_close'}

    def action_add_all(self):
        """全部新增"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError('沒有可選的工項！')

        schedule = self.schedule_id
        existing_seqs = schedule.line_ids.mapped('sequence')
        max_seq = max(existing_seqs) if existing_seqs else 0

        vals_list = []
        for idx, wiz_line in enumerate(self.line_ids, start=1):
            vals_list.append({
                'schedule_id': schedule.id,
                'task_id': wiz_line.task_id.id,
                'sequence': max_seq + (idx * 10),
            })

        self.env['construction.weekly.schedule.line'].create(vals_list)
        return {'type': 'ir.actions.act_window_close'}
