# -*- coding: utf-8 -*-
"""P19：驗收缺失的 chatter 通知，標籤要是真的標籤，使用者輸入含 <script> 要被跳脫。"""
from markupsafe import Markup

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'construction_acceptance')
class TestDefectChatter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '驗收缺失通知測試', 'code': 'MF-ACC',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})
        cls.preliminary = cls.env['acceptance.preliminary'].create({
            'project_id': cls.project.id,
            'acceptance_date': fields.Date.today()})
        cls.user = cls.env['res.users'].create({
            'name': '缺失通知測試員', 'login': 'mf_acc_user',
            'email': 'mf_acc_user@example.com'})

    def _defect(self, **kw):
        vals = {
            'project_id': self.project.id, 'description': XSS,
            'source': 'preliminary',
            'preliminary_acceptance_id': self.preliminary.id,
            'deadline': fields.Date.today(), 'name': 'MF-ACC-<1>'}
        vals.update(kw)
        return self.env['acceptance.defect'].create(vals)

    def _last_body(self, rec):
        return self.env['mail.message'].search(
            [('model', '=', rec._name), ('res_id', '=', rec.id),
             ('message_type', '=', 'notification')], order='id desc', limit=1).body

    def test_assign_body_is_markup_and_escapes_input(self):
        defect = self._defect()
        defect.write({'responsible_user_id': self.user.id})
        body = self._last_body(defect)
        self.assertIsInstance(body, Markup)
        self.assertIn('<b>', body, '標籤要是真的標籤')
        self.assertNotIn('&lt;b&gt;', body, '標籤不可被當文字跳脫')
        self.assertNotIn('<script>', body, '缺失說明的 <script> 必須被跳脫')
        self.assertIn('&lt;script&gt;', body)

    def test_submit_body_is_markup(self):
        defect = self._defect(discovery_user_id=self.user.id)
        defect.write({'state': 'improving', 'improvement_description': XSS})
        defect.action_submit_improvement()
        body = self._last_body(defect)
        self.assertIsInstance(body, Markup)
        self.assertIn('<b>', body)
        self.assertNotIn('&lt;b&gt;', body)
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;1&gt;', body, '缺失編號含 < > 要被跳脫')
