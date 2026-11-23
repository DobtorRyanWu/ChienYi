# -*- coding: utf-8 -*-
"""累計預定／累計實際進度：所有地方共用的一套算法（2026-11-24 使用者定案）。

以前首頁、進度表、進度報告、進度曲線、印出來的日報各算各的，同一天會出現不同的數字
（實測：首頁預定 30／印的 22、進度報告含期間後的日誌、空檔日子的日誌進度表不算、交界日預定多算一天…）。
現在全部用這一份。規則：

到某一天（含）的累計預定
- 用哪一版進度表：變更日（effective_change_date＝change_date）在這一天或之前的最新一版；
  一版都還沒生效 → 第一版。契約變更當天用新版（「變更後」）；進度曲線那一天另外畫一個「變更前」的點。
- 一段的預定平均分到這一段的每一天，當天算進去（10 天 20% → 第 1 天 2%、第 10 天 20%）。
- 兩段共用的交界日算在前一段（照日期排在前面的那一段）；後一段的預定分到它自己剩下的日子。
  整段的日子都被前面的段占走（交界日上的單日列）→ 那一段的預定在它的結束日一次算進去。
- 兩段中間的空檔：累計停在前一段結束的值。

到某一天（含）的累計實際
- 每一篇施工日誌的本日實際進度都算（草稿也算），照日期加總，不看分段（空檔的日子也算）。
- 基準點：變更日進度填的「變更後累計實際進度」（變更日當天就是那個數字）、舊系統匯入的累計值
  （daily.log.sheet.actual_progress，同一天取最大）。取這一天或之前日期最晚的一個；同一天以變更日進度為準。
  基準點之後再加每天的本日實際進度。
- 契約變更當天的「變更前」：不算當天的變更日基準點（給進度曲線畫垂直線用）。
"""

import bisect
from datetime import timedelta

from odoo import fields

SCHEDULE_STATES = ('active', 'archived')

# 進度表自己在切分／重算變更日那一列時帶的 context：明細的寫入不要再回頭觸發重算（2026-11-24）
SKIP_CHANGE_DAY = 'progress_skip_change_day_refresh'


def line_key(line):
    """進度區間的先後：開始日 → 結束日 → 序號 → id（交界日上的單日列排在從交界日開始的那一段前面）"""
    today = fields.Date.today()
    return (line.date_start or today, line.date_end or today, line.sequence or 0,
            line.id if isinstance(line.id, int) else 0)


def owned_days(lines):
    """{line.id: [這一段自己的日子（遞增）]}：交界日算在排前面的那一段。"""
    covered = set()
    result = {}
    for line in sorted(lines, key=line_key):
        days = []
        if line.date_start and line.date_end:
            day = line.date_start
            while day <= line.date_end:
                if day not in covered:
                    covered.add(day)
                    days.append(day)
                day += timedelta(days=1)
        result[line.id] = days
    return result


def effective_date(schedule):
    return schedule.effective_change_date or schedule.change_date


class ProgressCalc:
    """一個工程的累計進度計算器：建立時把進度表、變更日進度、日誌一次讀進來，之後問哪一天都不再查資料庫。

    :param project: project.project
    :param max_version: 只用這一版（含）以前的進度表——舊版進度表自己的數字不受之後變更的調整影響
    :param include_schedule: 草稿的進度表也要算進來時（例：草稿版自己的明細）帶它
    """

    def __init__(self, project, max_version=None, include_schedule=None):
        project = project.sudo()
        env = project.env
        domain = [('project_id', '=', project.id), ('state', 'in', SCHEDULE_STATES)]
        if max_version:
            domain.append(('version', '<=', max_version))
        schedules = env['progress.schedule'].sudo().search(domain)
        if include_schedule:
            schedules |= include_schedule.sudo()
        self.schedules = schedules.filtered(lambda s: s.line_ids).sorted('version')
        self._schedule_cache = {}

        # 基準點：(日期, 優先（變更日進度 1＞舊系統匯入 0）, 數字)
        anchors = []
        for schedule in self.schedules:
            for line in schedule.line_ids:
                if line.actual_correction_target and line.date_start:
                    anchors.append((line.date_start, 1, line.actual_correction_target))
        increments = {}
        legacy = {}
        Sheet = env['daily.log.sheet'].sudo()
        fnames = ['log_date', 'daily_actual_progress']
        if 'actual_progress' in Sheet._fields:
            fnames.append('actual_progress')
        for row in Sheet.search_read([('supervision_project_id', '=', project.id)], fnames):
            day = row['log_date']
            if not day:
                continue
            if row.get('daily_actual_progress'):
                increments[day] = increments.get(day, 0.0) + row['daily_actual_progress']
            if (row.get('actual_progress') or 0) > 0:
                legacy[day] = max(legacy.get(day, 0.0), row['actual_progress'])
        anchors.extend((day, 0, value) for day, value in legacy.items())
        anchors.sort()
        self.anchors = anchors
        self.inc_days = sorted(increments)
        self.inc_prefix = []
        total = 0.0
        for day in self.inc_days:
            total += increments[day]
            self.inc_prefix.append(total)

    # ── 累計實際 ──────────────────────────────────────────────────────────────
    def _inc_upto(self, day):
        """日期 ≤ day 的本日實際進度加總"""
        i = bisect.bisect_right(self.inc_days, day)
        return self.inc_prefix[i - 1] if i else 0.0

    def actual(self, day, before=False):
        """到 day（含）的累計實際進度；沒有任何資料（沒有基準點、day 以前也沒有本日進度）回 None。"""
        if not day:
            return None
        anchor = None
        for a_day, prio, value in reversed(self.anchors):
            if a_day > day:
                continue
            if before and prio == 1 and a_day == day:
                continue
            anchor = (a_day, value)
            break
        if anchor:
            return anchor[1] + self._inc_upto(day) - self._inc_upto(anchor[0])
        if not self.inc_days or self.inc_days[0] > day:
            return None
        return self._inc_upto(day)

    # ── 累計預定 ──────────────────────────────────────────────────────────────
    def governing(self, day, before=False):
        """day 那一天用哪一版進度表（變更當天：before＝舊版、否則新版）"""
        if not self.schedules:
            return None
        chosen = None
        for schedule in self.schedules:
            eff = effective_date(schedule)
            if eff and (eff < day if before else eff <= day):
                chosen = schedule
        return chosen or self.schedules[0]

    def _schedule_data(self, schedule):
        data = self._schedule_cache.get(schedule.id)
        if data is None:
            lines = schedule.line_ids.filtered(lambda l: l.date_start and l.date_end)
            owned = owned_days(lines)
            data = [(line.planned_progress or 0.0, line.date_end, owned.get(line.id) or [])
                    for line in lines]
            self._schedule_cache[schedule.id] = data
        return data

    def planned_in(self, schedule, day):
        """這一版進度表到 day（含）的累計預定"""
        data = self._schedule_data(schedule)
        if not data:
            return None
        total = 0.0
        for planned, date_end, days in data:
            if not days:
                if day >= date_end:
                    total += planned
                continue
            done = bisect.bisect_right(days, day)
            if done:
                total += planned * done / len(days)
        return total

    def planned(self, day, before=False):
        """到 day（含）的累計預定進度；沒有進度表回 None。"""
        if not day:
            return None
        schedule = self.governing(day, before=before)
        if schedule is None:
            return None
        return self.planned_in(schedule, day)

    def change_days(self):
        """契約變更（新版生效）的日子：{日期: (變更前那一版, 變更後那一版)}"""
        result = {}
        for schedule in self.schedules[1:]:
            eff = effective_date(schedule)
            if eff:
                result[eff] = (self.governing(eff, before=True), self.governing(eff))
        return result
