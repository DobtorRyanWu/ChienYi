# -*- coding: utf-8 -*-
# 18.0.6.10.3：單號是「/」的一般式／預約式自主檢查，依工程所屬公司補號（使用者 2026-11-16 決定）。
#
# 來源：單號以前依「登入者目前選的公司」取號，任泰（jt 公司 2）沒有自主檢查序列 → 全部寫成「/」
# （jt 2026-11-16 唯讀實查：一般式 2,313／2,362 張、預約式 309／318 張，多是 2022–2023 匯入的舊資料）。
# 取號已在 construction_supervision_base 18.0.6.7.5 改成依工程公司（ir.sequence._next_by_code_for_project）。
#
# 編法（使用者選「依單據日期」）：依檢查日期、同日再依 id 排序；前綴年月用檢查日期（例 GSI-202206-0001）。
# 那家公司沒有序列時自動複製一支、從 1 起。用 SQL 寫回單號，不經過 write()、不產生追蹤訊息。
# 補了哪些 id 寫在 log；回復＝把那些 id 的單號寫回「/」。
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    Seq = env['ir.sequence']
    Seq._backfill_slash_numbers(
        'general.self.inspection', 'name', 'general.self.inspection', ('inspection_date',))
    Seq._backfill_slash_numbers(
        'reservation.self.inspection', 'inspection_no', 'reservation.self.inspection', ('inspection_date',))
