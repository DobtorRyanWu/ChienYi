# -*- coding: utf-8 -*-
"""照片資料表收斂：把「施工日誌」這個來源掛到 supervision.photo 上。

由本模組（而非 construction_photo）宣告這個欄位，是為了維持模組分層——
上游不必知道下游有哪些模型。construction_photo 只提供掛載規則，
每個有照片的模組各自加自己的一欄。
"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res['daily.log.sheet'] = 'daily_log_id'
        return res

    daily_log_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌',
        ondelete='cascade',
        index=True,
        help='這張照片所屬的施工日誌')

    def _photo_source_project(self):
        """施工日誌照片歸屬到該日誌的工程案件。"""
        res = super()._photo_source_project()
        if res:
            return res
        return self.daily_log_id.supervision_project_id

    def _photo_source_model_code(self):
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'daily_log' if self.daily_log_id else False
