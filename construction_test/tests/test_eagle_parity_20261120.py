# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：檢試驗紀錄的進場數量、抽樣數量可以是負數。

舊系統（EAGLE）對這些輸入沒有檢查：這兩欄在舊系統是文字欄位，沒有任何驗證（後端 models/schemas/testRecord.js）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（TS-05）。
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_test')
class TestEagleParityTestRecord(TransactionCase):

    def test_negative_quantities_allowed(self):
        project = self.env['project.project'].create({
            'name': '回復原版檢試驗', 'code': 'EP-TS', 'company_id': self.env.company.id})
        standard = self.env['supervision.test.standard'].create({
            'name': '回復原版試驗項目', 'material': '回復原版材料', 'project_id': project.id})
        record = self.env['supervision.test.record'].create({
            'project_id': project.id, 'standard_id': standard.id,
            'in_site_quantity': -1.0, 'sample_quantity': -2.0})
        self.env.flush_all()
        self.assertEqual((record.in_site_quantity, record.sample_quantity), (-1.0, -2.0))
