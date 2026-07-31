# -*- coding: utf-8 -*-
"""照片收斂：工程告示牌 M2M → supervision_photo.signboard_project_id

只處理本模組自己的表與欄位。缺失照片行、自主檢查、施工日誌等由各自的模組
遷移（見各模組 migrations/），這樣載入順序天然正確 —— construction_photo 是
其他模組的依賴，在這裡碰它們的欄位一定拿不到。
"""

from odoo.addons.construction_photo.tools import photo_merge as pm

REL = 'supervision_project_signboard_photo_rel'


def migrate(cr, version):
    if not version:
        return          # 全新安裝直接就是收斂後結構

    before = pm.snapshot(cr)
    # 告示牌的來源記錄本身就是工程案件，project_id 直接取 r.project_id
    pm.migrate_m2m(cr, REL, 'project_id', 'signboard_project_id')

    if pm.verify(cr, before, rel_tables=[REL]):
        pm.drop_tables(cr, [REL])
