# -*- coding: utf-8 -*-

from odoo import models


class NotificationSlipPortal(models.Model):
    """通報單 Portal 擴展 — 加入 portal.mixin 支援 chatter 訊息"""
    _name = 'reservation.notification.slip'
    _inherit = ['reservation.notification.slip', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for record in self:
            record.access_url = f'/my/construction/{record.project_id.id}/slip/{record.id}'
