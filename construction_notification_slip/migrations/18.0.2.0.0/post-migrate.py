# -*- coding: utf-8 -*-
"""照片收斂：通報單照片的來源關聯改成真 Many2one

情況與檢試驗相同：照片本來就直接建在 supervision_photo，只是靠
source_model='notification' + source_id 掛著且唯讀，後台因此沒有上傳入口。
"""

from odoo.addons.construction_photo.tools import photo_merge as pm


def migrate(cr, version):
    if not version:
        return
    pm.backfill_from_source_ref(
        cr, 'notification', 'slip_id', 'reservation_notification_slip')
