# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PriceLibraryCategory(models.Model):
    """
    價格庫分類

    工項價格的分類管理 (例如：土方工程、結構工程、裝修工程)
    支援樹狀階層結構，使用 _parent_store 優化查詢效能
    """
    _name = 'price.library.category'
    _description = '價格庫分類'
    _parent_store = True
    _order = 'sequence, name'

    # === 基本資訊 ===
    name = fields.Char(
        string='分類名稱',
        required=True,
        translate=True,
        help='分類名稱，如：土方工程、結構工程')

    code = fields.Char(
        string='分類編號',
        index=True,
        help='分類編號，用於快速識別')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='排序順序，數字越小越前面')

    # === 多公司支援 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help='所屬公司，每個公司有獨立的價格庫分類')

    # === 樹狀結構 ===
    parent_id = fields.Many2one(
        'price.library.category',
        string='上層分類',
        index=True,
        ondelete='cascade',
        help='上層分類，留空表示為根分類')

    parent_path = fields.Char(
        index=True,
        help='樹狀結構路徑，用於高效查詢')

    child_ids = fields.One2many(
        'price.library.category',
        'parent_id',
        string='子分類',
        help='此分類下的子分類')

    # === 關聯項目 ===
    item_ids = fields.One2many(
        'price.library.item',
        'category_id',
        string='價格項目',
        help='此分類下的價格項目')

    item_count = fields.Integer(
        string='項目數',
        compute='_compute_item_count',
        help='此分類下的項目數量')

    # === 啟用狀態 ===
    active = fields.Boolean(
        string='啟用',
        default=True,
        help='停用的分類不會顯示在選擇清單中')

    # === 備註 ===
    description = fields.Text(
        string='說明',
        help='分類的詳細說明')

    # === 計算方法 ===
    @api.depends('item_ids')
    def _compute_item_count(self):
        """計算分類下的項目數量"""
        for category in self:
            category.item_count = len(category.item_ids)

    # === 顯示名稱 ===
    def name_get(self):
        """顯示完整分類路徑"""
        result = []
        for category in self:
            names = []
            current = category
            while current:
                names.append(current.name)
                current = current.parent_id
            # 反轉順序：根分類 / 子分類 / 當前分類
            full_name = ' / '.join(reversed(names))
            result.append((category.id, full_name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """支援依編號或名稱搜尋"""
        domain = domain or []
        if name:
            domain = ['|', ('code', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # === 約束 ===
    @api.constrains('parent_id')
    def _check_parent_id(self):
        """檢查父分類不能是自己或自己的子分類"""
        if self._has_cycle():
            from odoo.exceptions import ValidationError
            raise ValidationError('分類不能設定自己或子分類為上層分類！')

    # === SQL 約束 ===
    # 註：分類編號（code）不強制唯一，因為不同公司可能使用相同編號
    _sql_constraints = []

    # === 動作方法 ===
    def action_view_items(self):
        """檢視此分類下的價格項目"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 價格項目',
            'res_model': 'price.library.item',
            'view_mode': 'list,kanban,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
