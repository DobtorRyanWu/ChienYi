"""
Phase 8 Template UI Builder（ADR-022）— 範本欄位定位。

Phase 2.1 inline control 模式：
- 欄位插入「目前游標位置」（canvas-editor `executeInsertControl`）
- canvas-editor control 的 conceptId 寫入本記錄的 id（前端 ↔ 後端對應）

Phase 2.2 / Sprint D overlay 絕對定位模式：
- 欄位浮動在頁面 (pos_x, pos_y) 座標、不依賴文字流
- 切換模式由 layout_mode 欄位控制（預設 inline，既有資料無影響）
- 縮放 / 切頁時 overlay 在前端用 CSS 跟著聯動

field_type 對應前端 FIELD_TYPES（doc_editor.js）。新增類型時兩邊都要同步。
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


FIELD_TYPE_SELECTION = [
    ('name',       '名稱'),
    ('email',      '電子郵件'),
    ('phone',      '電話'),
    ('company',    '公司'),
    ('title',      '標題'),
    ('text',       '文字'),
    ('date',       '日期'),
    ('checkbox',   '核取方塊'),
    ('signature',  '簽名'),
    ('initial',    '繕寫簽名'),
    ('odoo_field', 'Odoo 欄位'),
]

LAYOUT_MODE_SELECTION = [
    ('inline',  '行內（隨文字流）'),
    ('overlay', '浮動（絕對定位）'),
]


class DocTemplateField(models.Model):
    _name = 'doc.template.field'
    _description = '文件範本欄位'
    _order = 'template_id, page_no, id'

    template_id = fields.Many2one(
        'doc.template',
        string='所屬範本',
        required=True,
        ondelete='cascade',
        index=True,
    )
    signer_id = fields.Many2one(
        'doc.template.signer',
        string='填寫者',
        required=True,
        ondelete='cascade',
        domain="[('template_id', '=', template_id)]",
    )
    field_type = fields.Selection(
        FIELD_TYPE_SELECTION,
        string='欄位類型',
        required=True,
        default='text',
    )
    # Sprint D：layout_mode 切換 inline / overlay
    layout_mode = fields.Selection(
        LAYOUT_MODE_SELECTION,
        string='版面模式',
        required=True,
        default='inline',
        help='inline：隨文字流插入 control；overlay：依 (pos_x, pos_y) 絕對定位浮動於頁面',
    )
    page_no = fields.Integer(string='頁碼', default=1)
    pos_x = fields.Float(string='X 座標', default=0.0, help='overlay 模式專用，相對於頁面左上角的 CSS px')
    pos_y = fields.Float(string='Y 座標', default=0.0, help='overlay 模式專用，相對於頁面左上角的 CSS px')
    width = fields.Float(string='寬度', default=120.0)
    height = fields.Float(string='高度', default=24.0)
    required = fields.Boolean(string='必填', default=False)
    placeholder_text = fields.Char(string='佔位符', help='欄位空白時顯示的文字')
    font_size = fields.Integer(string='字型大小', default=12)
    odoo_field_name = fields.Char(
        string='Odoo 欄位名稱',
        help="field_type='odoo_field' 時對應 doc.template.model_id 上的欄位名（如 'partner_id.name'）",
    )

    @api.constrains('template_id', 'signer_id')
    def _check_signer_belongs_to_template(self):
        for rec in self:
            if rec.signer_id and rec.signer_id.template_id != rec.template_id:
                raise ValidationError(_(
                    "簽約人「%(signer)s」屬於範本「%(other)s」，與本欄位的範本「%(self)s」不一致。",
                    signer=rec.signer_id.name,
                    other=rec.signer_id.template_id.display_name,
                    self=rec.template_id.display_name,
                ))
