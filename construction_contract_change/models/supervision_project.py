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
    _inherit = 'project.project'

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
    # original_contract_amount 已移至 construction_supervision_base（消費者所在地），
    # 避免 base 的 _compute_contract_amount 在僅載入 base 時前向參照失敗。此處僅延伸使用。

    # === 累計變更資訊 (計算欄位) ===
    total_change_amount = fields.Monetary(
        string='累計變更金額',
        currency_field='currency_id',
        compute='_compute_current_contract',
        store=True,
        help='所有已核定變更的金額總和')

    change_rate = fields.Float(
        string='累計變更比率 (%)',
        compute='_compute_current_contract',
        store=True,
        digits=(16, 4),
        help='累計變更金額佔原始契約金額的百分比（小數，如 0.2567 = 25.67%）')

    # === 現行契約資訊 (計算欄位) ===
    current_contract_amount = fields.Monetary(
        string='現行契約金額',
        currency_field='currency_id',
        compute='_compute_current_contract',
        store=True,
        help='原始契約金額 + 累計變更金額')

    # === 採購法 50% 管制豁免（唯讀彙總；資料落點在變更單）===
    change_limit_exempt = fields.Boolean(
        string='已啟用 50% 管制豁免',
        compute='_compute_change_limit_exempt',
        help='本工程已有一張已核定的契約變更單啟用豁免，'
             '之後的變更一律沿用，不再受採購法 50% 累計變更管制。')

    change_limit_exempt_order_id = fields.Many2one(
        'contract.change.order',
        string='豁免來源變更單',
        compute='_compute_change_limit_exempt')

    change_limit_exempt_note = fields.Char(
        string='豁免緣由',
        compute='_compute_change_limit_exempt')

    @api.depends('change_order_ids.is_limit_exempt',
                 'change_order_ids.exempt_reason',
                 'change_order_ids.state',
                 'change_order_ids.change_no')
    def _compute_change_limit_exempt(self):
        """豁免以「最早一張已核定/已套用且勾了豁免的變更單」為準。

        只認已核定的：一張還沒人審過的草稿不應該就把全工程的管制拆掉，
        這與 50% 累計金額的計入範圍一致。
        """
        for project in self:
            source = project.change_order_ids.filtered(
                lambda o: o.is_limit_exempt and o.state in ('approved', 'applied')
            ).sorted(key=lambda o: (o.change_no or 9999, o.id))[:1]
            project.change_limit_exempt_order_id = source
            project.change_limit_exempt = bool(source)
            if source:
                reason = (source.exempt_reason or '').strip().replace('\n', ' ')
                project.change_limit_exempt_note = (
                    '第 %s 次變更啟用：%s' % (source.change_no or '?', reason))[:200]
            else:
                project.change_limit_exempt_note = False

    # === 計算方法 ===
    @api.depends('change_order_ids', 'change_order_ids.state')
    def _compute_change_order_count(self):
        for project in self:
            project.change_order_count = len(project.change_order_ids)
            project.approved_change_count = len(
                project.change_order_ids.filtered(
                    lambda o: o.state in ('approved', 'applied')))

    @api.depends('contract_amount', 'original_contract_amount',
                 'change_order_ids.state', 'change_order_ids.change_amount')
    def _compute_current_contract(self):
        """現行契約金額 = 任務級 rollup（contract_amount = Σ 頂層工項 planned_amount）。

        以 task rollup 為單一真實來源，不再用「original + Σ 已核定變更額」的鏈式累積
        （該鏈會逐次累積誤差）。累計變更金額改以「現行 - 原始」呈現。
        """
        for project in self:
            # 現行契約金額 = 任務級 rollup（套用變更後 task 已反映，含稅什費比率重算）
            project.current_contract_amount = project.contract_amount

            # 累計變更金額 = 現行 - 原始
            base_amount = project.original_contract_amount or 0.0
            project.total_change_amount = (
                project.current_contract_amount - base_amount
                if base_amount else 0.0)

            # 累計變更比率（[0,1] 小數，widget="percentage" 會乘 100 顯示）
            if project.original_contract_amount:
                project.change_rate = (
                    project.total_change_amount /
                    project.original_contract_amount)
            else:
                project.change_rate = 0.0

    # === Onchange ===
    @api.onchange('contract_amount')
    def _onchange_contract_amount(self):
        """契約金額變更時，如果沒有原始金額則同步設定"""
        if self.contract_amount and not self.original_contract_amount:
            self.original_contract_amount = self.contract_amount

    # === 動作方法 ===
    def action_view_change_orders(self):
        """查看契約變更單"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '契約變更單',
            'res_model': 'contract.change.order',
            'view_mode': 'list,form',
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
                # original_contract_amount 已改為由變更單明細（頂層彙總項）計算，
                # 不再以 context 預設快照。
            },
        }

    def action_set_original_values(self):
        """設定原始契約值 (首次使用時)"""
        for project in self:
            if not project.original_contract_amount and project.contract_amount:
                project.original_contract_amount = project.contract_amount
