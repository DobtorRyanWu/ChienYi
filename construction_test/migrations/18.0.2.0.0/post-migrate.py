# -*- coding: utf-8 -*-
"""照片收斂：檢試驗照片的來源關聯改成真 Many2one

檢試驗照片本來就直接建在 supervision_photo（沒有中間表），只是靠
source_model='test' + source_id 這組字串+整數的假關聯掛著，所以是唯讀的
——這正是後台檢試驗表單「有關聯照片頁籤卻沒有上傳入口」的原因。
這裡只需把假關聯回填成真欄位，沒有表要刪。
"""

from odoo.addons.construction_photo.tools import photo_merge as pm


def migrate(cr, version):
    if not version:
        return
    pm.backfill_from_source_ref(
        cr, 'test', 'test_record_id', 'supervision_test_record')
