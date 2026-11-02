# -*- coding: utf-8 -*-
"""說明書發現問題的回歸（2026-11-02）。

- B2  契約變更精靈的麵包屑不能露出 contract.change.wizard / NewId。
- P19 發包工程費調整寫進工程 chatter 的訊息：標籤要是真的標籤，
      使用者輸入（調整說明、變更編號）含 <script> 要被跳脫。
"""
from markupsafe import Markup

from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestManualFixes20261102(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '手冊修正測試工程', 'code': 'MF-CHG',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})

    def test_b2_wizard_display_name(self):
        Wizard = self.env['contract.change.wizard']
        new = Wizard.new({})
        self.assertNotIn('NewId', new.display_name)
        self.assertEqual(new.display_name, Wizard._description)
        saved = Wizard.create({'project_id': self.project.id})
        self.assertEqual(saved.display_name, Wizard._description)
        self.assertNotIn('contract.change.wizard', saved.display_name)

    def test_p19_lump_adjust_body_is_markup_and_escapes_input(self):
        order = self.env['contract.change.order'].create({
            'project_id': self.project.id,
            'lump_adjust_amount': 1000.0,
            'lump_adjust_reason': XSS})
        order.sudo().write({'name': XSS})
        order._update_project_contract()
        body = self.env['mail.message'].search(
            [('model', '=', 'project.project'), ('res_id', '=', self.project.id),
             ('message_type', 'in', ('comment', 'notification'))], order='id desc', limit=1).body
        self.assertIsInstance(body, Markup)
        self.assertIn('<b>', body, '標籤要是真的標籤')
        self.assertNotIn('&lt;b&gt;', body, '標籤不可被當文字跳脫')
        self.assertNotIn('<script>', body, '使用者輸入的 <script> 必須被跳脫')
        self.assertIn('&lt;script&gt;', body)
