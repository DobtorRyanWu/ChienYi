# -*- coding: utf-8 -*-
"""檢查時機的 `code` 降級為 `legacy_code`（比照 self.inspection.type.stage）。

為什麼改：
  5.0.0 把 code 做成「匯入用的穩定鍵」並顯示在畫面上，等於要求使用者替每個
  自訂的檢查時機想一個代碼、還要記得它，否則那個選項**永遠匯不進來**
  （留空的 code 沒有任何 _timing_codes 指得到）。
  同一支檔案裡的查驗段落 self.inspection.type.stage 根本不是這樣做的 ——
  它的 legacy_code 明寫「資料遷移用，手動新增的段落請留空」，
  匯入一律以「段落名稱」解析（3_匯入_引擎.py 的 stage_map()）。
  檢查時機沒有任何理由跟它不同，故改回同一個契約。

本 script 只做欄位改名，不動資料：
  UNIQUE(type_id, code) 的索引會隨欄位改名自動跟著走，
  但約束名稱要換成新的，否則 Odoo 會另外再建一條 legacy_code 的約束、
  留下一條指向已改名欄位的孤兒約束。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'self_inspection_type_timing'
           AND column_name = 'code'
    """)
    if not cr.fetchone():
        _logger.info('檢查時機：沒有 code 欄，略過（已經是 legacy_code）')
        return

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'self_inspection_type_timing'
           AND column_name = 'legacy_code'
    """)
    if cr.fetchone():
        # 兩欄並存＝上一次跑到一半。把 code 的值補進 legacy_code 再丟掉 code。
        cr.execute("""
            UPDATE self_inspection_type_timing
               SET legacy_code = code
             WHERE legacy_code IS NULL AND code IS NOT NULL
        """)
        cr.execute('ALTER TABLE self_inspection_type_timing DROP COLUMN code')
        _logger.info('檢查時機：code 與 legacy_code 並存 → 已合併並移除 code')
        return

    cr.execute('ALTER TABLE self_inspection_type_timing '
               'RENAME COLUMN code TO legacy_code')

    # 舊約束名帶著 code 字樣，改名讓 Odoo 認得（否則會多建一條、舊的變孤兒）
    cr.execute("""
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'self_inspection_type_timing'::regclass
           AND conname = 'self_inspection_type_timing_code_type_uniq'
    """)
    if cr.fetchone():
        cr.execute('ALTER TABLE self_inspection_type_timing '
                   'RENAME CONSTRAINT self_inspection_type_timing_code_type_uniq '
                   'TO self_inspection_type_timing_legacy_code_type_uniq')

    cr.execute('SELECT count(*) FROM self_inspection_type_timing '
               'WHERE legacy_code IS NOT NULL')
    _logger.info('檢查時機：code → legacy_code 改名完成，%s 筆帶有舊代碼',
                 cr.fetchone()[0])
