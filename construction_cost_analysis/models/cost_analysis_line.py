# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CostAnalysisLine(models.Model):
    """
    成本分析明細

    支援：
    - 父子階層結構（_parent_store）
    - 自動比對價格庫
    - 5 級差異警示（0-5%, 5-10%, 10-20%, 20-30%, >30%）
    - 彙總項目識別
    """
    _name = 'cost.analysis.line'
    _description = '成本分析明細'
    _parent_store = True
    _order = 'planning_id, sequence, item_no, id'

    # === 基本關聯 ===
    planning_id = fields.Many2one(
        'cost.analysis',
        string='成本分析',
        required=True,
        ondelete='cascade',
        index=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='planning_id.company_id',
        store=True,
        index=True)

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='工項顯示順序')

    # === 階層結構 ===
    parent_id = fields.Many2one(
        'cost.analysis.line',
        string='上層工項',
        index=True,
        ondelete='cascade')

    parent_path = fields.Char(
        index=True,
        help='樹狀結構路徑')

    child_ids = fields.One2many(
        'cost.analysis.line',
        'parent_id',
        string='子工項')

    # === 工項資訊 ===
    item_no = fields.Char(
        string='項目編號',
        help='工項編號')

    name = fields.Char(
        string='項目名稱',
        required=True,
        help='工項名稱')

    unit = fields.Char(
        string='單位',
        help='計量單位')

    ref_item_code = fields.Char(
        string='參考工項代碼',
        index=True,
        help='標單中的 refItemCode，用於匹配價格庫')

    unit_id = fields.Many2one(
        'uom.uom', string='單位（標準）',
        help='由工項匯入時同步帶入，用於提升比對準確率')

    task_id = fields.Many2one(
        'project.task',
        string='來源工項',
        ondelete='set null',
        index=True,
        help='模式1（從專案匯入）時設定，用於資料追溯')

    product_id = fields.Many2one(
        'product.product',
        string='標準工項',
        compute='_compute_product_id',
        store=True,
        index=True,
        help='從來源工項取得，用於 Strategy 0 精確比對')

    @api.depends('task_id.product_id')
    def _compute_product_id(self):
        for line in self:
            line.product_id = line.task_id.product_id if line.task_id else False

    match_status = fields.Selection([
        ('none', '未比對'),
        ('matched', '已比對'),
        ('ambiguous', '多結果待確認'),
    ], string='比對狀態', default='none',
       help='成本分析比對結果；舊資料升級後為 None，filter 請用 not match_status')

    # === 契約預算 ===
    quantity = fields.Float(
        string='契約數量',
        digits=(16, 4),
        help='契約預估數量')

    contract_unit_price = fields.Float(
        string='契約單價',
        digits=(16, 2),
        help='契約預估單價')

    contract_amount = fields.Float(
        string='契約金額',
        compute='_compute_contract_amount',
        store=True,
        digits=(16, 2),
        help='契約數量 × 契約單價')

    @api.depends('quantity', 'contract_unit_price')
    def _compute_contract_amount(self):
        """計算契約金額"""
        for line in self:
            line.contract_amount = line.quantity * line.contract_unit_price

    # === 價格庫比對 ===
    library_item_id = fields.Many2one(
        'price.library.item',
        string='價格庫項目',
        help='關聯的價格庫項目')

    suggested_unit_price = fields.Float(
        string='建議單價',
        compute='_compute_suggested_prices',
        store=True,
        digits=(16, 2),
        help='從價格庫取得的建議單價')

    suggested_amount = fields.Float(
        string='建議金額',
        compute='_compute_suggested_prices',
        store=True,
        digits=(16, 2),
        help='契約數量 × 建議單價')

    @api.depends('library_item_id', 'library_item_id.suggested_unit_price', 'quantity')
    def _compute_suggested_prices(self):
        """計算建議單價與建議金額"""
        for line in self:
            if line.library_item_id and line.library_item_id.suggested_unit_price > 0:
                line.suggested_unit_price = line.library_item_id.suggested_unit_price
                line.suggested_amount = line.quantity * line.suggested_unit_price
            else:
                line.suggested_unit_price = 0.0
                line.suggested_amount = 0.0

    has_suggestion = fields.Boolean(
        string='有建議單價',
        compute='_compute_has_suggestion',
        store=True,
        help='是否已匹配到價格庫並有建議單價')

    @api.depends('library_item_id', 'suggested_unit_price')
    def _compute_has_suggestion(self):
        """判斷是否有建議單價"""
        for line in self:
            line.has_suggestion = bool(line.library_item_id and line.suggested_unit_price > 0)

    # === 差異分析 ===
    price_variance_amount = fields.Float(
        string='差異金額',
        compute='_compute_price_variance',
        store=True,
        digits=(16, 2),
        help='契約金額 - 建議金額')

    price_variance_pct = fields.Float(
        string='差異百分比 (%)',
        compute='_compute_price_variance',
        store=True,
        digits=(12, 2),
        help='(契約單價 - 建議單價) / 建議單價 × 100%')

    price_variance_level = fields.Selection([
        ('excellent', '優良 (0-5%)'),
        ('good', '良好 (5-10%)'),
        ('warning', '警示 (10-20%)'),
        ('alert', '注意 (20-30%)'),
        ('critical', '嚴重 (>30%)'),
    ], string='差異等級', compute='_compute_price_variance', store=True,
       help='基於差異百分比的 5 級警示')

    @api.depends('contract_unit_price', 'suggested_unit_price', 'contract_amount', 'suggested_amount')
    def _compute_price_variance(self):
        """
        計算差異金額、百分比與等級

        5 級警示標準：
        - 0-5%: excellent (綠色)
        - 5-10%: good (淺綠)
        - 10-20%: warning (黃色)
        - 20-30%: alert (橙色)
        - >30%: critical (紅色)
        """
        for line in self:
            if line.has_suggestion and line.suggested_unit_price > 0:
                # 計算差異金額
                variance_amount = line.contract_amount - line.suggested_amount

                # 計算差異百分比（基於單價）
                variance_pct = abs(
                    (line.contract_unit_price - line.suggested_unit_price) /
                    line.suggested_unit_price * 100.0
                )

                # 判定差異等級
                if variance_pct <= 5.0:
                    level = 'excellent'
                elif variance_pct <= 10.0:
                    level = 'good'
                elif variance_pct <= 20.0:
                    level = 'warning'
                elif variance_pct <= 30.0:
                    level = 'alert'
                else:
                    level = 'critical'

                line.price_variance_amount = variance_amount
                line.price_variance_pct = variance_pct
                line.price_variance_level = level
            else:
                line.price_variance_amount = 0.0
                line.price_variance_pct = 0.0
                line.price_variance_level = False

    # === 彙總項目識別 ===
    is_summary_item = fields.Boolean(
        string='彙總項目',
        compute='_compute_is_summary_item',
        store=True,
        help='是否為彙總項目（有子工項）')

    @api.depends('child_ids')
    def _compute_is_summary_item(self):
        """判斷是否為彙總項目"""
        for line in self:
            line.is_summary_item = bool(line.child_ids)

    # === 顯示名稱 ===
    def name_get(self):
        """顯示編號和名稱"""
        result = []
        for line in self:
            if line.item_no:
                name = f'[{line.item_no}] {line.name}'
            else:
                name = line.name
            result.append((line.id, name))
        return result
