# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from collections import defaultdict
from datetime import date
from itertools import groupby

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round

# 累計數量比對/寫入的小數位數（避免浮點加總誤差造成無謂的重寫）
CUMULATIVE_PRECISION_DIGITS = 6
# 連結契約材料的列，本日數量上限（遠大於任何工程的單日用量；防 1e303 這種值讓之後的重算溢位）
MAX_MATERIAL_DAILY_QTY = 1e9


class DailyLogMaterial(models.Model):
    """工地材料管理 — 含約定之重要材料使用狀況及數量等"""
    _name = 'daily.log.material'
    _description = '工地材料管理'
    _order = 'daily_log_id, sequence'

    sequence = fields.Integer('排序', default=10)
    daily_log_id = fields.Many2one(
        'daily.log.sheet', string='施工日誌',
        required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        related='daily_log_id.supervision_project_id', store=True)

    name = fields.Char(string='施工項目', required=True)
    unit = fields.Char(string='單位')
    contract_qty = fields.Float(string='契約數量')
    daily_qty = fields.Float(string='本日完成數量')
    cumulative_qty = fields.Float(string='累計完成數量')
    note = fields.Text(string='備註')
    catalog_item_id = fields.Many2one(
        'construction.contract.material', string='契約材料',
        index=True, ondelete='restrict',
        help='連結到案件契約材料清單的列：累計由系統依日期重算，不可手改。'
             '沒有連結的列（人工手填）完全不受影響。')

    @api.constrains('catalog_item_id', 'daily_log_id')
    def _check_catalog_item_project(self):
        for rec in self:
            if not rec.catalog_item_id:
                continue
            if rec.catalog_item_id.project_id != rec.daily_log_id.supervision_project_id:
                raise ValidationError(
                    '契約材料「%s」不屬於本日誌的工程案件，無法連結。'
                    % rec.catalog_item_id.display_name)

    @api.constrains('catalog_item_id', 'daily_qty')
    def _check_catalog_daily_qty(self):
        # 只管連結列；未連結的人工手填列維持原本行為
        for rec in self.filtered('catalog_item_id'):
            # NaN 的比較一律為 False、inf 超過上限，都會被這一行擋下
            if not 0 <= (rec.daily_qty or 0.0) <= MAX_MATERIAL_DAILY_QTY:
                raise ValidationError(
                    '「%s」本日數量必須是 0～%s 之間的數字。' % (rec.name, '{:,.0f}'.format(MAX_MATERIAL_DAILY_QTY)))

    # -------------------------------------------------------------------------
    # 累計：普通欄位 + 顯式重算（不是 stored compute）
    # -------------------------------------------------------------------------

    @api.model
    def _recompute_catalog_cumulative(self, items):
        """重算指定契約材料清單項的累計數量。

        只讀取/寫入 catalog_item_id 屬於 items 的列；未連結的列永遠不會被碰到。
        同一天（含不同日誌）的列共用同一個累計 = 該日以前（含）所有列 daily_qty 加總。
        只寫有變的值。寫入直接呼叫上層 write（跳過本類別的 write 覆寫）防遞迴——
        不用 context 旗標，因為 context 可以由 JSON-RPC 的呼叫端帶進來。
        已鎖定日誌的連結列累計也會被改寫：累計是衍生值（同施工項目累計），不是使用者輸入。
        """
        if not items:
            return
        Material = self.sudo()
        rows = Material.search([('catalog_item_id', 'in', items.ids)])
        by_item = defaultdict(list)
        for row in rows:
            by_item[row.catalog_item_id.id].append(row)
        changes = defaultdict(list)  # 新累計值 -> [row ids]
        for item_rows in by_item.values():
            item_rows.sort(key=lambda r: (r.daily_log_id.log_date or date.min, r.id))
            running = 0.0
            # 同一天（含不同日誌）的列共用同一個累計
            for _day, day_rows in groupby(item_rows, key=lambda r: r.daily_log_id.log_date):
                day_rows = list(day_rows)
                running += sum(r.daily_qty or 0.0 for r in day_rows)
                total = float_round(running, precision_digits=CUMULATIVE_PRECISION_DIGITS)
                for row in day_rows:
                    current = float_round(
                        row.cumulative_qty or 0.0,
                        precision_digits=CUMULATIVE_PRECISION_DIGITS)
                    if current != total:
                        changes[total].append(row.id)
        for total, ids in changes.items():
            super(DailyLogMaterial, Material.browse(ids)).write({'cumulative_qty': total})

    def _check_locked_linked_rows(self):
        """已鎖定（超過 14 天且未解鎖）日誌的連結列，非 sudo 不可新增／修改／刪除。

        日誌表單的修改走 daily.log.sheet.write，那裡本來就擋鎖定；但材料列本身也能被直接
        寫（例如 JSON-RPC），連結列一改就會重算並改寫後面所有日誌的累計。前台路由、
        系統帶入走 sudo，各自先判斷過鎖定。未連結的人工手填列維持原本行為。
        """
        if self.env.su:
            return
        # 同一個交易裡剛建立的日誌不算鎖定：後台補登超過 14 天的日誌時，連同材料列一起建立要能成功
        # （create_date 是交易時間，不能由呼叫端偽造）
        now = self.env.cr.now()
        locked = self.filtered(lambda m: m.catalog_item_id and m.daily_log_id.create_date != now
                               and m.daily_log_id._is_edit_locked())
        if locked:
            raise UserError(
                '已鎖定（超過14天）的日誌不能修改契約材料列：\n'
                + '\n'.join('- %s %s' % (m.daily_log_id.complete_name, m.name) for m in locked)
                + '\n\n請先申請解鎖。')

    @api.onchange('catalog_item_id')
    def _onchange_catalog_item_id(self):
        # 後台新增列選了契約材料：名稱、單位、契約數量帶入（name 必填，不帶入就存不了）
        if self.catalog_item_id:
            self.name = self.catalog_item_id.name
            self.unit = self.catalog_item_id.unit
            self.contract_qty = self.catalog_item_id.contract_qty

    @api.model_create_multi
    def create(self, vals_list):
        rows = super().create(vals_list)
        rows._check_locked_linked_rows()
        self._recompute_catalog_cumulative(rows.catalog_item_id)
        return rows

    def write(self, vals):
        self._check_locked_linked_rows()
        items = self.catalog_item_id
        res = super().write(vals)
        self._check_locked_linked_rows()
        # 改到 daily_qty / 連結 / 所屬日誌，或有人直接手改連結列的累計 → 重算（覆蓋手改）
        if {'daily_qty', 'catalog_item_id', 'daily_log_id',
                'cumulative_qty'} & set(vals):
            self._recompute_catalog_cumulative(items | self.catalog_item_id)
        return res

    def unlink(self):
        self._check_locked_linked_rows()
        items = self.catalog_item_id
        res = super().unlink()
        self._recompute_catalog_cumulative(items)
        return res
