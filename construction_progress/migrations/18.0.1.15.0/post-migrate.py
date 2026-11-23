# -*- coding: utf-8 -*-
"""18.0.1.15.0：「計畫倒退校正」改成「變更日進度」之後收尾。

- 生效日（effective_change_date，存起來的）改成一律＝變更時間 → 重算（stored compute 不會因 -u 自己重算）。
  pre-migrate 已經把兩個日期不一樣的版本的變更時間改成原本的校正基準日，所以每一張的生效日都不會變（逐張核對、印出）。
- 拿掉的欄位（需要計畫基準校正、校正基準日、校正區間開始／結束日、校正增量）與改成不存的「變更前累計預定進度」
  留下的資料表欄刪掉（Odoo 不會自己刪）。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

DROPPED = ('needs_plan_correction', 'correction_date', 'correction_period_start',
           'correction_period_end', 'plan_correction_offset', 'correction_pre_cumulative')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Schedule = env['progress.schedule']
    schedules = Schedule.with_context(active_test=False).search([])
    before = {s.id: s.effective_change_date for s in schedules}
    env.add_to_compute(Schedule._fields['effective_change_date'], schedules)
    env.flush_all()
    changed = [s for s in schedules if s.effective_change_date != before[s.id]]
    for s in changed:
        _logger.warning('生效日變了：%s v%s %s → %s', s.project_id.code, s.version, before[s.id], s.effective_change_date)
    _logger.info('重算生效日：%d 張進度表，變了 %d 張', len(schedules), len(changed))

    for column in DROPPED:
        cr.execute('ALTER TABLE progress_schedule DROP COLUMN IF EXISTS %s' % column)
    _logger.info('刪掉舊欄位的資料表欄：%s', '、'.join(DROPPED))
