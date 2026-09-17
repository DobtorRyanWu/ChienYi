# -*- coding: utf-8 -*-
"""自主檢查表「檢查時機」欄位設定：單選 inspection_timing → 複選 inspection_timing_ids。

construction_quality 18.0.5.0.0 起，自主檢查的檢查時機由單選 Selection
（inspection_timing）改為複選 Many2many（inspection_timing_ids），舊欄位已移除。
data/doc_template_data.xml 的 field_self_inspection_timing 已跟著改，但它在
<data noupdate="1"> 裡，既有 DB 升級不會吃到 XML —— 仍指著已刪除的欄位，
doc_controller 以 _fields.get() 取不到欄位定義，前端「檢查時機」下拉靜靜變空、不報錯。

本 migration 對已安裝、升級到本版的 DB 就地轉換。新裝 DB 由 XML 直接帶新值，
不需本 script。idempotent：已轉過、或被人改成別的欄位 → 不動。
"""
from odoo import api, SUPERUSER_ID

_OLD_FIELD = "inspection_timing"
_NEW_FIELD = "inspection_timing_ids"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    field = env.ref(
        "dobtor_doc_editor.field_self_inspection_timing", raise_if_not_found=False
    )
    if not field or field.selection_field_name != _OLD_FIELD:
        return  # 找不到、已轉換過，或被人改成別的來源欄位 → 不動
    field.write({"selection_field_name": _NEW_FIELD, "is_multi_select": True})
