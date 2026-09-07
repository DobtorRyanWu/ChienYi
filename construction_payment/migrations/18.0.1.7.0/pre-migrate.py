# -*- coding: utf-8 -*-
"""18.0.1.7.0 —— 廢除「封存」：把沒人用的非契約工項定義**真的刪掉**，並移除 active 欄。

為什麼要廢除封存
----------------
1.6.4 把「明細列被刪光的工項定義」改成封存（active=False），想留一條誤刪的回頭路。
實測下來那是錯的方向 —— 封存 ＝ **看不見也改不動的隱藏狀態**，
而隱藏狀態配上 `UNIQUE (project_id, code)` 連續製造了兩次事故：

  ・1.6.5：`_make_code()` 用 `search_count()` 看不到封存列 → 產生撞號的 code
    → `psycopg2.UniqueViolation`，使用者只看到看不懂的原始 SQL 錯誤。
  ・使用者實測：同一個工程累積出 5 筆封存定義、其中 3 筆都叫「廢料變賣」，
    「預設計入」還互相矛盾（False / True / False）。新增子項時繼承到哪一筆
    完全看不出來，而使用者在畫面上一個都看不到、也修不了。

改成直接刪掉之後沒有東西會遺失：定義只在「零明細列」時才會被清掉，
那時本來就沒有任何金額或累計歷史。「誤刪加回來」改由精靈的
「選用已建立的項目」頁籤處理 —— 那是**看得見**的。

這支做三件事
------------
1. 反覆刪除「已封存 ＋ 沒有明細列 ＋ 沒有子項」的定義（要迴圈：父項要等子項先被刪掉）
2. 萬一還有封存但**有人在用**的（理論上不該存在），一律解除封存讓它現形，
   不要留下任何看不見的東西
3. 移除 active 欄位本身，杜絕再度製造隱藏狀態
"""

import logging

_logger = logging.getLogger(__name__)

ITEM = 'payment_estimate_extra_item'
LINE = 'payment_estimate_extra_line'


def migrate(cr, version):
    if not version:
        return

    cr.execute("SELECT to_regclass(%s)", (ITEM,))
    if not cr.fetchone()[0]:
        _logger.info('18.0.1.7.0：%s 還不存在，略過。', ITEM)
        return

    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = 'active'
    """, (ITEM,))
    if not cr.fetchone():
        _logger.info('18.0.1.7.0：active 欄已不存在，略過。')
        return

    # ① 逐層刪掉「封存 ＋ 沒明細列 ＋ 沒子項」的定義
    #    要迴圈：彙總項要等它的子項先被刪掉，才會符合「沒子項」
    total = 0
    for _ in range(10):
        cr.execute(f"""
            DELETE FROM {ITEM} i
             WHERE i.active = false
               AND NOT EXISTS (SELECT 1 FROM {LINE} l WHERE l.extra_item_id = i.id)
               AND NOT EXISTS (SELECT 1 FROM {ITEM} c WHERE c.parent_id = i.id)
        """)
        if not cr.rowcount:
            break
        total += cr.rowcount
    _logger.info('18.0.1.7.0：刪除 %d 筆沒人用的封存定義。', total)

    # ② 還封存著卻有人在用的 → 解除封存（理論上不該有，但不要留看不見的東西）
    cr.execute(f"UPDATE {ITEM} SET active = true WHERE active = false")
    if cr.rowcount:
        _logger.warning(
            '18.0.1.7.0：有 %d 筆封存定義仍被明細列或子項參照，已解除封存讓它現形。',
            cr.rowcount)

    # ③ 移除 active 欄位本身
    cr.execute(f'ALTER TABLE {ITEM} DROP COLUMN active')
    _logger.info('18.0.1.7.0：已移除 %s.active（不再有封存狀態）。', ITEM)
