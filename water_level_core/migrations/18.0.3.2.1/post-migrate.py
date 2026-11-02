# -*- coding: utf-8 -*-
"""3.2.1：既有庫的後台地圖底圖網址若是空的或字串 False，補成 OSM；已設定的不動。"""

from odoo import SUPERUSER_ID, api

from odoo.addons.water_level_core.hooks import ensure_default_tile_url


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ensure_default_tile_url(env)
