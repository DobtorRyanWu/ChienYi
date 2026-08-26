# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class EstimateManualAmountWizard(models.TransientModel):
    """解除手動金額

    列出本估驗單中「本次估驗金額」被人工覆寫的工項，讓使用者逐項挑選：
    勾選者還原為系統計算值（單價 × 本次估驗數量），未勾選者保留手動金額。
    """
    _name = 'estimate.manual.amount.wizard'
    _description = '解除手動金額'

    # 同 estimate_line_id：不加 readonly=True，否則前端不回送、存檔時撞 not-null
    estimate_id = fields.Many2one(
        'payment.estimate',
        '估驗單',
        required=True,
        ondelete='cascade'
    )
    line_ids = fields.One2many(
        'estimate.manual.amount.wizard.line',
        'wizard_id',
        '手動金額工項'
    )
    selected_count = fields.Integer(
        '已勾選數',
        compute='_compute_selected_count'
    )

    @api.depends('line_ids.to_clear')
    def _compute_selected_count(self):
        for wiz in self:
            wiz.selected_count = len(wiz.line_ids.filtered('to_clear'))

    @api.model
    def default_get(self, fields_list):
        """由估驗單帶出所有手動金額工項（預設全部勾選）"""
        res = super().default_get(fields_list)
        estimate_id = res.get('estimate_id') or self.env.context.get('active_id')
        if not estimate_id:
            return res
        estimate = self.env['payment.estimate'].browse(estimate_id)
        res['estimate_id'] = estimate.id
        manual_lines = estimate.line_ids.filtered(
            lambda l: l.is_amount_manual and not l.is_summary_item
        ).sorted(key=lambda l: (l.sequence or 0, l.id))
        res['line_ids'] = [
            (0, 0, {
                'estimate_line_id': line.id,
                'sequence': line.sequence,
                'to_clear': True,
            })
            for line in manual_lines
        ]
        return res

    def action_select_all(self):
        """全選"""
        self.ensure_one()
        self.line_ids.to_clear = True
        return self._reopen()

    def action_unselect_all(self):
        """全不選"""
        self.ensure_one()
        self.line_ids.to_clear = False
        return self._reopen()

    def _reopen(self):
        """保持在同一張精靈（全選／全不選後重新顯示）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '解除手動金額',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_clear(self):
        """把勾選的工項還原為系統計算值（單價 × 本次估驗數量）"""
        self.ensure_one()
        if self.estimate_id.state not in ('draft', 'pending_approval'):
            raise UserError('已核定或已歸檔的估驗單不能修改金額。')
        target_lines = self.line_ids.filtered('to_clear').mapped('estimate_line_id')
        if not target_lines:
            raise UserError('請至少勾選一個要解除手動金額的工項。')

        # is_amount_manual 在 estimate_amount 的 depends 內，清掉旗標即觸發重算
        target_lines.write({
            'is_amount_manual': False,
            'manual_estimate_amount': 0.0,
        })

        kept = len(self.line_ids) - len(target_lines)
        self.estimate_id.message_post(
            body='解除手動金額：%s 個工項已還原為 單價 × 本次估驗數量%s。' % (
                len(target_lines),
                ('，另保留 %s 個工項的手動金額' % kept) if kept else '',
            )
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '已解除手動金額',
                'message': '%s 個工項已還原為系統計算值。' % len(target_lines),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class EstimateManualAmountWizardLine(models.TransientModel):
    """解除手動金額 — 候選工項"""
    _name = 'estimate.manual.amount.wizard.line'
    _description = '解除手動金額明細'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'estimate.manual.amount.wizard',
        '精靈',
        required=True,
        ondelete='cascade'
    )
    # ⚠ 不可加 readonly=True：Odoo 17+ 前端不回送 readonly 欄位，
    #   精靈存檔時 estimate_line_id 會變 NULL 而撞 not-null（實測 NotNullViolation）。
    #   本欄在 view 內是 column_invisible，使用者本來就改不到。
    estimate_line_id = fields.Many2one(
        'payment.estimate.line',
        '估驗明細',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer('序號')
    to_clear = fields.Boolean(
        '解除手動',
        default=True,
        help='勾選＝還原為 單價 × 本次估驗數量；不勾＝保留目前的手動金額'
    )

    # === 顯示用（唯讀）===
    item_no = fields.Char('項目編號', related='estimate_line_id.item_no', readonly=True)
    description = fields.Char('項目及說明', related='estimate_line_id.description', readonly=True)
    unit = fields.Char('單位', related='estimate_line_id.unit', readonly=True)
    unit_price = fields.Float('單價', related='estimate_line_id.unit_price', readonly=True)
    estimate_qty = fields.Float(
        '本次估驗數量',
        related='estimate_line_id.estimate_qty',
        readonly=True
    )
    # 金額一律即時由估驗明細算出（非儲存）：既不必在 default_get 塞值，
    # 也避開「view readonly 欄位不回送」而在存檔後歸零的坑。
    manual_amount = fields.Float(
        '目前手動金額',
        digits=(16, 2),
        compute='_compute_display_amounts'
    )
    auto_amount = fields.Float(
        '系統計算金額',
        digits=(16, 2),
        compute='_compute_display_amounts',
        help='單價 × 本次估驗數量'
    )
    diff_amount = fields.Float(
        '差額',
        digits=(16, 2),
        compute='_compute_display_amounts',
        help='目前手動金額 − 系統計算金額（解除後金額的變動量）'
    )

    @api.depends('estimate_line_id', 'estimate_line_id.estimate_amount',
                 'estimate_line_id.unit_price', 'estimate_line_id.estimate_qty')
    def _compute_display_amounts(self):
        for line in self:
            est_line = line.estimate_line_id
            line.manual_amount = est_line.estimate_amount
            line.auto_amount = est_line.unit_price * est_line.estimate_qty
            line.diff_amount = line.manual_amount - line.auto_amount
