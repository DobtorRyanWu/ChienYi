# -*- coding: utf-8 -*-
"""重算每一張契約變更單的「變更前／變更後契約金額、本次變更、變更比率」（2.5.0）。

2.5.0 改了 `_compute_amount_totals` 的算法：已套用的單，「之前的調整」只加排在它前面、
已套用的變更單的調整金額（以前用工程今天的累計調整、只扣自己這一張）。
這四個欄位存在資料庫裡，-u 不會自己重算（Odoo 只在欄位的資料庫欄剛建立時才強制重算），
所以這裡把它們整批重算一次，並逐張印出有變的。

不做的事：
・不補頂層彙總列。2.5.0 的「套用時自己補『壹 發包工程費』那一列」只管以後套用的單；
  以前匯入時補的、不含調整金額的那一列（例：正式站 112-07-AEG 第 2 次變更）不在這裡改
  —— 使用者 2026-11-16 決定先不補（那一案可能整個重匯）。
・不改任何工項、工程的金額。
"""

import logging

_logger = logging.getLogger(__name__)

FIELDS = ('original_contract_amount', 'new_contract_amount', 'change_amount', 'change_amount_rate')


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['contract.change.order'].search([('project_id', '!=', False)])
    if not orders:
        _logger.info('[變更前後] 沒有掛工程的變更單，略過')
        return

    before = {o.id: tuple(o[f] for f in FIELDS) for o in orders}

    # 四個金額的計算依據有 state、lump_adjust_amount（本單與同工程其他單）→
    # 標記這兩個欄位「變了」，四個金額就會整串重算。
    orders.modified(['state', 'lump_adjust_amount'])
    env.flush_all()

    changed = 0
    for o in orders.sorted(lambda r: (r.project_id.id, r.change_no, r.id)):
        old = before[o.id]
        new = tuple(o[f] for f in FIELDS)
        if all(abs((a or 0.0) - (b or 0.0)) < 0.005 for a, b in zip(old, new)):
            continue
        changed += 1
        _logger.info(
            '[變更前後] %s（第 %s 次，%s）：變更前 %.2f → %.2f、變更後 %.2f → %.2f、'
            '本次變更 %.2f → %.2f',
            o.name, o.change_no, o.state, old[0] or 0.0, new[0], old[1] or 0.0, new[1],
            old[2] or 0.0, new[2])
    _logger.info('[變更前後] 掃描 %s 張變更單，數字有變 %s 張', len(orders), changed)
