# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：檢試驗紀錄的進場數量、抽樣數量可以是負數。

舊系統（EAGLE）對這些輸入沒有檢查：這兩欄在舊系統是文字欄位，沒有任何驗證（後端 models/schemas/testRecord.js）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（TS-05）。
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_test')
class TestEagleParityTestRecord(TransactionCase):

    def test_negative_quantities_blocked(self):
        """TS-05（2026-11-22 使用者決定加回）：進場數量、抽樣數量不可為負數；0 與正數照常。"""
        project = self.env['project.project'].create({
            'name': '回復原版檢試驗', 'code': 'EP-TS', 'company_id': self.env.company.id})
        standard = self.env['supervision.test.standard'].create({
            'name': '回復原版試驗項目', 'material': '回復原版材料', 'project_id': project.id})
        Record = self.env['supervision.test.record']
        record = Record.create({
            'project_id': project.id, 'standard_id': standard.id,
            'in_site_quantity': 0.0, 'sample_quantity': 2.0})
        self.assertEqual((record.in_site_quantity, record.sample_quantity), (0.0, 2.0))
        with self.assertRaises(ValidationError):
            record.write({'in_site_quantity': -1.0})
        with self.assertRaises(ValidationError):
            record.write({'sample_quantity': -2.0})
