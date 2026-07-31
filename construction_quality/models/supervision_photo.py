# -*- coding: utf-8 -*-
"""照片資料表收斂：把 construction_quality 的三個來源掛到 supervision.photo 上。

由本模組（而非 construction_photo）宣告這些欄位，維持模組分層——
上游不必知道下游有哪些模型。
"""

from odoo import models, fields, api


class SupervisionPhoto(models.Model):
    _inherit = 'supervision.photo'

    @api.model
    def _photo_source_field_map(self):
        res = super()._photo_source_field_map()
        res.update({
            'general.self.inspection': 'general_inspection_id',
            'reservation.self.inspection': 'reservation_inspection_id',
            'reservation.defect.improvement': 'reservation_defect_id',
        })
        return res

    general_inspection_id = fields.Many2one(
        'general.self.inspection',
        string='一般式自主檢查',
        ondelete='cascade',
        index=True)

    reservation_inspection_id = fields.Many2one(
        'reservation.self.inspection',
        string='預約式自主檢查',
        ondelete='cascade',
        index=True)

    reservation_defect_id = fields.Many2one(
        'reservation.defect.improvement',
        string='預約式缺失改善',
        ondelete='cascade',
        index=True)

    def _photo_source_project(self):
        res = super()._photo_source_project()
        if res:
            return res
        if self.general_inspection_id:
            return self.general_inspection_id.project_id
        if self.reservation_inspection_id:
            # 預約式檢查掛在通報單下，工程案件要往上取
            insp = self.reservation_inspection_id
            return getattr(insp, 'project_id', False) or insp.slip_id.project_id
        if self.reservation_defect_id:
            return self.reservation_defect_id.project_id
        return self.env['project.project']

    def _photo_source_model_code(self):
        res = super()._photo_source_model_code()
        if res:
            return res
        if self.general_inspection_id or self.reservation_inspection_id:
            return 'inspection'
        if self.reservation_defect_id:
            return 'defect'
        return False

    def _geo_fallback_source(self):
        """預約式的照片：沒有 GPS 時借所屬通報單的施工地點座標。

        預約式自主檢查與預約式缺失都掛在某張通報單底下，通報單代表工區內
        一個特定地點，比工程案件的中心點精確 —— 所以放在這一層，而不是讓
        它掉到 _fallback_coordinates() 最後的工程案件兜底。

        一般式自主檢查沒有通報單可借，不在這裡處理，自然退到工程案件。
        """
        res = super()._geo_fallback_source()
        if res:
            return res
        if self.reservation_inspection_id:
            return self.reservation_inspection_id.slip_id
        if self.reservation_defect_id:
            return self.reservation_defect_id.slip_id
        return self.env['reservation.notification.slip']
