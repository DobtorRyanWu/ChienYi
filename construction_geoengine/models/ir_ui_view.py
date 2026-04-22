# -*- coding: utf-8 -*-
from odoo import fields, models


class IrUIView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(
        selection_add=[('photo_map', '照片地圖')],
        ondelete={'photo_map': 'cascade'},
    )

    def _get_view_info(self):
        """將 photo_map 加入 session.view_info，讓前端 action 驗證通過"""
        res = super()._get_view_info()
        res['photo_map'] = {'icon': 'fa fa-map-marker'}
        return res
