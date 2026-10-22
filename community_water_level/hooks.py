# -*- coding: utf-8 -*-
"""既有庫升級時，把社區這一側的歸屬從 construction_water_level 改掛過來。

做法與為什麼要在 pre_init_hook 做，見 water_level_core/hooks.py 檔頭；
哪些 xmlid／約束／關聯表算社區的，也由那支的 classify_* 一份判斷，這裡不另寫一套。
空庫安裝或從沒有社區資料的庫安裝時是 no-op。
"""

import logging

from odoo.addons.water_level_core.hooks import COMMUNITY_MODULE, move_ownership

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    moved = move_ownership(env.cr, COMMUNITY_MODULE)
    if any(moved.values()):
        _logger.info('水位拆模組：歸屬改掛到 %s：%s', COMMUNITY_MODULE, moved)
