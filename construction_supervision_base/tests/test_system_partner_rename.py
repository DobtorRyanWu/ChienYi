# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestSystemPartnerRename(TransactionCase):
    """訊息記錄作者 OdooBot 改名「系統」：只改預設名稱，不蓋掉使用者改過的名稱。"""

    def setUp(self):
        super().setUp()
        self.root = self.env.ref('base.partner_root')

    def test_odoobot_renamed(self):
        self.root.sudo().write({'name': 'OdooBot'})
        self.env['res.partner']._rename_system_partner()
        self.assertEqual(self.root.name, '系統')

    def test_custom_name_kept(self):
        self.root.sudo().write({'name': '自訂系統名'})
        self.env['res.partner']._rename_system_partner()
        self.assertEqual(self.root.name, '自訂系統名')
