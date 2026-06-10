# -*- coding: utf-8 -*-
"""
照片分類 master data
取代原 supervision.photo.category Selection 欄位的硬編碼分類，
使用者可在後台自由新增/停用分類。
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SupervisionPhotoCategory(models.Model):
    _name = 'supervision.photo.category'
    _description = '照片分類'
    _order = 'sequence, code'

    name = fields.Char(string='分類名稱', required=True, translate=True)
    code = fields.Char(string='分類代碼', required=True, size=16,
                       help='英文縮寫代碼，匯入腳本以此關聯（如 STL/CON/PILE）')
    sequence = fields.Integer(string='顯示順序', default=10)
    active = fields.Boolean(string='啟用', default=True)
    color = fields.Integer(string='顏色索引')
    description = fields.Text(string='說明')

    photo_count = fields.Integer(
        string='照片數', compute='_compute_photo_count'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', '分類代碼必須唯一'),
    ]

    @api.depends()
    def _compute_photo_count(self):
        Photo = self.env['supervision.photo']
        for cat in self:
            cat.photo_count = Photo.search_count([('category_id', '=', cat.id)])

    @api.constrains('code')
    def _check_code_format(self):
        for rec in self:
            if not rec.code or not rec.code.strip():
                raise ValidationError('分類代碼不可為空')
            # 強制大寫，避免大小寫混雜造成匯入對不上
            if rec.code != rec.code.upper():
                raise ValidationError(f'分類代碼必須為大寫英文：{rec.code}')

    def name_get(self):
        return [(rec.id, f'[{rec.code}] {rec.name}') for rec in self]
