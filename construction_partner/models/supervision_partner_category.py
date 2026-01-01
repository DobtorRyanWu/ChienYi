# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SupervisionPartnerCategory(models.Model):
    """
    工程單位分類標籤

    設計參考: res.partner.category
    - 支援樹狀階層分類
    - parent_path 優化 child_of 搜尋
    - 可多維度標籤工程相關單位

    分類體系:
    - 業主 (政府機關/國營事業/民間企業)
    - 施工廠商 (總承包商/專業分包商/供應商)
    - 監造單位 (建築/結構/機電監造)
    - 設計單位 (建築師/結構技師/機電技師事務所)
    - 政府部門 (主管機關/消防/環保單位)
    """
    _name = 'supervision.partner.category'
    _description = '工程單位分類標籤'
    _parent_store = True
    _order = 'sequence, name'

    # === 基本資料 ===
    name = fields.Char(
        string='標籤名稱',
        required=True,
        translate=True,
        help='分類標籤名稱')

    code = fields.Char(
        string='標籤代碼',
        help='分類標籤代碼，用於程式識別')

    color = fields.Integer(
        string='顏色索引',
        default=0,
        help='標籤顯示顏色')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='顯示順序')

    active = fields.Boolean(
        string='啟用',
        default=True,
        help='取消勾選可隱藏此分類')

    # === 階層結構 ===
    parent_id = fields.Many2one(
        'supervision.partner.category',
        string='上層分類',
        ondelete='cascade',
        index=True,
        help='上層分類標籤')

    child_ids = fields.One2many(
        'supervision.partner.category',
        'parent_id',
        string='子分類',
        help='下層分類標籤')

    parent_path = fields.Char(
        index=True,
        help='Odoo parent_store 路徑欄位')

    # === 完整路徑名稱 ===
    complete_name = fields.Char(
        string='完整分類名稱',
        compute='_compute_complete_name',
        recursive=True,
        store=True,
        help='包含上層分類的完整名稱')

    # === 關聯單位 ===
    partner_ids = fields.Many2many(
        'res.partner',
        'supervision_partner_category_rel',
        'category_id', 'partner_id',
        string='相關單位',
        help='屬於此分類的工程單位')

    partner_count = fields.Integer(
        string='單位數量',
        compute='_compute_partner_count',
        help='屬於此分類的單位數量')

    # === 說明 ===
    note = fields.Text(
        string='說明',
        translate=True,
        help='分類說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('unique_name_parent',
         'UNIQUE(name, parent_id)',
         '同層級下標籤名稱不可重複！'),
        ('unique_code',
         'UNIQUE(code)',
         '標籤代碼必須唯一！'),
    ]

    # === 計算方法 ===
    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        """計算完整分類名稱 (含上層)"""
        for category in self:
            if category.parent_id:
                category.complete_name = f"{category.parent_id.complete_name} / {category.name}"
            else:
                category.complete_name = category.name

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        """計算關聯單位數量"""
        for category in self:
            category.partner_count = len(category.partner_ids)

    # === 約束驗證 ===
    @api.constrains('parent_id')
    def _check_parent_id(self):
        """檢查是否建立遞迴分類"""
        if self._has_cycle():
            raise ValidationError('不可建立遞迴分類！上層分類不能選擇自己或子分類。')

    # === 顯示名稱 ===
    def name_get(self):
        """顯示完整分類路徑"""
        result = []
        for category in self:
            result.append((category.id, category.complete_name or category.name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """搜尋時同時比對代碼和名稱"""
        domain = domain or []
        if name:
            domain = [
                '|', '|',
                ('code', operator, name),
                ('name', operator, name),
                ('complete_name', operator, name)
            ] + domain
        return self._search(domain, limit=limit, order=order)

    # === 動作方法 ===
    def action_view_partners(self):
        """查看此分類下的工程單位"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 相關單位',
            'res_model': 'res.partner',
            'view_mode': 'list,kanban,form',
            'domain': [('supervision_category_ids', 'in', [self.id])],
            'context': {
                'default_supervision_category_ids': [self.id],
            },
        }
