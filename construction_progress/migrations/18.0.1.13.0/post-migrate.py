# -*- coding: utf-8 -*-
"""18.0.1.13.0：照新的算法重算進度區間的實際進度。

- 使用中的進度表：每一段都重算（交界日只算一次；以前啟用新版時前面幾段沒有重算、停在 0 的也一起補）。
- 已歸檔的舊版：只重算有共用交界日（上一段結束日＝下一段開始日）的那幾張——它們以前多算了一次。
  其他舊版是歷史，不動。
「校正後累計實際進度」是新欄位、舊資料都是 0，這次不會產生任何調整。
每一張重算前後累計實際進度不一樣的逐一印進 log。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _shared_boundary_schedule_ids(cr):
    cr.execute("""
        SELECT DISTINCT a.schedule_id
          FROM progress_schedule_line a
          JOIN progress_schedule_line b
            ON b.schedule_id = a.schedule_id AND b.id <> a.id
           AND b.date_start <= a.date_end AND b.date_end >= a.date_start
    """)
    return [r[0] for r in cr.fetchall()]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['progress.schedule']
    active = Schedule.search([('state', '=', 'active')])
    shared = Schedule.browse(_shared_boundary_schedule_ids(cr)).filtered(lambda s: s.state == 'archived')
    targets = active | shared
    _logger.info('重算實際進度：使用中 %d 張、有共用交界日的舊版 %d 張', len(active), len(shared))
    changed = 0
    for schedule in targets:
        lines = schedule.line_ids.sorted(lambda l: (l.sequence, l.date_start, l.id))
        before = {l.id: (l.actual_progress, l.cumulative_actual) for l in lines}
        lines._sync_actual_from_daily_logs()
        env.flush_all()
        diff = [(l, before[l.id]) for l in lines
                if abs((before[l.id][1] or 0) - (l.cumulative_actual or 0)) > 0.005]
        if diff:
            changed += 1
            last = lines[-1:]
            _logger.warning(
                '進度表 %s（%s，v%s）重算後 %d 段累計實際進度不一樣；最後一段 %.2f → %.2f',
                schedule.id, schedule.project_id.code, schedule.version, len(diff),
                before[last.id][1] if last else 0, last.cumulative_actual if last else 0)
    _logger.info('重算完成：%d 張的累計實際進度有變', changed)
