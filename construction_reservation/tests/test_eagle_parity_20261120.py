# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：預約式通報單上建立自主檢查、缺失單，不再限「未開始／施工中／停工」。

舊系統（EAGLE）的通報單狀態是下拉自己選，不拿來擋別的單據
（前端 components/resource/m_appointment/AppointmentSheet.vue）。
草稿、已退單的通報單不能掛單據是退單功能的一部分，維持。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（RS-01）。
"""
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

FORM_XMLID = 'construction_reservation.view_reservation_notification_slip_form_reservation'
CREATE_BUTTONS = ('action_create_self_inspection', 'action_create_defect_improvement')


@tagged('post_install', '-at_install', 'construction_reservation')
class TestEagleParityReservationSlip(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({
            'name': '回復原版預約式', 'code': 'EP-RS', 'project_type': 'reservation',
            'state': 'construction', 'company_id': cls.env.company.id})
        cls.slip = cls.env['reservation.notification.slip'].create({'project_id': project.id, 'location': '回復原版測試地點'})

    def test_closed_slip_can_open_create_forms(self):
        self.slip.sudo().write({'state': 'closed'})
        self.assertEqual(self.slip.action_create_self_inspection()['res_model'], 'reservation.self.inspection')
        self.assertEqual(self.slip.action_create_defect_improvement()['res_model'], 'reservation.defect.improvement')

    def test_draft_slip_still_refused(self):
        self.assertEqual(self.slip.state, 'draft')
        for name in CREATE_BUTTONS:
            with self.assertRaises(UserError, msg=name):
                getattr(self.slip, name)()

    def test_buttons_shown_on_closed_slip(self):
        arch = etree.fromstring(self.env.ref(FORM_XMLID).arch)
        for name in CREATE_BUTTONS:
            invisible = arch.xpath("//button[@name='%s']" % name)[0].get('invisible') or ''
            self.assertNotIn('closed', invisible, name)
            self.assertNotIn('not in', invisible, '%s 不再用「只有這幾個狀態才顯示」的寫法' % name)
            self.assertIn('draft', invisible, '%s 草稿時仍隱藏' % name)
            self.assertIn('cancelled', invisible, '%s 退單後仍隱藏' % name)
