# -*- coding: utf-8 -*-
"""已經有檢查單用到的檢查類型，不能改「結果欄位」（W5 E2-7，2026-11-25）。

檢查單讀的是類型「現在」的結果欄位（related，不是建立當下的快照）。用過之後再改，舊檢查的勾選不在新樣式的
選項裡、檢查結果也不會重算（紀錄型的「不足」原本算缺失，改成只紀錄後還是缺失），列印時那一列整列空白。
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_quality')
class TestResultLayoutInUse(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '結果欄位鎖定測試', 'code': 'QA-LAYOUTLOCK',
            'project_type': 'general', 'company_id': cls.env.company.id})
        cls.Type = cls.env['self.inspection.type']

    def _use(self, itype):
        """建一張用到這個類型的一般式檢查"""
        return self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'name': 'QA-LAYOUTLOCK', 'inspection_type_id': itype.id,
            'sub_project_name': '結果欄位鎖定', 'inspection_date': fields.Date.today()})

    def test_used_type_cannot_change_result_layout(self):
        itype = self.Type.create({'name': '鎖定：生態保育', 'result_layout': 'yes_partial_no'})
        self._use(itype)
        with self.assertRaises(UserError) as cm:
            itype.write({'result_layout': 'yes_no'})
        self.assertIn('結果欄位', str(cm.exception))
        self.assertIn('1', str(cm.exception), '訊息要說有幾張檢查用到')
        self.assertEqual(itype.result_layout, 'yes_partial_no')

    def test_used_type_writing_same_layout_is_allowed(self):
        """種子工具、匯入會把原值寫回去：值沒變不擋，其他欄位照樣改得了"""
        itype = self.Type.create({'name': '鎖定：環境清潔', 'result_layout': 'yes_no'})
        self._use(itype)
        itype.write({'result_layout': 'yes_no', 'description': '只改說明'})
        self.assertEqual(itype.description, '只改說明')

    def test_unused_type_can_change_result_layout(self):
        itype = self.Type.create({'name': '鎖定：還沒用過', 'result_layout': 'yes_no'})
        itype.write({'result_layout': 'yes_partial_no'})
        self.assertEqual(itype.result_layout, 'yes_partial_no')

    def test_mixed_batch_names_the_used_one(self):
        """一次改兩個類型，其中一個用過：整批擋下，訊息點名用過的那一個"""
        used = self.Type.create({'name': '鎖定：用過的', 'result_layout': 'standard'})
        free = self.Type.create({'name': '鎖定：沒用過的', 'result_layout': 'standard'})
        self._use(used)
        with self.assertRaises(UserError) as cm:
            (used + free).write({'result_layout': 'yes_no'})
        self.assertIn('鎖定：用過的', str(cm.exception))
        self.assertNotIn('鎖定：沒用過的', str(cm.exception))
