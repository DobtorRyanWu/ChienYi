# -*- coding: utf-8 -*-
"""價格庫全域公司隔離（18.0.1.1.0）：多家公司共用一個庫時，只看得到目前選取公司的價格庫。"""
from odoo.tests import TransactionCase, tagged

ADMIN_GROUP = 'construction_supervision_base.group_supervisor_admin'


@tagged('post_install', '-at_install', 'construction_price_library')
class TestPriceLibraryCompanyRule(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': '價格庫隔離測試 B 公司'})
        Cat, Item = cls.env['price.library.category'], cls.env['price.library.item']
        cls.items = {}
        for key, company in (('a', cls.company_a), ('b', cls.company_b)):
            cat = Cat.create({'name': '隔離測試分類 %s' % key, 'company_id': company.id})
            cls.items[key] = Item.create({'name': '隔離測試工項', 'unit': 'm', 'unit_price': 10.0,
                                          'category_id': cat.id, 'company_id': company.id})
        # 價格歷史：改單價會自動寫一筆
        cls.items['b'].write({'unit_price': 12.0})
        cls.user = cls.env['res.users'].create({
            'name': '價格庫隔離測試管理者', 'login': 'price_rule_admin',
            'company_id': cls.company_a.id, 'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref(ADMIN_GROUP).id])],
        })

    def test_rig(self):
        # 只驗資料有建立；規則本身由 mutation（把規則改成 1=1 → 下面兩支要紅）證明
        self.assertEqual(self.items['b'].company_id, self.company_b)
        self.assertTrue(self.items['b'].history_ids, '改單價應寫一筆價格歷史')

    def test_admin_only_sees_own_company_items(self):
        both = self.items['a'] | self.items['b']
        got = self.env['price.library.item'].with_user(self.user).search([('id', 'in', both.ids)])
        self.assertEqual(got, self.items['a'])

    def test_admin_only_sees_own_company_categories_and_history(self):
        cats = (self.items['a'] | self.items['b']).category_id
        Cat = self.env['price.library.category'].with_user(self.user)
        self.assertEqual(Cat.search([('id', 'in', cats.ids)]), self.items['a'].category_id)
        History = self.env['price.library.item.history'].with_user(self.user)
        self.assertFalse(History.search([('item_id', '=', self.items['b'].id)]))
