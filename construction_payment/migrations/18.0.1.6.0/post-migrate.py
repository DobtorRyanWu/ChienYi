# -*- coding: utf-8 -*-
"""18.0.1.6.0 —— 估驗總金額拆成三個小計，強制重算既有估驗單。

為什麼一定要有這一支
--------------------
`payment.estimate.subtotal` 是 stored compute，而 **stored compute 在 `-u` 時不會
自動重算**：Odoo 只在「欄位的資料庫欄剛被建立」那一次才強制重算，公式改了但欄位早就
存在時，舊資料原封不動且**完全靜默**。這個坑在本專案發生過兩次
（見 E:\\work\\CLAUDE.md 更新紀錄 2026-09-06 的契約變更原金額）。

本版的實際情形
--------------
`subtotal` 的公式由「Σ 契約葉列」改成「契約工項小計 ＋ 有勾計入的非契約工項」。
升級當下沒有任何 extra 列，所以每一張既有估驗單的 subtotal **算出來會與升級前相同**；
真正需要落地的是三個**新欄位**（contract_subtotal / extra_subtotal /
extra_excluded_total）—— 新欄位的資料庫欄是這次才建的，理論上 Odoo 會自己算，
但那個「理論上」正是上面兩次踩坑時大家以為的事。

所以這裡不賭，直接用 `modified()` 把四個欄位一起戳成待重算，讓 flush 時逐張重算。
成本很低（估驗單是一個工程十幾張的量級），換掉的是一個靜默錯誤。
"""

import logging

_logger = logging.getLogger(__name__)

FIELDS = ['subtotal', 'contract_subtotal', 'extra_subtotal', 'extra_excluded_total']


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    estimates = env['payment.estimate'].with_context(active_test=False).search([])
    if not estimates:
        _logger.info('18.0.1.6.0：沒有估驗單，無須重算。')
        return

    before = {e.id: e.subtotal for e in estimates}

    # 戳成待重算 → 讀取時逐張重跑 _compute_subtotal → flush 落庫
    estimates.modified(FIELDS)
    estimates.flush_recordset(FIELDS)

    changed = [e for e in estimates
               if abs((e.subtotal or 0.0) - (before.get(e.id) or 0.0)) > 0.005]
    _logger.info(
        '18.0.1.6.0：重算 %d 張估驗單的總金額欄位，其中 %d 張的 subtotal 有變動。',
        len(estimates), len(changed))
    for est in changed:
        # 升級當下不該有任何一張變動（沒有 extra 列）。真的變了就把它印出來，
        # 不要讓「金額被改掉」這件事只存在於資料庫裡。
        _logger.warning(
            '18.0.1.6.0：估驗單 id=%s（%s）subtotal %s → %s',
            est.id, est.display_name, before.get(est.id), est.subtotal)
