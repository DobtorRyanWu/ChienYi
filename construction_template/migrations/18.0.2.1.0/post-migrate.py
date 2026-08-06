# -*- coding: utf-8 -*-
"""新增估驗詳細表／估驗照片兩個樣板類型，並把進度報告換成 EAGLE 的 xlsx 版。

`seed_default_templates` 本身冪等：既有記錄 update、缺的才 create。
進度報告原本是 .docx（來源「111年 P11102 西區/檢陳週報表」，沒有對照表也
不是同一份表單），這支跑完會把它的附件換成 EAGLE 的 progressReportTemplate.xlsx。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        # 全新安裝走 post_init_hook，這裡不重複做
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
