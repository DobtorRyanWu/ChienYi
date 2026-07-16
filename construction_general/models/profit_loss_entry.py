# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProfitLossEntry(models.Model):
    """即時損益 - 支出記錄"""
    _name = 'profit.loss.entry'
    _description = '即時損益 - 支出記錄'
    _order = 'estimate_id'

    project_id = fields.Many2one(
        'project.project',
        string='工程',
        required=True,
        ondelete='cascade',
        index=True,
    )

    estimate_id = fields.Many2one(
        'payment.estimate',
        string='估驗計價',
        required=True,
        ondelete='cascade',
        index=True,
    )

    expense_amount = fields.Float(
        string='支出金額',
        digits=(16, 2),
        default=0.0,
        help='使用者自行輸入的支出金額',
    )

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        index=True,
    )

    _sql_constraints = [
        ('unique_project_estimate',
         'UNIQUE(project_id, estimate_id)',
         '同一工程的同一次估驗只能有一筆支出記錄！'),
    ]
