# -*- coding: utf-8 -*-
"""移除 NCR（supervision.defect）的資料庫殘留。

背景：系統曾並存兩套一般式缺失模型 —— general.defect.improvement（實際在用）與
supervision.defect（NCR，後台選單 active="0" 的停用模型）。NCR 的程式碼資產已在
18.0.2.2.0 移除；Odoo 會自動清掉 ir_model / ir_model_fields / ir_model_access /
ir_rule / ir_ui_view / ir_act_window / ir_cron，但**不會 drop 資料表**，也清不掉
其它模組（mail / portal / rating / sms / snailmail / construction_supervision_base）
為 NCR 建立的 ir_model_data 列。本 script 補完這兩件事。

⚠️ 不可逆：會 DROP 四張表。執行前請確認已 pg_dump。
   本機執行時 supervision_defect 僅 1 筆測試資料（NCR-202607-0001），
   三張關聯表全空，且沒有任何記錄指向它。

冪等：全部用 IF EXISTS / 條件式 DELETE，重跑無副作用。
"""

import logging

_logger = logging.getLogger(__name__)

_NCR_TABLES = (
    'defect_before_photo_rel',
    'defect_after_photo_rel',
    'defect_attachment_rel',
    'supervision_defect',
)


def migrate(cr, version):
    # ── 1. 先記錄將被丟棄的資料量，方便事後追溯 ──────────────
    for table in _NCR_TABLES:
        cr.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table,))
        if not cr.fetchone():
            continue
        cr.execute('SELECT count(*) FROM "%s"' % table)
        count = cr.fetchone()[0]
        if count:
            _logger.warning(
                '[NCR 移除] 即將 DROP TABLE %s，內含 %s 筆資料', table, count)

    # ── 2. DROP 四張表 ─────────────────────────────────────
    # CASCADE 只會帶走指向這些表的外鍵/約束；經全庫掃描確認沒有其它現役
    # 模型參照 supervision_defect（general.defect.improvement.ncr_id 與
    # general.self.inspection.item.defect_id 都已在 18.0.2.2.0 移除）。
    cr.execute('DROP TABLE IF EXISTS %s CASCADE' % ', '.join(_NCR_TABLES))
    _logger.info('[NCR 移除] 已 DROP %s', ', '.join(_NCR_TABLES))

    # ── 3. 清 ir_model_data 殘留 ───────────────────────────
    # Odoo 的 _process_end 只清理發起升級的那些模組自己的 xmlid；
    # mail/portal/rating/sms/snailmail 等為 NCR 產生的 selection 與
    # model_inherit 記錄不在其中，會留成孤兒。
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE name LIKE '%%supervision_defect%%'
           OR name LIKE '%%__supervision_defect__%%'
    """)
    _logger.info('[NCR 移除] 清除 %s 筆 ir_model_data 殘留', cr.rowcount)

    # ── 4. 保險：Odoo 已清過的表，重跑或狀態不一致時仍能收尾 ──
    cr.execute("""
        DELETE FROM ir_model_fields WHERE model = 'supervision.defect'
    """)
    cr.execute("""
        DELETE FROM ir_model_access
        WHERE model_id IN (SELECT id FROM ir_model WHERE model = 'supervision.defect')
    """)
    cr.execute("""
        DELETE FROM ir_rule
        WHERE model_id IN (SELECT id FROM ir_model WHERE model = 'supervision.defect')
    """)
    cr.execute("""
        DELETE FROM ir_sequence WHERE code = 'supervision.defect'
    """)

    # ir.cron 以 delegation inheritance 掛在 ir.actions.server 上，且該 FK 不是
    # ON DELETE CASCADE。若 DB 還留著 NCR 的排程（例如從 2.1.x 一次跳版上來、
    # 從未跑過本 script 的資料庫），直接 DELETE ir_model 會被 cascade 帶到
    # ir_act_server，然後撞上 ir_cron_ir_actions_server_id_fkey 而整個升級失敗。
    # 必須由內而外：先 ir_cron，再 ir_act_server，最後才 ir_model。
    cr.execute("""
        DELETE FROM ir_cron
        WHERE ir_actions_server_id IN (
              SELECT id FROM ir_act_server
               WHERE model_id IN (SELECT id FROM ir_model
                                   WHERE model = 'supervision.defect'))
    """)
    if cr.rowcount:
        _logger.info('[NCR 移除] 清除 %s 個指向 NCR 的排程作業', cr.rowcount)
    cr.execute("""
        DELETE FROM ir_act_server
        WHERE model_id IN (SELECT id FROM ir_model WHERE model = 'supervision.defect')
    """)
    if cr.rowcount:
        _logger.info('[NCR 移除] 清除 %s 個指向 NCR 的伺服器動作', cr.rowcount)

    cr.execute("""
        DELETE FROM ir_model WHERE model = 'supervision.defect'
    """)

    # ── 5. 順手清無關但每次升級都報錯的殘留 ────────────────
    # construction_hide_import_export 於 2026-07-17 已從 addons 移走
    # （備份在 _removed_C_backup_20260717），但 DB 仍標 installed，
    # 導致每次升級固定出現：
    #   ERROR ... Some modules are not loaded ... ['construction_hide_import_export']
    cr.execute("""
        SELECT id, state FROM ir_module_module
        WHERE name = 'construction_hide_import_export'
    """)
    row = cr.fetchone()
    if row:
        cr.execute("""
            DELETE FROM ir_model_data
            WHERE module = 'construction_hide_import_export'
        """)
        cr.execute("""
            DELETE FROM ir_module_module_dependency WHERE module_id = %s
        """, (row[0],))
        cr.execute("DELETE FROM ir_module_module WHERE id = %s", (row[0],))
        _logger.info(
            '[清理] 移除 DB 中已不存在的模組 construction_hide_import_export'
            '（原狀態 %s）', row[1])
