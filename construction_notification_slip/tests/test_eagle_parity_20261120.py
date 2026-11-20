# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：通報單裡舊系統沒有的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的通報單每一欄離開輸入框就存，狀態是下拉自己選，沒有依狀態鎖欄位或擋動作
（前端 components/resource/m_appointment/AppointmentSheet.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（NS 開頭的編號）。
退單（新功能）之後整張唯讀的規則不動。
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged

FORM_XMLID = 'construction_notification_slip.view_reservation_notification_slip_form'
# 已結案後照舊系統還能改的欄位（NS-14）
EDITABLE_AFTER_CLOSED = ('location', 'location_detail', 'latitude', 'longitude', 'detail_line_ids')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipForm(TransactionCase):

    def test_closed_slip_fields_not_readonly_in_form(self):
        """NS-14：已結案的通報單，明細與施工地點在表單上不再唯讀；退單後照舊唯讀。"""
        arch = etree.fromstring(self.env.ref(FORM_XMLID).arch)
        for name in EDITABLE_AFTER_CLOSED:
            nodes = arch.xpath("//field[@name='%s']" % name)
            self.assertTrue(nodes, name)
            readonly = nodes[0].get('readonly') or ''
            self.assertNotIn('closed', readonly, '%s 已結案後不該唯讀' % name)
            self.assertIn('cancelled', readonly, '%s 退單後仍要唯讀' % name)
        add_button = arch.xpath("//button[@name='action_open_add_lines_wizard']")[0]
        self.assertNotIn('closed', add_button.get('invisible') or '', '已結案後「加入工項」按鈕不該消失')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipFlow(TransactionCase):

    def _slip(self, code):
        project = self.env['project.project'].create({
            'name': '回復原版通報單 %s' % code, 'code': code, 'project_type': 'reservation',
            'state': 'construction', 'company_id': self.env.company.id})
        return self.env['reservation.notification.slip'].create({'project_id': project.id, 'location': '回復原版測試地點'})

    def test_confirm_without_detail_lines(self):
        """NS-01：沒有明細的通報單也能確認。"""
        slip = self._slip('EP-NS-1')
        self.assertFalse(slip.detail_line_ids, '前提：沒有明細')
        slip.action_confirm()
        self.assertEqual(slip.state, 'not_started')

    def test_close_without_actual_qty_or_amount(self):
        """NS-03：沒有填實際完成數量或金額也能結案。"""
        slip = self._slip('EP-NS-3')
        slip.action_confirm()
        slip.action_start()
        slip.action_close()
        self.assertEqual(slip.state, 'closed')
        self.assertTrue(slip.actual_end_date, '結案時仍要記下實際竣工日')


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestEagleParitySlipInput(TransactionCase):
    """NS-07、NS-12：日期先後、數量與單價正負不再檢查。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版通報單輸入值', 'code': 'EP-NS-I', 'project_type': 'reservation',
            'state': 'construction', 'company_id': cls.env.company.id})
        cls.task = cls.env['project.task'].create({
            'name': '回復原版通報單工項', 'project_id': cls.project.id, 'item_no': 'EPN-1',
            'unit': 'M', 'planned_qty': 100.0, 'unit_price': 10.0})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': '回復原版測試地點'})

    def test_end_dates_before_start_dates_allowed(self):
        self.slip.write({'planned_start_date': '2026-06-10', 'planned_end_date': '2026-06-01',
                         'actual_start_date': '2026-06-10', 'actual_end_date': '2026-06-05'})
        self.env.flush_all()          # 預定日期是資料庫層的 CHECK 約束，flush 才會擋
        self.slip.invalidate_recordset()
        self.assertLess(self.slip.planned_end_date, self.slip.planned_start_date)
        self.assertLess(self.slip.actual_end_date, self.slip.actual_start_date)

    def test_negative_line_qty_and_price_allowed(self):
        line = self.env['reservation.notification.slip.line'].create({
            'slip_id': self.slip.id, 'task_id': self.task.id, 'item_no': '1', 'unit': 'M'})
        line.write({'planned_qty': -1.0, 'actual_qty': -2.0, 'unit_price': -3.0})
        self.env.flush_all()
        self.assertEqual((line.planned_qty, line.actual_qty, line.unit_price), (-1.0, -2.0, -3.0))
