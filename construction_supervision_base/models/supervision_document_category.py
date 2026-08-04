# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SupervisionDocumentCategory(models.Model):
    """
    文件分類
    
    允許使用者自訂文件分類方式，支援階層結構
    """
    _name = 'supervision.document.category'
    _description = '文件分類'
    _order = 'sequence, name'
    _parent_name = 'parent_id'
    _parent_store = True
    
    # === 基本資訊 ===
    name = fields.Char(
        string='分類名稱', 
        required=True, 
        translate=True,
        help='文件分類的名稱，例如：契約文件、施工計畫、竣工文件等')
    
    code = fields.Char(
        string='分類代碼', 
        index=True,
        help='分類的唯一識別碼，可用於程式判斷')
    
    sequence = fields.Integer(
        string='排序', 
        default=10,
        help='數字越小越前面')
    
    active = fields.Boolean(
        string='啟用', 
        default=True,
        help='停用後將不會出現在選單中')
    
    description = fields.Text(
        string='說明',
        help='此分類的用途說明')
    
    # === 階層結構 ===
    parent_id = fields.Many2one(
        'supervision.document.category', 
        string='上層分類',
        index=True,
        ondelete='cascade',
        help='建立多層級的分類結構')
    
    parent_path = fields.Char(index=True)
    
    child_ids = fields.One2many(
        'supervision.document.category', 
        'parent_id', 
        string='子分類')
    
    # === 系統標記 ===
    is_system = fields.Boolean(
        string='系統預設', 
        default=False, 
        copy=False,
        help='系統預設分類無法刪除，但可以停用')
    
    # === 統計欄位 ===
    document_count = fields.Integer(
        string='文件數量',
        compute='_compute_document_count',
        help='此分類下的文件數量')
    
    @api.depends('code')
    def _compute_document_count(self):
        """計算此分類下的文件數量"""
        Document = self.env['supervision.document']
        for category in self:
            category.document_count = Document.search_count([
                ('document_category_id', '=', category.id)
            ])
    
    # === 顯示名稱 ===
    # Odoo 17 起 name_get() 已移除，改用 _compute_display_name()。
    # 原本這裡寫的是 name_get，等於整段從未被呼叫過 —— 下拉選單只顯示
    # 「01-圖說」而看不到上層，分類樹一多就分不清。
    @api.depends('name', 'parent_id.name')
    def _compute_display_name(self):
        for category in self:
            if category.parent_id:
                category.display_name = f'{category.parent_id.name} / {category.name}'
            else:
                category.display_name = category.name
    
    # === 約束檢查 ===
    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        """防止循環繼承"""
        if self._has_cycle():
            raise ValidationError('不可建立循環的分類結構！')
    
    @api.constrains('code')
    def _check_code_unique(self):
        """確保分類代碼唯一（如果有填寫）"""
        for category in self:
            if category.code:
                duplicate = self.search([
                    ('code', '=', category.code),
                    ('id', '!=', category.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(f'分類代碼 "{category.code}" 已被使用！')
    
    # === CRUD 限制 ===
    def unlink(self):
        """系統預設分類無法刪除"""
        for category in self:
            if category.is_system:
                raise UserError(f'無法刪除系統預設分類「{category.name}」，您可以選擇停用它。')
            
            # 檢查是否有文件使用此分類
            if category.document_count > 0:
                raise UserError(
                    f'無法刪除分類「{category.name}」，因為還有 {category.document_count} 個文件使用此分類。'
                )
        
        return super().unlink()
    
    # === 動作方法 ===
    def action_view_documents(self):
        """查看此分類下的所有文件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 文件列表',
            'res_model': 'supervision.document',
            'view_mode': 'list,form',
            'domain': [('document_category_id', '=', self.id)],
            'context': {'default_document_category_id': self.id},
        }
