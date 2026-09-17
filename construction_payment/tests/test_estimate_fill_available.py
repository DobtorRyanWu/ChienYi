# -*- coding: utf-8 -*-
"""估驗計價：「帶入可估驗數量」精靈（estimate.fill.available.wizard）。

把系統依施工日誌算出的本次可估驗數量(available_qty)預覽後寫入本次估驗數量(estimate_qty)，
免去承辦逐列重打。鎖定行為：
1. 空白（estimate_qty == 0）且可估量 > 0 的列，預設勾選並可正確帶入
2. 已填（estimate_qty != 0）的列，預設不勾選、套用後維持原值不動
3. 彙總項（is_summary_item）恆為 1.0，硬跳過、不出現在候選清單、不受套用影響
4. 金額手動輸入（is_amount_manual）的旗標不因本精靈寫入 estimate_qty 而被翻動
5. estimate_amount 只能透過 store compute 由 estimate_qty 自動跟上，
   本精靈全程只寫 estimate_qty 一個鍵，絕不顯式寫 estimate_amount
6. 已核定的估驗單一律擋下（UserError）
"""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEstimateFillAvailable(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '帶入可估驗數量測試工程',
            'code': 'EST-FILL',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.company.id,
        })
        # 建立日誌前專案須有「使用中」進度表（construction_progress 約束，
        # 見 construction_daily_log/tests/test_lock_and_cumulative.py 的同款前置）
        cls.schedule = cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        })
        cls.schedule.write({'state': 'active'})
        cls.employee = cls.env['hr.employee'].create({
            'name': '帶入測試員工',
            'company_id': cls.company.id,
        })

        cls.parent_task = cls.env['project.task'].create({
            'name': '彙總群組',
            'project_id': cls.project.id,
            'item_no': '1',
            'unit': '式',
            'planned_qty': 1.0,
            'unit_price': 0.0,
        })
        cls.task_blank = cls.env['project.task'].create({
            'name': '空白工項',
            'project_id': cls.project.id,
            'parent_id': cls.parent_task.id,
            'item_no': '1.1',
            'unit': 'm3',
            'planned_qty': 100.0,
            'unit_price': 10.0,
        })
        cls.task_filled = cls.env['project.task'].create({
            'name': '已填工項',
            'project_id': cls.project.id,
            'item_no': '2',
            'unit': 'm2',
            'planned_qty': 50.0,
            'unit_price': 20.0,
        })
        cls.task_manual = cls.env['project.task'].create({
            'name': '金額手動工項',
            'project_id': cls.project.id,
            'item_no': '3',
            'unit': 'm',
            'planned_qty': 20.0,
            'unit_price': 5.0,
        })

        cls.today = fields.Date.today()
        cls.estimate = cls.env['payment.estimate'].create({
            'project_id': cls.project.id,
            'estimate_date': cls.today,
        })
        cls.summary_line = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.parent_task.id,
            'estimate_qty': 1.0,
            'unit_price': 0.0,
        })
        cls.line_blank = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.task_blank.id,
            'estimate_qty': 0.0,
            'unit_price': 10.0,
        })
        cls.line_filled = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.task_filled.id,
            'estimate_qty': 8.0,
            'unit_price': 20.0,
        })
        cls.line_manual = cls.env['payment.estimate.line'].create({
            'estimate_id': cls.estimate.id,
            'task_id': cls.task_manual.id,
            'estimate_qty': 0.0,
            'unit_price': 5.0,
        })
        # 模擬使用者手動改過金額（write() 覆寫會自動標記 is_amount_manual）
        cls.line_manual.write({'estimate_amount': 99.0})

        # 施工日誌：同一專案同一天只能有一張日誌（_check_overlapping_sheets
        # 鍵為 log_date+employee_id+company_id+supervision_project_id），
        # 故三個葉節點的明細合掛同一張已確認（filled）日誌。
        cls._make_confirmed_sheet([
            (cls.task_blank, 30.0),
            (cls.task_filled, 15.0),
            (cls.task_manual, 12.0),
        ])

    @classmethod
    def _make_confirmed_sheet(cls, task_qty_pairs):
        """建一張當日、已標記「已填寫」的施工日誌，掛多筆契約工項明細"""
        sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': cls.company.id,
            'employee_id': cls.employee.id,
            'log_date': cls.today,
        })
        for task, qty in task_qty_pairs:
            cls.env['daily.log.line'].create({
                'sheet_id': sheet.id,
                'work_item_id': task.id,
                'entry_type': 'contract',
                'daily_qty': qty,
                'date': sheet.log_date,
            })
        sheet.action_mark_filled()
        return sheet

    def _open_wizard(self):
        return self.env['estimate.fill.available.wizard'].with_context(
            default_estimate_id=self.estimate.id).create({})

    def test_blank_line_gets_filled(self):
        """空白且可估量 > 0 的列，預設勾選並可正確帶入"""
        self.line_blank.invalidate_recordset()
        self.assertEqual(self.line_blank.available_qty, 30.0)
        wizard = self._open_wizard()
        wline = wizard.line_ids.filtered(lambda l: l.estimate_line_id == self.line_blank)
        self.assertTrue(wline.to_apply, '空白且可估量 > 0 應預設勾選')
        wizard.action_fill_available_qty()
        self.line_blank.invalidate_recordset()
        self.assertEqual(self.line_blank.estimate_qty, 30.0)

    def test_filled_line_not_touched_by_default(self):
        """已填列預設不勾選，套用後維持原值不動"""
        wizard = self._open_wizard()
        wline = wizard.line_ids.filtered(lambda l: l.estimate_line_id == self.line_filled)
        self.assertFalse(wline.to_apply, '已填列不應預設勾選')
        wizard.action_fill_available_qty()
        self.line_filled.invalidate_recordset()
        self.assertEqual(self.line_filled.estimate_qty, 8.0, '已填列不應被套用動作改動')

    def test_summary_line_always_one(self):
        """彙總項恆為 1.0，硬跳過、不出現在候選清單、不受套用影響"""
        wizard = self._open_wizard()
        wline = wizard.line_ids.filtered(lambda l: l.estimate_line_id == self.summary_line)
        self.assertFalse(wline, '彙總項不應出現在候選清單')
        wizard.action_fill_available_qty()
        self.summary_line.invalidate_recordset()
        self.assertEqual(self.summary_line.estimate_qty, 1.0)

    def test_is_amount_manual_not_flipped(self):
        """金額手動輸入的旗標不因本精靈寫入 estimate_qty 而被翻動"""
        self.assertTrue(self.line_manual.is_amount_manual)
        wizard = self._open_wizard()
        wline = wizard.line_ids.filtered(lambda l: l.estimate_line_id == self.line_manual)
        self.assertFalse(wline.to_apply, '金額手動列不應預設勾選')
        # 使用者手動勾選覆寫，驗證即使寫入 qty 也不動 is_amount_manual／手動金額
        wline.to_apply = True
        wizard.action_fill_available_qty()
        self.line_manual.invalidate_recordset()
        self.assertEqual(self.line_manual.estimate_qty, 12.0, '手動勾選後應正常寫入 qty')
        self.assertTrue(
            self.line_manual.is_amount_manual,
            '只寫 estimate_qty 不應翻動 is_amount_manual',
        )
        self.assertEqual(
            self.line_manual.manual_estimate_amount, 99.0,
            '手動金額本身不應被本精靈改動',
        )
        self.assertEqual(
            self.line_manual.estimate_amount, 99.0,
            '金額手動列的 estimate_amount 不應因 qty 變動被系統計算值覆蓋',
        )

    def test_estimate_amount_follows_qty(self):
        """estimate_amount 只能透過 store compute 由 estimate_qty 自動跟上"""
        wizard = self._open_wizard()
        wizard.action_fill_available_qty()
        self.line_blank.invalidate_recordset()
        self.assertEqual(
            self.line_blank.estimate_amount,
            self.line_blank.unit_price * self.line_blank.estimate_qty,
        )

    def test_approved_estimate_raises(self):
        """已核定的估驗單一律擋下（精靈動作與開啟精靈的表頭動作皆同）"""
        wizard = self._open_wizard()
        self.estimate.write({'state': 'approved'})
        with self.assertRaises(UserError):
            wizard.action_fill_available_qty()
        with self.assertRaises(UserError):
            self.estimate.action_open_fill_available_wizard()
