# -*- coding: utf-8 -*-
"""18.0.2.5.0：把「從資料來源撈取」的排程間隔改成 15 分鐘。

為什麼要寫成 migration 而不是改 XML 就好：
`cron_water_level_source_pull` 定義在 `<data noupdate="1">` 區塊裡，
改 XML 只對**還沒安裝過**的資料庫生效，既有的庫升級時完全不會被更新。
這種「改了但沒生效」最難查，因為程式碼看起來是對的。

刻意**不動 `active`**：啟用與否是每個資料庫自己的事（要有資料來源才有意義），
在這裡一律打開會讓所有租戶的庫多一支每 15 分鐘空轉的排程。
"""

import logging

_logger = logging.getLogger(__name__)

PULL_INTERVAL_MINUTES = 15


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_cron SET interval_number = %s, interval_type = 'minutes'
         WHERE id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'construction_water_level'
                         AND name = 'cron_water_level_source_pull')
    """, (PULL_INTERVAL_MINUTES,))
    _logger.info('水位來源撈取排程間隔已設為 %s 分鐘（更新 %s 筆）',
                 PULL_INTERVAL_MINUTES, cr.rowcount)
