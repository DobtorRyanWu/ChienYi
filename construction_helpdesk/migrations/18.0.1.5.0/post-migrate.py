# -*- coding: utf-8 -*-
"""發生功能：「名稱」改以後台選單名稱為主，前台叫法放「前台顯示名稱」（使用者 D 段回饋）。

資料檔是 noupdate，已安裝的庫不會因 -u 更新，所以在這裡改。
前台的「工程列表」「工程資訊」看的都是後台「工程案件」→ 併成一項，「工程列表」那筆封存
（不刪：可能已被服務單／問題單引用，ondelete='restrict'）。
"""
from odoo import SUPERUSER_ID, api

RENAME = {
    # xmlid: (後台名稱, 前台顯示名稱)
    'module_project_info': ('工程案件', '工程列表／工程資訊'),
    'module_photo': ('照片管理', '照片中心'),
    'module_defect': ('缺失管理', '缺失改善'),
    'module_file': ('文件管理', '檔案管理'),
    'module_test': ('檢試驗管理', '檢試驗管制'),
    'module_inspection_type': ('自主檢查類型設定', '自主檢查樣板庫'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (name, portal_name) in RENAME.items():
        rec = env.ref('construction_helpdesk.' + xmlid, raise_if_not_found=False)
        if rec:
            rec.write({'name': name, 'portal_name': portal_name})
    old = env.ref('construction_helpdesk.module_project_list', raise_if_not_found=False)
    info = env.ref('construction_helpdesk.module_project_info', raise_if_not_found=False)
    if old and old.active:
        if info:
            # 已選「工程列表」的單改指到合併後的「工程案件」
            for model in ('construction.service.ticket', 'construction.problem'):
                env[model].with_context(active_test=False).search(
                    [('functional_module_id', '=', old.id)]).write({'functional_module_id': info.id})
        old.write({'active': False})
