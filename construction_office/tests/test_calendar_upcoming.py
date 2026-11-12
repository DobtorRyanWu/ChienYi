# -*- coding: utf-8 -*-
"""近期行事曆清單（models/calendar_event.py 的 _office_local_when、_office_upcoming_domain、_office_upcoming）。

手機行事曆頁的「7 天內」與公司儀表板的行事曆區塊讀同一份（淞源 2026-11-10 會議 C7：
「在電腦上一打開就看到」）。這裡鎖住：
* 日期與時間一律是台灣時間（台灣 00:30 的事算當天，不是 UTC 的前一天）；
* 「N 天內」的邊界是台灣今天 00:00 起算 N 天（剛好第 N 天 00:00 的不算）；
* 還沒完成的過期事項要列（不然會被忘掉），已完成、取消的不列；
* 件數不受筆數上限影響；以呼叫者自己的權限讀（另一方的看不到）。
"""
from datetime import datetime

from freezegun import freeze_time

from odoo.tests import tagged

from .common import OfficeCase

EVENT_MODEL = 'construction.calendar.event'
FROZEN_NOW = '2026-11-05 04:00:00'       # UTC；台灣 2026-11-05（四）12:00
DAYS = 7


def utc(*args):
    return datetime(*args)


@tagged('post_install', '-at_install', 'construction_office')
class TestCalendarUpcoming(OfficeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env[EVENT_MODEL]

    def _event(self, name, start, stop=None, company=None, **vals):
        values = {'name': 'UPC %s' % name, 'company_id': (company or self.co_s).id, 'project_id': self.p1.id,
                  'start': start, 'responsible_user_id': self.staff.id}
        if stop:
            values['stop'] = stop
        values.update(vals)
        return self.Event.create(values)

    def _upcoming(self, user, events, **kw):
        """user 看到的近期清單裡，屬於這次測試的事項（庫裡可能有別的事項）。"""
        data = self.Event.with_user(user)._office_upcoming(**kw)
        return data, [item for item in data['items'] if item['id'] in events.ids]

    # ── 時間的說法 ──────────────────────────────────────────────────────
    def test_local_when_is_taiwan_time(self):
        timed = self._event('有起訖', utc(2026, 11, 6, 6, 30), utc(2026, 11, 6, 8, 0))
        self.assertEqual(timed._office_local_when(), (datetime(2026, 11, 6).date(), '14:30–16:00'))
        # UTC 11-05 16:30＝台灣 11-06 00:30：算 11-06
        after_midnight = self._event('台灣凌晨', utc(2026, 11, 5, 16, 30), utc(2026, 11, 5, 17, 30))
        self.assertEqual(after_midnight._office_local_when(), (datetime(2026, 11, 6).date(), '00:30–01:30'))
        allday = self._event('整天', utc(2026, 11, 5, 16, 0), utc(2026, 11, 6, 15, 59), allday=True)
        self.assertEqual(allday._office_local_when(), (datetime(2026, 11, 6).date(), '整天'))
        cross_day = self._event('跨日', utc(2026, 11, 6, 14, 0), utc(2026, 11, 7, 2, 0))
        self.assertEqual(cross_day._office_local_when(), (datetime(2026, 11, 6).date(), '22:00'))
        no_length = self._event('沒有長度', utc(2026, 11, 6, 1, 0), utc(2026, 11, 6, 1, 0))
        self.assertEqual(no_length._office_local_when()[1], '09:00')

    # ── 近期清單 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_upcoming_window_boundaries_and_states(self):
        overdue = self._event('過期未完成', utc(2026, 11, 3, 1, 0), utc(2026, 11, 3, 2, 0))
        today = self._event('今天稍早', utc(2026, 11, 5, 1, 0), utc(2026, 11, 5, 2, 0), event_type='site_visit',
                            location='工區大門')
        # 台灣 11-11 23:59（第 7 天的最後一分鐘）算；台灣 11-12 00:00（剛好第 7 天結束）不算
        last_minute = self._event('第七天最後一分鐘', utc(2026, 11, 11, 15, 59), utc(2026, 11, 11, 16, 0))
        just_outside = self._event('第八天零時', utc(2026, 11, 11, 16, 0), utc(2026, 11, 11, 17, 0))
        done = self._event('已完成', utc(2026, 11, 6, 1, 0), utc(2026, 11, 6, 2, 0), state='done')
        cancelled = self._event('取消', utc(2026, 11, 6, 1, 0), utc(2026, 11, 6, 2, 0), state='cancelled')
        events = overdue | today | last_minute | just_outside | done | cancelled
        data, mine = self._upcoming(self.staff, events, days=DAYS, limit=200)
        self.assertEqual([item['id'] for item in mine], [overdue.id, today.id, last_minute.id], '由早到晚')
        self.assertEqual((data['today'], data['days']), ('2026-11-05', DAYS))
        by_id = {item['id']: item for item in mine}
        self.assertEqual({key: by_id[overdue.id][key] for key in ('day', 'day_label', 'when', 'overdue', 'is_today')},
                         {'day': '2026-11-03', 'day_label': '11/03（二）', 'when': '09:00–10:00', 'overdue': True,
                          'is_today': False})
        self.assertEqual({key: by_id[today.id][key] for key in (
            'day', 'day_label', 'when', 'overdue', 'is_today', 'event_type', 'type_label', 'location',
            'responsible', 'project_name')},
            {'day': '2026-11-05', 'day_label': '11/05（四）', 'when': '09:00–10:00', 'overdue': False, 'is_today': True,
             'event_type': 'site_visit', 'type_label': '會勘', 'location': '工區大門',
             'responsible': self.staff.name, 'project_name': self.p1.name})
        self.assertEqual(by_id[last_minute.id]['day'], '2026-11-11')
        # 條件就是手機頁用的那一份：同一個 domain 的筆數＝清單件數
        domain = self.Event._office_upcoming_domain(DAYS) + [('id', 'in', events.ids)]
        self.assertEqual(self.Event.search(domain), overdue | today | last_minute)
        # 不設上限＝全部待辦（第八天的也在；已完成、取消的還是不在）
        everything = self.Event.search(self.Event._office_upcoming_domain(None) + [('id', 'in', events.ids)])
        self.assertEqual(everything, overdue | today | last_minute | just_outside)

    @freeze_time('2026-11-04 16:30:00')      # 台灣 11-05 00:30：UTC 日期還在 11-04
    def test_today_is_taiwan_date_just_after_midnight(self):
        yesterday = self._event('台灣昨天', utc(2026, 11, 4, 9, 0), utc(2026, 11, 4, 10, 0))
        today = self._event('台灣今天', utc(2026, 11, 4, 18, 0), utc(2026, 11, 4, 19, 0))
        data, mine = self._upcoming(self.staff, yesterday | today, limit=200)
        self.assertEqual(data['today'], '2026-11-05')
        flags = {item['id']: (item['overdue'], item['is_today']) for item in mine}
        self.assertEqual(flags, {yesterday.id: (True, False), today.id: (False, True)})

    @freeze_time(FROZEN_NOW)
    def test_count_is_not_cut_by_limit(self):
        before = self.Event.with_user(self.staff)._office_upcoming(days=DAYS, limit=1)['count']
        events = self.Event
        for hour in (1, 2, 3):
            events |= self._event('第 %s 件' % hour, utc(2026, 11, 6, hour, 0))
        data = self.Event.with_user(self.staff)._office_upcoming(days=DAYS, limit=1)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['count'], before + 3)

    @freeze_time(FROZEN_NOW)
    def test_other_party_not_listed(self):
        """營造 A 的事項：監造方前台帳號看不到；監造公司的事項：營造 A 的帳號看不到。"""
        of_a = self._event('營造 A 的', utc(2026, 11, 6, 1, 0), company=self.co_a,
                           responsible_user_id=self.a_field.id)
        of_s = self._event('監造 S 的', utc(2026, 11, 6, 2, 0), company=self.co_s)
        events = of_a | of_s
        _data, seen_by_a = self._upcoming(self.a_field, events, limit=200)
        _data, seen_by_s = self._upcoming(self.sup_field, events, limit=200)
        self.assertEqual([item['id'] for item in seen_by_a], [of_a.id])
        self.assertEqual([item['id'] for item in seen_by_s], [of_s.id])
