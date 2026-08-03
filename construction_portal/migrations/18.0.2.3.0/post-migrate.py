# -*- coding: utf-8 -*-
"""construction_portal 18.0.2.2.1 → 18.0.2.3.0 升級（現已 no-op）

## 現況：這支 migration 不再做事

原本它負責把「升級前由前台上傳、從未同步的缺失照片」補建成 supervision.photo，
作法是呼叫缺失本體的 `_auto_sync_photos()` / `_get_photo_sync_config()`
（photo.sync.mixin 提供）。

**construction_photo 18.0.3.x 的照片資料表收斂讓這兩件事都不成立了**：

1. `photo.sync.mixin` 已退場（`construction_photo/models/photo_sync_mixin.py` 已刪除）。
   收斂後照片本身就是 `supervision.photo`，沒有「同步」這件事，
   各模組的 `_get_photo_sync_config()` / `_auto_sync_photos()` override 也一併移除。
   照原樣執行會拋：
       AttributeError: 'general.defect.improvement' object has no attribute
                       '_get_photo_sync_config'

2. 它想補的資料，收斂 migration 已經補完了。`construction_portal` depends
   `construction_photo`，載入順序保證收斂先跑。實測（odoo18_dev，2026-08-03）：
   收斂後 `supervision_photo.general_defect_id` 非空正好 121 筆，與升級前
   `general_defect_improvement_photo` 的 121 筆相符；`general_inspection_id` 59 筆、
   `test_record_id` 472 筆，資料完整無損。

## 為什麼保留檔案而不是刪掉

Odoo 靠檔案存在與否決定要不要跑；留一個有說明的 no-op，比留一個空目錄
或直接消失更能讓後人知道「這一版曾經做過什麼、為什麼不用做了」。

## 這個 bug 怎麼被發現的

只有當 `general_defect_improvement_photo` 有資料時才會踩到——表為空時
`_backfill()` 走到 `if not records: return` 就提早返回。測試庫（migtest /
template / c2）都是 0 筆所以升級全綠，odoo18_dev 有 121 筆才爆出來。
測試資料不足造成的假通過。
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info(
        '[portal 18.0.2.3.0] 缺失照片回填已由 construction_photo 的資料表收斂'
        '取代，本 migration 不再執行（photo.sync.mixin 已退場）')
