# -*- coding: utf-8 -*-
# 日誌標題（name）原本依「重算當下的語言」格式化：context 沒帶語言（排程、匯入、
# shell）時落到 en_US，於是同一個庫裡混著「Tue, Nov 3」與「11月3日 週二」。
# 2.10.4 起固定用中文格式（SHEET_NAME_LOCALE），這裡把既有日誌重算一次。
#
# 走 add_to_compute 而不是 write：重算不經過 write()，不受 14 天鎖定的守門擋，
# 也不留訊息記錄。complete_name 依賴 name，要在 name 落庫後另外排程（理由同
# 18.0.2.6.0：同一輪 flush 中才被標記的下游欄位不保證會處理）。

from odoo import api, SUPERUSER_ID

FIELDS_IN_ORDER = ('name', 'complete_name')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sheet = env['daily.log.sheet'].with_context(active_test=False)
    sheets = Sheet.search([])
    if not sheets:
        return
    for field_name in FIELDS_IN_ORDER:
        env.add_to_compute(Sheet._fields[field_name], sheets)
        env.flush_all()
