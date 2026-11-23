# -*- coding: utf-8 -*-
"""18.0.1.15.0：「計畫倒退校正」改成「變更日進度」，拿掉「校正基準日」（直接用變更日）。

以前有校正的版本，生效日（effective_change_date）＝校正基準日（correction_date），不是變更時間（change_date）。
拿掉之後生效日一律＝變更時間 → 兩個日期不一樣的版本，先把變更時間改成原本的校正基準日，
生效日、哪一天用哪一版、算出來的數字都不變。逐筆印出改了哪一版。
"""
import logging

_logger = logging.getLogger(__name__)


def _has_column(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not (_has_column(cr, 'progress_schedule', 'needs_plan_correction')
            and _has_column(cr, 'progress_schedule', 'correction_date')):
        return
    cr.execute("""
        SELECT s.id, s.version, s.change_date, s.correction_date, p.code
          FROM progress_schedule s
          LEFT JOIN project_project p ON p.id = s.project_id
         WHERE s.needs_plan_correction AND s.correction_date IS NOT NULL
           AND s.correction_date <> s.change_date
    """)
    rows = cr.fetchall()
    for sid, ver, change_date, correction_date, code in rows:
        _logger.info('變更日改成原本的校正基準日：%s v%s（id %s）%s → %s', code, ver, sid, change_date, correction_date)
    if rows:
        cr.execute("""
            UPDATE progress_schedule
               SET change_date = correction_date
             WHERE needs_plan_correction AND correction_date IS NOT NULL
               AND correction_date <> change_date
        """)
    _logger.info('有校正、兩個日期不一樣的版本：%d 張', len(rows))
