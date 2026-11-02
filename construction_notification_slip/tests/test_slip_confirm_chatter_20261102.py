# -*- coding: utf-8 -*-
"""P19：通報單確認的 chatter 通知，標籤要是真的標籤，工程地點含 <script> 要被跳脫。"""
from markupsafe import Markup

from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'construction_notification_slip')
class TestSlipConfirmChatter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['res.users'].create({
            'name': '通報單通知測試主任', 'login': 'mf_slip_mgr',
            'email': 'mf_slip_mgr@example.com'})
        cls.project = cls.env['project.project'].create({
            'name': '通報單通知測試', 'code': 'MF-SLIP',
            'project_type': 'reservation', 'company_id': cls.env.company.id,
            'site_manager_id': cls.manager.id})
        cls.task = cls.env['project.task'].create({
            'name': '通知測試工項', 'project_id': cls.project.id, 'item_no': '1'})

    def test_confirm_body_is_markup_and_escapes_input(self):
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.project.id, 'location': XSS})
        self.env['reservation.notification.slip.line'].create({
            'slip_id': slip.id, 'task_id': self.task.id,
            'item_no': '1', 'unit': '式'})
        slip.action_confirm()
        body = self.env['mail.message'].search(
            [('model', '=', slip._name), ('res_id', '=', slip.id),
             ('message_type', '=', 'notification')], order='id desc', limit=1).body
        self.assertIsInstance(body, Markup)
        self.assertIn('<b>%s</b>' % slip.slip_number, body, '標籤要是真的標籤')
        self.assertNotIn('&lt;b&gt;', body, '標籤不可被當文字跳脫')
        self.assertNotIn('<script>', body, '工程地點的 <script> 必須被跳脫')
        self.assertIn('&lt;script&gt;', body)
