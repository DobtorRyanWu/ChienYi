# -*- coding: utf-8 -*-
"""18.0.2.8.0：保存期間由兩年（730 天）改為三年（1095 天）。

依據：新北市政府水利局 115.10.02 函（新北水河計字第1151900632號）要求透水保水
監測資料等佐證「保存期限至少 3 年」；DM 同步改為「依法保存三年」。

只改還停在舊預設 730 的場域。其他數字是有人刻意設定的（例如合約另議），不能蓋掉。
欄位預設值改了只影響之後新建的場域，既有的要靠這支補。
"""

import logging

_logger = logging.getLogger(__name__)

OLD_DEFAULT_DAYS = 730
NEW_DEFAULT_DAYS = 1095


def migrate(cr, version):
    cr.execute("""
        UPDATE water_level_site SET retention_days = %s
         WHERE retention_days = %s
     RETURNING id
    """, (NEW_DEFAULT_DAYS, OLD_DEFAULT_DAYS))
    ids = [row[0] for row in cr.fetchall()]
    _logger.info('水位場域保存天數 %s → %s：更新 %s 筆 %s',
                 OLD_DEFAULT_DAYS, NEW_DEFAULT_DAYS, len(ids), ids)
