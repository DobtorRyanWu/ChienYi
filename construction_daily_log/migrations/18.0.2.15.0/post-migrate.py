# -*- coding: utf-8 -*-
"""日誌不再鎖定（1118 會議回復原版）：把「自動鎖定」的日誌改回「已填寫」、清掉鎖定標記。

2.15.0 起 daily.log.sheet 不再因為超過 14 天而鎖住（_is_edit_locked 一律 False）。
既有資料要跟著整理，不然畫面上還掛著「自動鎖定」：

- state 'auto_locked' → 'filled'。兩者在累計完成數量、可估驗數量、實際進度的計算裡本來就同樣算
  「已確認」，所以改完計算結果不變。state_sequence 是跟著 state 的儲存欄位，一起改。
  明細表 daily_log_line.sheet_state 是日誌狀態的儲存複本（related store），也要一起改，
  不然用 SQL 改完日誌，明細上還留著「自動鎖定」。
- is_locked 一律改成 False（儲存欄位，新版恆為否）。
- 'locked'（早期匯入工具手動設的）不動：它不是 14 天規則產生的，新版也不會擋修改。
- 排程名稱改掉「自動鎖定」字樣（排程資料是 noupdate，-u 不會更新名稱，所以在這裡改）。

直接下 SQL：幾千筆日誌逐筆走 ORM 會各寫一筆狀態異動到討論區，沒有必要。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

FILLED_SEQUENCE = 2          # 對應 daily.log.sheet.STATE_SEQUENCE_MAP['filled']
CRON_XMLID = 'construction_daily_log.ir_cron_auto_lock_daily_logs'
CRON_NAME = '施工日誌 - 滿 14 天的編輯中日誌自動標成已填寫'


def migrate(cr, version):
    if not version:          # 新裝：沒有舊資料要整理
        return
    cr.execute("""
        UPDATE daily_log_sheet
           SET state = 'filled', state_sequence = %s
         WHERE state = 'auto_locked'
    """, [FILLED_SEQUENCE])
    converted = cr.rowcount
    cr.execute("UPDATE daily_log_line SET sheet_state = 'filled' WHERE sheet_state = 'auto_locked'")
    converted_lines = cr.rowcount
    cr.execute("UPDATE daily_log_sheet SET is_locked = FALSE WHERE is_locked IS DISTINCT FROM FALSE")
    unlocked = cr.rowcount
    cr.execute("SELECT count(*) FROM daily_log_sheet WHERE state = 'locked'")
    manual_locked = cr.fetchone()[0]
    _logger.info('日誌不再鎖定：自動鎖定→已填寫 %d 筆（明細上的狀態複本 %d 筆）、清掉鎖定標記 %d 筆；'
                 '手動「已鎖定」%d 筆維持原狀態（不擋修改）', converted, converted_lines, unlocked, manual_locked)

    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref(CRON_XMLID, raise_if_not_found=False)
    if cron:
        cron.name = CRON_NAME
    else:
        _logger.warning('找不到排程 %s，名稱沒有更新', CRON_XMLID)
