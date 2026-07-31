# -*- coding: utf-8 -*-
"""照片資料表收斂：把「一般式缺失改善」這個來源掛到 supervision.photo 上。"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res['general.defect.improvement'] = 'general_defect_id'
        return res

    general_defect_id = fields.Many2one(
        'general.defect.improvement',
        string='一般式缺失改善',
        ondelete='cascade',
        index=True)

    def _photo_source_project(self):
        res = super()._photo_source_project()
        if res:
            return res
        return self.general_defect_id.project_id

    def _photo_source_model_code(self):
        res = super()._photo_source_model_code()
        if res:
            return res
        return 'defect' if self.general_defect_id else False
