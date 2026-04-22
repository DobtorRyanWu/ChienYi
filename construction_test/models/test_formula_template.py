# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TestFormulaTemplate(models.Model):
    """
    自訂公式範本庫

    儲存可跨專案重複使用的自訂公式，使用者可在檢試驗項目中
    透過「套用公式範本」按鈕快速套用，套用後仍可微調。
    """
    _name = 'supervision.test.formula.template'
    _description = '自訂公式範本'
    _inherit = ['mail.thread']
    _order = 'category, sequence, id'

    # === 基本資料 ===
    name = fields.Char(
        string='範本名稱',
        required=True,
        tracking=True,
        help='例如：鋼筋取樣（質量階梯）')

    active = fields.Boolean(
        string='啟用',
        default=True)

    sequence = fields.Integer(
        string='排序',
        default=10)

    category = fields.Char(
        string='分類',
        tracking=True,
        help='例如：鋼筋、混凝土、瀝青...')

    description = fields.Text(
        string='公式邏輯說明',
        help='人類可讀的公式邏輯描述')

    # === 公式 ===
    custom_formula = fields.Text(
        string='計算公式',
        required=True,
        help='Python 表達式，回傳應檢驗次數（整數）')

    custom_warning_formula = fields.Text(
        string='預警公式',
        help='Python 表達式，回傳下一個預警門檻數量（選填）')

    # === 變數 ===
    variable_ids = fields.One2many(
        'supervision.test.formula.template.variable',
        'template_id',
        string='自定義變數')

    # === 使用統計 ===
    usage_count = fields.Integer(
        string='使用次數',
        readonly=True,
        default=0)

    last_used_date = fields.Datetime(
        string='最近使用時間',
        readonly=True)

    # === 其他 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        default=lambda self: self.env.company)

    is_global = fields.Boolean(
        string='全域可用',
        default=True,
        help='勾選後所有公司皆可使用')

    note = fields.Text(string='備註')

    @api.depends('name', 'category')
    def _compute_display_name(self):
        for rec in self:
            if rec.category:
                rec.display_name = f'[{rec.category}] {rec.name}'
            else:
                rec.display_name = rec.name

    def record_usage(self):
        """記錄範本被套用一次"""
        self.ensure_one()
        self.sudo().write({
            'usage_count': self.usage_count + 1,
            'last_used_date': fields.Datetime.now(),
        })
