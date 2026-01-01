# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionProject(models.Model):
    """
    工程案件 - 契約變更關聯擴展 (v5.2)

    擴展 supervision.project 支援：
    - 契約變更單關聯
    - 原始契約金額與工期記錄
    - 累計變更計算
    - 現行契約狀態追蹤
    """
    _inherit = 'supervision.project'

    # === 契約變更關聯 ===
    change_order_ids = fields.One2many(
        'contract.change.order',
        'project_id',
        string='契約變更單')

    change_order_count = fields.Integer(
        string='變更次數',
        compute='_compute_change_order_count')

    approved_change_count = fields.Integer(
        string='已核定變更次數',
        compute='_compute_change_order_count')

    # === 原始契約資訊 ===
    original_contract_amount = fields.Monetary(
        string='原始契約金額',
        currency_field='currency_id',
        tracking=True,
        help='初始契約金額 (不含變更)')

    original_duration = fields.Integer(
        string='原始工期(日)',
        tracking=True,
        help='初始契約工期')

    # === 累計變更資訊 (計算欄位) ===
    total_change_amount = fields.Monetary(
        string='累計變更金額',
        currency_field='currency_id',
        compute='_compute_current_contract',
        store=True,
        help='所有已核定變更的金額總和')

    total_duration_change = fields.Integer(
        string='累計工期變更(日)',
        compute='_compute_current_contract',
        store=True,
        help='所有已核定變更的工期總和')

    change_rate = fields.Float(
        string='累計變更比率 (%)',
        compute='_compute_current_contract',
        store=True,
        digits=(5, 2),
        help='累計變更金額佔原始契約金額的百分比')

    # === 現行契約資訊 (計算欄位) ===
    current_contract_amount = fields.Monetary(
        string='現行契約金額',
        currency_field='currency_id',
        compute='_compute_current_contract',
        store=True,
        help='原始契約金額 + 累計變更金額')

    current_duration = fields.Integer(
        string='現行工期(日)',
        compute='_compute_current_contract',
        store=True,
        help='原始工期 + 累計工期變更')

    # === 計算方法 ===
    @api.depends('change_order_ids', 'change_order_ids.state')
    def _compute_change_order_count(self):
        for project in self:
            project.change_order_count = len(project.change_order_ids)
            project.approved_change_count = len(
                project.change_order_ids.filtered(
                    lambda o: o.state in ('approved', 'applied')))

    @api.depends('change_order_ids.state', 'change_order_ids.change_amount',
                 'change_order_ids.change_duration', 'original_contract_amount',
                 'original_duration')
    def _compute_current_contract(self):
        """計算現行契約金額與工期"""
        for project in self:
            # 取得已核定/已套用的變更單
            approved_orders = project.change_order_ids.filtered(
                lambda o: o.state in ('approved', 'applied'))

            # 累計變更金額與工期
            project.total_change_amount = sum(
                approved_orders.mapped('change_amount'))
            project.total_duration_change = sum(
                approved_orders.mapped('change_duration'))

            # 計算現行契約金額與工期
            # 如果有設定原始金額則用原始金額，否則用契約金額作為基準
            base_amount = project.original_contract_amount or project.contract_amount or 0.0
            base_duration = project.original_duration or project.contract_duration or 0

            project.current_contract_amount = (
                base_amount + project.total_change_amount)
            project.current_duration = (
                base_duration + project.total_duration_change)

            # 計算累計變更比率
            if project.original_contract_amount:
                project.change_rate = (
                    project.total_change_amount /
                    project.original_contract_amount) * 100
            else:
                project.change_rate = 0.0

    # === Onchange ===
    @api.onchange('contract_amount')
    def _onchange_contract_amount(self):
        """契約金額變更時，如果沒有原始金額則同步設定"""
        if self.contract_amount and not self.original_contract_amount:
            self.original_contract_amount = self.contract_amount

    @api.onchange('contract_duration')
    def _onchange_contract_duration(self):
        """契約工期變更時，如果沒有原始工期則同步設定"""
        if self.contract_duration and not self.original_duration:
            self.original_duration = self.contract_duration

    # === 動作方法 ===
    def action_view_change_orders(self):
        """查看契約變更單"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '契約變更單',
            'res_model': 'contract.change.order',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }

    def action_create_change_order(self):
        """新增契約變更單"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '新增契約變更單',
            'res_model': 'contract.change.order',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_project_id': self.id,
                'default_original_contract_amount': (
                    self.current_contract_amount or self.contract_amount),
                'default_original_duration': (
                    self.current_duration or self.contract_duration),
            },
        }

    def action_set_original_values(self):
        """設定原始契約值 (首次使用時)"""
        for project in self:
            if not project.original_contract_amount and project.contract_amount:
                project.original_contract_amount = project.contract_amount
            if not project.original_duration and project.contract_duration:
                project.original_duration = project.contract_duration
