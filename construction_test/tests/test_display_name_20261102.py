# -*- coding: utf-8 -*-
"""B2：檢驗頻率條件的麵包屑要顯示條件摘要，新建未存檔不露出 NewId。"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_test')
class TestFrequencyConditionDisplayName(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env['project.project'].create({
            'name': '頻率條件顯示測試', 'code': 'DISP-FC', 'project_type': 'general'})
        cls.standard = cls.env['supervision.test.standard'].create({
            'name': '頻率條件試驗', 'material': '材料', 'project_id': project.id})

    def test_saved_condition_shows_summary(self):
        cond = self.env['supervision.test.frequency.condition'].create({
            'standard_id': self.standard.id, 'condition_type': 'every_batch'})
        self.assertEqual(cond.display_name, '每批檢驗1次')
        self.assertNotIn('supervision.test.frequency.condition', cond.display_name)

    def test_new_condition_does_not_show_newid(self):
        cond = self.env['supervision.test.frequency.condition'].new({})
        self.assertNotIn('NewId', cond.display_name)
        self.assertEqual(cond.display_name, cond._description)
