# -*- coding: utf-8 -*-
"""日摘要：用台灣時區切「一天」，晚到的讀值要算進去。

**這個測試在防什麼**（2026-10-21 在 odoo18_dev 實查到的兩個錯）
1. 用 UTC 切日：舊寫法拿本地日期字串去比 UTC 的 ts，「10-20」的摘要其實是台灣 10-20 08:00 到 10-21 08:00。
   實例：設備 22 在 09-07 的摘要 43 筆＝UTC 那天的筆數；台灣那天實際 91 筆。
2. 只算一次：每天只算「昨天」，之後才補進來的讀值（斷網續存、缺號補送）永遠不會進摘要。
   實例：設備 23、27 在 10-18 的摘要記 22 筆，實際 144 筆。

讀值的 ts 存的是 UTC。台灣 = UTC+8：台灣 10-20 23:30 = UTC 10-20 15:30，台灣 10-21 00:30 = UTC 10-20 16:30。
"""

from datetime import date

from odoo.tests import common, tagged

from .common import site_vals


@tagged('post_install', '-at_install')
class TestDailyRollup(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        site = cls.env['water.level.site'].create(site_vals(cls.env, '日摘要測試'))
        cls.device = cls.env['water.level.device'].create({
            'name': '日摘要測試站', 'site_id': site.id, 'device_uid': 'TEST-ROLLUP-001'})
        cls.monitor = cls.env['water.level.monitor']

    def _reading(self, utc_ts, value):
        self.env['water.level.reading'].create(
            {'device_id': self.device.id, 'ts': utc_ts, 'value': value})

    def _daily(self, day):
        return self.env['water.level.reading.daily'].search(
            [('device_id', '=', self.device.id), ('day', '=', day)])

    def test_day_boundary_is_taiwan_midnight(self):
        """台灣 23:30 與 00:30 這兩筆，UTC 是同一天，但台灣是兩天。"""
        self._reading('2026-10-20 15:30:00', 1.0)     # 台灣 10-20 23:30
        self._reading('2026-10-20 16:30:00', 3.0)     # 台灣 10-21 00:30

        self.monitor._cron_daily_rollup(today=date(2026, 10, 22))

        self.assertEqual(self._daily(date(2026, 10, 20)).reading_count, 1,
                         '台灣 10-21 凌晨的讀值被算進 10-20——摘要用的是 UTC 日')
        self.assertEqual(self._daily(date(2026, 10, 21)).reading_count, 1)
        self.assertEqual(self._daily(date(2026, 10, 21)).max_value, 3.0)

    def test_late_reading_is_counted(self):
        """摘要算過之後才補進來的讀值，下一次排程要算進去。"""
        self._reading('2026-10-20 02:00:00', 1.0)
        self.monitor._cron_daily_rollup(today=date(2026, 10, 21))
        self.assertEqual(self._daily(date(2026, 10, 20)).reading_count, 1)

        self._reading('2026-10-20 03:00:00', 5.0)     # 隔天才補送進來
        self.monitor._cron_daily_rollup(today=date(2026, 10, 22))

        daily = self._daily(date(2026, 10, 20))
        self.assertEqual(daily.reading_count, 2, '晚到的讀值沒有算進日摘要')
        self.assertEqual(daily.max_value, 5.0)

    def test_window_drops_days_without_readings(self):
        """重算的那幾天裡，若某天已經沒有讀值（維護視窗刪過），舊摘要要跟著消失。"""
        Daily = self.env['water.level.reading.daily']
        Daily.create({'device_id': self.device.id, 'day': '2026-10-19', 'reading_count': 5})

        self.monitor._cron_daily_rollup(today=date(2026, 10, 22))

        self.assertFalse(self._daily(date(2026, 10, 19)))

    def test_retention_audit_counts_taiwan_yesterday(self):
        """保存稽核的「昨天實收幾筆」要與日摘要同一套日界。"""
        self._reading('2026-10-20 15:30:00', 1.0)     # 台灣 10-20 23:30
        self._reading('2026-10-20 16:30:00', 3.0)     # 台灣 10-21 00:30

        self.monitor._cron_retention_audit(today=date(2026, 10, 22))

        check = self.env['water.level.integrity.check'].search(
            [('device_id', '=', self.device.id), ('check_type', '=', 'retention')])
        self.assertEqual(check.checked_count, 1, '稽核量的是 UTC 那一天')
        self.assertEqual(str(check.range_from_ts), '2026-10-20 16:00:00')

    def test_rollup_all_replaces_utc_rows_and_keeps_older_history(self):
        """升級時整個重算：舊的 UTC 日摘要要換掉；但比「現存最早讀值的 UTC 日期」更早的摘要，
        對應的讀值已依保存期清除，是僅存的歷史，不能刪。

        最早一筆刻意放在 UTC 16:30（UTC 10-10、台灣 10-11）：刪除下界用 UTC 日期才會清掉 10-10 的舊列，
        用台灣日期會漏掉、用台灣日期減一天會多刪 10-09。10-10、10-12 都選在「依台灣日沒有讀值」的日子：
        重算不會更新它們，只有刪除會讓它們消失。日期都早於今天：摘要只寫到今天。"""
        self._reading('2026-10-10 16:30:00', 2.0)     # 台灣 10-11 00:30（現存最早一筆）
        self._reading('2026-10-12 16:30:00', 3.0)     # 台灣 10-13 00:30
        Daily = self.env['water.level.reading.daily']
        for day, count in (('2026-10-09', 144), ('2026-10-10', 99), ('2026-10-12', 99)):
            Daily.create({'device_id': self.device.id, 'day': day, 'reading_count': count})

        self.monitor._rollup_all()

        self.assertEqual(self._daily(date(2026, 10, 9)).reading_count, 144,
                         '最早讀值之前的摘要被刪了（那天的讀值已清除）')
        self.assertFalse(self._daily(date(2026, 10, 10)), '最早讀值那天的舊 UTC 摘要還留著')
        self.assertFalse(self._daily(date(2026, 10, 12)), '舊的 UTC 日摘要還留著')
        self.assertEqual(self._daily(date(2026, 10, 11)).reading_count, 1)
        self.assertEqual(self._daily(date(2026, 10, 13)).reading_count, 1)

    def test_rollup_all_keeps_day_before_first_reading(self):
        """最早一筆在 UTC 10:00（UTC 與台灣同一天）：前一天的摘要是已清除讀值的歷史，不能刪。
        跟上一支互補——那支的最早讀值在 UTC 16:30，兩種情況合起來才分得出刪除下界算對沒有。"""
        self._reading('2026-10-10 10:00:00', 2.0)     # 台灣 10-10 18:00（現存最早一筆）
        self.env['water.level.reading.daily'].create(
            {'device_id': self.device.id, 'day': '2026-10-09', 'reading_count': 144})

        self.monitor._rollup_all()

        self.assertEqual(self._daily(date(2026, 10, 9)).reading_count, 144, '最早讀值前一天的歷史被刪了')
        self.assertEqual(self._daily(date(2026, 10, 10)).reading_count, 1)
