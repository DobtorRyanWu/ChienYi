# -*- coding: utf-8 -*-
"""行事曆事項（models/calendar_event.py、security/office_rules.xml；淞源 2026-11-10 會議 C7）。

老闆答應的是「行事曆＋權責人＋改時間，先用手建」。這裡鎖住：預設結束時間、過期判斷、
所屬公司（營造方建立的一律是自己的公司）、誰看得到（權責人本人一定看得到）、公文可以帶出事項。
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import OfficeCase

EVENT_MODEL = 'construction.calendar.event'


@tagged('post_install', '-at_install', 'construction_office')
class TestCalendarEvent(OfficeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env[EVENT_MODEL]
        cls.now = fields.Datetime.now().replace(microsecond=0)

    def _event(self, name, company, project=None, responsible=None, **vals):
        values = {'name': name, 'company_id': company.id, 'project_id': project.id if project else False,
                  'start': self.now + timedelta(days=1),
                  'responsible_user_id': (responsible or self.staff).id}
        values.update(vals)
        return self.Event.create(values)

    def _visible(self, user, events):
        return self.Event.with_user(user).with_context(active_test=False).search([('id', 'in', events.ids)])

    def test_stop_defaults_to_one_hour_after_start(self):
        event = self._event('預設長度', self.co_s, self.p1)
        self.assertEqual(event.stop - event.start, timedelta(hours=1))
        self.assertEqual((event.state, event.event_type), ('planned', 'meeting'))
        with self.assertRaises(ValidationError):
            self._event('時間顛倒', self.co_s, self.p1, stop=self.now)

    def test_overdue_is_planned_and_already_ended(self):
        past = self._event('過期', self.co_s, self.p1, start=self.now - timedelta(days=2),
                           stop=self.now - timedelta(days=2) + timedelta(hours=1))
        future = self._event('未來', self.co_s, self.p1)
        done = self._event('已完成的舊事', self.co_s, self.p1, start=self.now - timedelta(days=2),
                           stop=self.now - timedelta(days=2) + timedelta(hours=1), state='done')
        events = past | future | done
        self.assertEqual([e.is_overdue for e in events], [True, False, False])
        self.assertEqual(self.Event.search([('id', 'in', events.ids), ('is_overdue', '=', True)]), past)
        self.assertEqual(self.Event.search([('id', 'in', events.ids), ('is_overdue', '=', False)]), future | done)
        past.action_mark_done()
        self.assertFalse(past.is_overdue)

    def test_contractor_created_event_belongs_to_own_company(self):
        event = self.Event.with_user(self.a_field).sudo().create({
            'name': '營造 A 建的', 'start': self.now, 'project_id': self.p1.id,
            'company_id': self.co_b.id, 'responsible_user_id': self.a_field.id})
        self.assertEqual(event.company_id, self.co_a)
        with self.assertRaises(AccessError):
            event.with_user(self.a_field).sudo().write({'company_id': self.co_b.id})

    def test_member_responsible_boss_outsider(self):
        on_p1 = self._event('工程一的事', self.co_s, self.p1)
        on_p2 = self._event('工程二的事', self.co_s, self.p2)
        company_wide = self._event('公司共通的事', self.co_s)
        mine_no_project = self._event('我負責、沒掛工程', self.co_s, responsible=self.sup_field)
        mine_other_project = self._event('我負責、不是成員的工程', self.co_s, self.p2, responsible=self.sup_outsider)
        events = on_p1 | on_p2 | company_wide | mine_no_project | mine_other_project
        self.assertEqual(self._visible(self.sup_field, events), on_p1 | mine_no_project,
                         '成員：參與工程的＋自己負責的')
        self.assertEqual(self._visible(self.sup_outsider, events), mine_other_project, '權責人本人一定看得到')
        self.assertEqual(self._visible(self.sup_boss, events), events)

    def test_other_party_cannot_see(self):
        s_event = self._event('監造的事', self.co_s, self.p1)
        a_event = self._event('營造 A 的事', self.co_a, self.p1)
        self.assertEqual(self._visible(self.sup_field, s_event | a_event), s_event)
        self.assertEqual(self._visible(self.sup_boss, s_event | a_event), s_event)

    def test_contractor_portal_sees_only_own_company(self):
        if not self.dashboard_installed:
            self.skipTest('沒裝 construction_company_dashboard：營造方的範圍收窄由它負責')
        s_event = self._event('監造的事', self.co_s, self.p1)
        a_event = self._event('營造 A 的事', self.co_a, self.p1)
        self.assertEqual(self._visible(self.a_field, s_event | a_event), a_event)

    def test_portal_accounts_cannot_write_through_orm(self):
        event = self._event('唯讀', self.co_s, self.p1)
        for user in (self.sup_field, self.sup_boss):
            with self.assertRaises(AccessError, msg=user.login):
                event.with_user(user).write({'name': '被改了'})

    def test_portal_cannot_read_source_doc_through_event(self):
        """前台帳號看得到事項（自己負責）但看不到它連到的公文（沒掛工程的公文只有老闆與後台看得到）：
        不能經「來源公文」欄位讀到公文的主旨與 id（2026-11-12 權限審查的重現案例）。"""
        secret = self._doc('不給現場看的公文主旨', self.co_s)
        event = self._event('交辦事項', self.co_s, responsible=self.sup_field, official_doc_id=secret.id)
        self.env.invalidate_all()
        self.assertEqual(self._visible(self.sup_field, event), event, '前提：權責人看得到這件事')
        self.assertFalse(self.Doc.with_user(self.sup_field).search([('id', '=', secret.id)]), '前提：他看不到那份公文')
        as_field = event.with_user(self.sup_field)
        with self.assertRaises(AccessError):
            as_field.read(['official_doc_id'])
        with self.assertRaises(AccessError):
            self.Event.with_user(self.sup_field).search_read([('id', '=', event.id)], ['official_doc_id'])
        with self.assertRaises(AccessError):
            self.Event.with_user(self.sup_field).read_group([('id', '=', event.id)], ['name'], ['official_doc_id'])
        self.assertNotIn('official_doc_id', as_field.read()[0], '沒指定欄位時也不會帶出來')
        self.assertNotIn(secret.subject, str(as_field.read()[0]))
        # 後台人員照常讀得到（表單上的「來源公文」）
        self.env.invalidate_all()
        self.assertEqual(event.with_user(self.staff).read(['official_doc_id'])[0]['official_doc_id'][0], secret.id)

    def test_official_doc_prefills_new_event(self):
        doc = self._doc('請於期限內提送施工計畫', self.co_s, self.p1, reply_deadline=self.tomorrow,
                        responsible_user_id=self.staff.id)
        action = doc.action_create_calendar_event()
        context = action['context']
        self.assertEqual(action['res_model'], EVENT_MODEL)
        self.assertEqual((context['default_name'], context['default_official_doc_id'], context['default_project_id'],
                          context['default_company_id'], context['default_responsible_user_id']),
                         (doc.subject, doc.id, self.p1.id, self.co_s.id, self.staff.id))
        self.assertEqual((context['default_event_type'], context['default_allday']), ('deadline', True))
        self.assertEqual(fields.Datetime.to_datetime(context['default_start']).date(), self.tomorrow)
        event = self.Event.with_context(**context).create({})
        self.assertEqual((event.name, event.official_doc_id, event.project_id, event.event_type),
                         (doc.subject, doc, self.p1, 'deadline'))
        doc.invalidate_recordset()
        self.assertEqual(doc.calendar_event_count, 1)
