# -*- coding: utf-8 -*-
"""B2：價格歷史的麵包屑要顯示「項目名稱 - 日期」，新建未存檔也不能露出 NewId。"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_price_library')
class TestHistoryDisplayName(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cat = cls.env['price.library.category'].create({'name': '顯示名稱測試分類'})
        cls.item = cls.env['price.library.item'].create({
            'name': '顯示名稱測試工項', 'unit': 'm', 'unit_price': 10.0,
            'category_id': cat.id})

    def test_saved_history_shows_item_and_date(self):
        hist = self.env['price.library.item.history'].create({
            'item_id': self.item.id, 'change_date': '2026-11-02'})
        self.assertEqual(hist.display_name, '顯示名稱測試工項 - 2026-11-02')
        self.assertNotIn('price.library.item.history', hist.display_name)

    def test_new_record_does_not_show_newid(self):
        hist = self.env['price.library.item.history'].new({})
        self.assertNotIn('NewId', hist.display_name)
        self.assertEqual(hist.display_name, hist._description)
