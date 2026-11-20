# -*- coding: utf-8 -*-
"""回填工程的「進度表啟用過」（project_project.progress_ever_activated）。

欄位在 construction_supervision_base 6.8.0 新增，舊資料一律是空的。
有任何一張使用中或已歸檔的進度表＝啟用過（已歸檔只會在啟用過的工程出現：啟用新版時
舊版被歸檔）。啟用過又退回草稿、現在全部都是草稿的工程，資料裡看不出來，只能當沒啟用過
（開工後仍可改日期，跟改版前一樣）——這種工程逐一印進 log。
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE project_project p
           SET progress_ever_activated = TRUE
         WHERE COALESCE(p.progress_ever_activated, FALSE) = FALSE
           AND EXISTS (SELECT 1 FROM progress_schedule s
                        WHERE s.project_id = p.id AND s.state IN ('active', 'archived'))
     RETURNING p.id, p.code
    """)
    rows = cr.fetchall()
    _logger.info('回填「進度表啟用過」：%d 個工程 %s', len(rows), [r[1] for r in rows])
    cr.execute("""
        SELECT p.code, p.state FROM project_project p
         WHERE COALESCE(p.progress_ever_activated, FALSE) = FALSE
           AND p.state <> 'draft'
           AND EXISTS (SELECT 1 FROM progress_schedule s WHERE s.project_id = p.id)
    """)
    for code, state in cr.fetchall():
        _logger.warning('工程 %s（%s）有進度表但目前沒有使用中或已歸檔的版本，'
                        '看不出有沒有啟用過，當成沒啟用過（日期不鎖）', code, state)
