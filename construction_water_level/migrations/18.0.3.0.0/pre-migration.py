# -*- coding: utf-8 -*-
"""18.0.3.0.0：水位拆成三個模組。

歸屬改掛由 water_level_core 的 pre_init_hook 處理（見 water_level_core/hooks.py 檔頭：
必須在新模組安裝前做，不能等到這裡）。這支只做一件事：再確認一次「有社區資料就一起裝
社區模組」——核心若早先已單獨裝好，它的 hook 不會再跑，最後一道關卡就在這裡。
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.water_level_core.hooks import ensure_community_module_scheduled


def migrate(cr, version):
    ensure_community_module_scheduled(api.Environment(cr, SUPERUSER_ID, {}))
