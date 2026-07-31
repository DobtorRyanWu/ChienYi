# -*- coding: utf-8 -*-
"""照片收斂：施工日誌照片 M2M → supervision_photo.daily_log_id"""

from odoo.addons.construction_photo.tools import photo_merge as pm

REL = 'daily_log_sheet_photo_rel'


def migrate(cr, version):
    if not version:
        return

    before = pm.snapshot(cr)
    pm.migrate_m2m(
        cr, REL, 'sheet_id', 'daily_log_id',
        project_sql='(select s.supervision_project_id from daily_log_sheet s'
                    '  where s.id = r.sheet_id)')

    if pm.verify(cr, before, rel_tables=[REL]):
        pm.drop_tables(cr, [REL])
