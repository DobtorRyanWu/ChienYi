# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：契約變更明細的新數量、新單價可以是負數。

舊系統（EAGLE）對這些輸入沒有檢查：契約工項只是數字輸入框，沒有正負檢查（前端 components/resource/m_contract/Contract.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（CC-08）。
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestEagleParityChangeLine(TransactionCase):

    def test_negative_new_qty_and_price_allowed(self):
        project = self.env['project.project'].create({
            'name': '回復原版契約變更', 'code': 'EP-CC', 'project_type': 'general', 'state': 'construction',
            'company_id': self.env.company.id})
        Task = self.env['project.task']
        top = Task.create({'name': '發包工程費', 'project_id': project.id, 'item_no': '壹'})
        leaf = Task.create({'name': '工項A', 'project_id': project.id, 'item_no': '一', 'parent_id': top.id,
                            'planned_qty': 10.0, 'unit_price': 100.0, 'unit': 'M'})
        order = self.env['contract.change.order'].create({
            'project_id': project.id, 'change_date': fields.Date.today(),
            'change_reason': 'other', 'other_reason_detail': '回復原版測試'})
        line = self.env['contract.change.order.line'].create({
            'change_order_id': order.id, 'task_id': leaf.id, 'change_type': 'modify',
            'item_no': leaf.item_no, 'item_name': leaf.name, 'unit': leaf.unit,
            'original_qty': 10.0, 'original_unit_price': 100.0, 'new_qty': -2.0, 'new_unit_price': -5.0})
        self.env.flush_all()
        self.assertEqual((line.new_qty, line.new_unit_price), (-2.0, -5.0))
