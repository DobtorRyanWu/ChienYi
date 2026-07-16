# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PriceLibraryItemSource(models.Model):
    """
    價格庫項目來源

    追蹤價格庫項目從哪些專案的工項提取而來
    用於計算建議單價（平均值）和價格穩定性（變異係數 CV）
    """
    _name = 'price.library.item.source'
    _description = '價格庫項目來源'
    _order = 'created_date desc, id desc'

    # === 基本關聯 ===
    library_item_id = fields.Many2one(
        'price.library.item',
        string='價格庫項目',
        required=True,
        ondelete='cascade',
        index=True,
        help='關聯的價格庫項目')

    project_id = fields.Many2one(
        'project.project',
        string='來源專案',
        required=True,
        ondelete='restrict',
        index=True,
        help='此價格來自哪個專案')

    task_id = fields.Many2one(
        'project.task',
        string='來源工項',
        required=True,
        ondelete='restrict',
        index=True,
        help='此價格來自哪個工項')

    # === 價格資訊 ===
    unit_price = fields.Float(
        string='契約單價',
        required=True,
        digits=(12, 2),
        help='該專案此工項的契約單價')

    planned_qty = fields.Float(
        string='契約數量',
        digits=(12, 2),
        help='該專案此工項的契約數量')

    planned_amount = fields.Float(
        string='契約金額',
        digits=(12, 2),
        help='該專案此工項的契約金額（單價 × 數量）')

    # === 建立資訊 ===
    created_date = fields.Date(
        string='建立日期',
        default=fields.Date.today,
        required=True,
        index=True,
        help='此來源記錄建立的日期')

    created_by_id = fields.Many2one(
        'res.users',
        string='建立者',
        default=lambda self: self.env.user,
        help='建立此記錄的使用者')

    # === 關聯欄位（用於顯示） ===
    project_name = fields.Char(
        string='專案名稱',
        related='project_id.name',
        store=True,
        help='來源專案名稱')

    project_code = fields.Char(
        string='專案編號',
        related='project_id.code',
        store=True,
        help='來源專案編號')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='library_item_id.company_id',
        store=True,
        index=True,
        help='所屬公司')

    # === SQL 約束 ===
    _sql_constraints = [
        ('task_library_item_unique',
         'UNIQUE(library_item_id, task_id)',
         '同一工項不可重複提取到相同價格庫項目！'),
        ('unit_price_positive',
         'CHECK(unit_price >= 0)',
         '契約單價不可為負數！'),
    ]

    # === 顯示名稱 ===
    def name_get(self):
        """顯示來源資訊"""
        result = []
        for source in self:
            name = f'{source.project_code or source.project_name} - {source.unit_price:.2f}'
            result.append((source.id, name))
        return result
