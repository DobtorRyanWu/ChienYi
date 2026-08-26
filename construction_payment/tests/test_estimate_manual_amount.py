# -*- coding: utf-8 -*-
"""估驗計價：本次估驗金額可手動編輯，且手動值優先於 單價 × 本次估驗數量。

鎖定行為：
1. 未手動時，金額 = 單價 × 本次估驗數量（原行為不變）
2. 手動輸入後，數量／單價再變動都不得覆蓋手動值
3. 手動值要一路反映到 本次估驗總金額、累計估驗金額、彙總項金額
4. 取消勾選「金額手動輸入」即還原為系統計算值
5. editable list 的實際操作順序（先改金額、再改數量）不得把金額吃掉
   —— onchange 內若先設旗標再讀 estimate_amount，會觸發重算而讀回 0
"""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEstimateManualAmount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '估驗手動金額測試工程',
            'code': 'EST-MAN',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.parent_task = cls.env['project.task'].create({
            'name': '彙總群組',
            'project_id': cls.project.id,
            'item_no': '1',
            'unit': '式',
            'planned_qty': 1.0,
            'unit_price': 0.0,
        })
        cls.task = cls.env['project.task'].create({
            'name': '估驗工項M',
            'project_id': cls.project.id,
            'parent_id': cls.parent_task.id,
            'item_no': '1.1',
            'unit': 'm3',
            'planned_qty': 100.0,
            'unit_price': 10.0,
        })
        cls.estimate = cls.env['payment.estimate'].create({
            'project_id': cls.project.id,
            'estimate_date': fields.Date.today(),
        })
        cls.summary_line = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.parent_task.id,
            'estimate_qty': 1.0,
            'unit_price': 0.0,
        })
        cls.line = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.task.id,
            'estimate_qty': 5.0,
            'unit_price': 10.0,
        })
        # 第二個工項（不掛在彙總群組下），用來驗證精靈可逐項挑選
        cls.task2 = cls.env['project.task'].create({
            'name': '估驗工項N',
            'project_id': cls.project.id,
            'item_no': '2',
            'unit': 'm2',
            'planned_qty': 50.0,
            'unit_price': 20.0,
        })
        cls.line2 = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.task2.id,
            'estimate_qty': 5.0,
            'unit_price': 20.0,
        })

    def test_auto_amount_by_default(self):
        """未手動輸入 → 金額 = 單價 × 數量"""
        self.assertFalse(self.line.is_amount_manual)
        self.assertEqual(self.line.estimate_amount, 50.0)
        self.assertEqual(self.line2.estimate_amount, 100.0)
        self.assertEqual(self.estimate.subtotal, 150.0)

    def test_manual_amount_wins_over_computed(self):
        """手動輸入後，數量與單價變動都不得覆蓋手動值"""
        self.line.write({'estimate_amount': 88.0})
        self.assertTrue(self.line.is_amount_manual)
        self.assertEqual(self.line.manual_estimate_amount, 88.0)

        self.line.write({'estimate_qty': 7.0})
        self.assertEqual(
            self.line.estimate_amount, 88.0,
            '改數量後手動金額被系統計算值覆蓋',
        )
        self.line.write({'unit_price': 20.0})
        self.assertEqual(
            self.line.estimate_amount, 88.0,
            '改單價後手動金額被系統計算值覆蓋',
        )

        # 總金額／累計金額／彙總項金額都要沿用手動值
        self.assertEqual(self.estimate.subtotal, 88.0 + 100.0)
        self.assertEqual(self.line.cumulative_estimate_amount, 88.0)
        self.assertEqual(self.summary_line.estimate_amount, 88.0)

    def test_clear_manual_flag_restores_computed(self):
        """清掉手動旗標 → 還原為 單價 × 數量（精靈走的就是這條路）"""
        self.line.write({'estimate_amount': 88.0})
        self.line.write({'is_amount_manual': False})
        self.assertEqual(self.line.estimate_amount, 50.0)
        self.assertEqual(self.estimate.subtotal, 150.0)

    def test_form_amount_then_qty(self):
        """editable list：先輸入金額、再改數量，金額不得被吃掉"""
        form = Form(self.estimate)
        idx = list(self.estimate.line_ids).index(self.line)
        with form.line_ids.edit(idx) as line:
            line.estimate_amount = 999.0
            self.assertTrue(line.is_amount_manual)
            line.estimate_qty = 7.0
            self.assertEqual(
                line.estimate_amount, 999.0,
                '同一次編輯中改數量，把剛輸入的手動金額重算掉',
            )
        form.save()
        self.line.invalidate_recordset()
        self.assertEqual(self.line.estimate_amount, 999.0)
        self.assertEqual(self.line.estimate_qty, 7.0)

    def test_form_typing_computed_value_is_not_manual(self):
        """輸入的值恰等於系統計算值 → 視為未覆寫（可用來解除手動）"""
        form = Form(self.estimate)
        idx = list(self.estimate.line_ids).index(self.line)
        with form.line_ids.edit(idx) as line:
            line.estimate_amount = 50.0
            self.assertFalse(line.is_amount_manual)

    # === 解除手動金額 精靈 ===
    def _set_manual(self):
        self.line.write({'estimate_amount': 111.0})
        self.line2.write({'estimate_amount': 222.0})
        self.estimate.invalidate_recordset()

    def test_wizard_button_only_when_manual_lines_exist(self):
        """沒有手動金額工項時，按鈕不顯示（count=0）且直接叫用會擋下"""
        self.assertEqual(self.estimate.manual_amount_line_count, 0)
        with self.assertRaises(UserError):
            self.estimate.action_open_manual_amount_wizard()
        self._set_manual()
        self.assertEqual(self.estimate.manual_amount_line_count, 2)
        action = self.estimate.action_open_manual_amount_wizard()
        self.assertEqual(action['res_model'], 'estimate.manual.amount.wizard')
        self.assertEqual(action['target'], 'new')

    def test_wizard_lists_manual_lines_with_amounts(self):
        """精靈只列手動金額工項，並顯示系統計算值與差額"""
        self._set_manual()
        wiz_form = Form(self.env['estimate.manual.amount.wizard'].with_context(
            default_estimate_id=self.estimate.id))
        self.assertEqual(len(wiz_form.line_ids), 2)
        with wiz_form.line_ids.edit(0) as wline:
            self.assertEqual(wline.manual_amount, 111.0)
            self.assertEqual(wline.auto_amount, 50.0)
            self.assertEqual(wline.diff_amount, 61.0)
            self.assertTrue(wline.to_clear, '預設應全部勾選')

    def test_wizard_clears_selected_keeps_unselected(self):
        """只解除勾選的工項，未勾選者保留手動金額"""
        self._set_manual()
        wiz_form = Form(self.env['estimate.manual.amount.wizard'].with_context(
            default_estimate_id=self.estimate.id))
        # 找出第二個工項那一列並取消勾選
        for idx in range(len(wiz_form.line_ids)):
            with wiz_form.line_ids.edit(idx) as wline:
                if wline.manual_amount == 222.0:
                    wline.to_clear = False
        self.assertEqual(wiz_form.selected_count, 1)
        wizard = wiz_form.save()
        wizard.action_clear()

        self.line.invalidate_recordset()
        self.line2.invalidate_recordset()
        self.estimate.invalidate_recordset()
        self.assertFalse(self.line.is_amount_manual)
        self.assertEqual(self.line.estimate_amount, 50.0, '勾選者未還原為系統計算值')
        self.assertTrue(self.line2.is_amount_manual)
        self.assertEqual(self.line2.estimate_amount, 222.0, '未勾選者的手動金額被誤清')
        self.assertEqual(self.estimate.manual_amount_line_count, 1)
        self.assertEqual(self.estimate.subtotal, 50.0 + 222.0)

    def test_wizard_guards(self):
        """一個都沒勾、以及已核定的估驗單，都要擋下"""
        self._set_manual()
        wizard = self.env['estimate.manual.amount.wizard'].with_context(
            default_estimate_id=self.estimate.id).create({})
        self.assertEqual(len(wizard.line_ids), 2)
        wizard.action_unselect_all()
        with self.assertRaises(UserError):
            wizard.action_clear()

        wizard.action_select_all()
        self.assertEqual(wizard.selected_count, 2)
        self.estimate.write({'state': 'approved'})
        with self.assertRaises(UserError):
            wizard.action_clear()
