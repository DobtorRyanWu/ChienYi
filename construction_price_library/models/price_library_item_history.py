# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PriceLibraryItemHistory(models.Model):
    """
    價格變更歷史

    記錄價格庫項目的歷史價格變更，用於：
    - 追蹤價格趨勢
    - 分析價格波動
    - 稽核目的
    """
    _name = 'price.library.item.history'
    _description = '價格變更歷史'
    _order = 'change_date desc, id desc'

    # === 關聯項目 ===
    item_id = fields.Many2one(
        'price.library.item',
        string='價格項目',
        required=True,
        ondelete='cascade',
        index=True,
        help='關聯的價格庫項目')

    # === 關聯資訊（便於查詢）===
    item_name = fields.Char(
        related='item_id.name',
        string='項目名稱',
        store=True,
        help='項目名稱（便於搜尋）')

    item_no = fields.Char(
        related='item_id.item_no',
        string='項目編號',
        store=True,
        help='項目編號（便於搜尋）')

    category_id = fields.Many2one(
        related='item_id.category_id',
        string='分類',
        store=True,
        help='項目所屬分類（便於篩選）')

    # === 價格變更資訊 ===
    old_price = fields.Float(
        string='變更前單價',
        digits=(12, 2),
        help='變更前的單價')

    new_price = fields.Float(
        string='變更後單價',
        digits=(12, 2),
        help='變更後的單價')

    price_change = fields.Float(
        string='價格變動',
        compute='_compute_price_change',
        digits=(12, 2),
        store=True,
        help='新價格 - 舊價格')

    price_change_rate = fields.Float(
        string='變動率 (%)',
        compute='_compute_price_change',
        digits=(6, 2),
        store=True,
        help='價格變動百分比')

    @api.depends('old_price', 'new_price')
    def _compute_price_change(self):
        """計算價格變動金額和百分比"""
        for record in self:
            record.price_change = record.new_price - record.old_price
            if record.old_price:
                record.price_change_rate = (
                    (record.new_price - record.old_price) / record.old_price * 100
                )
            else:
                record.price_change_rate = 0.0

    # === 變更資訊 ===
    change_date = fields.Date(
        string='變更日期',
        required=True,
        default=fields.Date.today,
        index=True,
        help='價格變更的日期')

    change_reason = fields.Char(
        string='變更原因',
        help='說明為何調整價格')

    # === 操作者資訊 ===
    user_id = fields.Many2one(
        'res.users',
        string='操作者',
        default=lambda self: self.env.user,
        help='執行價格變更的使用者')

    # === 顯示名稱 ===
    def name_get(self):
        """顯示項目名稱和變更日期"""
        result = []
        for record in self:
            name = f'{record.item_id.name} - {record.change_date}'
            result.append((record.id, name))
        return result
