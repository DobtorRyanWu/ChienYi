# -*- coding: utf-8 -*-
"""工作天與政府辦公日曆（合約 §4、§10 B 列）。

期望值由測試獨立寫出（日曆官方內容、逐日判斷的參考實作），不 import 實作的常數，常數或算法寫錯才測得出來。
年度狀態（未公告＝晚於已有資料的最後一年且不早於今年）跟「今天」有關，相關測試把時間凍結在 2026-11-05。
"""
from datetime import date, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

# 凍結時間：UTC 04:00＝台灣 2026-11-05（週四）12:00
FROZEN_NOW = '2026-11-05 04:00:00'
FROZEN_TODAY = date(2026, 11, 5)
# 官方資料涵蓋的年度（民國 106–116）與各年國定假日／補行上班日筆數（轉檔時由原始檔算出、人工抽查過）
EXPECT_YEARS = {
    2017: (17, 3), 2018: (15, 2), 2019: (14, 3), 2020: (18, 3), 2021: (19, 2), 2022: (13, 1),
    2023: (20, 6), 2024: (14, 1), 2025: (18, 1), 2026: (22, 0), 2027: (24, 0),
}
SAT, SUN = 5, 6


def oracle_is_workday(day, rest_weekdays, special):
    """參考實作：逐日套合約 §4 的優先序（勞動節／國定假日 → 否；補行上班日 → 是；其他依例假日）。"""
    if (day.month, day.day) == (5, 1):
        return False
    kind = special.get(day)
    if kind == 'holiday':
        return False
    if kind == 'makeup_workday':
        return True
    return day.weekday() not in rest_weekdays


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestWorkday(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project']
        cls.p_default = Project.create({'name': 'DASH-WD 預設例假日', 'code': 'DASH-WD1', 'project_type': 'general'})
        cls.p_sunday = Project.create({'name': 'DASH-WD 只休週日', 'code': 'DASH-WD2', 'project_type': 'general',
                                       'rest_day_sat': False})
        cls.special = {r.date: r.day_type for r in cls.env['construction.official.calendar'].search([])}

    # ── 資料 ────────────────────────────────────────────────────────────
    def test_calendar_years_and_counts(self):
        """有資料的年度恰好是 2017–2027（2015、2016 平台上沒有），各年兩種例外日筆數與轉檔結果相同。"""
        years = self.env['construction.official.calendar.year'].search([])
        self.assertEqual({y.year: (y.holiday_count, y.makeup_count) for y in years}, EXPECT_YEARS)
        for year, (holidays, makeups) in EXPECT_YEARS.items():
            in_year = {d: t for d, t in self.special.items() if d.year == year}
            self.assertEqual(sum(1 for t in in_year.values() if t == 'holiday'), holidays, year)
            self.assertEqual(sum(1 for t in in_year.values() if t == 'makeup_workday'), makeups, year)
        self.assertFalse([d for d in self.special if d.year < 2017 or d.year > 2027])
        self.assertTrue(all(y.source_url and len(y.source_sha256) == 64 for y in years), '每年都要記來源網址與雜湊')

    def test_default_rest_days(self):
        """預設例假日＝週六、週日（合約 §13-1）。"""
        self.assertEqual(self.p_default._dash_rest_weekdays(), frozenset({SAT, SUN}))
        self.assertEqual(self.p_sunday._dash_rest_weekdays(), frozenset({SUN}))

    # ── 單日 ────────────────────────────────────────────────────────────
    def test_national_holiday(self):
        """國定假日不是工作天（2026-02-17 週二春節）；前後的一般週二是。"""
        self.assertEqual(self.special.get(date(2026, 2, 17)), 'holiday')
        self.assertFalse(self.p_default._dash_is_workday(date(2026, 2, 17)))
        self.assertTrue(self.p_default._dash_is_workday(date(2026, 3, 3)))

    def test_makeup_workday_on_rest_day(self):
        """補行上班日落在例假日（2025-02-08 週六）算工作天；一般週六不算。"""
        self.assertEqual(self.special.get(date(2025, 2, 8)), 'makeup_workday')
        self.assertTrue(self.p_default._dash_is_workday(date(2025, 2, 8)))
        self.assertFalse(self.p_default._dash_is_workday(date(2025, 2, 15)))

    def test_sunday_only_project(self):
        """只休週日的工程：一般週六是工作天；週六的國定假日（2025-05-31 端午節）不是；週日照休。"""
        saturday = date(2025, 11, 8)
        self.assertTrue(self.p_sunday._dash_is_workday(saturday))
        self.assertFalse(self.p_default._dash_is_workday(saturday))
        self.assertEqual(self.special.get(date(2025, 5, 31)), 'holiday')
        self.assertFalse(self.p_sunday._dash_is_workday(date(2025, 5, 31)))
        self.assertFalse(self.p_sunday._dash_is_workday(date(2025, 11, 9)))

    def test_labor_day_never_workday(self):
        """勞動節一律不算工作天，含 2025 年以前日曆標上班的（日曆裡沒有那天，靠程式規則）與未公告年度。"""
        for day in (date(2017, 5, 1), date(2019, 5, 1), date(2024, 5, 1), date(2025, 5, 1)):
            self.assertNotIn(day, self.special, f'{day}：日曆標上班，不在例外日裡')
            self.assertLess(day.weekday(), SAT, f'{day} 是平日，否則測不到')
            self.assertFalse(self.p_default._dash_is_workday(day), day)
            self.assertFalse(self.p_sunday._dash_is_workday(day), day)
        self.assertEqual(self.special.get(date(2026, 5, 1)), 'holiday', '2026 起日曆本身就放假')
        self.assertFalse(self.p_default._dash_is_workday(date(2026, 5, 1)))
        # 2021-05-01 是週六：只休週日的工程那天也不上工
        self.assertFalse(self.p_sunday._dash_is_workday(date(2021, 5, 1)))
        with freeze_time(FROZEN_NOW):
            self.assertFalse(self.p_default._dash_is_workday(date(2028, 5, 1)), '未公告年度也排除勞動節')
            self.assertEqual(self.p_default._dash_count_workdays(date(2025, 4, 28), date(2025, 5, 2)), 4)

    # ── 期間 ────────────────────────────────────────────────────────────
    def test_count_matches_day_by_day_oracle(self):
        """整週＋零頭的算法＝逐日參考實作（2017–2027 全期間、多種例假日組合、各種起訖日）。"""
        projects = [self.p_default, self.p_sunday, self.env['project.project'].create({
            'name': 'DASH-WD 休二四', 'code': 'DASH-WD3', 'project_type': 'general',
            'rest_day_sat': False, 'rest_day_sun': False, 'rest_day_tue': True, 'rest_day_thu': True})]
        ranges = [(date(2017, 1, 1), date(2027, 12, 31)), (date(2023, 1, 5), date(2023, 2, 20)),
                  (date(2025, 4, 30), date(2025, 5, 1)), (date(2026, 11, 4), date(2026, 11, 5)),
                  (date(2019, 12, 30), date(2020, 1, 3))]
        index = self.env['construction.official.calendar']._dash_calendar_index()
        for project in projects:
            rest = project._dash_rest_weekdays()
            for start, end in ranges:
                days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
                expected = sum(1 for day in days if oracle_is_workday(day, rest, self.special))
                self.assertGreater(expected, 0, (project.name, start, end))
                self.assertEqual(project._dash_count_workdays(start, end), expected, (project.name, start, end))
                single = sum(1 for day in days if project._dash_is_workday(day, index))
                self.assertEqual(single, expected, '單日判斷與期間計數一致')
        self.assertEqual(self.p_default._dash_count_workdays(date(2026, 1, 2), date(2026, 1, 1)), 0, '起日晚於迄日')

    def test_missing_year_2015(self):
        """缺年度（2015、2016 平台上沒有）→ 大聲失敗「缺 YYYY 年政府辦公日曆」，不推算。"""
        with self.assertRaises(UserError) as cm:
            self.p_default._dash_is_workday(date(2015, 6, 1))
        self.assertEqual(cm.exception.args[0], '缺 2015 年政府辦公日曆')
        with self.assertRaises(UserError) as cm:
            self.p_default._dash_count_workdays(date(2015, 4, 2), date(2017, 1, 10))
        self.assertEqual(cm.exception.args[0], '缺 2015、2016 年政府辦公日曆')

    @freeze_time(FROZEN_NOW)
    def test_unannounced_future_year_estimated(self):
        """尚未公告的未來年度（2028）依例假日推算並回報為預估；已公告年度不算預估。"""
        count, estimated = self.p_default._dash_count_workdays_detail(date(2028, 1, 1), date(2028, 1, 31))
        self.assertEqual(estimated, [2028])
        # 2028-01：例假日以外 21 天，扣掉不了任何國定假日（沒有資料）
        self.assertEqual(count, sum(1 for i in range(31) if date(2028, 1, 1 + i).weekday() < SAT))
        _count, estimated = self.p_default._dash_count_workdays_detail(date(2027, 1, 1), date(2027, 1, 31))
        self.assertEqual(estimated, [])

    @freeze_time('2030-03-01 04:00:00')
    def test_past_year_without_data_is_missing_not_estimated(self):
        """今天是 2030 而 2028 沒資料：2028 早於今年，是缺資料（不是「還沒公告」）。"""
        with self.assertRaises(UserError) as cm:
            self.p_default._dash_count_workdays(date(2027, 12, 1), date(2028, 1, 31))
        self.assertEqual(cm.exception.args[0], '缺 2028 年政府辦公日曆')

    def test_incomplete_year_treated_as_missing(self):
        """某年例外日筆數與年度表宣告不符（資料被刪了一筆）→ 該年度當缺，不靜默少扣一天。"""
        self.env['construction.official.calendar'].search([('date', '=', date(2026, 2, 17))]).unlink()
        with self.assertLogs('odoo.addons.construction_company_dashboard.models.official_calendar', 'ERROR') as logs, \
                self.assertRaises(UserError) as cm:
            self.p_default._dash_is_workday(date(2026, 2, 17))
        self.assertEqual(cm.exception.args[0], '缺 2026 年政府辦公日曆')
        self.assertIn('2026 年不完整', logs.output[0])
