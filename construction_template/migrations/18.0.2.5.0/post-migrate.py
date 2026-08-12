# -*- coding: utf-8 -*-
"""檢試驗管制表換成工程會新版格式，需要重灌 test_control 空白樣板。

實際測試人員回報「目前系統的檢試驗管制表與工程會新版格式要求不符」，
新樣板由 tools/gen_doc_templates/build_test_control.py 從工程會提供的
「材料設備檢（試）驗管制總表（修正版）」產生：進場日期拆成預定／實際兩欄、
契約數量欄取消、項次改流水序號、規定抽樣頻率改印頻率、會同人員補業主方。

`seed_default_templates` 冪等：既有的系統預設記錄只 update 附件內容，
專案專屬／公司層級樣板（is_default=False）不受影響。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
