# -*- coding: utf-8 -*-
"""服務單單號改用 no_gap。

序號資料是 noupdate，改 XML 不會套用到已安裝的庫，所以在這裡補。
standard 實作用 PostgreSQL sequence，交易 rollback 不退號 → 測試會讓正式單號跳號。
若尚無任何服務單，順便把下一號歸回 1（測試用掉的號碼收回來）。
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seq = env.ref('construction_helpdesk.seq_service_ticket', raise_if_not_found=False)
    if not seq:
        return
    vals = {'implementation': 'no_gap'}
    if not env['construction.service.ticket'].with_context(active_test=False).search_count([]):
        vals['number_next'] = 1
    seq.write(vals)
