# -*- coding: utf-8 -*-
"""既有比例項明細一律標成「手動金額」。

3.2.0 以前比例項（稅什費、自主品管費…）的金額本來就是手填（建立時試算一次當預設、
之後照使用者或匯入寫的值）。新欄位 is_amount_manual 預設 False，不標的話，下一次
同一張通報單有任何明細被存檔，這些金額就會被「比例 × 本單基數」靜靜蓋掉。
標成手動金額＝保持現值；要改回自動算，在明細上按「解除手動金額」。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE reservation_notification_slip_line l
           SET is_amount_manual = TRUE
          FROM project_task t
         WHERE t.id = l.task_id
           AND COALESCE(t.tax_misc_rate, 0) <> 0
           AND NOT EXISTS (SELECT 1 FROM project_task c WHERE c.parent_id = t.id)
           AND COALESCE(l.is_amount_manual, FALSE) = FALSE
    """)
    _logger.info('既有比例項明細標成手動金額 %d 列（保持現值）', cr.rowcount)
