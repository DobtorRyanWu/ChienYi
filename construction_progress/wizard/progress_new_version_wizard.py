# -*- coding: utf-8 -*-

from odoo import fields, models


class ProgressNewVersionWizard(models.TransientModel):
    """建立新版本（2026-11-24）：先問變更日期，一定要填、不預設今天。

    以前按「建立新版本」直接複製、變更日期預設今天；契約變更常是事後補登（生效日比建檔日早），
    又要照這個日期切分明細，忘了改就切在錯的日子、而且不會報錯 → 改成先問。"""
    _name = 'progress.new.version.wizard'
    _description = '建立進度表新版本'

    schedule_id = fields.Many2one(
        'progress.schedule',
        string='從這一版建立',
        required=True,
        readonly=True,
    )
    change_date = fields.Date(
        string='變更日期',
        required=True,
        help='新版從這一天開始生效（契約變更、工期檢討核定的生效日，不是今天建檔的日子）。'
             '這一天在進度明細裡會獨立成一列，這一天以後的各段預定進度會清成 0，照新計畫重填。',
    )
    change_reason = fields.Text(string='變更原因')

    def action_confirm(self):
        self.ensure_one()
        new = self.schedule_id._create_new_version(self.change_date, self.change_reason)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }
