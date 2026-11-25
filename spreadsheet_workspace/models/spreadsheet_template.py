# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

# 模板分類（工程監造用；學長那套是財會分類，不照搬）
TEMPLATE_CATEGORIES = [
    ('payment', '估驗計價'),
    ('progress', '進度'),
    ('quality', '品質'),
    ('cost', '成本'),
    ('report', '報表'),
    ('custom', '自訂'),
]


class SpreadsheetWorkspaceTemplate(models.Model):
    """試算表模板。

    繼承 spreadsheet.abstract，所以模板本身就能用 OCA 編輯器開啟
    （``open_spreadsheet`` 會帶 model 名稱）；沒有寫入權的人開啟時 OCA 自動給唯讀模式。
    """

    _name = 'spreadsheet.workspace.template'
    _description = '試算表模板'
    _inherit = ['spreadsheet.abstract']
    _order = 'sequence, name, id'

    name = fields.Char(string='名稱', required=True)
    active = fields.Boolean(string='啟用', default=True)
    category = fields.Selection(
        selection=TEMPLATE_CATEGORIES,
        string='分類',
        required=True,
        default='custom',
    )
    description = fields.Html(string='描述')
    preview_image = fields.Image(string='預覽圖', max_width=1024, max_height=1024)
    sequence = fields.Integer(string='順序', default=10)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='公司',
        ondelete='restrict',
        default=lambda self: self.env.company,
        help='留空＝所有公司共用；有填則只有該公司的人看得到。',
    )

    def action_create_spreadsheet(self):
        """從本模板建立一份新試算表並直接開啟。"""
        self.ensure_one()
        raw, _revisions = self._workspace_content_snapshot()
        spreadsheet = self.env['spreadsheet.spreadsheet'].create({
            'name': self.name,
            'source_template_id': self.id,
            'spreadsheet_binary_data': self._workspace_binary_from_raw(raw),
        })
        # 模板若正在被編輯，還沒併回底稿的操作也要帶過去
        self._workspace_copy_revisions_to(spreadsheet)
        return spreadsheet.open_spreadsheet()

    def action_preview(self):
        """用編輯器開啟模板：沒有寫入權的人是唯讀預覽，管理員則可直接修改模板。"""
        self.ensure_one()
        return self.open_spreadsheet()

    def unlink(self):
        # 同試算表：刪模板時清掉它的協作操作列（2026-11-25，D4）
        revisions = self._workspace_revisions_of_self()
        result = super().unlink()
        revisions.unlink()
        return result
