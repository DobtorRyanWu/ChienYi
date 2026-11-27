# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProgressResetDraftWizard(models.TransientModel):
    """重設草稿之前的提醒（2026-11-27 使用者定）。

    使用中那一版重設時前一版會自動接手（工程的預定完工日與累計展延跟著改回）→ 按之前先講清楚
    「重設後先回到第 N 版，改好請重新啟用。」。按鈕的 confirm 只能寫固定的字、帶不出 N，所以用這個小視窗。"""
    _name = 'progress.reset.draft.wizard'
    _description = '進度表重設草稿'

    schedule_id = fields.Many2one(
        'progress.schedule',
        string='進度表',
        required=True,
        readonly=True,
    )
    message = fields.Char(string='提醒', compute='_compute_message')

    @api.depends('schedule_id')
    def _compute_message(self):
        for wiz in self:
            wiz.message = wiz.schedule_id._reset_draft_message() if wiz.schedule_id else ''

    def action_confirm(self):
        self.ensure_one()
        self.schedule_id._do_reset_draft()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': self.schedule_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
