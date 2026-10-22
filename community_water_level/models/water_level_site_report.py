# -*- coding: utf-8 -*-
"""社區的讀值彙總：前台 CSV（日彙總）與週期報表（週／月／季／半年／年）共用。

* 一律以**台灣時區**切日、切期間（core 的日摘要是 UTC 日、晚到的讀值也不重算，不用它）
* 設備一律含停用的：core 規定設備要搬就「停用、另建一台」，只看在用的設備，換過表之後舊的歷史就從合規報表消失
* 依「現在」的池歸屬列設備——換池的歷史不追溯（設備的 tank_id 有 tracking，日後要追溯從 chatter 還原）
* 統計一律在資料庫裡算（一年每分鐘一筆＝五十多萬筆，不搬進 Python）
"""

from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

from odoo.addons.community_water_level.utils import FULL_STAMP_FORMAT, LOCAL_TZ_NAME, local_stamp, to_utc_naive

PERIOD_WEEK = 'week'
PERIOD_MONTH = 'month'
PERIOD_QUARTER = 'quarter'
PERIOD_HALF = 'half'
PERIOD_YEAR = 'year'
PERIOD_LABELS = {PERIOD_WEEK: '週報', PERIOD_MONTH: '月報', PERIOD_QUARTER: '季報',
                 PERIOD_HALF: '半年報', PERIOD_YEAR: '年報'}
MONTHS_PER_QUARTER = 3
MONTHS_PER_HALF = 6
DAYS_PER_WEEK = 7
PERCENT_FULL = 100.0
SECONDS_PER_MINUTE = 60


class WaterLevelSiteReport(models.Model):
    _inherit = 'water.level.site'

    # ==================== 期間 ====================

    @api.model
    def _community_period_bounds(self, period, anchor):
        """含 `anchor`（台灣日期）的那一期：(期初日, 下一期期初日, 期初 UTC, 下一期期初 UTC)。期末是開區間。"""
        if period == PERIOD_WEEK:
            start = anchor - timedelta(days=anchor.weekday())          # 週一起算
            end = start + timedelta(days=DAYS_PER_WEEK)
        elif period == PERIOD_MONTH:
            start = anchor.replace(day=1)
            end = start + relativedelta(months=1)
        elif period == PERIOD_QUARTER:
            start = date(anchor.year, (anchor.month - 1) // MONTHS_PER_QUARTER * MONTHS_PER_QUARTER + 1, 1)
            end = start + relativedelta(months=MONTHS_PER_QUARTER)
        elif period == PERIOD_HALF:
            start = date(anchor.year, 1 if anchor.month <= MONTHS_PER_HALF else MONTHS_PER_HALF + 1, 1)
            end = start + relativedelta(months=MONTHS_PER_HALF)
        elif period == PERIOD_YEAR:
            start = date(anchor.year, 1, 1)
            end = date(anchor.year + 1, 1, 1)
        else:
            raise ValueError('unknown period %r' % period)
        return (start, end, to_utc_naive(datetime.combine(start, time.min)),
                to_utc_naive(datetime.combine(end, time.min)))

    @api.model
    def _community_period_label(self, period, start, end):
        last = end - timedelta(days=1)
        if period == PERIOD_WEEK:
            return _('%(start)s～%(end)s 週報', start=start.strftime('%Y-%m-%d'), end=last.strftime('%m-%d'))
        if period == PERIOD_MONTH:
            return _('%(y)s 年 %(m)s 月 月報', y=start.year, m=start.month)
        if period == PERIOD_QUARTER:
            return _('%(y)s 年第 %(q)s 季 季報', y=start.year, q=(start.month - 1) // MONTHS_PER_QUARTER + 1)
        if period == PERIOD_HALF:
            return _('%(y)s 年%(h)s 半年報', y=start.year, h=_('上') if start.month == 1 else _('下'))
        return _('%(y)s 年 年報', y=start.year)

    # ==================== 彙總（SQL） ====================

    def _community_report_devices(self):
        """這個社區的設備，含停用的；依池、名稱排。"""
        self.ensure_one()
        return self.env['water.level.device'].sudo().with_context(active_test=False).search(
            [('site_id', '=', self.id)], order='tank_id, name, id')

    @api.model
    def _community_daily_rows(self, devices, start_utc, end_utc):
        """每台設備每個**台灣日**的筆數／最高／最低／平均水位。[start_utc, end_utc)。"""
        if not devices:
            return []
        self.env.cr.execute(
            """
            SELECT device_id,
                   ((ts AT TIME ZONE 'UTC') AT TIME ZONE %s)::date AS day,
                   count(*), max(value), min(value), avg(value)
              FROM water_level_reading
             WHERE device_id IN %s AND ts >= %s AND ts < %s
             GROUP BY device_id, day
             ORDER BY device_id, day
            """,
            (LOCAL_TZ_NAME, tuple(devices.ids), start_utc, end_utc))
        return [{'device_id': row[0], 'day': row[1], 'count': row[2],
                 'max': float(row[3]), 'min': float(row[4]), 'avg': float(row[5])}
                for row in self.env.cr.fetchall()]

    def _community_device_stats(self, device, start_utc, end_utc, now):
        cr = self.env.cr
        cr.execute(
            """SELECT count(*), max(value), min(value), avg(value) FROM water_level_reading
                WHERE device_id = %s AND ts >= %s AND ts < %s""",
            (device.id, start_utc, end_utc))
        count, high, low, mean = cr.fetchone()
        tank = device.tank_id
        capacity = tank._capacity() if tank else 0.0

        def fill(level):
            if level is None or not capacity:
                return None
            return tank._volume_at(float(level)) / capacity * PERCENT_FULL

        return {
            'name': device.name,
            'inactive': not device.active,
            'count': count,
            'max': float(high) if high is not None else None,
            'min': float(low) if low is not None else None,
            'avg': float(mean) if mean is not None else None,
            # 「最高水位時的儲水率」：容量曲線不保證單調，最高水位的儲水率不一定等於最高儲水率——欄名照實寫
            'max_fill': fill(high),
            'min_fill': fill(low),
            'completeness': self._community_completeness(device, start_utc, end_utc, now),
            'gaps': self._community_gap_count(device, start_utc, end_utc),
        }

    def _community_completeness(self, device, start_utc, end_utc, now):
        """資料完整率（%）：期間內**有讀值的時間格數** ÷ 應收格數，封頂 100。

        格＝設備的回報間隔（`expected_interval_min`，以目前設定計算、沒有歷史）。
        應收從 max(期初, 這台的第一筆讀值) 到 min(期末, 現在)——設備還沒裝之前、期間還沒到的部分不算缺。
        比回報間隔密的設備，一格裡多筆只算一格，所以不會超過 100%；應收 ≤ 0 回 None（無法計算，不是 0%）。
        """
        cr = self.env.cr
        cr.execute('SELECT min(ts) FROM water_level_reading WHERE device_id = %s', (device.id,))
        first = cr.fetchone()[0]
        interval_sec = max(device.expected_interval_min or 1, 1) * SECONDS_PER_MINUTE
        begin = max(start_utc, first) if first else None
        finish = min(end_utc, now)
        if not begin or finish <= begin:
            return None
        expected = int((finish - begin).total_seconds() // interval_sec)
        if expected <= 0:
            return None
        cr.execute(
            """SELECT count(DISTINCT floor(extract(epoch FROM ts) / %s)) FROM water_level_reading
                WHERE device_id = %s AND ts >= %s AND ts < %s""",
            (interval_sec, device.id, begin, finish))
        actual = cr.fetchone()[0]
        return min(PERCENT_FULL, actual / expected * PERCENT_FULL)

    def _community_gap_count(self, device, start_utc, end_utc):
        """期間內開始的缺口數。序號缺口沒有時間欄位，用缺口前一筆讀值的時間放進期間；兩者都沒有的放不進任何期間。"""
        self.env.cr.execute(
            """
            SELECT count(*)
              FROM water_level_gap g
              LEFT JOIN water_level_reading r ON r.device_id = g.device_id AND r.seq_no = g.seq_from - 1
             WHERE g.device_id = %s AND COALESCE(g.ts_from, r.ts) >= %s AND COALESCE(g.ts_from, r.ts) < %s
            """,
            (device.id, start_utc, end_utc))
        return self.env.cr.fetchone()[0]

    # ==================== 週期報表 ====================

    def _community_period_stats(self, period, anchor):
        """報表要印的全部數字（給 QWeb 用的 dict，不帶 recordset 以外的東西）。"""
        self.ensure_one()
        start, end, start_utc, end_utc = self._community_period_bounds(period, anchor)
        now = fields.Datetime.now()
        devices = self._community_report_devices()
        tanks = {}
        for device in devices:
            key = device.tank_id.id or 0
            group = tanks.setdefault(key, {'name': device.tank_id.name or _('未指定蓄水池'), 'devices': []})
            group['devices'].append(self._community_device_stats(device, start_utc, end_utc, now))
        events = self.env['water.level.event'].sudo().search([
            ('site_id', '=', self.id), ('start_ts', '<', end_utc),
            '|', ('end_ts', '=', False), ('end_ts', '>=', start_utc)], order='start_ts')
        labels = self.env['water.level.event']._fields
        type_labels = dict(labels['event_type'].selection)
        severity_labels = dict(labels['severity'].selection)
        return {
            'site_name': self.name,
            # 示範資料要在報表最上面講清楚（core 的事件報表同一條規則）
            'is_demo': bool(self.is_demo or any(devices.mapped('is_demo'))),
            'period': period,
            'title': self._community_period_label(period, start, end),
            'range_text': '%s ～ %s' % (start.strftime('%Y-%m-%d'), (end - timedelta(days=1)).strftime('%Y-%m-%d')),
            'generated_at': local_stamp(now, FULL_STAMP_FORMAT),
            'tanks': [tanks[key] for key in sorted(tanks, key=lambda k: (k == 0, k))],
            'events': [{
                'name': ev.name,
                'type': type_labels.get(ev.event_type, ev.event_type),
                'severity': severity_labels.get(ev.severity, ev.severity),
                'tank': ev.tank_id.name or '',
                'start': local_stamp(ev.start_ts, FULL_STAMP_FORMAT),
                'end': local_stamp(ev.end_ts, FULL_STAMP_FORMAT) if ev.end_ts else _('尚未結束'),
                'ack': ('%s（%s）' % (ev.ack_user_id.name, local_stamp(ev.ack_at, FULL_STAMP_FORMAT))
                        if ev.ack_user_id else _('未簽收')),
            } for ev in events],
        }
