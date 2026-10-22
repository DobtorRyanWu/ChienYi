# -*- coding: utf-8 -*-
"""讀值 CSV 與週期報表：時間一律以台灣時區切日、切期間。

邊界要測在「UTC 與台灣不同一天」的那一側：台灣 00:00–07:59 在 UTC 是前一天（UTC 16:00–23:59），
用 UTC 切日的錯只會在這段現形；台灣 23:30（UTC 15:30）兩邊同一天，測了也抓不到（抗辯時抓到計畫寫錯）。
"""

import csv
import io
from datetime import date, datetime, timedelta

from freezegun import freeze_time

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.community_water_level.utils import local_today

PASSWORD = 'cw-reports-Pass-2026'
BOM = '﻿'


def _site_with_tank(env, name, **site_vals):
    owner = env['res.partner'].create({'name': '%s（管委會）' % name})
    site = env['water.level.site'].create(dict({'name': name, 'site_type': 'community',
                                                'owner_partner_id': owner.id}, **site_vals))
    tank = env['water.level.tank'].create({'name': '%s 一號池' % name, 'site_id': site.id, 'bottom_elevation': 0.0,
                                           'full_elevation': 2.0, 'effective_volume_m3': 20.0})
    return site, tank


def _device(env, site, tank, uid, **vals):
    return env['water.level.device'].create(dict({'name': uid, 'device_uid': uid, 'site_id': site.id,
                                                  'tank_id': tank.id}, **vals))


def _readings(env, device, stamps, value=1.0):
    env['water.level.reading'].create([{'device_id': device.id, 'ts': ts, 'value': value, 'raw_value': value}
                                       for ts in stamps])


@tagged('post_install', '-at_install')
class TestCommunityPeriods(TransactionCase):

    def test_period_bounds_in_taiwan_time(self):
        Site = self.env['water.level.site']
        wed = date(2026, 10, 21)
        self.assertEqual(Site._community_period_bounds('week', wed)[:2], (date(2026, 10, 19), date(2026, 10, 26)), '週一起算')
        self.assertEqual(Site._community_period_bounds('month', wed)[:2], (date(2026, 10, 1), date(2026, 11, 1)))
        self.assertEqual(Site._community_period_bounds('quarter', wed)[:2], (date(2026, 10, 1), date(2027, 1, 1)))
        self.assertEqual(Site._community_period_bounds('half', date(2026, 6, 30))[:2], (date(2026, 1, 1), date(2026, 7, 1)))
        self.assertEqual(Site._community_period_bounds('half', date(2026, 7, 1))[:2], (date(2026, 7, 1), date(2027, 1, 1)))
        self.assertEqual(Site._community_period_bounds('year', wed)[:2], (date(2026, 1, 1), date(2027, 1, 1)))
        _start, _end, start_utc, end_utc = Site._community_period_bounds('week', wed)
        self.assertEqual(start_utc, datetime(2026, 10, 18, 16, 0), '台灣週一 00:00＝UTC 前一天 16:00')
        self.assertEqual(end_utc, datetime(2026, 10, 25, 16, 0))

    @freeze_time('2026-10-20 17:00:00')
    def test_today_is_taiwan_today(self):
        """UTC 10-20 17:00＝台灣 10-21 01:00：「今天」要是 21 號，不能落到上一天（或上一期）。"""
        self.assertEqual(local_today(), date(2026, 10, 21))

    @freeze_time('2026-11-02 00:00:00')
    def test_week_stats_split_at_taiwan_midnight(self):
        site, tank = _site_with_tank(self.env, '週報社區')
        device = _device(self.env, site, tank, 'RPT-WEEK')
        _readings(self.env, device, [
            datetime(2026, 10, 18, 15, 59, 59),   # 台灣 10-18（日）23:59:59 → 上一週
            datetime(2026, 10, 18, 16, 0, 0),     # 台灣 10-19（一）00:00:00 → 這一週
            datetime(2026, 10, 18, 23, 59, 59),   # 台灣 10-19（一）07:59:59 → 這一週（UTC 還是 18 號）
            datetime(2026, 10, 25, 15, 59, 59),   # 台灣 10-25（日）23:59:59 → 這一週最後一秒
            datetime(2026, 10, 25, 16, 0, 0),     # 台灣 10-26（一）00:00 → 下一週
        ])
        stats = site._community_period_stats('week', date(2026, 10, 21))
        row = stats['tanks'][0]['devices'][0]
        self.assertEqual(row['count'], 3)
        days = {d['day']: d['count'] for d in site._community_daily_rows(device, datetime(2026, 10, 18, 16), datetime(2026, 10, 25, 16))}
        self.assertEqual(days, {date(2026, 10, 19): 2, date(2026, 10, 25): 1}, '台灣 07:59 的讀值算台灣那一天')

    @freeze_time('2026-11-02 00:00:00')
    def test_completeness_counts_from_the_first_reading_and_is_capped(self):
        site, tank = _site_with_tank(self.env, '完整率社區')
        start = datetime(2026, 10, 19, 16, 0)     # 台灣 10-20 00:00（期初後一天才開始有資料）
        sparse = _device(self.env, site, tank, 'RPT-SPARSE', expected_interval_min=10)
        _readings(self.env, sparse, [start + timedelta(minutes=10 * i) for i in range(144)])   # 只有一天
        dense = _device(self.env, site, tank, 'RPT-DENSE', expected_interval_min=10)
        # 比應收密、而且起點不在整格上：第一筆 16:05 → 應收 863 格，實收落在 864 個格子裡（不封頂會是 100.1%）
        _readings(self.env, dense, [start + timedelta(minutes=5 + 5 * i) for i in range(6 * 24 * 12 - 1)])
        late = _device(self.env, site, tank, 'RPT-LATE', expected_interval_min=10)
        _readings(self.env, late, [datetime(2026, 10, 30, 0, 0)])  # 第一筆在期末之後
        rows = {r['name']: r for r in site._community_period_stats('week', date(2026, 10, 21))['tanks'][0]['devices']}
        # 應收＝台灣 10-20 00:00 到 10-26 00:00＝6 天 × 144 格
        self.assertAlmostEqual(rows['RPT-SPARSE']['completeness'], 144 / (6 * 144) * 100, places=1)
        self.assertEqual(rows['RPT-DENSE']['completeness'], 100.0, '比回報間隔密不能超過 100%')
        self.assertIsNone(rows['RPT-LATE']['completeness'], '期間內還沒開始收資料＝無法計算，不是 0%')

    @freeze_time('2026-11-02 00:00:00')
    def test_archived_device_and_long_running_event_and_seq_gap_are_included(self):
        site, tank = _site_with_tank(self.env, '歷史社區')
        old = _device(self.env, site, tank, 'RPT-OLD')
        _readings(self.env, old, [datetime(2026, 10, 20, 1, 0)])
        old.active = False
        live = _device(self.env, site, tank, 'RPT-LIVE')
        Event = self.env['water.level.event']
        running = Event.create({'device_id': live.id, 'event_type': 'level_high', 'start_ts': datetime(2026, 9, 30, 0, 0)})
        ended = Event.create({'device_id': live.id, 'event_type': 'level_low', 'start_ts': datetime(2026, 9, 1, 0, 0),
                              'end_ts': datetime(2026, 9, 2, 0, 0)})
        self.env['water.level.reading'].create([
            {'device_id': live.id, 'ts': datetime(2026, 10, 20, 2, 0), 'value': 1.0, 'raw_value': 1.0, 'seq_no': 10},
            {'device_id': live.id, 'ts': datetime(2026, 10, 20, 3, 0), 'value': 1.0, 'raw_value': 1.0, 'seq_no': 15}])
        self.env['water.level.gap'].create({'device_id': live.id, 'gap_type': 'seq', 'seq_from': 11, 'seq_to': 14})
        stats = site._community_period_stats('month', date(2026, 10, 21))
        names = [r['name'] for r in stats['tanks'][0]['devices']]
        self.assertIn('RPT-OLD', names, '停用的設備的歷史也要在報表上（合規匯出不能少一段）')
        event_names = [e['name'] for e in stats['events']]
        self.assertIn(running.name, event_names, '月初前開始、還沒結束的事件要出現在月報')
        self.assertNotIn(ended.name, event_names)
        live_row = next(r for r in stats['tanks'][0]['devices'] if r['name'] == 'RPT-LIVE')
        self.assertEqual(live_row['gaps'], 1, '序號缺口沒有時間欄位，要用前一筆讀值的時間放進期間')


@tagged('post_install', '-at_install')
class TestCommunityCsv(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = new_test_user(cls.env, login='cw_csv_member', password=PASSWORD, groups='base.group_portal')
        cls.outsider = new_test_user(cls.env, login='cw_csv_out', password=PASSWORD, groups='base.group_portal')
        cls.site, cls.tank = _site_with_tank(cls.env, 'CSV 社區', member_user_ids=[(6, 0, [cls.member.id])])
        cls.other_site, cls.other_tank = _site_with_tank(cls.env, 'CSV 別社區')
        cls.device = _device(cls.env, cls.site, cls.tank, 'CSV-LIVE')
        _readings(cls.env, cls.device, [datetime(2026, 10, 19, 23, 30)], value=1.5)   # 台灣 10-20 07:30
        cls.old = _device(cls.env, cls.site, cls.tank, 'CSV-OLD')
        _readings(cls.env, cls.old, [datetime(2026, 10, 19, 1, 0)], value=0.5)
        cls.old.active = False

    def _csv(self, user, **params):
        self.authenticate(user.login, PASSWORD)
        query = '&'.join('%s=%s' % kv for kv in params.items())
        return self.url_open('/community/%s/reports/readings.csv?%s' % (self.site.id, query))

    def test_raw_csv_has_bom_taiwan_time_and_archived_devices(self):
        res = self._csv(self.member, kind='raw', **{'from': '2026-10-19', 'to': '2026-10-20'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.headers['Content-Type'])
        text = res.content.decode('utf-8')
        self.assertTrue(text.startswith(BOM), 'Excel 要有 BOM 才認得 UTF-8')
        rows = list(csv.reader(io.StringIO(text[len(BOM):])))
        body = [r for r in rows[1:] if r]
        stamps = {r[2]: r[0] for r in body}
        self.assertEqual(stamps.get('CSV-LIVE'), '2026-10-20 07:30:00', 'UTC 10-19 23:30＝台灣 10-20 07:30')
        self.assertTrue(any(r[2].startswith('CSV-OLD') for r in body), '停用的設備的讀值也要匯出')

    def test_daily_csv_groups_by_taiwan_day(self):
        res = self._csv(self.member, kind='daily', **{'from': '2026-10-19', 'to': '2026-10-20'})
        body = [r for r in csv.reader(io.StringIO(res.content.decode('utf-8')[len(BOM):]))][1:]
        live = [r for r in body if r and r[2] == 'CSV-LIVE']
        self.assertEqual([r[0] for r in live], ['2026-10-20'], '台灣 07:30 的讀值算 20 號，不是 UTC 的 19 號')

    def test_bad_requests_are_refused_not_truncated(self):
        cases = {
            '期間超過上限': {'kind': 'raw', 'from': '2026-01-01', 'to': '2026-10-20'},
            '別社區的池': {'kind': 'raw', 'from': '2026-10-19', 'to': '2026-10-20', 'tank': self.other_tank.id},
            '起訖顛倒': {'kind': 'raw', 'from': '2026-10-20', 'to': '2026-10-19'},
            '日期格式錯': {'kind': 'raw', 'from': 'abc', 'to': '2026-10-19'},
            '結束日在未來很遠': {'kind': 'daily', 'from': '2026-10-19', 'to': '9999-12-31'},
            # 下面兩個期間長度都合法，只有「在未來」這一條擋得到（上面那個會先被期間上限擋下，測不到它）
            '迄日是明天': {'kind': 'daily', 'from': local_today().isoformat(),
                         'to': (local_today() + timedelta(days=1)).isoformat()},
            '遠未來兩天': {'kind': 'daily', 'from': '9999-12-30', 'to': '9999-12-31'},
        }
        for label, params in cases.items():
            res = self._csv(self.member, **params)
            self.assertNotIn('text/csv', res.headers.get('Content-Type', ''), '%s：不能照樣給檔案' % label)
            self.assertNotEqual(res.status_code, 500, '%s：不能 500' % label)

    def test_outsider_gets_no_csv(self):
        res = self._csv(self.outsider, kind='raw', **{'from': '2026-10-19', 'to': '2026-10-20'})
        self.assertNotIn('text/csv', res.headers.get('Content-Type', ''))
        self.assertNotIn('CSV-LIVE', res.text)

    def test_period_pdf_route_renders_for_member_only(self):
        self.authenticate(self.member.login, PASSWORD)
        res = self.url_open('/community/%s/reports/period.pdf?period=week&date=2026-10-21' % self.site.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn('CSV-LIVE', res.text, '測試模式下回 HTML；真的 PDF 在 E2E 打開看')
        self.authenticate(self.outsider.login, PASSWORD)
        res = self.url_open('/community/%s/reports/period.pdf?period=week&date=2026-10-21' % self.site.id)
        self.assertEqual(res.status_code, 404)
