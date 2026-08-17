# -*- coding: utf-8 -*-
"""自主檢查承攬廠商：Many2one(res.company) → 純文字，並與工程案件同步。

背景：
  兩式自主檢查原本有 contractor_company_id（Many2one res.company，domain
  company_type=contractor）與 contractor_name（compute store，抄前者的 name）。
  本系統是一庫一公司，res_company 只有 1 筆 → 那個下拉永遠只有一個選項，
  選了等於沒填，反而誘導填表的人把「這次派工的協力廠商」填進去
  （那該填 subcontractor_name）。
  改為：contractor_name 成為 compute + store + readonly=False，
  預設帶入 project_id.contractor_company_name，允許逐筆覆寫。

本 script 做的事（純資料落值，不動 schema）：
  1. 舊 M2O 有值 → 把 res_company.name 落到 contractor_name
  2. 舊 M2O 也是空 → 改由工程案件的 contractor_company_name 回填

  兩段都只補「contractor_name 目前為空」的列，不覆蓋既有值
  （前台早就在手打這個欄位，那些值不能被蓋掉）。

為何放 post 而非 pre：
  Odoo 是在所有模組載入完畢後才跑 ir.model.data._process_end() 清掉
  程式碼中已消失的欄位（並可能 DROP COLUMN），那晚於 post-migrate，
  所以 post 執行時 contractor_company_id 必定還在；同時 post 又晚於
  任何可能發生的 ORM 重算。兩個風險方向 post 都滿足。

  第 1 步實務上多半是 no-op —— contractor_name 本來就是 stored compute，
  值早就落在文字欄裡了。保留它是為了防「舊 compute 未觸發而留空」的個案，
  並留下可對帳的筆數紀錄。

不自己 DROP COLUMN：交給 Odoo 的 _process_end 處理，升級後以 SQL 驗證；
若確認沒被 drop 再手動補。

冪等：兩段 UPDATE 都有 COALESCE(...)='' 守衛，且先檢查舊欄位是否存在，重跑安全。
"""

import logging

_logger = logging.getLogger(__name__)

_TABLES = ('general_self_inspection', 'reservation_self_inspection')


def _has_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    # 全新安裝沒有舊資料
    if not version:
        return

    # --- 1) 舊 M2O 的公司名 → contractor_name（只補空的） ---
    for table in _TABLES:
        if not _has_column(cr, table, 'contractor_company_id'):
            _logger.info(
                '[承攬廠商遷移] %s 已無 contractor_company_id，跳過公司名落值', table)
            continue
        cr.execute("""
            UPDATE {table} i
               SET contractor_name = c.name
              FROM res_company c
             WHERE c.id = i.contractor_company_id
               AND COALESCE(i.contractor_name, '') = ''
               AND COALESCE(c.name, '') <> ''
        """.format(table=table))
        _logger.info('[承攬廠商遷移] %s 由 res_company 落值 %s 筆', table, cr.rowcount)

    # --- 2) 舊 M2O 也是空 → 由工程案件的營造廠商回填（只補空的） ---
    cr.execute("""
        UPDATE general_self_inspection i
           SET contractor_name = p.contractor_company_name
          FROM project_project p
         WHERE p.id = i.project_id
           AND COALESCE(i.contractor_name, '') = ''
           AND COALESCE(p.contractor_company_name, '') <> ''
    """)
    _logger.info('[承攬廠商遷移] general 由工程案件回填 %s 筆', cr.rowcount)

    # 預約式一律走 slip_id 上一層取工程：i.project_id 是 stored related，
    # 歷史資料可能為 NULL，不可信。
    cr.execute("""
        UPDATE reservation_self_inspection i
           SET contractor_name = p.contractor_company_name
          FROM reservation_notification_slip s
          JOIN project_project p ON p.id = s.project_id
         WHERE s.id = i.slip_id
           AND COALESCE(i.contractor_name, '') = ''
           AND COALESCE(p.contractor_company_name, '') <> ''
    """)
    _logger.info('[承攬廠商遷移] reservation 由工程案件回填 %s 筆', cr.rowcount)
