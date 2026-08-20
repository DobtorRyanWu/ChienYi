# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class GeneralRealtimeProfit(models.Model):
    """
    一般式即時損益

    設計說明：
    - 計算工程的即時損益狀況
    - 追蹤收入、成本與毛利
    - 支援多種成本類別
    - 提供即時財務狀況分析
    """
    _name = 'general.realtime.profit'
    _description = '一般式即時損益'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
    _order = 'report_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='報告編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('general.realtime.profit') or '/')

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        tracking=True,
        index=True,
        domain="[('project_type', '=', 'general')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='project_id.currency_id',
        store=True)

    # === 報告資訊 ===
    report_date = fields.Date(
        string='報告日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    report_type = fields.Selection([
        ('monthly', '月報'),
        ('quarterly', '季報'),
        ('annual', '年報'),
        ('adhoc', '臨時報告'),
    ], string='報告類型', required=True, default='monthly', tracking=True)

    period_start = fields.Date(
        string='期間起',
        required=True)

    period_end = fields.Date(
        string='期間迄',
        required=True)

    # === 報告人 ===
    reporter_id = fields.Many2one(
        'res.users',
        string='編製人',
        default=lambda self: self.env.uid,
        tracking=True)

    reviewer_id = fields.Many2one(
        'res.users',
        string='審核人',
        tracking=True)

    review_date = fields.Date(
        string='審核日期')

    # === 契約資訊 (快照) ===
    contract_amount = fields.Monetary(
        string='契約金額',
        currency_field='currency_id',
        help='契約總金額')

    change_order_amount = fields.Monetary(
        string='變更追加減金額',
        currency_field='currency_id',
        help='契約變更追加減總額')

    total_contract_amount = fields.Monetary(
        string='調整後契約金額',
        compute='_compute_total_contract',
        store=True,
        currency_field='currency_id')

    @api.depends('contract_amount', 'change_order_amount')
    def _compute_total_contract(self):
        for record in self:
            record.total_contract_amount = record.contract_amount + record.change_order_amount

    # === 收入 (累計) ===
    estimated_revenue = fields.Monetary(
        string='累計估驗金額',
        currency_field='currency_id',
        tracking=True,
        help='截至報告日累計已估驗請款金額')

    received_revenue = fields.Monetary(
        string='累計實收金額',
        currency_field='currency_id',
        tracking=True,
        help='截至報告日累計已收款金額')

    receivable_amount = fields.Monetary(
        string='應收帳款',
        compute='_compute_receivable',
        store=True,
        currency_field='currency_id',
        help='估驗金額 - 實收金額')

    @api.depends('estimated_revenue', 'received_revenue')
    def _compute_receivable(self):
        for record in self:
            record.receivable_amount = record.estimated_revenue - record.received_revenue

    # === 收入 (本期) ===
    period_estimated_revenue = fields.Monetary(
        string='本期估驗金額',
        currency_field='currency_id',
        help='本期新增估驗金額')

    period_received_revenue = fields.Monetary(
        string='本期收款金額',
        currency_field='currency_id',
        help='本期實際收款金額')

    # === 成本明細 ===
    cost_line_ids = fields.One2many(
        'general.realtime.profit.cost',
        'profit_id',
        string='成本明細')

    # === 累計成本 ===
    total_labor_cost = fields.Monetary(
        string='累計人工成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_material_cost = fields.Monetary(
        string='累計材料成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_equipment_cost = fields.Monetary(
        string='累計機具成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_subcontract_cost = fields.Monetary(
        string='累計分包成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_indirect_cost = fields.Monetary(
        string='累計間接成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_other_cost = fields.Monetary(
        string='累計其他成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    total_cost = fields.Monetary(
        string='累計總成本',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id')

    @api.depends('cost_line_ids.cumulative_amount', 'cost_line_ids.cost_type')
    def _compute_costs(self):
        for record in self:
            costs = record.cost_line_ids
            record.total_labor_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'labor').mapped('cumulative_amount'))
            record.total_material_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'material').mapped('cumulative_amount'))
            record.total_equipment_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'equipment').mapped('cumulative_amount'))
            record.total_subcontract_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'subcontract').mapped('cumulative_amount'))
            record.total_indirect_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'indirect').mapped('cumulative_amount'))
            record.total_other_cost = sum(
                costs.filtered(lambda c: c.cost_type == 'other').mapped('cumulative_amount'))
            record.total_cost = sum(costs.mapped('cumulative_amount'))

    # === 損益計算 ===
    gross_profit = fields.Monetary(
        string='毛利',
        compute='_compute_profit',
        store=True,
        currency_field='currency_id',
        help='累計估驗金額 - 累計總成本')

    gross_profit_rate = fields.Float(
        string='毛利率 (%)',
        compute='_compute_profit',
        store=True,
        digits=(5, 2))

    net_cash_flow = fields.Monetary(
        string='淨現金流',
        compute='_compute_profit',
        store=True,
        currency_field='currency_id',
        help='累計實收金額 - 累計總成本')

    @api.depends('estimated_revenue', 'received_revenue', 'total_cost')
    def _compute_profit(self):
        for record in self:
            record.gross_profit = record.estimated_revenue - record.total_cost
            if record.estimated_revenue:
                record.gross_profit_rate = (record.gross_profit / record.estimated_revenue) * 100
            else:
                record.gross_profit_rate = 0.0
            record.net_cash_flow = record.received_revenue - record.total_cost

    # === 預估完工損益 ===
    estimated_final_revenue = fields.Monetary(
        string='預估完工總收入',
        currency_field='currency_id',
        help='預估工程完工時的總收入')

    estimated_final_cost = fields.Monetary(
        string='預估完工總成本',
        currency_field='currency_id',
        help='預估工程完工時的總成本')

    estimated_final_profit = fields.Monetary(
        string='預估完工毛利',
        compute='_compute_final_profit',
        store=True,
        currency_field='currency_id')

    estimated_final_profit_rate = fields.Float(
        string='預估完工毛利率 (%)',
        compute='_compute_final_profit',
        store=True,
        digits=(5, 2))

    @api.depends('estimated_final_revenue', 'estimated_final_cost')
    def _compute_final_profit(self):
        for record in self:
            record.estimated_final_profit = record.estimated_final_revenue - record.estimated_final_cost
            if record.estimated_final_revenue:
                record.estimated_final_profit_rate = (
                    record.estimated_final_profit / record.estimated_final_revenue) * 100
            else:
                record.estimated_final_profit_rate = 0.0

    # === 進度資訊 ===
    actual_progress = fields.Float(
        string='實際進度 (%)',
        digits=(5, 2),
        help='截至報告日的實際累計進度')

    cost_progress = fields.Float(
        string='成本進度 (%)',
        compute='_compute_cost_progress',
        store=True,
        digits=(5, 2),
        help='累計成本 / 預估完工總成本')

    @api.depends('total_cost', 'estimated_final_cost')
    def _compute_cost_progress(self):
        for record in self:
            if record.estimated_final_cost:
                record.cost_progress = (record.total_cost / record.estimated_final_cost) * 100
            else:
                record.cost_progress = 0.0

    # === 狀況分析 ===
    profit_status = fields.Selection([
        ('good', '良好'),
        ('normal', '正常'),
        ('warning', '警示'),
        ('critical', '危險'),
    ], string='獲利狀態',
       compute='_compute_profit_status',
       store=True)

    @api.depends('gross_profit_rate', 'net_cash_flow')
    def _compute_profit_status(self):
        for record in self:
            if record.gross_profit_rate >= 15:
                record.profit_status = 'good'
            elif record.gross_profit_rate >= 5:
                record.profit_status = 'normal'
            elif record.gross_profit_rate >= 0:
                record.profit_status = 'warning'
            else:
                record.profit_status = 'critical'

    # === 說明欄位 ===
    analysis_summary = fields.Html(
        string='損益分析摘要',
        help='本期損益狀況分析說明')

    cost_variance_note = fields.Text(
        string='成本差異說明',
        help='成本與預算差異的原因說明')

    risk_description = fields.Text(
        string='風險說明',
        help='可能影響獲利的風險因素')

    improvement_plan = fields.Text(
        string='改善計畫',
        help='針對獲利改善的行動計畫')

    # === 審核意見 ===
    review_comment = fields.Text(
        string='審核意見')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_profit_attachment_rel',
        'profit_id', 'attachment_id',
        string='相關附件')

    def _attachment_default_category(self):
        """即時損益附件 → 12-文書資料 / 11-其他資料"""
        return self.env.ref(
            'construction_supervision_base.cat_12_11',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_default_folder(self):
        """即時損益附件 → 12-文書資料 / 11-其他資料 / 即時損益

        末層用固定名稱而非報告編號：損益報告是同一個案子持續更新的東西，
        每份報告各開一個資料夾只會讓樹變得很碎。

        因為是多份報告共用的資料夾，bind_source 要關掉 —— 綁了會變成
        「開啟來源單據」永遠跳到剛好第一個建它的那份報告。
        """
        return self._attachment_category_folder(['即時損益'], bind_source=False)

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提交'),
        ('reviewed', '已審核'),
        ('approved', '已核准'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 動作方法 ===
    def action_submit(self):
        """提交報告"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以提交')
            record.state = 'submitted'

    def action_review(self):
        """審核報告"""
        for record in self:
            if record.state != 'submitted':
                raise UserError('只有已提交狀態可以審核')
            record.write({
                'state': 'reviewed',
                'reviewer_id': self.env.uid,
                'review_date': fields.Date.today(),
            })

    def action_approve(self):
        """核准報告"""
        for record in self:
            if record.state != 'reviewed':
                raise UserError('只有已審核狀態可以核准')
            record.state = 'approved'

    def action_return(self):
        """退回修改"""
        for record in self:
            if record.state not in ('submitted', 'reviewed'):
                raise UserError('只有已提交或已審核狀態可以退回')
            record.state = 'draft'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state != 'submitted':
                raise UserError('只有已提交狀態可以重設')
            record.state = 'draft'

    # === 計算方法 ===
    def action_sync_from_project(self):
        """從工程同步資料"""
        self.ensure_one()
        if self.project_id:
            self.contract_amount = self.project_id.contract_amount
            self.actual_progress = self.project_id.actual_progress
            # 預設預估完工收入等於調整後契約金額
            if not self.estimated_final_revenue:
                self.estimated_final_revenue = self.total_contract_amount

    def action_create_cost_lines(self):
        """建立成本類別明細"""
        self.ensure_one()
        if self.cost_line_ids:
            raise UserError('已有成本明細，如需重新建立請先清除')

        cost_types = [
            ('labor', '人工成本'),
            ('material', '材料成本'),
            ('equipment', '機具成本'),
            ('subcontract', '分包成本'),
            ('indirect', '間接成本'),
            ('other', '其他成本'),
        ]

        lines = []
        for cost_type, name in cost_types:
            lines.append(Command.create({
                'cost_type': cost_type,
                'description': name,
            }))

        self.cost_line_ids = lines
        return True

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('general.realtime.profit') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft',):
                raise UserError('只有草稿狀態的報告可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('period_start', 'period_end')
    def _check_period_dates(self):
        for record in self:
            if record.period_start and record.period_end:
                if record.period_end < record.period_start:
                    raise ValidationError('期間迄日不得早於起日')


class GeneralRealtimeProfitCost(models.Model):
    """
    一般式即時損益成本明細

    設計說明：
    - 記錄各類成本明細
    - 區分本期與累計金額
    """
    _name = 'general.realtime.profit.cost'
    _description = '一般式即時損益成本明細'
    _order = 'sequence, id'

    # === 關聯 ===
    profit_id = fields.Many2one(
        'general.realtime.profit',
        string='損益報告',
        required=True,
        ondelete='cascade')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='profit_id.currency_id',
        store=True)

    # === 成本類別 ===
    sequence = fields.Integer(
        string='序號',
        default=10)

    cost_type = fields.Selection([
        ('labor', '人工成本'),
        ('material', '材料成本'),
        ('equipment', '機具成本'),
        ('subcontract', '分包成本'),
        ('indirect', '間接成本'),
        ('other', '其他成本'),
    ], string='成本類別', required=True)

    description = fields.Char(
        string='說明')

    # === 金額 ===
    budget_amount = fields.Monetary(
        string='預算金額',
        currency_field='currency_id',
        help='此類別的預算金額')

    prev_amount = fields.Monetary(
        string='前期累計',
        currency_field='currency_id',
        help='截至上期的累計成本')

    period_amount = fields.Monetary(
        string='本期發生',
        currency_field='currency_id',
        help='本期發生的成本')

    cumulative_amount = fields.Monetary(
        string='累計金額',
        compute='_compute_cumulative',
        store=True,
        currency_field='currency_id')

    remaining_budget = fields.Monetary(
        string='剩餘預算',
        compute='_compute_cumulative',
        store=True,
        currency_field='currency_id')

    budget_usage_rate = fields.Float(
        string='預算使用率 (%)',
        compute='_compute_cumulative',
        store=True,
        digits=(5, 2))

    @api.depends('budget_amount', 'prev_amount', 'period_amount')
    def _compute_cumulative(self):
        for line in self:
            line.cumulative_amount = line.prev_amount + line.period_amount
            line.remaining_budget = line.budget_amount - line.cumulative_amount
            if line.budget_amount:
                line.budget_usage_rate = (line.cumulative_amount / line.budget_amount) * 100
            else:
                line.budget_usage_rate = 0.0

    # === 備註 ===
    note = fields.Text(string='備註')
