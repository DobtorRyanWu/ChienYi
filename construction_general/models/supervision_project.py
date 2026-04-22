# -*- coding: utf-8 -*-

import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class SupervisionProjectProfitLoss(models.Model):
    """擴展工程案件 - 即時損益 Dashboard API"""
    _inherit = 'supervision.project'

    @api.model
    def get_profit_loss_data(self, project_id):
        """
        取得指定工程的即時損益資料

        回傳格式：
        {
            'project_name': '...',
            'currency_symbol': 'NT$',
            'estimates': [
                {
                    'estimate_id': 1,
                    'estimate_no': 1,
                    'estimate_date': '2025-01-15',
                    'income': 500000.0,
                    'expense': 300000.0,
                    'entry_id': 5 or False,
                },
                ...
            ],
        }
        """
        project = self.browse(project_id)
        if not project.exists():
            return {'project_name': '', 'currency_symbol': '', 'estimates': []}

        # 取得所有非草稿的估驗計價，依估驗日期排序
        estimates = self.env['payment.estimate'].search([
            ('project_id', '=', project_id),
            ('state', '!=', 'draft'),
        ], order='estimate_date asc, estimate_no asc')

        # 取得所有對應的支出記錄
        entries = self.env['profit.loss.entry'].search([
            ('project_id', '=', project_id),
        ])
        entry_map = {e.estimate_id.id: e for e in entries}

        result_estimates = []
        for est in estimates:
            entry = entry_map.get(est.id)
            result_estimates.append({
                'estimate_id': est.id,
                'estimate_no': est.estimate_no,
                'estimate_date': str(est.estimate_date) if est.estimate_date else '',
                'income': est.subtotal or 0.0,
                'expense': entry.expense_amount if entry else 0.0,
                'entry_id': entry.id if entry else False,
            })

        currency = project.company_id.currency_id
        return {
            'project_name': project.name or '',
            'currency_symbol': currency.symbol if currency else 'NT$',
            'estimates': result_estimates,
        }

    @api.model
    def save_profit_loss_expense(self, project_id, estimate_id, expense_amount):
        """
        儲存或更新支出金額

        回傳更新後的完整資料
        """
        Entry = self.env['profit.loss.entry']
        entry = Entry.search([
            ('project_id', '=', project_id),
            ('estimate_id', '=', estimate_id),
        ], limit=1)

        if entry:
            entry.write({'expense_amount': expense_amount})
        else:
            Entry.create({
                'project_id': project_id,
                'estimate_id': estimate_id,
                'expense_amount': expense_amount,
            })

        # 回傳更新後的完整資料
        return self.get_profit_loss_data(project_id)
