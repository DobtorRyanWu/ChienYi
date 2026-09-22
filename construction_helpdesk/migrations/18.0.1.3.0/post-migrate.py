# -*- coding: utf-8 -*-
"""前台意見回饋：功能模組 → 發生功能。

預設資料是 noupdate，已安裝的庫不會因 -u 更新，所以在這裡補：
- 既有 8 筆依前台實際功能更名、重排序；
- 後台專用的「契約工項」「估驗計價」取消「前台顯示」（新欄位預設 True）；
- 「操作疑問」「系統問題」兩類勾「詢問發生功能」。
新增的項目（工程列表、照片中心…）由資料檔建立（noupdate 只擋更新、不擋建立）。
"""
from odoo import SUPERUSER_ID, api

MODULES = {
    # xmlid: (名稱, 排序, 前台顯示)
    'module_login': ('登入／帳號', 10, True),
    'module_daily_log': ('施工日誌', 20, True),
    'module_self_inspection': ('自主檢查', 30, True),
    'module_notification_slip': ('通報單', 40, True),
    'module_file': ('檔案管理', 45, True),
    'module_contract_item': ('契約工項', 70, False),
    'module_payment': ('估驗計價', 75, False),
    'module_other': ('不確定／其他', 99, True),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (name, seq, portal) in MODULES.items():
        rec = env.ref('construction_helpdesk.' + xmlid, raise_if_not_found=False)
        if rec:
            rec.write({'name': name, 'sequence': seq, 'show_in_portal': portal})
    for xmlid in ('category_operation_question', 'category_system_problem'):
        cat = env.ref('construction_helpdesk.' + xmlid, raise_if_not_found=False)
        if cat:
            cat.write({'ask_functional_module': True})
