# -*- coding: utf-8 -*-
# 18.0.6.7.4：把空的 project_task.item_no（NULL 或空字串）依專案補成 1、2…，
# 讓同一次 -u 能把 item_no 設成 NOT NULL。
#
# 來源（2026-11-16 唯讀查 jt）：jt 有 6 列，全是 hr_timesheet 自動建的「內部專案」任務
# （Training／Meeting、培訓／會議）。id 1、2 在 item_no 欄位出現前就存在，所以本模組安裝時
# NOT NULL 就沒設成功；07-31 新增公司時 core 建的內部任務，因為 create() 的自動補號當時是死碼
# （063c585 才救回），NULL 也寫得進去。後果是每次 -u 都報
# 「Table 'project_task': unable to set NOT NULL on column 'item_no'」，而且 DB 沒有這個約束。
#
# 補號規則：同一專案內依 id 由小到大給 1、2、3…（沒有專案的任務視為同一組）。
# 不避開專案裡已有的編號：內部專案的自動任務本來就會重號（dev 實查是 1、1、2），
# project_task.item_no 也沒有唯一約束。
#
# 為什麼用 SQL、放在 pre：pre 階段本模組的新程式碼還沒載入 registry，ORM 用不到 item_no。
# Odoo 18 在整個 -u 最後（loading.py 的 registry.finalize_constraints()）才設 NOT NULL，
# 所以這裡補完值，同一次 -u 就會設成功。
# 依 item_no 計算的 stored 欄位（item_no_path、item_no_sort…）由同版的 post-migrate 用 ORM 重算。
import logging

_logger = logging.getLogger(__name__)

# log 最多列出幾筆；正式站預期是個位數，超過只列前面幾筆，總數照實印
LOG_ROW_LIMIT = 50


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        WITH empty AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY id) AS seq
              FROM project_task
             WHERE item_no IS NULL OR item_no = ''
        )
        UPDATE project_task AS t
           SET item_no = empty.seq::varchar
          FROM empty
         WHERE t.id = empty.id
     RETURNING t.id, t.project_id, t.item_no
    """)
    rows = sorted(cr.fetchall())
    if not rows:
        return
    _logger.info(
        'item_no 回填：%d 列空的 item_no 已依專案補號 (id, project_id, item_no)=%s%s',
        len(rows), rows[:LOG_ROW_LIMIT], ' …' if len(rows) > LOG_ROW_LIMIT else '')
