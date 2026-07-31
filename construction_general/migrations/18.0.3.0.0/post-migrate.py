# -*- coding: utf-8 -*-
"""照片收斂：一般式缺失照片行 → supervision_photo.general_defect_id"""

from odoo.addons.construction_photo.tools import photo_merge as pm

LINE_TABLE = 'general_defect_improvement_photo'
LINE_MODEL = 'general.defect.improvement.photo'
DEFECT_TABLE = 'general_defect_improvement'
LEGACY = ['general_defect_photo_rel', 'general_improvement_photo_rel']


def migrate(cr, version):
    if not version:
        return

    before = pm.snapshot(cr)
    pm.migrate_defect_lines(
        cr, LINE_TABLE, DEFECT_TABLE, 'general_defect_id', LINE_MODEL)

    if pm.verify(cr, before, line_tables=[LINE_TABLE]):
        # legacy 兩張表實測 0 筆、欄位註解本來就寫「不要直接使用」，一併清掉
        pm.drop_tables(cr, [LINE_TABLE] + LEGACY, models=[LINE_MODEL])
