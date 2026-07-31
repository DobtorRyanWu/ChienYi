# -*- coding: utf-8 -*-
"""照片資料表收斂：把「通報單」這個來源掛到 supervision.photo 上。"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res['reservation.notification.slip'] = 'slip_id'
        return res

    slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='通報單',
        ondelete='cascade',
        index=True)

    def _photo_source_project(self):
        res = super()._photo_source_project()
        if res:
            return res
        return self.slip_id.project_id

    def _photo_source_model_code(self):
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'notification' if self.slip_id else False

    def _geo_fallback_source(self):
        """通報單照片：照片沒有 GPS 時沿用該通報單的施工地點座標。

        與工程告示牌並列，是使用者指定「可以繼承座標」的兩個來源之一。
        通報單代表工區內一個特定地點，比工程案件的中心點精確。
        """
        res = super()._geo_fallback_source()
        if res:
            return res
        return self.slip_id
