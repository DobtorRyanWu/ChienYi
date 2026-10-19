# -*- coding: utf-8 -*-

from odoo import fields, models


class ContractChangeOrderPaymentInherit(models.Model):
    """擴展契約變更單，加入開啟估驗計價工項同步精靈的入口"""
    _inherit = 'contract.change.order'

    def action_open_sync_wizard(self):
        """開啟同步估驗計價工項精靈"""
        self.ensure_one()
        # 同步基準日的預設值＝變更單的「變更日期」（18.0.1.8.3，使用者 2026-10-19 裁示）。
        # 它就是工項版本的「生效日期」，施工日誌的「當時契約數量」也以它為界；
        # 以前預設套用日（按「套用」按鈕的那天）—— 補建歷史資料時套用日遠晚於
        # 變更日期（DEMO：變更 2022-01-14、套用 2026-07-31），變更後的舊期別預設全部同步不到。
        # 沒填變更日期才退回套用日、再退回今天。
        sync_date = (
            self.change_date
            or (self.applied_date.date() if self.applied_date else False)
            or fields.Date.context_today(self)
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
