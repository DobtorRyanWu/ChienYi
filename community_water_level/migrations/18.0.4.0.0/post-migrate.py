# -*- coding: utf-8 -*-
"""18.0.4.0.0：方案等級從設備搬到社區場域。

每個社區場域取旗下（含停用）設備的最高等級（使用者定案：不讓客戶掉功能），再同步回每一台設備。
邏輯在 water.level.site._community_migrate_service_levels()（測試直接呼叫那一支——空庫 -i 不跑 migrations）。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    result = env['water.level.site']._community_migrate_service_levels()
    sites = env['water.level.site'].with_context(active_test=False).browse(list(result))
    for site in sites:
        before, after = result[site.id]
        _logger.info('方案等級搬到社區：%s（id %s）%s → %s', site.name, site.id, before, after)
    _logger.info('方案等級搬到社區：共 %s 個社區場域', len(result))
