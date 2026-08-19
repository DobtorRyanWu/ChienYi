# -*- coding: utf-8 -*-
"""照片資料表收斂：把「估驗計價」這個來源掛到 supervision.photo 上。

實際工程資料裡有明確屬於某一期估驗的照片（例如
`07_估驗計價\第4次\04.1.jpg`），路徑已經指明歸屬，但收斂後的
supervision.photo 沒有對應的來源外鍵，只能退回「工程照片」——
語意上是把「第幾次估驗」這個資訊丟掉。加一個 Many2one 補上。
"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res['payment.estimate'] = 'estimate_id'
        return res

    estimate_id = fields.Many2one(
        'payment.estimate',
        string='估驗計價',
        ondelete='cascade',
        index=True)

    def _photo_source_project(self):
        res = super()._photo_source_project()
        if res:
            return res
        return self.estimate_id.project_id

    def _photo_source_model_code(self):
        # source_model 是「舊系統的字串假關聯」，只留給既有查詢與前台篩選用；
        # 新的來源判斷一律看 estimate_id。這裡回 'other' 而不是新增
        # selection_add('estimate')，理由有三：
        #   1. 與同樣沒有舊系統對應值的 signboard_project_id 一致（也回 'other'）
        #   2. construction_geoengine 的照片地圖把 source_model 的顏色／標籤
        #      寫死在 JS 的 SOURCE_COLORS / SOURCE_LABELS（未知值→灰色、空標籤），
        #      多一個值會在地圖上變成沒有名字的灰點
        #   3. 舊系統本來就沒有「估驗照片」這個分類，硬塞進相容欄位沒有意義
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'other' if self.estimate_id else False
