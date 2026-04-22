# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SupervisionProjectPayment(models.Model):
    """擴展 supervision.project，加入估驗週期設定"""
    _inherit = 'supervision.project'

    # === 估驗週期設定 ===
    valuation_cycle = fields.Selection([
        ('monthly', '每月'),
        ('biweekly', '每兩週'),
        ('custom', '自訂天數'),
    ], string='估驗週期',
       help='設定後可在啟用進度表時自動產生估驗計價單')

    valuation_cycle_days = fields.Integer(
        string='自訂週期天數',
        default=30,
        help='選擇「自訂天數」時有效',
    )

    # === 估驗計價關聯 ===
    estimate_ids = fields.One2many(
        'payment.estimate', 'project_id',
        string='估驗計價單',
    )
    estimate_count = fields.Integer(
        string='估驗數',
        compute='_compute_estimate_count',
    )

    @api.depends('estimate_ids')
    def _compute_estimate_count(self):
        for project in self:
            project.estimate_count = len(project.estimate_ids)

    def action_view_estimates(self):
        """查看估驗計價單"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '估驗計價單',
            'res_model': 'payment.estimate',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
