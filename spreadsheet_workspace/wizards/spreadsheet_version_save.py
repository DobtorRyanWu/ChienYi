# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class SpreadsheetWorkspaceVersionSave(models.TransientModel):
    """「存成版本」小視窗：只填說明，實際建立與權限檢查在 spreadsheet.spreadsheet.action_save_version。"""

    _name = 'spreadsheet.workspace.version.save'
    _description = '存成版本'

    spreadsheet_id = fields.Many2one(
        comodel_name='spreadsheet.spreadsheet',
        string='試算表',
        required=True,
        ondelete='cascade',
    )
    commit_message = fields.Char(string='提交說明')

    def action_confirm(self):
        self.ensure_one()
        self.spreadsheet_id.action_save_version(self.commit_message)
        return {'type': 'ir.actions.act_window_close'}
