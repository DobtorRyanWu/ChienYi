# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class NotificationAcceptanceLine(models.Model):
    """
    通報單驗收明細

    設計參考: work.acceptance 數量追蹤
    """
    _name = 'notification.acceptance.line'
    _description = '通報單驗收明細'
    _order = 'sequence, id'

    # === 關聯 ===
    acceptance_id = fields.Many2one(
        'notification.acceptance', string='驗收單',
        required=True, ondelete='cascade', index=True)

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        related='acceptance_id.slip_id', store=True)

    slip_line_id = fields.Many2one(
        'reservation.notification.slip.line', string='通報單項目',
        required=True,
        domain="[('slip_id', '=', slip_id), ('qty_remaining', '>', 0)]")

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='acceptance_id.company_id', store=True)

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='acceptance_id.currency_id', store=True)

    sequence = fields.Integer(
        string='排序', default=10)

    # === 關聯欄位 (從通報單項目帶入) ===
    item_no = fields.Char(
        string='項次',
        related='slip_line_id.item_no', store=True)

    description = fields.Char(
        string='項目說明',
        related='slip_line_id.description', store=True)

    unit = fields.Char(
        string='單位',
        related='slip_line_id.unit', store=True)

    unit_price = fields.Monetary(
        string='單價',
        currency_field='currency_id',
        related='slip_line_id.unit_price', store=True)

    # === 數量追蹤 ===
    actual_qty = fields.Float(
        string='實際完成數量',
        related='slip_line_id.actual_qty')

    qty_previously_accepted = fields.Float(
        string='累計已驗收',
        compute='_compute_qty_previously_accepted',
        digits=(16, 4))

    qty_to_accept = fields.Float(
        string='待驗收數量',
        compute='_compute_qty_to_accept', store=True,
        digits=(16, 4))

    qty_accepted = fields.Float(
        string='本次驗收數量', required=True,
        digits=(16, 4),
        default=0.0)

    accepted_amount = fields.Monetary(
        string='驗收金額',
        currency_field='currency_id',
        compute='_compute_amount', store=True)

    # === 驗收結果 ===
    acceptance_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '條件式合格'),
        ('fail', '不合格'),
    ], string='驗收結果', default='pass')

    # === 備註 ===
    note = fields.Text(string='備註')

    # === 計算方法 ===
    @api.depends('slip_line_id', 'slip_line_id.qty_remaining')
    def _compute_qty_to_accept(self):
        """計算待驗收數量 (stored)"""
        for rec in self:
            if rec.slip_line_id:
                rec.qty_to_accept = rec.slip_line_id.qty_remaining
            else:
                rec.qty_to_accept = 0.0

    @api.depends('slip_line_id', 'slip_line_id.qty_accepted')
    def _compute_qty_previously_accepted(self):
        """計算累計已驗收數量 (non-stored)"""
        for rec in self:
            if rec.slip_line_id:
                rec.qty_previously_accepted = rec.slip_line_id.qty_accepted
            else:
                rec.qty_previously_accepted = 0.0

    @api.depends('qty_accepted', 'unit_price')
    def _compute_amount(self):
        for rec in self:
            rec.accepted_amount = rec.qty_accepted * rec.unit_price

    # === onchange 方法 ===
    @api.onchange('slip_line_id')
    def _onchange_slip_line(self):
        """選擇通報單項目時，預設驗收全部待驗收數量"""
        if self.slip_line_id:
            self.qty_accepted = self.slip_line_id.qty_remaining

    # === 約束驗證 ===
    @api.constrains('qty_accepted', 'qty_to_accept')
    def _check_qty(self):
        """驗證約束: 驗收數量限制"""
        for rec in self:
            # 忽略尚未儲存的記錄 (qty_to_accept 為 0 但 slip_line_id 存在時)
            if rec.slip_line_id and rec.acceptance_id.state == 'draft':
                max_qty = rec.slip_line_id.qty_remaining
                if rec.qty_accepted > max_qty:
                    raise ValidationError(
                        f'項目 {rec.item_no}: 驗收數量 ({rec.qty_accepted}) '
                        f'不得超過待驗收數量 ({max_qty})'
                    )
            if rec.qty_accepted < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 驗收數量不得為負數'
                )

    @api.constrains('acceptance_id', 'slip_line_id')
    def _check_unique_slip_line(self):
        """驗證約束：同一驗收單內不可重複項目"""
        for rec in self:
            if rec.acceptance_id and rec.slip_line_id:
                duplicate = self.search([
                    ('acceptance_id', '=', rec.acceptance_id.id),
                    ('slip_line_id', '=', rec.slip_line_id.id),
                    ('id', '!=', rec.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f'項目 {rec.item_no} 在此驗收單中已存在'
                    )

    def name_get(self):
        result = []
        for rec in self:
            name = f'{rec.item_no} - {rec.description} (驗收: {rec.qty_accepted} {rec.unit})'
            result.append((rec.id, name))
        return result
