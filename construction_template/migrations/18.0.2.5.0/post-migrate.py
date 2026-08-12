# -*- coding: utf-8 -*-
"""檢試驗管制表換成工程會修正版（新版型 + 套印標記），需要重灌這份空白樣板。

修正版拿掉「契約數量」欄、把「進場日期」拆成「預定進場日期／實際進場日期」兩欄、
用詞改為「檢(試)驗」，並依工程會版型逐格加上 +++INS/+++FOR 套印標記。
對照表 mappings/test_control.py 不變（沿用既有 token），只換樣板檔。

`seed_default_templates` 冪等：既有記錄只 update 附件內容。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
