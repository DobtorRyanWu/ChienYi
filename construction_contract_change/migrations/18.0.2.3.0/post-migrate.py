# -*- coding: utf-8 -*-
"""回填 contract.change.order.line.parent_kind。

新欄位，舊資料一律是 NULL。依父項欄位推導即可 ——
升級當下實查：221 列明細，change_type='add' 共 22 列，**22 列全部有 parent_task_id**，
parent_line_id 0 列、兩者皆空 0 列 → 沒有任何有歧義的列，不需要人工判斷。

非 add 的列（modify/zero_out/delete）本來就不看父項，留 NULL。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE contract_change_order_line
           SET parent_kind = CASE
                   WHEN parent_line_id IS NOT NULL THEN 'new_group'
                   WHEN parent_task_id IS NOT NULL THEN 'existing'
               END
         WHERE change_type = 'add'
           AND parent_kind IS NULL
           AND (parent_line_id IS NOT NULL OR parent_task_id IS NOT NULL)
    """)
    filled = cr.rowcount
    # 兩者皆空的 add 列：不猜。它們原本只有在「自己是被別列指向的新群組」時才存在，
    # 那種情況約束本來就放行，parent_kind 留空不影響。
    cr.execute("""
        SELECT count(*) FROM contract_change_order_line
         WHERE change_type = 'add'
           AND parent_line_id IS NULL AND parent_task_id IS NULL
    """)
    orphan = cr.fetchone()[0]
    _logger.info('[18.0.2.3.0] parent_kind 回填 %s 列；兩者皆空未回填 %s 列', filled, orphan)
