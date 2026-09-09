# -*- coding: utf-8 -*-
"""水位監測前台的自訂區間查詢（v2.16.0）。

原始缺口：前台只有 24 小時／7 天／30 天三顆快捷鈕，端點只吃一個 `hours` 整數，
`date_from`/`date_to` 送過去會被完全忽略（送 8/28 的區間仍回最近 24 小時）。

本測試鎖住新的 `_water_level_window()` 的每一條夾擠規則，以及 `_water_level_series()`
的粒度選擇與逐筆列（表格資料）。用 MockRequest 驅動真實 controller 方法，
沿用 test_photo_access.py 的做法。

夾擠規則刻意都「調整後繼續查詢」而不是丟錯：業主看到的是報表不是表單，
但每一次調整都必須回一句 notice，否則會讓人以為看到的是自己輸入的區間。
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers import portal_water_level as pwl
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

TAIPEI = 'Asia/Taipei'
TAIPEI_OFFSET_H = 8


@tagged('post_install', '-at_install', 'construction_portal')
class TestWaterLevelWindow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.env.user.tz = TAIPEI          # 時區換算是本功能最容易錯的一環，明確釘住
        cls.project = cls.env['project.project'].create({'name': '水位測試工程'})
        cls.site = cls.env['water.level.site'].create({
            'name': '水位測試場域',
            'site_type': 'project',
            'project_id': cls.project.id,
        })
        cls.device = cls.env['water.level.device'].create({
            'name': '測試站',
            'site_id': cls.site.id,
            'device_uid': 'TEST-WL-WINDOW-01',
            'level_3': 10.0,
            'level_2': 11.0,
            'level_1': 12.0,
        })
        # 每 10 分鐘一筆，往前鋪 6 小時（37 筆）。水位**隨時間遞增**（越新越高），
        # 這樣「表格最新在前」與「圖表舊到新」兩種排序可以用大小關係直接驗
        cls.base_ts = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        cls.reading_count = 37
        cls.env['water.level.reading'].create([{
            'device_id': cls.device.id,
            'ts': cls.base_ts - timedelta(minutes=10 * i),
            'value': 9.0 + (cls.reading_count - 1 - i) * 0.01,
        } for i in range(cls.reading_count)])

    # ==================== 區間夾擠 ====================

    def test_quick_range_when_no_custom_dates(self):
        """沒給自訂日期就走快捷 hours，行為與改動前一致。"""
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(hours=24)
        self.assertEqual(window['mode'], 'quick')
        self.assertEqual(window['hours'], 24)
        self.assertEqual(window['notice'], '')

    def test_custom_range_is_parsed_in_user_timezone(self):
        """'2026-08-28' + 0 時在台北 = UTC 前一天 16:00。少換一次時區，整張圖就偏 8 小時。"""
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                date_from='2026-08-28', hour_from='0',
                date_to='2026-08-28', hour_to='19')
        self.assertEqual(window['mode'], 'custom')
        self.assertEqual(window['start'], datetime(2026, 8, 27, 16, 0))
        self.assertEqual(window['end'], datetime(2026, 8, 28, 11, 0))
        self.assertEqual(window['hours'], 19)

    def test_reversed_dates_are_swapped_with_notice(self):
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                date_from='2026-08-28', hour_from='19',
                date_to='2026-08-28', hour_to='0')
        self.assertEqual(window['start'], datetime(2026, 8, 27, 16, 0))
        self.assertEqual(window['end'], datetime(2026, 8, 28, 11, 0))
        self.assertTrue(window['notice'], '對調了起訖就一定要說')

    def test_span_over_limit_is_clamped_with_notice(self):
        """跨度上限 30 天。默默截斷比報錯更糟——使用者會以為看到的是完整區間。"""
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                date_from='2026-07-01', hour_from='0',
                date_to='2026-08-15', hour_to='0')
        self.assertEqual(window['hours'], pwl.RANGE_HOURS_MAX)
        self.assertEqual(window['end'] - window['start'],
                         timedelta(hours=pwl.RANGE_HOURS_MAX))
        self.assertIn('30', window['notice'])

    def test_future_end_is_clamped_to_now(self):
        future = (fields.Datetime.now() + timedelta(days=400)).strftime('%Y-%m-%d')
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                date_from=(fields.Datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                hour_from='0', date_to=future, hour_to='0')
        self.assertLessEqual(window['end'], fields.Datetime.now())
        self.assertTrue(window['notice'])

    def test_garbage_input_falls_back_to_quick_range(self):
        """壞掉的查詢條件要退回快捷區間，不能丟例外給業主，也不能把字串往 SQL 送。"""
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                hours=24, date_from="day'); DROP TABLE water_level_reading;--",
                hour_from='99', date_to='', hour_to='x')
        self.assertEqual(window['mode'], 'quick')
        self.assertEqual(window['hours'], 24)

    def test_out_of_range_hour_is_rejected(self):
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                hours=24, date_from='2026-08-28', hour_from='24',
                date_to='2026-08-28', hour_to='0')
        self.assertEqual(window['mode'], 'quick')

    # ==================== 粒度與逐筆列 ====================

    def _series(self, **kw):
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(**kw)
            return self.ctrl._water_level_series(self.device, window)

    def test_short_range_gives_raw_points_newest_first(self):
        series = self._series(hours=24)
        self.assertEqual(series['granularity'], pwl.BUCKET_RAW)
        self.assertEqual(series['stats']['count'], 37)
        self.assertEqual(series['row_total'], 37)
        self.assertFalse(series['row_truncated'])
        # 表格最新在最上面：現場的人先看到的應該是「現在多高」
        self.assertGreater(series['rows'][0][1], series['rows'][-1][1])
        # 圖表仍是舊到新（Chart.js 的 x 軸）
        self.assertLess(series['values'][0], series['values'][-1])

    def test_long_range_switches_to_buckets(self):
        series = self._series(hours=25)
        self.assertEqual(series['granularity'], pwl.BUCKET_HOUR)
        series = self._series(hours=pwl.HOUR_BUCKET_LIMIT + 1)
        self.assertEqual(series['granularity'], pwl.BUCKET_DAY)

    def test_too_many_raw_points_degrade_to_hourly(self):
        """每分鐘上報的設備 24 小時就 1440 點，手機吃不消，要自動降一級。"""
        with patch.object(pwl, 'RAW_POINT_LIMIT', 5):
            series = self._series(hours=24)
        self.assertEqual(series['granularity'], pwl.BUCKET_HOUR)

    def test_table_rows_are_capped_but_total_is_honest(self):
        """表格截斷時，筆數不能跟著縮水——那會讓人以為區間內只有這麼多資料。"""
        with patch.object(pwl, 'TABLE_ROW_LIMIT', 10):
            series = self._series(hours=24)
        self.assertEqual(len(series['rows']), 10)
        self.assertTrue(series['row_truncated'])
        self.assertEqual(series['raw_total'], 37)

    def test_stats_come_from_raw_values_not_buckets(self):
        """分桶取的是每桶最大值，拿分桶結果算平均會比真實平均高。"""
        series = self._series(hours=25)
        self.assertEqual(series['granularity'], pwl.BUCKET_HOUR)
        self.assertEqual(series['stats']['count'], 37)
        self.assertAlmostEqual(series['stats']['max'], 9.36, places=2)
        self.assertAlmostEqual(series['stats']['min'], 9.0, places=2)

    def test_empty_range_returns_empty_series_without_crashing(self):
        series = self._series(date_from='2020-01-01', hour_from='0',
                              date_to='2020-01-02', hour_to='0')
        self.assertEqual(series['values'], [])
        self.assertEqual(series['rows'], [])
        self.assertEqual(series['stats']['count'], 0)
        self.assertIsNone(series['stats']['max'])

    # ==================== 匯出 ====================

    def test_export_filename_marks_demo_and_strips_path_chars(self):
        """匯出檔會離開頁面單獨流傳，示範資料的標示要跟著檔名走。"""
        self.device.is_demo = True
        self.device.name = 'A/B:站*名'
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(
                date_from='2026-08-28', hour_from='0',
                date_to='2026-08-28', hour_to='19')
            name = self.ctrl._water_level_export_filename(self.device, window)
        self.assertTrue(name.startswith('示範資料_水位_'))
        self.assertNotIn('/', name)
        self.assertNotIn(':', name)
        self.assertIn('202608280000-202608281900', name)

    def test_export_rows_are_raw_and_time_ordered(self):
        """匯出一律原始逐筆（表格截斷的解方就是它），而且是舊到新，方便直接畫圖。"""
        with MockRequest(self.env):
            window = self.ctrl._water_level_window(hours=24)
            rows, truncated = self.ctrl._water_level_export_rows(self.device, window)
        self.assertEqual(len(rows), 37)
        self.assertFalse(truncated)
        self.assertLess(rows[0][0], rows[-1][0])

    def test_export_rows_flag_truncation(self):
        with patch.object(pwl, 'EXPORT_ROW_LIMIT', 5):
            with MockRequest(self.env):
                window = self.ctrl._water_level_window(hours=24)
                rows, truncated = self.ctrl._water_level_export_rows(self.device, window)
        self.assertEqual(len(rows), 5)
        self.assertTrue(truncated)
