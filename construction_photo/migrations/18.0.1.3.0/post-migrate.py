# -*- coding: utf-8 -*-
"""照片管理模組 18.0.1.2.0 → 18.0.1.3.0 升級

背景
----
photo.sync.mixin 的 _auto_sync_photos() 第一道閘門原本是
`if not hasattr(record, 'project_id') or not record.project_id: continue`。
工程告示牌照片（project.project.signboard_photo_ids）宣告在 project.project 上，
而 project.project 沒有 project_id 欄位（Odoo core 沒有、9 個擴充它的
construction 模組也都沒加）→ 條件恆成立 → 100% 靜默跳過，只寫 debug log。

本版把「同步目標專案」抽成可覆寫的 _get_sync_project()，並在
construction_photo/models/supervision_project.py 覆寫為 return self，
告示牌照片自此可正常同步。

這支 migration 負責把**升級前已上傳、但從未同步**的告示牌照片補建成 supervision.photo。

⚠️ 為什麼這裡只處理告示牌、不處理缺失照片：
construction_photo 是 construction_general / construction_quality 的**依賴**，
載入順序在它們之前。本 migration 執行時 general/reservation.defect.improvement
還不存在於 registry（實測 log：「模型 general.defect.improvement 未安裝，略過」）。
缺失照片的回填因此放在 construction_portal 的 migration（它 depends 了
construction_general + construction_quality + construction_photo，載入順序在最後）。

實作方式
--------
直接呼叫剛修好的 _auto_sync_photos()，而不是自己寫一份平行的 SQL insert。
理由：
  1. 回填結果與日後即時同步完全一致，不會產生兩種長得不一樣的資料
  2. supervision.photo 有 compute+store 的 name 欄位與 create() 內的自動標籤
     邏輯，必須走 ORM 才會正確
  3. mixin 自身的去重（比對 attachment_id）會擋掉已存在的記錄 → 本腳本重跑安全
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

SIGNBOARD_FIELD = 'signboard_photo_ids'


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
    # version 為 None 代表全新安裝：沒有升級前的舊資料，修正後的程式碼
    # 會直接處理所有新上傳，不需回填。
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    scanned, ok, failed, created = _backfill(
        env, 'project.project', SIGNBOARD_FIELD, '告示牌照片')
    _logger.info(
        '告示牌照片回填完成：掃過 %s 個專案（成功 %s / 失敗 %s），新建 %s 筆 '
        'supervision.photo（已存在者由 attachment_id 去重略過，本腳本重跑安全）',
        scanned, ok, failed, created)
