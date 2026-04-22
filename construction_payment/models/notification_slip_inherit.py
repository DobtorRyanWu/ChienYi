# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ReservationNotificationSlipPayment(models.Model):
    """擴展通報單，加入估驗計價次數計算"""
    _inherit = 'reservation.notification.slip'

    valuation_count = fields.Integer(
        string='已估驗次數',
        compute='_compute_valuation_count')

    def _compute_valuation_count(self):
        """計算關聯的估驗次數（排除草稿）"""
        Estimate = self.env['payment.estimate']
        for rec in self:
            if rec.id:
                rec.valuation_count = Estimate.search_count([
                    ('slip_id', '=', rec.id),
                    ('state', '!=', 'draft'),
                ])
            else:
                rec.valuation_count = 0
