# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class EquipmentCategory(models.Model):
    """
    機具設備分類

    設計參考: maintenance.equipment.category
    - 支援階層式分類結構
    - 動態屬性定義 (Odoo 18 Properties)
    - 預設負責技師設定
    """
    _name = 'supervision.equipment.category'
    _description = '機具設備分類'
    _order = 'sequence, name'
    _parent_name = 'parent_id'
    _parent_store = True

    # === 基本資料 ===
    name = fields.Char(
        string='分類名稱',
        required=True,
        translate=True,
        index=True)

    complete_name = fields.Char(
        string='完整名稱',
        compute='_compute_complete_name',
        recursive=True,
        store=True)

    sequence = fields.Integer(
        string='排序',
        default=10)

    active = fields.Boolean(
        string='啟用',
        default=True)

    color = fields.Integer(
        string='顏色索引',
        default=0)

    # === 階層結構 ===
    parent_id = fields.Many2one(
        'supervision.equipment.category',
        string='上層分類',
        ondelete='cascade',
        index=True)

    parent_path = fields.Char(
        index=True)

    child_ids = fields.One2many(
        'supervision.equipment.category',
        'parent_id',
        string='子分類')

    # === 設備關聯 ===
    equipment_ids = fields.One2many(
        'supervision.equipment',
        'category_id',
        string='設備列表')

    equipment_count = fields.Integer(
        string='設備數量',
        compute='_compute_equipment_count',
        store=True)

    # === 動態屬性定義 (Odoo 18 Properties) ===
    equipment_properties_definition = fields.PropertiesDefinition(
        string='設備屬性定義',
        help='定義此分類設備的動態屬性欄位')

    # === 預設設定 ===
    default_technician_id = fields.Many2one(
        'res.users',
        string='預設負責技師',
        help='此分類設備的預設負責技師')

    note = fields.Html(
        string='說明',
        translate=True)

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        """計算完整分類名稱 (含階層路徑)"""
        for category in self:
            if category.parent_id:
                category.complete_name = f'{category.parent_id.complete_name} / {category.name}'
            else:
                category.complete_name = category.name

    @api.depends('equipment_ids')
    def _compute_equipment_count(self):
        """計算設備數量"""
        for category in self:
            category.equipment_count = len(category.equipment_ids)

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('parent_id')
    def _check_parent_id(self):
        """防止循環階層結構"""
        if self._has_cycle():
            raise models.ValidationError('錯誤！分類不能是自己的上層分類。')

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    def name_get(self):
        """顯示完整分類名稱"""
        result = []
        for category in self:
            result.append((category.id, category.complete_name or category.name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """支援以完整名稱或分類名稱搜尋"""
        domain = domain or []
        if name:
            domain = ['|', ('name', operator, name), ('complete_name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_view_equipment(self):
        """查看此分類的設備"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 設備列表',
            'res_model': 'supervision.equipment',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }

    # -------------------------------------------------------------------------
    # SQL Constraints
    # -------------------------------------------------------------------------

    _sql_constraints = [
        ('name_parent_unique',
         'UNIQUE(name, parent_id)',
         '同一上層分類下的分類名稱不可重複！'),
    ]
