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
        # 2026-08-20 改為 'estimate'（使用者要求估驗計價要能單獨篩選）。
        #
        # 原本回 'other'，理由是「地圖的 SOURCE_COLORS / SOURCE_LABELS 寫死在
        # JS，多一個值會變成沒有名字的灰點」。這次連同那兩張對照表一起補上了
        # estimate 與 signboard，該理由不再成立 —— 值定義在
        # construction_photo/models/supervision_photo.py 的 source_model，
        # 對照表在 construction_geoengine 兩支 photo_map_*.js。
        # 三處要一起維護，加新來源時別漏。
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'estimate' if self.estimate_id else False
