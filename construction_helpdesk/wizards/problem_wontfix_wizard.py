# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from ..models.problem import CLOSED_STATES, WONT_FIX_REASON_SELECTION


class ConstructionProblemWontfixWizard(models.TransientModel):
    """不處理：必須選原因並寫說明（分級標準 v0.3 第九節）。

    參考 ServiceNow 問題單的結案代碼（Fix Applied／Risk Accepted／Duplicate／Canceled）：
    「不處理」不是一個選項，而是幾種性質不同的結束方式。
    """
    _name = 'construction.problem.wontfix.wizard'
    _description = '不處理'

    problem_id = fields.Many2one('construction.problem', string='問題單', required=True, readonly=True)
    final_priority = fields.Selection(related='problem_id.final_priority', string='最終 P')
    reason = fields.Selection(WONT_FIX_REASON_SELECTION, string='原因', required=True)
    note = fields.Text(string='說明', required=True)
    duplicate_of_id = fields.Many2one(
        'construction.problem', string='重複於',
        domain="[('state', 'not in', %s), ('id', '!=', problem_id)]" % (list(CLOSED_STATES),),
        help='關聯服務單會一起移到這張問題單。')

    @api.onchange('reason')
    def _onchange_reason(self):
        if self.reason != 'duplicate':
            self.duplicate_of_id = False

    def action_confirm(self):
        self.ensure_one()
        self.problem_id._set_wont_fix(self.reason, self.note, self.duplicate_of_id)
        return {'type': 'ir.actions.act_window_close'}
