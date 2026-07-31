# -*- coding: utf-8 -*-
"""照片資料表收斂：把「檢試驗記錄」這個來源掛到 supervision.photo 上。

收斂前檢試驗只有 computed 的 related_photo_ids（靠 source_model/source_id
字串反查），是唯讀的 —— 這正是後台檢試驗表單「有關聯照片頁籤卻沒有任何
上傳入口」的原因。改成真 Many2one 之後，後台就能直接掛上傳。
"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res['supervision.test.record'] = 'test_record_id'
        return res

    test_record_id = fields.Many2one(
        'supervision.test.record',
        string='檢試驗記錄',
        ondelete='cascade',
        index=True)

    def _photo_source_project(self):
        res = super()._photo_source_project()
        if res:
            return res
        return self.test_record_id.project_id

    def _photo_source_model_code(self):
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'test' if self.test_record_id else False
