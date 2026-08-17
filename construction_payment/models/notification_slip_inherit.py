# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ReservationNotificationSlipPayment(models.Model):
    """擴展通報單，加入估驗計價次數計算"""
    _inherit = 'reservation.notification.slip'

    valuation_count = fields.Integer(
        string='本工程已估驗次數',
        compute='_compute_valuation_count',
        help='本張通報單所屬工程已辦理的估驗計價期數（排除草稿）。\n'
             '估驗計價以「工程 × 期別」為單位辦理，不歸屬於個別通報單，'
             '故此數字是工程層級而非本單層級；本單的金額請看「結算金額」。')

    @api.depends('project_id')
    def _compute_valuation_count(self):
        """計算所屬工程的估驗次數（排除草稿）

        2026-08-18 改定義：原本是 [('slip_id','=',rec.id)] 的本單估驗次數，
        但估驗與通報單無關聯（payment.estimate.slip_id 已移除），該算法恆為 0。
        改以工程為範圍，回答「這個工程辦到第幾期估驗了」。
        """
        # 一次查完全部工程的計數，避免逐筆 search_count
        projects = self.mapped('project_id')
        counts = {}
        if projects:
            counts = {
                project.id: count
                for project, count in self.env['payment.estimate']._read_group(
                    [('project_id', 'in', projects.ids), ('state', '!=', 'draft')],
                    groupby=['project_id'],
                    aggregates=['__count'],
                )
            }
        for rec in self:
            rec.valuation_count = counts.get(rec.project_id.id, 0)
