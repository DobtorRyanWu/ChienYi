# -*- coding: utf-8 -*-
"""查驗階段改為段落主檔：升級前的防呆與存證。

背景：自主檢查的逐項查驗階段原本是寫死三值的 Selection
（stage1 施工前 / stage2 施工中 / stage3 施工後），三個 item 模型各一份。
真實抽查紀錄表的段落遠不只三種且每種檢查表各自不同（瀝青混凝土 6 段、
模板 4 段、測量放樣 3 段），故改為每個檢查類型自訂的段落主檔
self.inspection.type.stage，逐項欄位由 stage 改名為 stage_id。

⚠️ 欄位是「改名」而非原地改型別。保留同名把 varchar 改成 int4 時，
   Odoo 的 schema 更新無法轉換 'stage1'::int4，會走 fallback 保留舊欄位
   另建新欄位，而且升級不報錯 —— 資料會在畫面上憑空消失。
   改名後舊 stage 欄位原封留著，由 post-migration 讀取回填。

本 script 只做兩件事，不改任何 schema：
  1. 確認三張表的舊 stage 欄位都在（不在就中止整個升級）
  2. 把升級前的 stage 分佈寫進 log，作為事後對帳的憑據

冪等：純唯讀，重跑無副作用。
"""

import logging

_logger = logging.getLogger(__name__)

_ITEM_TABLES = (
    'self_inspection_type_item',
    'general_self_inspection_item',
    'reservation_self_inspection_item',
)


def migrate(cr, version):
    # 全新安裝沒有舊資料，直接跳過
    if not version:
        return

    for table in _ITEM_TABLES:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = %s AND column_name = 'stage'
        """, (table,))
        if not cr.fetchone():
            raise Exception(
                '[段落遷移] %s 找不到舊 stage 欄位，無法安全遷移。'
                '請確認此 DB 未曾手動改過 schema，或本次升級是否重複執行。'
                % table)

        cr.execute('SELECT stage, count(*) FROM %s GROUP BY 1 ORDER BY 1' % table)
        _logger.info('[段落遷移] 升級前 %s 的 stage 分佈：%s', table, cr.fetchall())

    cr.execute('SELECT count(*) FROM self_inspection_type')
    _logger.info('[段落遷移] 既有自主檢查類型 %s 個，'
                 '每個將自動建立「施工前／施工中／施工後」三段',
                 cr.fetchone()[0])
