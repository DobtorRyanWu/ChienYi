# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .release import BUMP_SELECTION, VERSION_NAME_RE


class ConstructionReleaseConfirmWizard(models.TransientModel):
    _name = 'construction.release.confirm.wizard'
    _description = '確認系統版本'

    release_id = fields.Many2one('construction.release', string='系統版本', required=True,
                                 ondelete='cascade')
    bump = fields.Selection(BUMP_SELECTION, string='這一版屬於', required=True)
    version_name = fields.Char(string='版號', required=True,
                               help='由上面的選擇自動帶出；也可以自己改，格式 vX.Y.Z')
    last_version = fields.Char(string='目前最新版號', readonly=True)
    suggest_note = fields.Char(string='建議依據', readonly=True)
    entry_count = fields.Integer(related='release_id.entry_count', string='包含的更新紀錄數')
    warning = fields.Text(string='程式檔與資料庫版號不同的模組', readonly=True)

    @api.onchange('bump')
    def _onchange_bump(self):
        if self.bump and self.release_id:
            self.version_name = self.release_id._candidate_names()[self.bump]

    def action_confirm(self):
        self.ensure_one()
        name = (self.version_name or '').strip()
        if name and not name.startswith('v'):
            name = 'v' + name
        if not VERSION_NAME_RE.match(name):
            raise UserError(_('版號「%s」格式不對，應為 vX.Y.Z，例如 v1.5.0。', name))
        if self.env['construction.release'].sudo().search_count(
                [('name', '=', name), ('id', '!=', self.release_id.id)]):
            raise UserError(_('版號 %s 已經用過了。', name))
        self.release_id._do_confirm(name)
        return {'type': 'ir.actions.act_window_close'}
