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
- 實際（使用者 2026-10-28 選「照說明書＋保留舊資料」）：每日增量（本日實際進度）的加總，**所有狀態都算**
  ——jt 10-28 實查 5,679 張日誌全是「自動鎖定」、沒有一張「已填寫」：大家不按定稿、靠 14 天自動鎖定；
  只算已填寫／鎖定的話，當天印的日誌會少掉最近兩週的進度（r1 審查 F4）。進度表的同步照說明書只算已填寫／鎖定，
  所以最近 14 天內兩者可能不同。
  舊系統 xlsm 匯入的日誌在 actual_progress 存累計值（jt 3,391 張只靠它）：
  · 印那一張舊日誌本身＝它自己的值（與 2026-10-25 以前完全相同；同案同日多人各一張時不會印成別人的，r1 審查 F2）；
  · 其他日子＝當天或之前最後一個有匯入值的日期為基準（同日多張取最大）＋那天之後的增量。
  10-25 那一版是「最後一次有填的累計值」、前後台另開欄位手填，已撤回。
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


def actual_cumulative_on(project, day, sheet=None):
    """截至 day（含）的累計實際進度 %；沒有任何實際進度資料回 None。

    :param sheet: 印某一張日誌時傳它自己——舊匯入的日誌印它自己的累計值，不管同日有沒有別張
    """
    if not day:
        return None
    if sheet is not None and (sheet.actual_progress or 0) > 0:
        return sheet.actual_progress
    Sheet = project.env['daily.log.sheet']
    scope = [('supervision_project_id', '=', project.id), ('log_date', '<=', day)]
    last = Sheet.search(scope + [('actual_progress', '>', 0)], order='log_date desc, id desc', limit=1)
    found = bool(last)
    total = max(Sheet.search(scope + [('actual_progress', '>', 0), ('log_date', '=', last.log_date)])
                .mapped('actual_progress')) if last else 0.0
    if 'daily_actual_progress' not in Sheet._fields:      # 沒裝 construction_progress
        return total if found else None
    after = [('log_date', '>', last.log_date)] if last else []
    logs = Sheet.search(scope + after + [('daily_actual_progress', '!=', 0)])
    if logs:
        total += sum(logs.mapped('daily_actual_progress'))
        found = True
    return total if found else None


def rounded(value, digits=2):
    return None if value is None else round(value, digits)
