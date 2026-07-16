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

    # 可選工項（排除已在排程中的）——供 selected_task_ids 的 domain 與「全部新增」使用
    available_task_ids = fields.Many2many(
        'project.task',
        'wssched_add_wiz_avail_rel', 'wizard_id', 'task_id',
        string='可選工項(內部)',
        compute='_compute_available_task_ids',
    )
    # 使用者勾選/搜尋加入的工項（透過 SelectCreateDialog，享有改良後的工項搜尋）
    selected_task_ids = fields.Many2many(
        'project.task',
        'wssched_add_wiz_sel_rel', 'wizard_id', 'task_id',
        string='選擇施工項目',
    )
    available_item_count = fields.Integer(
        string='可選工項數',
        compute='_compute_available_task_ids',
    )

    @api.depends('schedule_id')
    def _compute_available_task_ids(self):
        for wizard in self:
            project = wizard.schedule_id.supervision_project_id \
                if wizard.schedule_id else False
            if not project:
                wizard.available_task_ids = False
                wizard.available_item_count = 0
                continue
            existing_items = wizard.schedule_id.line_ids.mapped('task_id')
            all_leaf_items = self.env['project.task'].search([
                ('project_id', '=', project.id),
                ('is_summary_item', '=', False),
                ('active', '=', True),
            ])
            available = all_leaf_items - existing_items
            wizard.available_task_ids = available
            wizard.available_item_count = len(available)

    def _create_schedule_lines(self, tasks):
        """從 project.task recordset 建立排程明細（跳過已存在的）"""
        schedule = self.schedule_id
        to_add = tasks - schedule.line_ids.mapped('task_id')
        if not to_add:
            raise UserError('選取的工項都已在排程中！')
        max_seq = max(schedule.line_ids.mapped('sequence') or [0])
        vals_list = [
            {'schedule_id': schedule.id, 'task_id': task.id, 'sequence': max_seq + (idx * 10)}
            for idx, task in enumerate(to_add, start=1)
        ]
        self.env['construction.weekly.schedule.line'].create(vals_list)
        return {'type': 'ir.actions.act_window_close'}

    def action_add_selected(self):
        """新增使用者選取的工項"""
        self.ensure_one()
        if not self.selected_task_ids:
            raise UserError('請至少選取一個工項！')
        return self._create_schedule_lines(self.selected_task_ids)

    def action_add_all(self):
        """全部新增（所有尚未在排程中的可選工項）"""
        self.ensure_one()
        if not self.available_task_ids:
            raise UserError('沒有可選的工項！')
        return self._create_schedule_lines(self.available_task_ids)
