# -*- coding: utf-8 -*-
"""受限帳號對行事曆事項的讀取範圍（rule_scope.COMPANY_OWNED_LEVEL／COMPANY_OWNED_PERSONAL；淞源 C7）。

和公文同一套（所屬公司＝自己的公司；後台主管再限參與的工程），多一條：
自己是權責人的事項一定看得到——主管被指定負責一件沒掛工程、或不是他參與工程的事，不能反而看不到。
沒裝 construction_office（或還沒有行事曆）的庫整組略過。期望值依夾具獨立寫出。
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_role_accounts import RoleMatrixCase

EVENT_MODEL = 'construction.calendar.event'
CALENDAR_MENU = 'construction_office.menu_calendar_event'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestOfficeCalendarScope(RoleMatrixCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar_installed = EVENT_MODEL in cls.env
        if not cls.calendar_installed:
            return
        cls.env['ir.model.access']._dash_sync_optional_manager_access()
        Event = cls.env[EVENT_MODEL]
        start = fields.Datetime.now() + timedelta(days=1)

        def event(name, company, project=None, responsible=None):
            return Event.create({'name': f'OFFICE {name}', 'company_id': company.id, 'start': start,
                                 'project_id': project.id if project else False,
                                 'responsible_user_id': (responsible or cls.sup).id})

        cls.e_a_shared = event('A 共用工程', cls.co_a, cls.p_shared)
        cls.e_a_pa = event('A 工程 PA', cls.co_a, cls.p_a)
        cls.e_a_none = event('A 公司共通', cls.co_a)
        cls.e_a_cm_own = event('A 公司共通、營造主管負責', cls.co_a, responsible=cls.cm)
        cls.e_a_cm_other_project = event('A 工程 PA、營造主管負責', cls.co_a, cls.p_a, responsible=cls.cm)
        cls.e_b_shared = event('B 共用工程', cls.co_b, cls.p_shared)
        cls.e_s_shared = event('S 共用工程', cls.co_s, cls.p_shared)
        cls.e_s_pa = event('S 工程 PA', cls.co_s, cls.p_a)
        cls.e_s_sm_own = event('S 公司共通、監造主管負責', cls.co_s, responsible=cls.sm)
        cls.e_b_cm = event('B 的事卻指定營造 A 主管負責', cls.co_b, cls.p_shared, responsible=cls.cm)
        cls.office_events = (cls.e_a_shared | cls.e_a_pa | cls.e_a_none | cls.e_a_cm_own | cls.e_a_cm_other_project
                             | cls.e_b_shared | cls.e_s_shared | cls.e_s_pa | cls.e_s_sm_own | cls.e_b_cm)

    def setUp(self):
        super().setUp()
        if not self.calendar_installed:
            self.skipTest('沒裝 construction_office 的行事曆')

    def _seen(self, user):
        Event = self.env[EVENT_MODEL].with_user(user).with_context(active_test=False)
        return Event.search([('id', 'in', self.office_events.ids)])

    def test_contractor_side(self):
        own = self.e_a_shared | self.e_a_pa | self.e_a_none | self.e_a_cm_own | self.e_a_cm_other_project
        self.assertEqual(self._seen(self.mgr_a), own)
        self.assertEqual(self._seen(self.cb), own)
        # 營造方主管：參與的共用工程＋自己負責的兩件；別家公司的事就算指定他負責也看不到（公司條件在最外層）
        self.assertEqual(self._seen(self.cm), self.e_a_shared | self.e_a_cm_own | self.e_a_cm_other_project)

    def test_supervision_role(self):
        self.assertEqual(self._seen(self.sb), self.e_s_shared | self.e_s_pa | self.e_s_sm_own)
        self.assertEqual(self._seen(self.sm), self.e_s_pa | self.e_s_sm_own)

    def test_restricted_accounts_cannot_write(self):
        for user in (self.mgr_a, self.cb, self.cm, self.sb, self.sm):
            readable = self._seen(user)
            self.assertTrue(readable, user.login)
            with self.assertRaises(AccessError, msg=user.login):
                readable[0].with_user(user).write({'name': '被改了'})

    def test_role_accounts_see_calendar_menu(self):
        menu = self.env.ref(CALENDAR_MENU)
        for user in (self.cb, self.cm, self.sb, self.sm):
            self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(user)._visible_menu_ids(), user.login)
