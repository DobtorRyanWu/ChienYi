# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ReservationNotificationSlipLine(models.Model):
    """
    通報單詳細表項目

    設計說明:
    - planned_qty/planned_amount = 預算 (planned)
    - actual_qty/actual_amount = 實際執行
    - task_id 關聯契約工項（由 wizard 批次帶入）
    """
    _name = 'reservation.notification.slip.line'
    _description = '通報單詳細表項目'
    _order = 'sequence, item_no, id'

    # === 關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, ondelete='cascade', index=True)

    project_id = fields.Many2one(
        'supervision.project', string='所屬工程',
        related='slip_id.project_id', store=True)

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='slip_id.company_id', store=True)

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='slip_id.currency_id', store=True)

    sequence = fields.Integer(
        string='排序', default=10)

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task', string='契約工項',
        domain="[('supervision_project_id', '=', project_id)]",
        help='關聯的契約工項')

    parent_item_name = fields.Char(
        string='父工項',
        compute='_compute_parent_item_name', store=True)

    # === 項目基本資訊 ===
    item_no = fields.Char(
        string='項目編號', required=True,
        help='工項編號')

    description = fields.Char(
        string='項目及說明', required=True)

    unit = fields.Char(
        string='單位', required=True,
        help='計量單位，如：M, M2, M3, 式')

    unit_price = fields.Monetary(
        string='單價', required=True,
        currency_field='currency_id')

    # === 預算欄位 (預估需求) ===
    planned_qty = fields.Float(
        string='預估數量 (預算)',
        digits=(16, 4),
        help='預估施作數量')

    planned_amount = fields.Monetary(
        string='預估金額 (預算)',
        currency_field='currency_id',
        compute='_compute_planned_amount', store=True,
        help='planned_qty x unit_price')

    # === 實際執行欄位 ===
    actual_qty = fields.Float(
        string='實際完成數量',
        digits=(16, 4),
        help='實際施作完成數量')

    actual_amount = fields.Monetary(
        string='實際金額',
        currency_field='currency_id',
        compute='_compute_actual_amount', store=True,
        help='actual_qty x unit_price')

    # === Portal 需要的欄位 ===
    specification = fields.Text(
        string='規格說明')

    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate', store=True,
        digits=(5, 2),
        help='(actual_amount / planned_amount) x 100')

    # === 備註 ===
    note = fields.Text(string='備註')

    # === 計算方法 ===
    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        for line in self:
            line.planned_amount = line.planned_qty * line.unit_price

    @api.depends('actual_qty', 'unit_price')
    def _compute_actual_amount(self):
        for line in self:
            line.actual_amount = line.actual_qty * line.unit_price

    @api.depends('planned_amount', 'actual_amount')
    def _compute_completion_rate(self):
        for line in self:
            if line.planned_amount:
                line.completion_rate = (line.actual_amount / line.planned_amount) * 100
            else:
                line.completion_rate = 0.0

    @api.depends('task_id', 'task_id.parent_id', 'task_id.parent_id.name')
    def _compute_parent_item_name(self):
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.name
            else:
                line.parent_item_name = ''

    # === 約束驗證 ===
    @api.constrains('planned_qty', 'actual_qty', 'unit_price')
    def _check_positive_values(self):
        """驗證約束：數量與單價必須為正數"""
        for rec in self:
            if rec.planned_qty < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 預估數量不得為負數'
                )
            if rec.actual_qty < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 實際數量不得為負數'
                )
            if rec.unit_price < 0:
                raise ValidationError(
                    f'項目 {rec.item_no}: 單價不得為負數'
                )

    @api.constrains('slip_id', 'item_no')
    def _check_unique_item_no(self):
        """驗證約束：同一通報單內項次不可重複"""
        for rec in self:
            if rec.slip_id and rec.item_no:
                duplicate = self.search([
                    ('slip_id', '=', rec.slip_id.id),
                    ('item_no', '=', rec.item_no),
                    ('id', '!=', rec.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f'項目編號 {rec.item_no} 在此通報單中已存在'
                    )

    def name_get(self):
        result = []
        for rec in self:
            name = f'{rec.item_no} - {rec.description}'
            result.append((rec.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|',
                      ('item_no', operator, name),
                      ('description', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
