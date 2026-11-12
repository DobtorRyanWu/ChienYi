# -*- coding: utf-8 -*-
"""手機行事曆頁（controllers/portal_calendar.py；淞源 2026-11-10 會議 C7）。

真實帳號跑真實路由。鎖住三件事：
* 表單輸入的是台灣時間，存進去的是 UTC（台灣 14:30 → 06:30），畫面顯示再換回來；
  不跟帳號的時區設定走（dev 就有帳號還是預設的 Europe/Brussels，後台網頁用的是瀏覽器時區）；
* 新增、改時間限老闆／主管；標為已完成限權責人本人或老闆／主管；
* 權責人、工程只能從本人可選的名單挑（表單值被改也塞不進去）。
"""
from datetime import datetime, timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..controllers.portal_calendar import ConstructionCalendarPortal
from .common import OfficeCase

EVENT_MODEL = 'construction.calendar.event'
TAIWAN_UTC_OFFSET_HOURS = 8


@tagged('post_install', '-at_install', 'construction_office')
class TestPortalCalendar(OfficeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionCalendarPortal()
        cls.Event = cls.env[EVENT_MODEL]
        # 帳號時區故意設成 Odoo 的預設值：換算要照台灣時間，不能跟著它走
        (cls.sup_boss | cls.sup_field | cls.sup_outsider).write({'tz': 'Europe/Brussels'})
        cls.env['supervision.project.member'].create({'project_id': cls.p1.id, 'user_id': cls.sup_boss.id})
        cls.now = fields.Datetime.now().replace(microsecond=0)
        cls.day = (cls.now + timedelta(days=3)).date()

    def _event(self, name, responsible, start, project=None, **vals):
        values = {'name': name, 'company_id': self.co_s.id, 'project_id': project.id if project else False,
                  'start': start, 'responsible_user_id': responsible.id}
        values.update(vals)
        return self.Event.create(values)

    def _drive(self, user, method, *args, **kw):
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = {}
            req.params = dict(kw)
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    # ── 列表 ────────────────────────────────────────────────────────────
    def test_list_groups_by_day_with_overdue_first_and_local_time(self):
        start = datetime.combine(self.day, datetime.min.time()) + timedelta(hours=6, minutes=30)   # UTC 06:30
        meeting = self._event('工務會議', self.sup_boss, start, self.p1, stop=start + timedelta(hours=2))
        overdue = self._event('過期的會勘', self.sup_field, self.now - timedelta(days=2), self.p1)
        self._event('已完成的', self.sup_boss, start, self.p1, state='done')
        values, html = self._drive(self.sup_boss, self.ctrl.calendar)
        labels = [(group['key'], [row['event'].name for row in group['rows']]) for group in values['groups']]
        self.assertEqual(labels, [('已過期未完成', ['過期的會勘']), (self.day.strftime('%Y-%m-%d'), ['工務會議'])])
        self.assertEqual(values['groups'][1]['rows'][0]['when'], '14:30–16:30', '畫面顯示台灣時間')
        self.assertIn('14:30–16:30', html)
        self.assertIn('工務會議', html)
        self.assertIn('id="cyDrawer"', html, '沒有工程頁首的頁面要自己帶抽屜選單')
        self.assertNotIn('已完成的', html)
        self.assertIn('新增事項', html)
        self.assertEqual(meeting.start, start, '讀取不會動到存的時間')
        # 只看我負責的
        values, _html = self._drive(self.sup_boss, self.ctrl.calendar, mine='1')
        self.assertEqual([row['event'] for group in values['groups'] for row in group['rows']], [meeting])
        # 範圍：7 天內看得到 3 天後的；範圍代碼被亂改時用預設
        values, _html = self._drive(self.sup_boss, self.ctrl.calendar, range='week')
        self.assertEqual(values['event_count'], 2)
        values, _html = self._drive(self.sup_boss, self.ctrl.calendar, range='???')
        self.assertEqual(values['range_key'], 'month')
        self.assertEqual(overdue.state, 'planned')

    def test_field_user_sees_own_and_member_project_events_without_manage_buttons(self):
        mine = self._event('我負責的', self.sup_field, self.now + timedelta(days=1))
        on_p1 = self._event('工程一的事', self.sup_boss, self.now + timedelta(days=1), self.p1)
        self._event('工程二的事', self.sup_boss, self.now + timedelta(days=1), self.p2)
        values, html = self._drive(self.sup_field, self.ctrl.calendar)
        seen = self.Event.browse([row['event'].id for group in values['groups'] for row in group['rows']])
        self.assertEqual(seen, mine | on_p1)
        self.assertNotIn('新增事項', html)
        self.assertNotIn('改時間', html)
        self.assertIn(f'/construction/calendar/{mine.id}/done', html, '自己負責的可以按完成')
        self.assertNotIn(f'/construction/calendar/{on_p1.id}/done', html)

    # ── 新增 ────────────────────────────────────────────────────────────
    def test_create_converts_local_time_to_utc(self):
        _values, location = self._drive(
            self.sup_boss, self.ctrl.calendar_create, name='  現場會勘  ', event_type='site_visit',
            date=self.day.strftime('%Y-%m-%d'), time_start='14:30', time_stop='16:00',
            responsible_user_id=str(self.sup_field.id), project_id=str(self.p1.id), location='工區大門',
            company_id='999999', state='done')
        self.assertEqual(location, '/construction/calendar?message=created')
        event = self.Event.search([('name', '=', '現場會勘')])
        self.assertEqual(len(event), 1)
        local_start = datetime.combine(self.day, datetime.min.time()) + timedelta(hours=14, minutes=30)
        self.assertEqual(event.start, local_start - timedelta(hours=TAIWAN_UTC_OFFSET_HOURS))
        self.assertEqual(event.stop - event.start, timedelta(hours=1, minutes=30))
        self.assertEqual((event.allday, event.event_type, event.responsible_user_id, event.project_id,
                          event.company_id, event.state, event.location),
                         (False, 'site_visit', self.sup_field, self.p1, self.co_s, 'planned', '工區大門'))

    def test_create_without_start_time_is_all_day_on_that_local_day(self):
        self._drive(self.sup_boss, self.ctrl.calendar_create, name='送件期限', date=self.day.strftime('%Y-%m-%d'))
        event = self.Event.search([('name', '=', '送件期限')])
        self.assertTrue(event.allday)
        self.assertEqual(event.responsible_user_id, self.sup_boss, '沒選權責人＝自己')
        self.assertEqual((event.start + timedelta(hours=TAIWAN_UTC_OFFSET_HOURS)).date(), self.day)

    def test_create_rejects_bad_input_and_values_outside_own_lists(self):
        count = self.Event.search_count([])
        day = self.day.strftime('%Y-%m-%d')
        new_url = '/construction/calendar/new'
        cases = [
            ({'name': ' ', 'date': day}, 'no_name'),
            ({'name': 'x', 'date': '2026-99-99'}, 'bad_date'),
            ({'name': 'x', 'date': day, 'time_start': '25:99'}, 'bad_date'),
            # 同一個工程的成員，但是別家公司的（營造 A）→ 不能指定：事項是監造公司的，他看不到
            ({'name': 'x', 'date': day, 'responsible_user_id': str(self.a_field.id)}, 'bad_user'),
            # 不是任何可見工程的成員 → 不能指定
            ({'name': 'x', 'date': day, 'responsible_user_id': str(self.sup_outsider.id)}, 'bad_user'),
            # 自己看不到的工程（別家公司的工程不在老闆的可見範圍時；這裡用不存在的 id）
            ({'name': 'x', 'date': day, 'project_id': '999999999'}, 'bad_project'),
            # 結束早於開始：模型擋下
            ({'name': 'x', 'date': day, 'time_start': '15:00', 'time_stop': '14:00'}, 'invalid'),
        ]
        for post, code in cases:
            _values, location = self._drive(self.sup_boss, self.ctrl.calendar_create, **post)
            self.assertEqual(location, f'{new_url}?error={code}', post)
        self.assertEqual(self.Event.search_count([]), count)

    def test_only_boss_or_manager_can_create_and_reschedule(self):
        event = self._event('要改時間的', self.sup_field, self.now + timedelta(days=1), self.p1)
        with self.assertRaises(AccessError):
            self._drive(self.sup_field, self.ctrl.calendar_create, name='現場人員建的', date=self.day.strftime('%Y-%m-%d'))
        with self.assertRaises(AccessError):
            self._drive(self.sup_field, self.ctrl.calendar_update, event.id, date=self.day.strftime('%Y-%m-%d'))
        _values, location = self._drive(self.sup_field, self.ctrl.calendar_new)
        self.assertEqual(location, '/construction/calendar?error=forbidden')
        self.assertFalse(self.Event.search([('name', '=', '現場人員建的')]))

    # ── 改時間、完成 ────────────────────────────────────────────────────
    def test_reschedule_keeps_duration_when_no_stop_time(self):
        start = self.now + timedelta(days=1)
        event = self._event('要改時間的', self.sup_field, start, self.p1, stop=start + timedelta(hours=2))
        values, html = self._drive(self.sup_boss, self.ctrl.calendar_reschedule, event.id)
        self.assertEqual(values['event'], event)
        self.assertIn('要改時間的', html)
        _values, location = self._drive(self.sup_boss, self.ctrl.calendar_update, event.id,
                                        date=self.day.strftime('%Y-%m-%d'), time_start='09:00')
        self.assertEqual(location, '/construction/calendar?message=updated')
        local_start = datetime.combine(self.day, datetime.min.time()) + timedelta(hours=9)
        self.assertEqual(event.start, local_start - timedelta(hours=TAIWAN_UTC_OFFSET_HOURS))
        self.assertEqual(event.stop - event.start, timedelta(hours=2), '沒填結束時間：長度不變')
        self.assertEqual((event.name, event.responsible_user_id), ('要改時間的', self.sup_field), '只改時間')

    def test_done_by_responsible_or_manager_only(self):
        mine = self._event('我負責的', self.sup_field, self.now + timedelta(days=1), self.p1)
        boss_event = self._event('老闆負責的', self.sup_boss, self.now + timedelta(days=1), self.p1)
        with self.assertRaises(AccessError):
            self._drive(self.sup_field, self.ctrl.calendar_done, boss_event.id)
        self.assertEqual(boss_event.state, 'planned')
        _values, location = self._drive(self.sup_field, self.ctrl.calendar_done, mine.id)
        self.assertEqual(location, '/construction/calendar?message=done')
        self.assertEqual(mine.state, 'done')
        self._drive(self.sup_boss, self.ctrl.calendar_done, boss_event.id)
        self.assertEqual(boss_event.state, 'done')
        # 看不到的事項：導回列表、不動它
        hidden = self._event('工程二的事', self.staff, self.now + timedelta(days=1), self.p2)
        _values, location = self._drive(self.sup_field, self.ctrl.calendar_done, hidden.id)
        self.assertEqual(location, '/construction/calendar')
        self.assertEqual(hidden.state, 'planned')
