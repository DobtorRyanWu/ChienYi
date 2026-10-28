# -*- coding: utf-8 -*-
"""累計預定進度、累計實際進度（施工日誌與估驗附件「工程施工進度報告表」共用）。

為什麼不用既有欄位：
- daily.log.sheet.daily_planned_progress 是「當日份額」（區間預定 ÷ 區間天數），
  不是累計；附表9-1 註 4、進度報告表要的都是累計。
- 實際進度在系統裡記的是「本日實際進度」daily_actual_progress（每日增量，construction_progress），
  進度表「從日誌同步進度」把它加總成累計（說明書 5.4／6.x／7.x）。
- daily.log.sheet.actual_progress 只有舊系統 xlsm 匯入會寫，存的是當天的累計值。

規則：
- 預定（使用者 2026-10-25 裁示）：哪一版進度表「生效」照日誌自己的 base_progress_schedule_id——
  effective_change_date 嚴格小於該日的最新版；找不到才用當天生效的最舊版
  （construction_progress/models/daily_log_sheet.py 的 _compute_base_progress_schedule）。
  區間內線性內插：區間起點累計 + 區間預定 × 已過天數 / 區間天數。
- 實際（使用者 2026-10-28 選「照說明書＋保留舊資料」）：每日增量的加總，只算已填寫／鎖定的日誌
  （與進度表同步同一組狀態）；當天或之前若有 xlsm 匯入的累計值，以最後那一張為基準、只加它之後的增量
  ——舊日誌重印時印的還是它自己的累計值，與 2026-10-25 以前相同（jt 10-28 實查：5,679 張日誌有 3,391 張
  只有匯入累計值、沒有每日增量）。10-25 那一版是「最後一次有填的累計值」，前後台另開欄位手填，已撤回。

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


# 進度表「從日誌同步進度」加總的日誌狀態（construction_progress/models/progress_schedule_line.py）
COUNTED_STATES = ('filled', 'auto_locked', 'locked')


def actual_cumulative_on(project, day, include=None):
    """截至 day（含）的累計實際進度 %；沒有任何實際進度資料回 None。

    :param include: 印某一張日誌時傳它自己——還在編輯中（不在 COUNTED_STATES）的那一張也要算進去
    """
    if not day:
        return None
    Sheet = project.env['daily.log.sheet']
    scope = [('supervision_project_id', '=', project.id), ('log_date', '<=', day)]
    legacy = Sheet.search(scope + [('actual_progress', '>', 0)], order='log_date desc, id desc', limit=1)
    total, found = (legacy.actual_progress, True) if legacy else (0.0, False)
    if 'daily_actual_progress' not in Sheet._fields:      # 沒裝 construction_progress
        return total if found else None
    after = [('log_date', '>', legacy.log_date)] if legacy else []
    logs = Sheet.search(scope + after + [('state', 'in', COUNTED_STATES), ('daily_actual_progress', '!=', 0)])
    if include and include.state not in COUNTED_STATES and include.daily_actual_progress \
            and include.supervision_project_id == project and include.log_date <= day \
            and (not legacy or include.log_date > legacy.log_date):
        logs |= include
    if logs:
        total += sum(logs.mapped('daily_actual_progress'))
        found = True
    return total if found else None


def rounded(value, digits=2):
    return None if value is None else round(value, digits)
