# -*- coding: utf-8 -*-
"""18.0.1.14.0：累計進度統一成一套算法（models/progress_calc.py）之後，把存起來的數字照新算法重算。

- 全部進度區間：累計預定／實際改照日期排（以前照序號）→ 重算。
- 使用中與已歸檔的進度表：各段實際進度照共用算法重寫（草稿日誌也算、空檔與開工前的日誌也算、
  舊系統匯入的累計值當基準點）。逐張印出最後一段的累計實際前後。
- 進度表「目前累計預定／實際」改成到今天 → 重算。
- 有共用交界日的工程：日誌的所屬區間（照日期取前一段）、本日預定份額（預定 ÷ 這一段自己的日子）重算。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['progress.schedule.line']
    Schedule = env['progress.schedule']

    lines = Line.search([])
    before = {l.id: (round(l.cumulative_planned or 0, 2), round(l.cumulative_actual or 0, 2)) for l in lines}
    env.add_to_compute(Line._fields['cumulative_planned'], lines)
    env.add_to_compute(Line._fields['cumulative_actual'], lines)
    env.flush_all()

    schedules = Schedule.search([('state', 'in', ('active', 'archived'))])
    _logger.info('重算實際進度：%d 張進度表（使用中＋已歸檔）', len(schedules))
    schedules._sync_actual_all_lines()
    Schedule.search([])._compute_current_progress()
    env.flush_all()

    changed = 0
    for schedule in schedules.sorted(lambda s: (s.project_id.id, s.version)):
        diff = [l for l in schedule.line_ids
                if (round(l.cumulative_planned or 0, 2), round(l.cumulative_actual or 0, 2)) != before.get(l.id)]
        if diff:
            changed += 1
            last = schedule.line_ids.sorted(lambda l: (l.date_start, l.date_end, l.sequence, l.id))[-1:]
            _logger.warning(
                '進度表 %s（%s，v%s，%s）%d 段累計有變；最後一段 累計預定 %.2f → %.2f、累計實際 %.2f → %.2f',
                schedule.id, schedule.project_id.code, schedule.version, schedule.state, len(diff),
                before[last.id][0], last.cumulative_planned, before[last.id][1], last.cumulative_actual)
    _logger.info('重算完成：%d 張進度表的累計有變', changed)

    # 有共用交界日的工程：日誌的所屬區間與本日預定份額
    cr.execute("""
        SELECT DISTINCT s.project_id
          FROM progress_schedule_line a
          JOIN progress_schedule_line b
            ON b.schedule_id = a.schedule_id AND b.id <> a.id
           AND b.date_start <= a.date_end AND b.date_end >= a.date_start
          JOIN progress_schedule s ON s.id = a.schedule_id
    """)
    project_ids = [r[0] for r in cr.fetchall()]
    if project_ids:
        sheets = env['daily.log.sheet'].search([('supervision_project_id', 'in', project_ids)])
        sheets._compute_progress_line()
        sheets._compute_daily_planned_progress()
        sheets._compute_changed_planned_progress()
        env.flush_all()
        _logger.info('有共用交界日的工程 %d 個：重算 %d 張日誌的所屬區間與本日預定', len(project_ids), len(sheets))
    else:
        _logger.info('沒有共用交界日的進度表：日誌的所屬區間與本日預定不用重算')
