# -*- coding: utf-8 -*-
# 18.0.2.8.2：單號是「/」的試驗紀錄，依工程所屬公司補號（使用者 2026-11-16 決定）。
#
# 來源：單號以前依「登入者目前選的公司」取號，任泰（jt 公司 2）沒有試驗紀錄序列 → 寫成「/」
# （jt 2026-11-16 唯讀實查 149／688 張）。取號已在 construction_supervision_base 18.0.6.7.5 改成依工程公司。
#
# 編法（使用者選「依單據日期」）：日期依序取 取樣日 → 進場日 → 建立日，同日再依 id 排序；
# 前綴年月用這個日期。用 SQL 寫回，不經過 write()；補了哪些 id 寫在 log，回復＝寫回「/」。
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    env['ir.sequence']._backfill_slash_numbers(
        'supervision.test.record', 'name', 'supervision.test.record', ('sample_date', 'in_site_date'))
