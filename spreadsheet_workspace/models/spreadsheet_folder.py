# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SpreadsheetWorkspaceFolder(models.Model):
    _name = 'spreadsheet.workspace.folder'
    _description = '試算表資料夾'
    _parent_name = 'parent_id'
    # 資料夾放進自己的子資料夾底下時，核心的 _parent_store 會直接擋（UserError），不用另寫約束
    _parent_store = True
    _order = 'sequence, name, id'

    name = fields.Char(string='名稱', required=True)
    parent_id = fields.Many2one(
        comodel_name='spreadsheet.workspace.folder',
        string='上層資料夾',
        # 有子資料夾時不可刪上層：要先清空，避免一次連帶刪掉整棵樹
        ondelete='restrict',
        index=True,
    )
    parent_path = fields.Char(string='階層路徑', index=True)
    child_ids = fields.One2many(
        comodel_name='spreadsheet.workspace.folder',
        inverse_name='parent_id',
        string='子資料夾',
    )
    sequence = fields.Integer(string='序號', default=10)
    color = fields.Integer(string='顏色')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='公司',
        ondelete='restrict',
        default=lambda self: self.env.company,
        help='留空＝所有公司共用；有填則只有該公司的人看得到。',
    )
    spreadsheet_ids = fields.One2many(
        comodel_name='spreadsheet.spreadsheet',
        inverse_name='folder_id',
        string='試算表',
    )
    spreadsheet_count = fields.Integer(
        string='試算表數',
        compute='_compute_spreadsheet_count',
    )

    @api.constrains('company_id')
    def _check_company_allowed(self):
        """改掛公司也要擋：全域規則只查寫入前的舊值，可以把自己公司的資料夾改掛到別家（2026-11-25，D2）。
        留空（所有公司共用）不限；sudo（系統程式、資料修正）不檢查。"""
        if self.env.su:
            return
        allowed = self.env.user.company_ids
        for folder in self:
            if folder.company_id and folder.company_id not in allowed:
                # 不顯示公司名稱：使用者讀不到那家公司，顯示名稱本身會再丟存取錯誤
                raise ValidationError('不能把資料夾改掛到你沒有權限的公司。')

    @api.depends('name', 'parent_id')
    def _compute_display_name(self):
        """下拉選單顯示完整路徑（上層 / 本層），同名資料夾才分得出來。"""
        for folder in self:
            names = []
            current = folder
            while current:
                names.append(current.name or '')
                current = current.parent_id
            folder.display_name = ' / '.join(reversed(names))

    @api.depends('spreadsheet_ids')
    def _compute_spreadsheet_count(self):
        """只算直接放在本資料夾的試算表；經 ORM 計數，所以只會算到使用者看得到的。"""
        groups = self.env['spreadsheet.spreadsheet']._read_group(
            [('folder_id', 'in', self.ids)], ['folder_id'], ['__count'],
        )
        counts = {folder.id: count for folder, count in groups}
        for folder in self:
            folder.spreadsheet_count = counts.get(folder.id, 0)

    def action_view_spreadsheets(self):
        """開啟本資料夾的試算表清單。"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'spreadsheet_oca.spreadsheet_spreadsheet_act_window'
        )
        action['domain'] = [('folder_id', '=', self.id)]
        action['context'] = {'default_folder_id': self.id}
        return action
