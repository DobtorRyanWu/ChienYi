# -*- coding: utf-8 -*-
"""標記既有的「整包費用項」（is_lump_sum）。

新欄位 default=False，所以不標記的話既有資料一律走舊路徑。要標記的原因是：
專案 111 人孔調升降（北區）那類案子的整包項，unit_price 已經被契約變更寫髒了
（contract_change_order._apply_changes_to_tasks 會把 new_unit_price 寫回 task），
只靠 _mark_lump_sum_items 的「unit_price 為空」判準抓不到它們。

所以這裡改用結構判準：**無子項 + item_level == 1（掛在頂層彙總項底下）+ 無比例**。
全庫實測這個判準命中 12 筆 level-1 葉節點、其中扣掉有比例的稅什費之後剩下的
全部是自主品管費，零誤判；被排除的示範工程／基隆河左岸「自主品管費」確實有子項，
本來就走子項加總，不需要標記。

⚠️ 標記不會改變任何金額：
  - unit_price 為空者原本走分支⑤ xml_amount，標記後走分支③ xml_amount，同一個值
  - unit_price 被寫髒者（人孔案）planned_qty=1、unit_price == xml_amount，
    原本走分支④ 得 1 × 218,423.25，標記後走分支③ 得 xml_amount 218,423.25，同值
升級後的驗收條件因此是「planned_amount 一筆都不變」。
（actual_amount 會變，那是本版另一項修正：整包項改為跟著基數工項的完成比例走。）
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Task = env['project.task']

    candidates = Task.with_context(active_test=False).search([
        ('item_level', '=', 1),
        ('tax_misc_rate', '=', 0),
    ])
    hits = candidates.filtered(lambda t: not t.child_ids)

    if not hits:
        _logger.info('[is_lump_sum] 沒有需要標記的整包費用項')
        return

    hits.write({'is_lump_sum': True})
    _logger.info('[is_lump_sum] 已標記 %s 筆整包費用項：', len(hits))
    for t in hits:
        _logger.info(
            '[is_lump_sum]   proj=%s(%s) item_no=%s name=%s '
            'qty=%s unit_price=%s xml_amount=%s planned_amount=%s',
            t.project_id.id, (t.project_id.name or '')[:20], t.item_no, t.name,
            t.planned_qty, t.unit_price, t.xml_amount, t.planned_amount)
