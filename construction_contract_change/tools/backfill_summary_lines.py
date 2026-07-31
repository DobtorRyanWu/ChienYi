# -*- coding: utf-8 -*-
"""補上契約變更單缺少的「頂層彙總項」明細行。

【為什麼需要這支工具】

contract.change.order 的四個金額（變更前／變更額／變更後／變更比率）由
`_compute_amount_totals` 計算，而它**只加總 item_level == 0 的明細**：

    top = order.line_ids.filtered(lambda l: l.item_level == 0)
    order.original_contract_amount = sum(top.mapped('original_amount'))

UI 精靈會自動補這一筆（contract_change_wizard.py 的 H5 註解說明：
「所有頂層彙總/稅什費項即使未變更也必須納入，否則以 Σ 頂層項計算的
變更前/後契約金額會漏掉未變更群組的基底金額而短計」）。

但 Apps Script 匯入只建葉項明細 → 一筆 item_level==0 都沒有 → 四個金額全是 0。
（實測 P11001 的變更單：104 筆明細 item_level 全是 2。）

【算法】

不能用「葉項變更額加總」當變更金額 —— 稅什費項（tax_misc_rate）會隨前置
兄弟項的總額縮放，不在葉項明細裡。正確做法是讓 Odoo 自己算：

    變更後 = 頂層工項的 planned_amount（recursive stored compute，套用後已重算）
    變更前 = 變更後 − 本次變更淨額

而「本次變更淨額」同樣要含稅什費的連動，所以用比例還原：

    含稅倍率 = 變更後總額 / Σ(非稅什費頂層子項的變更後金額)
    變更前總額 = Σ(葉項 original_amount) × 含稅倍率

【用法】對已套用（state=applied）的變更單執行；可重複執行（已有頂層行就跳過）。

    docker exec <odoo> sh -c 'odoo shell -d <db> --no-http < 本檔'
"""

TOL = 0.05          # 金額對帳容差（元）；四捨五入誤差用


def _top_task(order):
    """取這張變更單所屬專案的頂層契約工項（item_level == 0）。"""
    tasks = order.project_id.task_ids.filtered(
        lambda t: t.active and not t.parent_id)
    return tasks


def _tax_multiplier(top):
    """含稅倍率 = 頂層總額 / 非稅什費子項總額。

    稅什費項（tax_misc_rate 有值）的金額 = 前置兄弟項總額 × 比率，
    所以「總額 / 非稅項總額」就是 1 + 有效稅什費率。
    沒有稅什費項時回 1.0。
    """
    non_tax = sum(
        c.planned_amount for c in top.child_ids if not c.tax_misc_rate)
    if not non_tax:
        return 1.0
    return top.planned_amount / non_tax


def backfill(env, order_ids=None, dry_run=False):
    CO = env['contract.change.order'].sudo()
    domain = [('state', '=', 'applied')]
    if order_ids:
        domain.append(('id', 'in', order_ids))
    orders = CO.search(domain, order='id')

    print('掃描已套用的變更單 %d 張%s' % (len(orders), '（dry-run，不寫入）' if dry_run else ''))
    print()
    fixed = failed = skipped = 0

    for o in orders:
        has_top = o.line_ids.filtered(lambda l: l.item_level == 0)
        if has_top:
            print('SKIP 變更單 %s：已有 %d 筆頂層明細' % (o.name, len(has_top)))
            skipped += 1
            continue

        tops = _top_task(o)
        if len(tops) != 1:
            print('FAIL 變更單 %s：找到 %d 個頂層工項，需人工處理' % (o.name, len(tops)))
            failed += 1
            continue
        top = tops

        after = top.planned_amount
        mult = _tax_multiplier(top)
        leaf_before = sum(o.line_ids.mapped('original_amount'))
        leaf_after = sum(o.line_ids.mapped('new_amount'))
        before = round(leaf_before * mult, 2)

        # 對帳：用同一個倍率把葉項變更後金額還原，必須等於 Odoo 算出來的頂層金額。
        # 不等就代表這張單的明細沒有涵蓋所有非稅什費葉項，推算的「變更前」不可信。
        check = round(leaf_after * mult, 2)
        if abs(check - after) > TOL:
            print('FAIL 變更單 %s：對帳不符 —— 葉項還原 %.2f vs 頂層實際 %.2f（差 %.2f）'
                  % (o.name, check, after, check - after))
            print('     可能原因：明細未涵蓋全部非稅什費葉項，或工項樹在套用後又被改過。')
            failed += 1
            continue

        print('變更單 %s' % o.name)
        print('   含稅倍率     = %.10f' % mult)
        print('   變更前契約金額 = %.2f   （葉項變更前 %.2f × 倍率）' % (before, leaf_before))
        print('   變更後契約金額 = %.2f   （＝頂層工項 planned_amount，對帳通過）' % after)
        print('   本次變更金額   = %.2f' % (after - before))

        if not dry_run:
            # 欄位組合與 UI 精靈的 _create_change_order_line() 一致：
            # 彙總行用 qty=1 × unit_price=總額，讓 original_amount/new_amount
            # （compute = qty × price）等於整份契約金額。
            # item_name 在資料庫是 NOT NULL，漏了會噴 NotNullViolation。
            env['contract.change.order.line'].sudo().create({
                'change_order_id': o.id,
                'task_id': top.id,
                'item_no': top.item_no or '',
                'item_name': top.name or '',
                'unit': top.unit or '',
                # change_type 留空＝自動納入的彙總行，不是一筆實際變更
                'is_summary_line': True,
                'original_qty': 1.0,
                'original_unit_price': before,
                'new_qty': 1.0,
                'new_unit_price': after,
            })
            o.invalidate_recordset()
            print('   → 已補頂層明細行；變更單抬頭現在是 前=%.2f 額=%.2f 後=%.2f 比率=%.4f%%'
                  % (o.original_contract_amount, o.change_amount,
                     o.new_contract_amount, o.change_amount_rate * 100))
        fixed += 1
        print()

    print('---')
    print('補齊 %d 張、略過 %d 張、失敗 %d 張' % (fixed, skipped, failed))
    return fixed, skipped, failed


if 'env' in dir():
    import sys
    _dry = '--dry-run' in ' '.join(sys.argv)
    backfill(env, dry_run=_dry)
    if not _dry:
        env.cr.commit()
