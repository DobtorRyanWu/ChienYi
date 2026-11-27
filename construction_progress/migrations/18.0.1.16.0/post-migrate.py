# -*- coding: utf-8 -*-
"""18.0.1.16.0（2026-11-27）：施工日誌照進度表推出來的欄位全部照新算法重算一次。

存起來的計算欄改了算法，`-u` 不會自己重算舊資料：
- 「有無進度變更」第 1 版不算（以前第 1 版的變更日期＝開工日，開工那天會被勾）、不能手動勾（以前手動勾的拿掉）。
- 以前啟用時變更日當天不重算「本日預定用哪一版」、重設草稿不重算 → 留著舊算法數字的日誌一起改正。
逐欄印出有變的筆數，有變的日誌印工程、日期、前後的值（最多 50 筆）。
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

FIELDS = ('active_progress_schedule_id', 'base_progress_schedule_id', 'progress_line_id',
          'daily_planned_progress', 'has_progress_change', 'changed_planned_progress')


def _value(sheet, fname):
    value = sheet[fname]
    if hasattr(value, 'ids'):
        return value.id or False
    if isinstance(value, float):
        return round(value, 2)
    return value


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sheet = env['daily.log.sheet']
    sheets = Sheet.search([])
    before = {s.id: {f: _value(s, f) for f in FIELDS} for s in sheets}
    for fname in FIELDS:
        env.add_to_compute(Sheet._fields[fname], sheets)
    env.flush_all()
    sheets.invalidate_recordset(list(FIELDS))

    counts = {f: 0 for f in FIELDS}
    shown = 0
    for sheet in sheets.sorted(lambda s: (s.supervision_project_id.id, s.log_date or False)):
        diff = []
        for fname in FIELDS:
            old, new = before[sheet.id][fname], _value(sheet, fname)
            if old != new:
                counts[fname] += 1
                diff.append('%s %s → %s' % (fname, old, new))
        if diff and shown < 50:
            shown += 1
            _logger.warning('日誌 %s（%s %s）：%s', sheet.id, sheet.supervision_project_id.code,
                            sheet.log_date, '；'.join(diff))
    _logger.info('重算 %d 張施工日誌：%s', len(sheets),
                 '、'.join('%s 變了 %d 張' % (f, n) for f, n in counts.items()))
