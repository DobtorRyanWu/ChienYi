# -*- coding: utf-8 -*-
"""預約式通報單 → 施工回報單樣板匯出。"""

from odoo import models

TEMPLATE_TYPE = 'notification_slip'


class ReservationNotificationSlip(models.Model):
    _name = 'reservation.notification.slip'
    _inherit = ['reservation.notification.slip', 'document.template.export.mixin']

    def action_export_slip_template(self):
        """把本張通報單的資料填進「預約式工程施工回報單」樣板並下載。"""
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', TEMPLATE_TYPE))
