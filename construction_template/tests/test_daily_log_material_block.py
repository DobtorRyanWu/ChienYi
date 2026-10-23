# -*- coding: utf-8 -*-
"""監造日報表第一聯「三、查核材料規格及品質」：只印人工手填的列。

連結契約材料清單的列是營造廠的工地材料使用量（營造版第一聯 c1 才印），印在監造的查核材料
這一節語意不對，還會和查核材料搶樣板預留的 5 列（自動帶入的列 id 較小、排在前面，
超過 5 列的查核紀錄會被擠出報表）。
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import daily_log_1
from odoo.addons.construction_template.utils.template_render import build_values


@tagged('post_install', '-at_install', 'construction_template')
class TestDailyLog1MaterialBlock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '日報表材料區塊測試', 'code': 'TPL-DL1MAT',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        employee = cls.env['hr.employee'].create(
            {'name': '日報表測試員工', 'company_id': company.id})
        Catalog = cls.env['construction.contract.material']
        cls.zero_item = Catalog.create({
            'project_id': cls.project.id, 'code': 'M001', 'name': '今日沒用的材料',
            'unit': 'M3', 'is_key': True})
        cls.used_item = Catalog.create({
            'project_id': cls.project.id, 'code': 'M002', 'name': '今日有用的材料',
            'unit': 'M3', 'is_key': True})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': company.id,
            'employee_id': employee.id,
            'log_date': fields.Date.today(),
        })
        cls.sheet.material_ids.filtered(
            lambda m: m.catalog_item_id == cls.used_item).write({'daily_qty': 5.0})
        cls.env['daily.log.material'].create({
            'daily_log_id': cls.sheet.id, 'name': '人工手填的零數量材料',
            'daily_qty': 0.0})

    def test_only_manual_rows_are_printed(self):
        values = build_values(self.sheet, daily_log_1)
        names = [values.get('A%d' % row) for row in range(28, 33)]
        self.assertIn('人工手填的零數量材料', names)
        self.assertNotIn('今日沒用的材料', names)
        self.assertNotIn('今日有用的材料', names)

    def test_linked_rows_do_not_push_out_manual_rows(self):
        # 5 列查核材料都要印得出來，即使當天有 2 列連結列、而且 id 比較小
        for i in range(4):
            self.env['daily.log.material'].create({
                'daily_log_id': self.sheet.id, 'name': '查核材料 %d' % i, 'daily_qty': 1.0})
        values = build_values(self.sheet, daily_log_1)
        names = [values.get('A%d' % row) for row in range(28, 33)]
        self.assertEqual(sorted(n for n in names if n), sorted(
            ['人工手填的零數量材料'] + ['查核材料 %d' % i for i in range(4)]))
