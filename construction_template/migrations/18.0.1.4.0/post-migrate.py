# -*- coding: utf-8 -*-
"""補灌系統預設樣板。

post_init_hook 只在「安裝」時執行、升級不跑，所以已安裝但缺這 13 筆的資料庫
（例如 07-01 那次是用 odoo shell 腳本手動灌的，沒灌到的庫就沒有）
要靠這支 migration 補上。

邏輯冪等：已經有 13 筆的庫（odoo18_dev / odoo18_template / odoo18_c2）
跑完只會 update，不會變成 26 筆。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates


def migrate(cr, version):
    if not version:
        # 全新安裝走 post_init_hook，這裡不重複做
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env)
