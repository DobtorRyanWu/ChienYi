# -*- coding: utf-8 -*-
"""18.0.1.15.1：變更日那一列多記三欄（split_row／split_share／split_origin_id），改變更日期時才併得回去。

既有的變更日那一列（以前計畫倒退校正「套用」切出來的、1.15.0 建立新版本切出來的）補上：
- 條件：第 2 版以後、變更日晚於第一段、明細有一列「開始日＝結束日＝變更日」，而且這一版填過兩格之一或是「建立新版本」建的
  （匯入的一天一段進度表剛好有一列落在變更日、又沒填兩格 → 不是系統切的，不動）。
- split_share（這一天本來的預定）＝前一版那一天的累計預定 − 這一版到前一天的累計預定（沒有前一版 → 照那一列現在的值）。
- split_origin_id＝前一天結束的那一段（沒有 → 隔天開始的那一段）。
只補這三欄，預定、實際一個數字都不改。逐筆印出。
"""
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api

from odoo.addons.construction_progress.models.progress_calc import ProgressCalc

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['progress.schedule']
    one = timedelta(days=1)
    marked = 0
    for sched in Schedule.search([('version', '>', 1)]):
        d = sched.change_date
        if not d or not sched._change_day_applicable():
            continue
        if not (sched.correction_target_cumulative or sched.correction_target_actual or sched.copied_from_id):
            continue
        row = sched.line_ids.filtered(lambda l: l.date_start == d and l.date_end == d)[:1]
        if not row or row.split_row:
            continue
        calc = ProgressCalc(sched.project_id, max_version=sched.version - 1)
        prev = calc.planned(d)
        before = calc.planned_in(sched, d - one) or 0.0
        share = round(prev - before, 2) if prev is not None else round(row.planned_progress or 0.0, 2)
        others = sched.line_ids - row
        origin = (others.filtered(lambda l: l.date_end == d - one)[:1]
                  or others.filtered(lambda l: l.date_start == d + one)[:1])
        cr.execute('UPDATE progress_schedule_line SET split_row = TRUE, split_share = %s, split_origin_id = %s '
                   'WHERE id = %s', (share, origin.id or None, row.id))
        marked += 1
        _logger.info('補上變更日那一列：%s v%s（%s）%s 預定 %.2f、這一天本來 %.2f、從哪一段 %s',
                     sched.project_id.code, sched.version, sched.state, d, row.planned_progress or 0.0, share,
                     origin and '%s～%s' % (origin.date_start, origin.date_end) or '—')
    env.invalidate_all()
    _logger.info('補上變更日那一列：%d 列', marked)
