# -*- coding: utf-8 -*-
"""18.0.1.6.3 —— 名稱改成「每期一份的快照」：建立並填好 name 欄。

改了什麼
--------
`payment.estimate.extra.line` 原本有兩個名稱概念：
    name_override      本期顯示名稱（可留空）
    item_display_name  compute：name_override or extra_item_id.name
清單上並排兩欄，使用者實測時直接指出「不知道哪一個才是對的」。

改成只有一個 `name`（required），語意與 unit_price 一致 ——
每期各存一份的快照，改任一期不影響其他期別與工項定義。

為什麼要 pre-migrate
--------------------
`name` 是 required=True。Odoo 會先把新欄位加成 NULL，再嘗試設 NOT NULL；
既有列的 name 是 NULL 時那一步會直接失敗，整個升級中斷。
所以在 ORM 載入模型之前，先用 SQL 把欄位建好並填滿：
    name_override 有值 → 用它（那就是該期實際印的名稱）
    留空           → 用工項定義的名稱（原本 item_display_name 的 fallback）
兩者都空 → 用 code，至少不是 NULL（不該發生，但不要讓升級死在這裡）。
"""

import logging

_logger = logging.getLogger(__name__)

TABLE = 'payment_estimate_extra_line'


def migrate(cr, version):
    if not version:
        return

    cr.execute("SELECT to_regclass(%s)", (TABLE,))
    if not cr.fetchone()[0]:
        _logger.info('18.0.1.6.3：%s 還不存在，略過。', TABLE)
        return

    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = %s AND column_name IN ('name', 'name_override')
    """, (TABLE,))
    cols = {r[0] for r in cr.fetchall()}

    if 'name' not in cols:
        cr.execute(f'ALTER TABLE {TABLE} ADD COLUMN name varchar')
        _logger.info('18.0.1.6.3：已新增 %s.name', TABLE)

    if 'name_override' in cols:
        cr.execute(f"""
            UPDATE {TABLE} l
               SET name = COALESCE(NULLIF(TRIM(l.name_override), ''),
                                   NULLIF(TRIM(i.name), ''),
                                   i.code)
              FROM payment_estimate_extra_item i
             WHERE i.id = l.extra_item_id
               AND (l.name IS NULL OR TRIM(l.name) = '')
        """)
        _logger.info('18.0.1.6.3：由 name_override／工項名稱填好 %d 列的 name',
                     cr.rowcount)
    else:
        cr.execute(f"""
            UPDATE {TABLE} l
               SET name = COALESCE(NULLIF(TRIM(i.name), ''), i.code)
              FROM payment_estimate_extra_item i
             WHERE i.id = l.extra_item_id
               AND (l.name IS NULL OR TRIM(l.name) = '')
        """)
        _logger.info('18.0.1.6.3：由工項名稱填好 %d 列的 name', cr.rowcount)

    # 還有 NULL 的話 NOT NULL 會失敗，寧可留下痕跡也不要讓升級死得莫名其妙
    cr.execute(f"SELECT count(*) FROM {TABLE} WHERE name IS NULL OR TRIM(name) = ''")
    remaining = cr.fetchone()[0]
    if remaining:
        _logger.warning(
            '18.0.1.6.3：仍有 %d 列的 name 是空的，先填入預留字串以免 NOT NULL 失敗。'
            ' 這些列的名稱要人工補。', remaining)
        cr.execute(
            f"UPDATE {TABLE} SET name = '（未命名非契約工項）' "
            f"WHERE name IS NULL OR TRIM(name) = ''")

    # item_display_name 是舊的 stored compute 欄，留著是無害的孤兒欄位，
    # 但清掉比較乾淨（Odoo 不會自動刪）。
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = 'item_display_name'
    """, (TABLE,))
    if cr.fetchone():
        cr.execute(f'ALTER TABLE {TABLE} DROP COLUMN item_display_name')
        _logger.info('18.0.1.6.3：已移除舊的 item_display_name 欄')
