# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import ValidationError


class PriceLibraryItem(models.Model):
    """
    價格庫項目

    標準工項單價資料，包含：
    - 基本資訊：名稱、編號、分類
    - 規格與單位
    - 價格資訊：單價、價格日期、來源
    - 成本組成：材料費、工資、機具費、管理費
    - 價格歷史追蹤
    """
    _name = 'price.library.item'
    _description = '價格庫項目'
    _order = 'category_id, item_no, name'
    _inherit = ['mail.thread']

    # === 基本資訊 ===
    name = fields.Char(
        string='項目名稱',
        required=True,
        index=True,
        tracking=True,
        help='工項名稱')

    item_no = fields.Char(
        string='項目編號',
        index=True,
        tracking=True,
        help='項目編號，用於快速識別和排序（注意：不同專案的相同編號可能指不同工項）')

    parent_item_no = fields.Char(
        string='父工項編號',
        index=True,
        help='父工項編號，用於參考層級關係（僅供參考，不參與唯一性判斷）')

    # === 多公司支援 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help='所屬公司，每個公司有獨立的價格庫')

    description = fields.Text(
        string='項目說明',
        help='工項的詳細說明')

    category_id = fields.Many2one(
        'price.library.category',
        string='分類',
        required=True,
        index=True,
        tracking=True,
        help='價格項目所屬的分類')

    # === 規格與單位 ===
    unit = fields.Char(
        string='單位',
        required=True,
        help='計量單位，如：M, M2, M3, 式, KG')

    specification = fields.Char(
        string='規格',
        help='工項規格說明')

    # === 價格資訊 ===
    unit_price = fields.Float(
        string='單價',
        required=True,
        digits=(12, 2),
        tracking=True,
        help='工項單價')

    price_date = fields.Date(
        string='價格日期',
        default=fields.Date.today,
        tracking=True,
        help='此單價的有效日期或更新日期')

    price_source = fields.Char(
        string='價格來源',
        help='例如：公共工程價格資料庫、廠商報價、歷史紀錄')

    # === 成本組成 (選填) ===
    material_cost = fields.Float(
        string='材料費',
        digits=(12, 2),
        help='材料成本')

    labor_cost = fields.Float(
        string='工資',
        digits=(12, 2),
        help='人工成本')

    equipment_cost = fields.Float(
        string='機具費',
        digits=(12, 2),
        help='機具設備成本')

    overhead_cost = fields.Float(
        string='管理費及利潤',
        digits=(12, 2),
        help='管理費用及利潤')

    cost_breakdown_total = fields.Float(
        string='成本組成合計',
        compute='_compute_cost_breakdown_total',
        digits=(12, 2),
        store=True,
        help='材料費 + 工資 + 機具費 + 管理費及利潤')

    has_cost_breakdown = fields.Boolean(
        string='有成本組成',
        compute='_compute_has_cost_breakdown',
        store=True,
        help='是否已填寫成本組成明細')

    @api.depends('material_cost', 'labor_cost', 'equipment_cost', 'overhead_cost')
    def _compute_cost_breakdown_total(self):
        """計算成本組成合計"""
        for item in self:
            item.cost_breakdown_total = (
                item.material_cost +
                item.labor_cost +
                item.equipment_cost +
                item.overhead_cost
            )

    @api.depends('material_cost', 'labor_cost', 'equipment_cost', 'overhead_cost')
    def _compute_has_cost_breakdown(self):
        """判斷是否有填寫成本組成"""
        for item in self:
            item.has_cost_breakdown = (
                item.material_cost > 0 or
                item.labor_cost > 0 or
                item.equipment_cost > 0 or
                item.overhead_cost > 0
            )

    @api.constrains('material_cost', 'labor_cost', 'equipment_cost',
                   'overhead_cost', 'unit_price')
    def _check_cost_breakdown(self):
        """
        驗證成本組成合計與單價一致

        只有當有填寫成本組成時才進行驗證
        允許誤差在 0.01 以內（避免浮點數計算誤差）
        """
        for item in self:
            total = (item.material_cost + item.labor_cost +
                    item.equipment_cost + item.overhead_cost)
            # 只有當有填寫成本組成時才驗證
            if total > 0 and abs(total - item.unit_price) > 0.01:
                raise ValidationError(
                    f'成本組成合計 ({total:.2f}) 與單價 ({item.unit_price:.2f}) 不符！\n'
                    f'差異: {abs(total - item.unit_price):.2f}'
                )

    # === 狀態 ===
    active = fields.Boolean(
        string='啟用',
        default=True,
        help='停用的項目不會顯示在選擇清單中')

    # === 歷史價格 ===
    history_ids = fields.One2many(
        'price.library.item.history',
        'item_id',
        string='價格歷史',
        help='此項目的歷史價格變更記錄')

    history_count = fields.Integer(
        string='歷史記錄數',
        compute='_compute_history_count',
        help='歷史價格記錄數量')

    @api.depends('history_ids')
    def _compute_history_count(self):
        """計算歷史記錄數量"""
        for item in self:
            item.history_count = len(item.history_ids)

    # === 價格來源追蹤（自動化） ===
    source_ids = fields.One2many(
        'price.library.item.source',
        'library_item_id',
        string='價格來源',
        help='此項目從哪些專案工項提取而來')

    source_count = fields.Integer(
        string='來源數',
        compute='_compute_source_count',
        store=True,
        help='來源記錄數量')

    @api.depends('source_ids')
    def _compute_source_count(self):
        """計算來源記錄數量"""
        for item in self:
            item.source_count = len(item.source_ids)

    # === 系統建議單價（基於來源統計） ===
    suggested_unit_price = fields.Float(
        string='建議單價',
        compute='_compute_price_statistics',
        store=True,
        digits=(12, 2),
        help='基於所有來源的平均單價')

    price_cv = fields.Float(
        string='變異係數 CV (%)',
        compute='_compute_price_statistics',
        store=True,
        digits=(12, 2),
        help='價格變異係數 (Coefficient of Variation)，用於衡量價格穩定性')

    price_std_dev = fields.Float(
        string='標準差',
        compute='_compute_price_statistics',
        digits=(12, 2),
        help='價格標準差')

    min_source_price = fields.Float(
        string='最低來源單價',
        compute='_compute_price_statistics',
        digits=(12, 2),
        help='所有來源中的最低單價')

    max_source_price = fields.Float(
        string='最高來源單價',
        compute='_compute_price_statistics',
        digits=(12, 2),
        help='所有來源中的最高單價')

    # === 自動建立標記 ===
    is_auto_created = fields.Boolean(
        string='自動建立',
        default=False,
        help='是否由專案結案時自動建立')

    auto_created_date = fields.Date(
        string='自動建立日期',
        help='自動建立的日期')

    @api.depends('source_ids', 'source_ids.unit_price')
    def _compute_price_statistics(self):
        """
        計算價格統計資訊

        - suggested_unit_price: 所有來源的平均單價
        - price_std_dev: 標準差
        - price_cv: 變異係數 (CV = 標準差 / 平均值 × 100%)
        - min_source_price: 最低單價
        - max_source_price: 最高單價

        當只有 1 筆來源時，CV 設為 0（無變異）
        """
        for item in self:
            prices = item.source_ids.mapped('unit_price')
            n = len(prices)

            if n == 0:
                # 無來源記錄
                item.suggested_unit_price = item.unit_price
                item.price_std_dev = 0.0
                item.price_cv = 0.0
                item.min_source_price = 0.0
                item.max_source_price = 0.0
            elif n == 1:
                # 只有 1 筆來源，CV 為 0
                item.suggested_unit_price = prices[0]
                item.price_std_dev = 0.0
                item.price_cv = 0.0
                item.min_source_price = prices[0]
                item.max_source_price = prices[0]
            else:
                # 多筆來源，計算統計值
                import statistics
                mean = statistics.mean(prices)
                std_dev = statistics.stdev(prices)
                cv = (std_dev / mean * 100.0) if mean > 0 else 0.0

                item.suggested_unit_price = mean
                item.price_std_dev = std_dev
                item.price_cv = cv
                item.min_source_price = min(prices)
                item.max_source_price = max(prices)

    # === CRUD 覆寫 ===
    def write(self, vals):
        """
        覆寫寫入方法以記錄價格變更歷史

        當 unit_price 變更時，自動建立歷史記錄
        """
        if 'unit_price' in vals:
            for item in self:
                # 只有當價格真的有變更時才記錄
                if item.unit_price != vals['unit_price']:
                    self.env['price.library.item.history'].create({
                        'item_id': item.id,
                        'old_price': item.unit_price,
                        'new_price': vals['unit_price'],
                        'change_date': fields.Date.today(),
                        'change_reason': vals.get('price_change_reason', ''),
                    })
        # 移除臨時欄位
        vals.pop('price_change_reason', None)
        return super().write(vals)

    # === 顯示名稱 ===
    def name_get(self):
        """顯示編號和名稱"""
        result = []
        for item in self:
            if item.item_no:
                name = f'[{item.item_no}] {item.name}'
            else:
                name = item.name
            result.append((item.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """支援依編號或名稱搜尋"""
        domain = domain or []
        if name:
            domain = ['|', ('item_no', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    # === 動作方法 ===
    def action_view_history(self):
        """查看價格歷史"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '價格歷史',
            'res_model': 'price.library.item.history',
            'view_mode': 'list,form',
            'domain': [('item_id', '=', self.id)],
            'context': {'default_item_id': self.id},
        }

    def action_update_price(self):
        """開啟價格更新精靈（可擴展）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '更新價格',
            'res_model': 'price.library.item',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {'focus_field': 'unit_price'},
        }

    def action_view_sources(self):
        """查看價格來源記錄"""
        self.ensure_one()
        return {
            'name': f'{self.name} - 價格來源',
            'type': 'ir.actions.act_window',
            'res_model': 'price.library.item.source',
            'view_mode': 'list,form',
            'domain': [('library_item_id', '=', self.id)],
            'context': {'default_library_item_id': self.id},
        }

    # === SQL 約束 ===
    _sql_constraints = [
        ('item_unique_per_company',
         'UNIQUE(company_id, name, unit)',
         '同一公司內，相同名稱和單位的項目已存在！'),
        ('unit_price_positive', 'CHECK(unit_price >= 0)',
         '單價不可為負數！'),
        ('material_cost_positive', 'CHECK(material_cost >= 0)',
         '材料費不可為負數！'),
        ('labor_cost_positive', 'CHECK(labor_cost >= 0)',
         '工資不可為負數！'),
        ('equipment_cost_positive', 'CHECK(equipment_cost >= 0)',
         '機具費不可為負數！'),
        ('overhead_cost_positive', 'CHECK(overhead_cost >= 0)',
         '管理費及利潤不可為負數！'),
    ]
