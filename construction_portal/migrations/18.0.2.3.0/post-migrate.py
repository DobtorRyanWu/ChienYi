# -*- coding: utf-8 -*-
"""construction_portal 18.0.2.2.1 → 18.0.2.3.0 升級

背景
----
前台上傳的缺失改善照片（3 個入口：缺失新增 `name="photo"`、改善後照片
`name="after_photo"`、詳情頁追加 `name="photos"`）原本**完全不進照片管理**。

原因：`portal_utils._defect_save_photos()` 是直接在照片行子模型
（general / reservation.defect.improvement.photo）上 create，缺失本體的 write
從頭到尾沒被呼叫過，而 photo.sync.mixin 的 write 觸發條件是
`field_name in vals` → mixin 永遠不會跑。
（後台是在表單裡以內嵌 One2many 編輯，欄位會出現在父記錄的 vals 裡，所以後台正常。）

本版已在 `_defect_save_photos` 補上同步呼叫。這支 migration 負責把**升級前**
由前台上傳、從未同步的缺失照片補建成 supervision.photo。

為什麼放在 construction_portal 而不是 construction_photo
--------------------------------------------------------
construction_photo 是 construction_general / construction_quality 的依賴，
載入順序在它們之前，它的 migration 執行時 general/reservation.defect.improvement
還不存在於 registry（實測 log：「模型 general.defect.improvement 未安裝，略過」）。
construction_portal depends 了 construction_general + construction_quality
+ construction_photo，載入順序在最後，是唯一能安全存取這些模型的位置。

實作方式
--------
呼叫缺失本體既有的 `_auto_sync_photos()` override
（construction_general / construction_quality 各有一份，已處理
「One2many 中間模型 → attachment_id → 去重 → 建檔」），
與即時同步走同一條路徑，不寫平行邏輯。
mixin 自身以 attachment_id 去重 → 本腳本重跑安全。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# (model, 照片欄位名) —— 缺失改善的三個階段
DEFECT_TARGETS = [
    ('general.defect.improvement', 'before_photo_ids'),
    ('general.defect.improvement', 'during_photo_ids'),
    ('general.defect.improvement', 'after_photo_ids'),
    ('reservation.defect.improvement', 'before_photo_ids'),
    ('reservation.defect.improvement', 'during_photo_ids'),
    ('reservation.defect.improvement', 'after_photo_ids'),
]


def _backfill(env, model_name, field_name, label):
    """對 model_name 上有 field_name 照片的所有記錄跑一次同步。

    回傳 (掃過筆數, 成功, 失敗, 新建的 supervision.photo 筆數)。
    """
    if model_name not in env:
        _logger.info('%s：模型 %s 未安裝，略過', label, model_name)
        return 0, 0, 0, 0

    Model = env[model_name]
    if field_name not in Model._fields:
        _logger.warning('%s：%s 上找不到 %s 欄位，略過',
                        label, model_name, field_name)
        return 0, 0, 0, 0

    # active_test=False：已封存記錄底下的照片同樣要回填
    records = Model.sudo().with_context(active_test=False).search(
        [(field_name, '!=', False)])
    if not records:
        return 0, 0, 0, 0

    config = records._get_photo_sync_config().get(field_name)
    if not config:
        _logger.warning('%s：%s 的 _get_photo_sync_config() 沒有 %s 設定，略過',
                        label, model_name, field_name)
        return len(records), 0, 0, 0

    Photo = env['supervision.photo'].sudo().with_context(active_test=False)
    before = Photo.search_count([])

    ok = failed = 0
    for rec in records:
        try:
            rec._auto_sync_photos(field_name, config)
            ok += 1
        except Exception as e:  # noqa: BLE001 — 單筆失敗不該中斷整個升級
            failed += 1
            _logger.warning('%s 回填失敗 - %s#%s, Error: %s',
                            label, model_name, rec.id, e)

    return len(records), ok, failed, Photo.search_count([]) - before


def migrate(cr, version):
    # version 為 None 代表全新安裝：沒有升級前的舊資料，修正後的
    # _defect_save_photos 會直接處理所有新上傳，不需回填。
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    total_created = 0

    for model_name, field_name in DEFECT_TARGETS:
        label = f'缺失照片({model_name}.{field_name})'
        scanned, ok, failed, created = _backfill(
            env, model_name, field_name, label)
        total_created += created
        if scanned:
            _logger.info('%s 回填：掃過 %s 筆（成功 %s / 失敗 %s），新建 %s 筆',
                         label, scanned, ok, failed, created)

    _logger.info(
        '前台缺失照片回填完成，共新建 %s 筆 supervision.photo'
        '（已存在者由 attachment_id 去重略過，本腳本重跑安全）', total_created)
