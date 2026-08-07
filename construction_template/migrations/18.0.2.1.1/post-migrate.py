# -*- coding: utf-8 -*-
"""把施工日誌第一聯（營造版）的系統預設樣板換成 EAGLE 的**一般式**版本。

先前放的是 `default_appointment.xlsx`（預約式版）。兩份除了「一、施工項目」
那一列的集合名之外完全相同：
    一般式 ${table:constructionItems.*}／預約式 ${table:projectSheets.*}
對照表 mappings/daily_log_c1.py 現在兩個鍵都給，所以兩份樣板都填得進去；
系統預設改放一般式版（千溢的工程案件是一般式）。

`seed_default_templates` 冪等：既有記錄只 update 附件內容。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
