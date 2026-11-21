# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：契約變更明細的新數量、新單價可以是負數。

舊系統（EAGLE）對這些輸入沒有檢查：契約工項只是數字輸入框，沒有正負檢查（前端 components/resource/m_contract/Contract.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（CC-08）。
"""

from lxml import etree

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


NEW_NAME = '回復原版工項改名後'
NEW_UNIT = 'M2'


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestEagleParityChangeNameUnit(TransactionCase):
    """CC-10（2026-11-22，鈺鈞補列）：契約變更可以改既有工項的名稱、單位，套用時寫回工項。
    舊系統契約變更是整份工項換新版（前端 components/resource/m_contract/Contract.vue），名稱、單位跟著新版走。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版契約變更改名', 'code': 'EP-CC-N', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})
        Task = cls.env['project.task']
        cls.top = Task.create({'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹'})
        cls.leaf = Task.create({'name': '回復原版工項改名前', 'project_id': cls.project.id, 'item_no': '一',
                                'parent_id': cls.top.id, 'planned_qty': 10.0, 'unit_price': 100.0, 'unit': 'M'})
        cls.other = Task.create({'name': '回復原版不改名工項', 'project_id': cls.project.id, 'item_no': '二',
                                 'parent_id': cls.top.id, 'planned_qty': 5.0, 'unit_price': 100.0, 'unit': 'M'})

    def _applied_order(self, *line_vals):
        order = self.env['contract.change.order'].create({
            'project_id': self.project.id, 'change_date': fields.Date.today(),
            'change_reason': 'other', 'other_reason_detail': '回復原版測試'})
        for vals in line_vals:
            task = vals['task']
            self.env['contract.change.order.line'].create(dict({
                'change_order_id': order.id, 'task_id': task.id, 'change_type': 'modify',
                'item_no': task.item_no, 'item_name': task.name, 'unit': task.unit,
                'original_qty': task.planned_qty, 'original_unit_price': task.unit_price,
                'new_qty': task.planned_qty, 'new_unit_price': task.unit_price},
                **{k: v for k, v in vals.items() if k != 'task'}))
        order.write({'is_limit_exempt': True, 'exempt_reason': '回復原版測試'})
        order.action_submit()
        order.action_review()
        order.action_approve()
        order.action_apply()
        return order

    def test_apply_writes_name_and_unit_back(self):
        order = self._applied_order({'task': self.leaf, 'item_name': NEW_NAME, 'unit': NEW_UNIT, 'new_qty': 12.0},
                                    {'task': self.other})
        self.assertEqual((self.leaf.name, self.leaf.unit, self.leaf.planned_qty), (NEW_NAME, NEW_UNIT, 12.0),
                         '修改前：套用只寫數量與單價，名稱、單位還是舊的')
        self.assertEqual((self.other.name, self.other.unit), ('回復原版不改名工項', 'M'), '沒改的工項不能被動到')
        notes = ' '.join(order.message_ids.mapped('body'))
        self.assertIn('回復原版工項改名前', notes, '舊名稱要記在變更單討論區')
        self.assertIn(NEW_NAME, notes)
        self.assertNotIn('回復原版不改名工項', notes)

    def test_blank_or_padded_values_do_not_rename(self):
        """名稱只差前後空白不算改；單位留空不寫回（工項的單位必填）。"""
        self._applied_order({'task': self.leaf, 'item_name': ' 回復原版工項改名前 ', 'unit': False})
        self.assertEqual((self.leaf.name, self.leaf.unit), ('回復原版工項改名前', 'M'))

    def test_name_editable_for_modify_lines_in_form(self):
        arch = etree.fromstring(self.env.ref('construction_contract_change.contract_change_order_view_form_v2').arch)
        fields_ = arch.xpath("//field[@name='line_ids']//field[@name='item_name']")
        self.assertTrue(fields_)
        for node in fields_:
            self.assertEqual(node.get('readonly'), "change_type not in ('add', 'modify')",
                             '「修改」的既有工項要能改名稱（修改前：readonly="1"）')
