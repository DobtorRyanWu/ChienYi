# -*- coding: utf-8 -*-
# 18.0.6.7.4：pre-migrate 用 SQL 補了 item_no，但依它計算的 stored 欄位
# （display_item_no、item_no_path、item_no_sort、full_item_path、full_item_no，以及子工項的路徑）
# 還是 item_no 空的時候算出來的值。這裡用 ORM 重算。
#
# 找法：item_no 有值，item_no_path 卻是空的。依 _compute_item_no_path，item_no 有值時
# item_no_path 一定不空，所以符合的列都是過時的，其中包含 pre 剛補號的列。
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# log 最多列出幾個 id
LOG_ID_LIMIT = 50


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT id
          FROM project_task
         WHERE COALESCE(item_no, '') <> ''
           AND COALESCE(item_no_path, '') = ''
         ORDER BY id
    """)
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    tasks = env['project.task'].browse(ids)
    # 當作 item_no 剛被改過：依賴 item_no 的 stored 欄位（含遞迴到子工項的路徑）都排入重算
    tasks.modified(['item_no'])
    env.flush_all()
    _logger.info(
        'item_no 回填：已重算 %d 列的項次衍生欄位 ids=%s%s',
        len(ids), ids[:LOG_ID_LIMIT], ' …' if len(ids) > LOG_ID_LIMIT else '')
