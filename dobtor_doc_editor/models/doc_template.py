from odoo import models, fields


class DocTemplate(models.Model):
    _name = 'doc.template'
    _description = '文件範本'
    _inherit = ['doc.render.mixin']
    _order = 'name asc'

    name = fields.Char(string='範本名稱', required=True)
    content_html = fields.Html(
        string='範本內容',
        sanitize=False,
        sanitize_attributes=False,
    )
    model_id = fields.Many2one(
        'ir.model',
        string='適用模型',
        ondelete='set null',
        help='此範本適用的 Odoo 模型，留空表示通用範本',
    )
    category = fields.Selection([
        ('general', '一般'),
        ('contract', '合約'),
        ('report', '報告'),
        ('letter', '信函'),
        ('other', '其他'),
    ], string='分類', default='general')
    description = fields.Text(string='說明')
    active = fields.Boolean(string='啟用', default=True)
    page_format = fields.Selection([
        ('A4', 'A4'),
        ('A3', 'A3'),
        ('A5', 'A5'),
        ('letter', 'Letter'),
        ('legal', 'Legal'),
    ], string='預設頁面格式', default='A4')

    # Phase 8 Template UI Builder（ADR-022）
    signer_ids = fields.One2many(
        'doc.template.signer',
        'template_id',
        string='簽約人角色',
    )
    field_ids = fields.One2many(
        'doc.template.field',
        'template_id',
        string='範本欄位',
    )
    signer_count = fields.Integer(string='簽約人數', compute='_compute_phase8_counts')
    field_count = fields.Integer(string='欄位數', compute='_compute_phase8_counts')

    def _compute_phase8_counts(self):
        for rec in self:
            rec.signer_count = len(rec.signer_ids)
            rec.field_count = len(rec.field_ids)
