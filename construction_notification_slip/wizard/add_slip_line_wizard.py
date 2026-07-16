# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class AddSlipLineWizard(models.TransientModel):
    """加入通報單詳細表項目 Wizard（Odoo 原生 M2M 選取）"""
    _name = 'add.slip.line.wizard'
    _description = '加入通報單詳細表項目'

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, readonly=True)

    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        related='slip_id.project_id', readonly=True)

    selected_task_ids = fields.Many2many(
        'project.task',
        'add_slip_line_wiz_task_rel',
        'wizard_id',
        'task_id',
        string='選擇施工項目',
    )

    def action_add_lines(self):
        """將選取的工項建立為通報單明細（跳過已存在的）"""
        self.ensure_one()
        if not self.selected_task_ids:
            raise UserError('請至少選取一個工項！')

        slip = self.slip_id
        existing_task_ids = slip.detail_line_ids.filtered(
            'task_id').mapped('task_id').ids
        new_tasks = self.selected_task_ids.filtered(
            lambda t: t.id not in existing_task_ids)

        SlipLine = self.env['reservation.notification.slip.line']
        for task in new_tasks:
            SlipLine.create({
                'slip_id': slip.id,
                'task_id': task.id,
                'item_no': task.item_no or '',
                'description': task.name or '',
                'unit': task.unit or '',
                'unit_price': task.unit_price or 0.0,
            })

        return {'type': 'ir.actions.act_window_close'}
