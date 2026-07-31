# -*- coding: utf-8 -*-
"""post-migration：既有照片的座標回填。

背景：18.0.3.2.0 把座標兜底全面化 —— 原本只有工程告示牌與通報單會在
照片沒有 GPS 時繼承來源座標，現在改成每張照片最後都退到所屬工程案件。

但那個邏輯只在 `create()` 時跑，**升級前就已經存在的照片不會自動變**。
那些照片的 latitude / longitude 仍是 0，而前台地圖與後台 photo_map 的
domain 都是 `latitude != 0` → 它們永遠不會出現在地圖上。

這裡對所有座標仍為空的照片重跑一次補完流程：EXIF 仍優先，讀不到才用兜底。
已經有座標的照片完全不碰，所以重複執行是安全的。
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # version 為 None 代表全新安裝，沒有既有照片可回填
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['supervision.photo']._backfill_missing_coordinates()
