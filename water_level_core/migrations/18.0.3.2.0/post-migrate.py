# -*- coding: utf-8 -*-
"""3.2.0：日摘要改用台灣日。既有的摘要是 UTC 日（日期標籤與筆數都不對），整批重算。

只重寫 water_level_reading_daily；讀值（append-only）一筆不動。
接手舊資料的新裝（jt 從 construction_water_level 2.x 升上來）不會跑 migration，由 post_init_hook 處理。
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['water.level.monitor']._rollup_all()
