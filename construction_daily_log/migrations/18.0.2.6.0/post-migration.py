# -*- coding: utf-8 -*-
# project_task.actual_qty 從「純欄位（從來沒有任何程式寫入）」改成
# 「由施工日誌自動計算的 compute+store」。
#
# Odoo 只會為「新增的欄位」自動排程重算；actual_qty 的資料庫欄位早就存在
# （值全是 0），升級時不會被觸發，畫面上仍然全部是 0。這裡明確排程一次重算，
# 讓既有工項一次補齊，之後才會靠 depends 自動維護。
#
# 下游的 actual_amount / completion_rate / qty_remaining / budget_status 也要
# 逐一明確排程、各自 flush：一次 flush_all() 只把「當下已排入」的重算做完，
# 在那個過程中才被標記的下游欄位不保證同輪處理（實測 actual_amount 仍為 0）。

from odoo import api, SUPERUSER_ID

# 依相依順序：數量 → 金額（recursive，彙總項沿子工項向上滾動）→ 對比分析
FIELDS_IN_ORDER = (
    'actual_qty',
    'actual_amount',
    'completion_rate',
    'qty_remaining',
    'budget_status',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Task = env['project.task']
    tasks = Task.search([])
    if not tasks:
        return
    for field_name in FIELDS_IN_ORDER:
        env.add_to_compute(Task._fields[field_name], tasks)
        env.flush_all()
