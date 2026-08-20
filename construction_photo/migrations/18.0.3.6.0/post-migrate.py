# -*- coding: utf-8 -*-
"""照片管理模組 18.0.3.5.0 → 18.0.3.6.0 升級

source_model（來源分類）Selection 調整：
  + estimate  估驗計價    ← 原本被塞進 'other'
  + signboard 工程告示牌  ← 原本被塞進 'other'
  - acceptance 驗收       ← 全庫 0 筆，也沒有任何模組會產生驗收照片

本腳本把既有資料重新歸類。實測（升級前，全庫 470 張）：
    other 10 筆 = estimate_id 9 筆 + signboard_project_id 1 筆
    acceptance 0 筆

為什麼用原生 SQL 而不是 ORM
---------------------------
`estimate_id` 是 construction_payment 加在 supervision.photo 上的欄位，而
construction_payment **depends construction_photo**，載入順序在本模組之後 ——
本腳本執行時 registry 裡的 supervision.photo 還沒有那個欄位
（同 18.0.1.3.0 post-migrate 遇到的狀況）。
資料庫的**欄位**卻是早就存在的，所以直接下 SQL 沒問題；
只在欄位真的存在時才跑，避免在還沒裝 construction_payment 的環境炸掉。

優先序與 _photo_source_model_code() 一致
---------------------------------------
那條 super() 鏈是 construction_photo（signboard）先判、construction_payment
（estimate）後判，所以**同時掛了兩者時 signboard 優先**。這裡先跑 signboard、
再跑 estimate，且第二段只挑仍然是 'other' 的，順序才對得起來。
"""

import logging

_logger = logging.getLogger(__name__)


def _has_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    # 1. 工程告示牌（欄位就在本模組，一定存在）
    cr.execute("""
        UPDATE supervision_photo
        SET source_model = 'signboard'
        WHERE source_model = 'other'
          AND signboard_project_id IS NOT NULL
    """)
    _logger.info('source_model: other → signboard，%s 筆', cr.rowcount)

    # 2. 估驗計價（欄位由 construction_payment 提供）
    if _has_column(cr, 'supervision_photo', 'estimate_id'):
        cr.execute("""
            UPDATE supervision_photo
            SET source_model = 'estimate'
            WHERE source_model = 'other'
              AND estimate_id IS NOT NULL
        """)
        _logger.info('source_model: other → estimate，%s 筆', cr.rowcount)
    else:
        _logger.info('supervision_photo 沒有 estimate_id 欄位'
                     '（construction_payment 未安裝），略過估驗計價歸類')

    # 3. 已移除的 acceptance：留著會變成畫面上顯示不出名稱的孤兒值。
    #    實測 0 筆，這段是防呆（別的環境可能有）。
    cr.execute("""
        UPDATE supervision_photo
        SET source_model = 'other'
        WHERE source_model = 'acceptance'
    """)
    if cr.rowcount:
        _logger.warning('source_model: acceptance（已移除）→ other，%s 筆。'
                        '這些照片原本標為「驗收」，請人工確認是否需要改掛其他來源',
                        cr.rowcount)

    # 4. 收尾統計，讓升級日誌看得出結果
    cr.execute("""
        SELECT COALESCE(source_model, '(空白)'), count(*)
        FROM supervision_photo GROUP BY 1 ORDER BY 2 DESC
    """)
    _logger.info('升級後 source_model 分布：%s',
                 '、'.join('%s=%s' % row for row in cr.fetchall()))
