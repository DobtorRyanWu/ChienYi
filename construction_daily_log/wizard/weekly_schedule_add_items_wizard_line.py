# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class WeeklyScheduleAddItemsWizardLine(models.TransientModel):
    """施工排程新增工項精靈明細"""
    _name = 'weekly.schedule.add.items.wizard.line'
    _description = '施工排程新增工項精靈明細'
    _order = 'task_sequence'

    wizard_id = fields.Many2one(
        'weekly.schedule.add.items.wizard',
        string='精靈',
        required=True,
        ondelete='cascade',
    )
    task_id = fields.Many2one(
        'project.task',
        string='施工項目',
        required=True,
        readonly=True,
    )
    selected = fields.Boolean(
        string='選取',
        default=False,
    )

    # Related 欄位（唯讀顯示用）
    task_sequence = fields.Integer(related='task_id.sequence', string='排序', store=True)
    name = fields.Char(related='task_id.name', string='施工項目')
    parent_id = fields.Many2one(related='task_id.parent_id', string='父工項')
    item_no = fields.Char(related='task_id.item_no', string='工項編號')
    unit = fields.Char(related='task_id.unit', string='單位')
    planned_qty = fields.Float(related='task_id.planned_qty', string='契約數量')
