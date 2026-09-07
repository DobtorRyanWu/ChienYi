# -*- coding: utf-8 -*-
"""修正整包／比例項明細列的「原金額」失真。

原本 _compute_original_amount 對整包費用項（is_lump_sum）與比例項
（tax_misc_rate）是**即時鏡射** task.planned_amount。而「套用變更」的目的
就是改 planned_amount —— 所以套用一完成，鏡子就失真：原金額變成新金額、
「追加」顯示 0。（磺港溪 111-22-AEF：自主品管費、稅什費兩列。）

本版把真相載體改成明細列自己的「原數量 × 原單價」。本腳本做兩件事：

1. **凍結救不回來的列**：已套用、且原單價是 0 的列（後台精靈舊路徑建的）。
   它的變更前金額從來沒有被存下來過，task.planned_amount 已經是變更後的值，
   只能把目前顯示的數字原地固定住（qty=1 × 現值），避免升級後又變成別的數。

2. **重算全部整包／比例列**：stored compute 的欄位在 -u 時不會自動重算
   （Odoo 只在「欄位的資料庫欄剛被建立」時才強制重算），所以要自己戳。
   原單價本來就有值的列（匯入這條路、以及精靈的彙總／稅什費列）會在這一步
   **自動修好** —— 磺港溪那兩列會從 318,384 / 2,034,625.78 回到
   240,749 / 1,517,731.11。
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['contract.change.order.line']

    lines = Line.search([
        '|', ('is_lump_sum_line', '=', True), ('is_rate_line', '=', True),
        ('task_id', '!=', False),
    ])
    if not lines:
        _logger.info('[original_amount] 沒有整包／比例項明細列，略過')
        return

    before = {l.id: l.original_amount for l in lines}

    # ── 1. 凍結：已套用且沒有原單價的列 ──────────────────────────
    orphans = lines.filtered(
        lambda l: l.change_order_id.state == 'applied'
        and not (l.original_qty and l.original_unit_price))
    for line in orphans:
        amount = round(line.original_amount or 0.0, 2)
        line.write({'original_qty': 1.0, 'original_unit_price': amount})
        _logger.warning(
            '[original_amount] 凍結（真相已遺失，維持現值）：order=%s line=%s %s → %.2f',
            line.change_order_id.name, line.id, line.item_name, amount)

    # ── 2. 重算全部（stored compute 在 -u 時不會自己重算）────────
    lines.modified(['original_qty', 'original_unit_price',
                    'is_lump_sum_line', 'is_rate_line'])
    env.flush_all()

    changed = 0
    for line in lines:
        old = before.get(line.id)
        if old is None or abs(old - line.original_amount) < 0.005:
            continue
        changed += 1
        _logger.info(
            '[original_amount] 修正：order=%s(%s) line=%s %s  %.2f → %.2f（追加 %.2f）',
            line.change_order_id.name, line.change_order_id.state, line.id,
            line.item_name, old, line.original_amount, line.change_amount)

    _logger.info('[original_amount] 掃描 %s 列，凍結 %s 列，修正 %s 列',
                 len(lines), len(orphans), changed)
