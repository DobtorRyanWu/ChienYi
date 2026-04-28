# -*- coding: utf-8 -*-

from odoo import models


class DailyLogSheetPortal(models.Model):
    """施工日誌 Portal 擴展 — 加入 portal.mixin 支援 chatter 訊息"""
    _name = 'daily.log.sheet'
    _inherit = ['daily.log.sheet', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for record in self:
            record.access_url = f'/construction/{record.supervision_project_id.id}/daily-log/{record.id}'
