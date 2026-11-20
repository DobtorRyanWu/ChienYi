# -*- coding: utf-8 -*-
"""2026-11-20：核定時有超量明細的確認視窗。

只由畫面上的「核定」按鈕（payment.estimate.action_approve_with_check）叫出；
系統內部的 action_approve 不經這裡（匯入步驟 14 直接呼叫它，若改成回傳視窗，
匯入會以為核定了、其實沒有，而且不報失敗）。
暫存精靈一張（transient，不是永久表）。
"""
from odoo import fields, models


class PaymentEstimateApproveConfirm(models.TransientModel):
    _name = 'payment.estimate.approve.confirm'
    _description = '估驗核定超量確認'

    estimate_ids = fields.Many2many('payment.estimate', string='估驗單', readonly=True)
    message = fields.Text(string='提醒', readonly=True)

    def action_confirm(self):
        self.ensure_one()
        self.estimate_ids.action_approve()
        return {'type': 'ir.actions.act_window_close'}
