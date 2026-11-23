# -*- coding: utf-8 -*-
"""18.0.1.15.2：施工日誌改了、刪了，每一版進度表都跟著重算。

以前存檔只重算「這一天所屬那一版」＋使用中那一版、刪日誌哪一版都不重算 → 已歸檔的舊版、草稿的明細可能停在舊數字。
這裡把每一張進度表（使用中、已歸檔、草稿）照現在的日誌重算一次實際進度，有變的逐段印出。預定進度不動。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['progress.schedule']
    Line = env['progress.schedule.line']
    schedules = Schedule.search([])
    lines = Line.search([('schedule_id', 'in', schedules.ids)])
    before = {l.id: round(l.actual_progress or 0.0, 2) for l in lines}
    schedules._sync_actual_all_lines()
    env.flush_all()
    changed = 0
    for line in Line.browse(list(before)):
        after = round(line.actual_progress or 0.0, 2)
        if after != before[line.id]:
            changed += 1
            sched = line.schedule_id
            _logger.info('重算實際進度：%s v%s（%s）%s～%s 實際 %.2f → %.2f',
                         sched.project_id.code, sched.version, sched.state,
                         line.date_start, line.date_end, before[line.id], after)
    _logger.info('重算實際進度：進度表 %d 張、明細 %d 段，有變 %d 段', len(schedules), len(lines), changed)
