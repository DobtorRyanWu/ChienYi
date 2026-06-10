# -*- coding: utf-8 -*-

from odoo import fields, models


class ContractChangeOrderPaymentInherit(models.Model):
    """擴展契約變更單，加入開啟估驗計價工項同步精靈的入口"""
    _inherit = 'contract.change.order'

    def action_open_sync_wizard(self):
        """開啟同步估驗計價工項精靈"""
        self.ensure_one()
        # 以套用日期作為同步基準日期的預設值
        sync_date = (
            self.applied_date.date() if self.applied_date
            else fields.Date.context_today(self)
        )
        return {
            'type': 'ir.actions.act_window',
            'name': '同步估驗計價工項',
            'res_model': 'estimate.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_change_order_id': self.id,
                'default_sync_from_date': sync_date,
            },
        }
