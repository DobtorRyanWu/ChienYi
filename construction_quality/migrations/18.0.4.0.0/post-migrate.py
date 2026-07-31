# -*- coding: utf-8 -*-
"""照片收斂：預約式缺失照片行 + 兩個自主檢查的 M2M → supervision_photo"""

from odoo.addons.construction_photo.tools import photo_merge as pm

LINE_TABLE = 'reservation_defect_improvement_photo'
LINE_MODEL = 'reservation.defect.improvement.photo'
DEFECT_TABLE = 'reservation_defect_improvement'
LEGACY = ['reservation_defect_photo_rel', 'reservation_improvement_photo_rel']

GEN_INSP_REL = 'general_inspection_photo_rel'
RES_INSP_REL = 'reservation_inspection_photo_rel'


def migrate(cr, version):
    if not version:
        return

    before = pm.snapshot(cr)

    pm.migrate_defect_lines(
        cr, LINE_TABLE, DEFECT_TABLE, 'reservation_defect_id', LINE_MODEL)

    # 一般式自主檢查有 project_id，直接取；預約式掛在通報單下，要往上一層取
    pm.migrate_m2m(
        cr, GEN_INSP_REL, 'inspection_id', 'general_inspection_id',
        project_sql='(select i.project_id from general_self_inspection i'
                    '  where i.id = r.inspection_id)')
    pm.migrate_m2m(
        cr, RES_INSP_REL, 'inspection_id', 'reservation_inspection_id',
        project_sql='(select s.project_id'
                    '   from reservation_self_inspection i'
                    '   join reservation_notification_slip s on s.id = i.slip_id'
                    '  where i.id = r.inspection_id)')

    if pm.verify(cr, before,
                 line_tables=[LINE_TABLE],
                 rel_tables=[GEN_INSP_REL, RES_INSP_REL]):
        pm.drop_tables(cr,
                       [LINE_TABLE, GEN_INSP_REL, RES_INSP_REL] + LEGACY,
                       models=[LINE_MODEL])
