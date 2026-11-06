# -*- coding: utf-8 -*-
"""工程的工作天（合約 §4；11-05 使用者決定）。

工作天＝不是該工程的例假日 且 不是國定假日；政府公告的補行上班日算工作天（即使是例假日）；
勞動節（每年 5/1）一律不算工作天，不論政府辦公日曆怎麼標（2025 年以前日曆標上班、工地勞工依法放假）。

規則優先序（_dash_is_workday）：
1. 該年度缺政府辦公日曆 → DashMissingCalendar（UserError）「缺 YYYY 年政府辦公日曆」（指標層接住顯示，不可當 0）
2. 勞動節、國定假日 → 非工作天
3. 補行上班日 → 工作天
4. 其他依工程例假日
尚未公告的未來年度：只依例假日推算（＋勞動節），呼叫端標「預估」。
"""
from datetime import date

from odoo import fields, models
from odoo.exceptions import UserError

from .official_calendar import DAY_TYPE_HOLIDAY, DAY_TYPE_MAKEUP, YEAR_ESTIMATED, YEAR_MISSING

# 例假日欄位，依 date.weekday()（0＝週一 … 6＝週日）排列
REST_DAY_FIELDS = (
    'rest_day_mon', 'rest_day_tue', 'rest_day_wed', 'rest_day_thu',
    'rest_day_fri', 'rest_day_sat', 'rest_day_sun',
)
DAYS_PER_WEEK = 7
LABOR_DAY_MONTH, LABOR_DAY_DAY = 5, 1


def missing_calendar_message(years):
    """「缺 2015、2016 年政府辦公日曆」（合約 §1-8、§13-11 的顯示文字）。"""
    return '缺 %s 年政府辦公日曆' % '、'.join(str(y) for y in sorted(years))


class DashMissingCalendar(UserError):
    """期間內有年度缺政府辦公日曆；years＝缺的年度（排序）。"""

    def __init__(self, years):
        self.years = sorted(years)
        super().__init__(missing_calendar_message(self.years))


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # 工程例假日（依契約；預設週六、週日，合約 §13-1）
    rest_day_mon = fields.Boolean(string='例假日：週一', default=False)
    rest_day_tue = fields.Boolean(string='例假日：週二', default=False)
    rest_day_wed = fields.Boolean(string='例假日：週三', default=False)
    rest_day_thu = fields.Boolean(string='例假日：週四', default=False)
    rest_day_fri = fields.Boolean(string='例假日：週五', default=False)
    rest_day_sat = fields.Boolean(string='例假日：週六', default=True)
    rest_day_sun = fields.Boolean(string='例假日：週日', default=True)

    def _dash_rest_weekdays(self):
        """例假日的 weekday() 集合。"""
        self.ensure_one()
        return frozenset(i for i, name in enumerate(REST_DAY_FIELDS) if self[name])

    def _dash_calendar(self):
        return self.env['construction.official.calendar']._dash_calendar_index()

    @staticmethod
    def _dash_is_labor_day(day):
        return day.month == LABOR_DAY_MONTH and day.day == LABOR_DAY_DAY

    def _dash_day_is_workday(self, day, rest, index):
        """單日判斷（不查缺年度；呼叫端先查）。"""
        if self._dash_is_labor_day(day):
            return False
        special = index.special.get(day)
        if special == DAY_TYPE_HOLIDAY:
            return False
        if special == DAY_TYPE_MAKEUP:
            return True
        return day.weekday() not in rest

    @staticmethod
    def _dash_missing_years(date_from, date_to, index):
        """期間涵蓋的年度中缺政府辦公日曆的（排序）；起日晚於迄日回空。"""
        if not date_from or not date_to or date_from > date_to:
            return []
        return [y for y in range(date_from.year, date_to.year + 1) if index.year_status(y) == YEAR_MISSING]

    def _dash_year_statuses(self, date_from, date_to, index):
        """期間涵蓋的年度有缺 → DashMissingCalendar；否則回傳預估年度的排序清單。"""
        missing = self._dash_missing_years(date_from, date_to, index)
        if missing:
            raise DashMissingCalendar(missing)
        return [y for y in range(date_from.year, date_to.year + 1) if index.year_status(y) == YEAR_ESTIMATED]

    def _dash_is_workday(self, day, index=None):
        """這一天是不是本工程的工作天。缺年度丟 DashMissingCalendar（UserError）。"""
        self.ensure_one()
        index = index or self._dash_calendar()
        self._dash_year_statuses(day, day, index)
        return self._dash_day_is_workday(day, self._dash_rest_weekdays(), index)

    def _dash_count_workdays(self, date_from, date_to, index=None):
        """date_from 到 date_to 的工作天數（含頭含尾；起日晚於迄日回 0）。缺年度丟 DashMissingCalendar（UserError）。"""
        return self._dash_count_workdays_detail(date_from, date_to, index)[0]

    def _dash_count_workdays_detail(self, date_from, date_to, index=None):
        """回傳 (工作天數, 預估年度清單)。

        算法：先數「不是例假日」的天數（整週＋零頭），再逐一修正期間內的例外日（國定假日、補行上班日、勞動節）
        與基本規則的差。結果與逐日套 _dash_day_is_workday 相同（測試有逐日比對）。
        """
        self.ensure_one()
        if not date_from or not date_to or date_from > date_to:
            return 0, []
        index = index or self._dash_calendar()
        estimated = self._dash_year_statuses(date_from, date_to, index)
        rest = self._dash_rest_weekdays()
        total_days = (date_to - date_from).days + 1
        full_weeks, remainder = divmod(total_days, DAYS_PER_WEEK)
        start_weekday = date_from.weekday()
        count = full_weeks * (DAYS_PER_WEEK - len(rest)) + sum(
            1 for i in range(remainder) if (start_weekday + i) % DAYS_PER_WEEK not in rest)
        exceptions = {d for d in index.special if date_from <= d <= date_to}
        exceptions.update(
            d for d in (date(y, LABOR_DAY_MONTH, LABOR_DAY_DAY) for y in range(date_from.year, date_to.year + 1))
            if date_from <= d <= date_to)
        for day in exceptions:
            count += int(self._dash_day_is_workday(day, rest, index)) - int(day.weekday() not in rest)
        return count, estimated
