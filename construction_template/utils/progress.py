# -*- coding: utf-8 -*-
"""累計預定進度、累計實際進度（施工日誌與估驗附件「工程施工進度報告表」共用）。

為什麼不用既有欄位：
- daily.log.sheet.daily_planned_progress 是「當日份額」（區間預定 ÷ 區間天數），
  不是累計；附表9-1 註 4、進度報告表要的都是累計。
- daily.log.sheet.actual_progress 只有 xlsm 匯入會寫，很多天是空的。

規則（使用者 2026-10-25 裁示）：
- 預定：哪一版進度表「生效」照日誌自己的 base_progress_schedule_id——
  effective_change_date 嚴格小於該日的最新版；找不到才用當天生效的最舊版
  （construction_progress/models/daily_log_sheet.py 的 _compute_base_progress_schedule）。
  區間內線性內插：區間起點累計 + 區間預定 × 已過天數 / 區間天數。
- 實際：當天或之前最後一張「實際進度 > 0」的日誌。

construction_template 不依賴 construction_progress，所以沒有進度表模型時回 None。
"""

SCHEDULE_STATES = ('active', 'archived')


def governing_schedule(project, day):
    if 'progress.schedule' not in project.env or not day:
        return None
    Schedule = project.env['progress.schedule']
    base = [('project_id', '=', project.id), ('state', 'in', SCHEDULE_STATES)]
    schedule = Schedule.search(base + [('effective_change_date', '<', day)],
                               order='version desc', limit=1)
    if not schedule:
        schedule = Schedule.search(base + [('effective_change_date', '=', day)],
                                   order='version asc', limit=1)
    if not schedule:
        # 第一版還沒生效（日期早於第一版的生效日）：用第一版，算出來是 0——
        # 「有進度表、只是還沒開始」與「根本沒有進度表（回 None、印空白）」要分開
        schedule = Schedule.search(base, order='version asc', limit=1)
    return schedule or None


def planned_cumulative_on(project, day):
    """截至 day（含）的累計預定進度 %；沒有進度表回 None"""
    schedule = governing_schedule(project, day)
    if schedule is None:
        return None
    # 依日期自己累加，不用明細的 cumulative_planned：那個欄位是「序號 <= 自己」的加總，
    # 兩條明細序號相同（預設都是 10）時會重複計算（2026-10-25 程式審查）
    lines = schedule.line_ids.filtered(lambda l: l.date_start and l.date_end).sorted(
        lambda l: (l.date_start, l.sequence, l.id))
    if not lines:
        return None
    cumulative = 0.0
    for line in lines:
        if day < line.date_start:
            break
        if day >= line.date_end:
            cumulative += line.planned_progress
            continue
        days = (line.date_end - line.date_start).days + 1
        elapsed = (day - line.date_start).days + 1
        return cumulative + line.planned_progress * elapsed / days
    return cumulative


def actual_cumulative_on(project, day):
    """當天或之前最後一次有填的累計實際進度 %；從沒填過回 None"""
    if not day:
        return None
    sheet = project.env['daily.log.sheet'].search([
        ('supervision_project_id', '=', project.id),
        ('log_date', '<=', day),
        ('actual_progress', '>', 0),
    ], order='log_date desc, id desc', limit=1)
    return sheet.actual_progress if sheet else None


def rounded(value, digits=2):
    return None if value is None else round(value, digits)
