# -*- coding: utf-8 -*-
"""3.8.1：補灌系統預設「自主檢查表（單張）」樣板。

這一種原本只在全新安裝時由 post_init_hook 建立，3.0.0 之前就有的庫升級上來是 0 筆，
匯出自主檢查表會跳「找不到可用的自主檢查表樣板」。

只補這一種；既有系統預設（含封存、被人換過的）一律不覆蓋——replaceable 給空集合，
seed 對已存在的記錄會略過並記 WARNING，沒有才新建。
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

SELF_INSPECTION_TYPES = ('self_inspection_form',)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(
        env, types=SELF_INSPECTION_TYPES,
        replaceable={t: set() for t in SELF_INSPECTION_TYPES})
