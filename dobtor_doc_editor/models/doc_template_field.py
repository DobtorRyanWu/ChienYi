"""
Phase 8 Template UI Builder（ADR-022）— 範本欄位定位。

Phase 2.1 inline control 模式：
- 欄位插入「目前游標位置」（canvas-editor `executeInsertControl`）
- pos_x / pos_y / width / height **本階段不使用**，但保留以承接 Phase 2.2 overlay 絕對定位
- canvas-editor control 的 conceptId 寫入本記錄的 id（前端 ↔ 後端對應）

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
    # Phase 2.2 overlay 預留（Phase 2.1 inline control 不使用）
    page_no = fields.Integer(string='頁碼', default=1)
    pos_x = fields.Float(string='X 座標', default=0.0, help='Phase 2.2 overlay 用，inline control 階段忽略')
    pos_y = fields.Float(string='Y 座標', default=0.0, help='Phase 2.2 overlay 用，inline control 階段忽略')
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
