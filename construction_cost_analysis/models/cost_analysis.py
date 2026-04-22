# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class CostAnalysis(models.Model):
    """成本分析"""
    _name = 'cost.analysis'
    _description = '成本分析'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # ========================================
    # 基本資訊
    # ========================================
    name = fields.Char(
        string='名稱',
        required=True,
        tracking=True,
        help='成本分析名稱'
    )

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='company_id.currency_id',
        store=True,
        readonly=True
    )

    # ========================================
    # 匯入模式
    # ========================================
    import_mode = fields.Selection(
        [
            ('project', '從專案匯入'),
            ('xml', '從 XML 匯入'),
        ],
        string='匯入模式',
        required=True,
        default='project',
        tracking=True,
        help='選擇從既有專案或 XML 標單匯入工項'
    )

    source_project_id = fields.Many2one(
        'supervision.project',
        string='來源專案',
        tracking=True,
        help='從此專案匯入契約工項'
    )

    xml_file = fields.Binary(
        string='XML 檔案',
        attachment=True,
        help='上傳政府採購網 XML 標單'
    )

    xml_filename = fields.Char(
        string='檔案名稱'
    )

    # ========================================
    # 狀態
    # ========================================
    state = fields.Selection(
        [
            ('draft', '草稿'),
            ('confirmed', '已確認'),
            ('done', '完成'),
        ],
        string='狀態',
        default='draft',
        required=True,
        tracking=True
    )

    # ========================================
    # 預算明細
    # ========================================
    line_ids = fields.One2many(
        'cost.analysis.line',
        'planning_id',
        string='預算明細',
        copy=True
    )

    line_count = fields.Integer(
        string='明細數量',
        compute='_compute_line_statistics',
        store=True
    )

    # ========================================
    # 金額統計
    # ========================================
    total_budget = fields.Monetary(
        string='招標總價',
        compute='_compute_budget_totals',
        store=True,
        currency_field='currency_id',
        help='所有明細的契約金額總和'
    )

    suggested_total = fields.Monetary(
        string='建議總價',
        compute='_compute_budget_totals',
        store=True,
        currency_field='currency_id',
        help='所有有建議單價的明細，其建議金額總和'
    )

    variance_amount = fields.Monetary(
        string='差異金額',
        compute='_compute_variance',
        store=True,
        currency_field='currency_id',
        help='建議總價 - 預算總價'
    )

    variance_percent = fields.Float(
        string='差異百分比',
        compute='_compute_variance',
        store=True,
        digits=(16, 2),
        help='(差異金額 / 預算總價) × 100%'
    )

    # ========================================
    # 匹配統計
    # ========================================
    matched_line_count = fields.Integer(
        string='已匹配明細數',
        compute='_compute_line_statistics',
        store=True,
        help='有建議單價的明細數量'
    )

    match_rate = fields.Float(
        string='匹配率',
        compute='_compute_line_statistics',
        store=True,
        digits=(16, 2),
        help='(已匹配明細數 / 明細總數) × 100%'
    )

    # ========================================
    # Compute Methods
    # ========================================
    @api.depends('line_ids', 'line_ids.has_suggestion')
    def _compute_line_statistics(self):
        """計算明細統計"""
        for record in self:
            lines = record.line_ids.filtered(lambda l: not l.is_summary_item)
            record.line_count = len(lines)
            record.matched_line_count = len(lines.filtered(lambda l: l.has_suggestion))
            record.match_rate = (
                (record.matched_line_count / record.line_count * 100.0)
                if record.line_count > 0 else 0.0
            )

    @api.depends('line_ids', 'line_ids.contract_amount', 'line_ids.suggested_amount')
    def _compute_budget_totals(self):
        """計算預算總計"""
        for record in self:
            lines = record.line_ids.filtered(lambda l: not l.is_summary_item)
            record.total_budget = sum(lines.mapped('contract_amount'))
            # 只加總有建議單價的明細
            suggested_lines = lines.filtered(lambda l: l.has_suggestion)
            record.suggested_total = sum(suggested_lines.mapped('suggested_amount'))

    @api.depends('total_budget', 'suggested_total')
    def _compute_variance(self):
        """計算差異"""
        for record in self:
            record.variance_amount = record.suggested_total - record.total_budget
            record.variance_percent = (
                (record.variance_amount / record.total_budget * 100.0)
                if record.total_budget > 0 else 0.0
            )

    # ========================================
    # 狀態切換方法
    # ========================================
    def action_confirm(self):
        """確認"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以確認！')
            record.state = 'confirmed'

    def action_done(self):
        """完成"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError('只有已確認狀態可以完成！')
            record.state = 'done'

    def action_reset_to_draft(self):
        """重設為草稿"""
        for record in self:
            record.state = 'draft'

    # ========================================
    # 價格庫匯入方法
    # ========================================
    def action_import_suggested_prices(self):
        """從價格庫導入建議單價"""
        self.ensure_one()

        if not self.line_ids:
            raise UserError('沒有可匹配的明細！')

        PriceLibraryItem = self.env['price.library.item']
        matched_count = 0

        for line in self.line_ids.filtered(lambda l: not l.is_summary_item):
            # 匹配策略 1：精確匹配 ref_item_code（如果有）
            library_item = False
            if line.ref_item_code:
                library_item = PriceLibraryItem.search([
                    ('company_id', '=', self.company_id.id),
                    ('item_no', '=', line.ref_item_code),
                    ('active', '=', True),
                ], limit=1)

            # 匹配策略 2：組合匹配 name + unit
            if not library_item:
                library_item = PriceLibraryItem.search([
                    ('company_id', '=', self.company_id.id),
                    ('name', 'ilike', line.name),
                    ('unit', '=', line.unit),
                    ('active', '=', True),
                ], limit=1)

            # 如果找到匹配項，填入建議單價
            if library_item:
                line.library_item_id = library_item.id
                matched_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '價格庫匯入完成',
                'message': f'成功匹配 {matched_count} 筆明細',
                'type': 'success',
                'sticky': False,
            }
        }

    # ========================================
    # 統計分析方法
    # ========================================
    def action_view_statistics(self):
        """查看統計分析"""
        self.ensure_one()
        return {
            'name': f'{self.name} - 統計分析',
            'type': 'ir.actions.act_window',
            'res_model': 'cost.analysis',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {'form_view_initial_mode': 'readonly'},
        }
