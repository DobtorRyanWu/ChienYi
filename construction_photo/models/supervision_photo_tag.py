# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionPhotoTag(models.Model):
    """
    照片標籤

    對應舊系統: image.tags
    用於分類工程照片，便於查詢和管理
    """
    _name = 'supervision.photo.tag'
    _description = '照片標籤'
    _order = 'sequence, name'

    name = fields.Char(
        string='標籤名稱',
        required=True,
        translate=True,
        help='照片分類標籤名稱')

    color = fields.Integer(
        string='顏色索引',
        default=0,
        help='用於前端顯示的顏色編號 (0-11)')

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='用於控制標籤顯示順序')

    active = fields.Boolean(
        string='啟用',
        default=True,
        help='取消勾選可停用此標籤')

    photo_count = fields.Integer(
        string='照片數量',
        compute='_compute_photo_count',
        help='使用此標籤的照片數量')

    note = fields.Text(
        string='說明',
        help='標籤用途說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('unique_name', 'UNIQUE(name)', '標籤名稱不可重複！'),
    ]

    @api.depends()
    def _compute_photo_count(self):
        """計算使用此標籤的照片數量"""
        photo_model = self.env['supervision.photo']
        for tag in self:
            tag.photo_count = photo_model.search_count([
                ('tag_ids', 'in', tag.id)
            ])

    def name_get(self):
        """顯示名稱"""
        return [(tag.id, tag.name) for tag in self]
