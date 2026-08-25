# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class AddSlipLineWizard(models.TransientModel):
    """加入通報單詳細表項目 Wizard（Odoo 原生 M2M 選取）

    2026-08-25 起可選彙總項：原本 domain 有 ('is_summary_item', '=', False)，
    像「三 雜項工程費」這種底下有子工項的項目根本加不進詳細表，
    但回報單的詳細表本來就會出現「只寫一個總數的彙總項」。

    選取葉節點時會自動補齊其所有祖先彙總項（壹 發包工程費、一 工程費…），
    讓詳細表永遠是契約工項樹的一個完整子樹——結算金額才有辦法只算根列而不重複。
    實作在 reservation.notification.slip.line._create_lines_for_tasks，
    與匯入共用同一份邏輯。
    """
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
        """將選取的工項（含自動補齊的祖先彙總項）建立為通報單明細"""
        self.ensure_one()
        if not self.selected_task_ids:
            raise UserError('請至少選取一個工項！')

        self.env['reservation.notification.slip.line']._create_lines_for_tasks(
            self.slip_id, self.selected_task_ids)

        return {'type': 'ir.actions.act_window_close'}
