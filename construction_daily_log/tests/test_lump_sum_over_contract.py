# -*- coding: utf-8 -*-
"""A10 — 「式」工項累計完成量不得超過契約量。

代操 2026-08-06 回報：「1式項項目累計完成數量不得大於1」，
截圖是單位「式」、契約數量 1.0000、本日完成 1.0000、累計完成 **2.0000**。

現況查證（2026-08-07，odoo18_dev）：`is_over_contract` 只用來把列標紅
（`decoration-danger`），完全沒有攔截；關於數量的 constrains 只有 `_check_daily_qty`
擋負數。

範圍是刻意限縮的——**只擋「式」**：
* 1,712 個有日誌的工項中，累計超過契約量的有 118 筆
* 其中單位=式只有 5 筆，非式有 113 筆
* 非式那批大量是「契約量沒匯進來被塞了佔位的 1」（株 契約=1 累計=15100），
  是匯入問題不是填寫問題，硬擋會讓現場因為契約資料錯而填不了日誌
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestLumpSumOverContract(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'A10 測試工程',
            'code': 'A10-TEST',
            'project_type': 'general',
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id, 'version': 1,
            'calculation_mode': 'weekly', 'change_date': '2026-08-01',
            'state': 'active',
        })
        cls.employee = cls.env['hr.employee'].create({'name': 'A10 填表人'})

    def _task(self, unit, planned_qty, item_no='1'):
        return self.env['project.task'].create({
            'name': 'A10 工項 %s' % item_no,
            'project_id': self.project.id,
            'item_no': item_no,
            'unit': unit,
            'planned_qty': planned_qty,
            'unit_price': 100.0,
        })

    def _sheet(self, log_date):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'employee_id': self.employee.id,
            'log_date': log_date,
        })

    def _line(self, sheet, task, qty):
        return self.env['daily.log.line'].create({
            'sheet_id': sheet.id,
            'date': sheet.log_date,
            'entry_type': 'contract',
            'work_item_id': task.id,
            'daily_qty': qty,
        })

    def test_lump_sum_single_line_over_contract_blocked(self):
        """單列就超過契約量 → 擋。"""
        task = self._task('式', 1.0, '1')
        sheet = self._sheet('2026-08-01')
        with self.assertRaises(ValidationError):
            self._line(sheet, task, 2.0)

    def test_lump_sum_cumulative_over_contract_blocked(self):
        """代操回報的原始情境：每期都填 1，第二期累計 2.0 → 擋。"""
        task = self._task('式', 1.0, '2')
        self._line(self._sheet('2026-08-01'), task, 1.0)   # 第一期剛好做滿，允許
        with self.assertRaises(ValidationError):
            self._line(self._sheet('2026-08-02'), task, 1.0)

    def test_lump_sum_exactly_contract_allowed(self):
        """累計剛好等於契約量 → 放行（不是 > 才擋）。"""
        task = self._task('式', 1.0, '3')
        self._line(self._sheet('2026-08-01'), task, 0.6)
        line = self._line(self._sheet('2026-08-02'), task, 0.4)
        self.assertEqual(line.daily_qty, 0.4)

    def test_lump_sum_proportional_entries_allowed(self):
        """正確填法：5 期各 0.2 → 全部放行。"""
        task = self._task('式', 1.0, '4')
        for day in range(1, 6):
            self._line(self._sheet('2026-08-%02d' % day), task, 0.2)
        lines = self.env['daily.log.line'].search([('work_item_id', '=', task.id)])
        self.assertEqual(len(lines), 5)
        self.assertAlmostEqual(sum(lines.mapped('daily_qty')), 1.0, places=4)

    def test_lump_sum_uses_actual_contract_qty_not_hardcoded_one(self):
        """契約量不是 1 的「式」以實際契約量為準，不是寫死 1。"""
        task = self._task('式', 280.0, '5')
        line = self._line(self._sheet('2026-08-01'), task, 200.0)   # < 280，放行
        self.assertEqual(line.daily_qty, 200.0)
        with self.assertRaises(ValidationError):
            self._line(self._sheet('2026-08-02'), task, 100.0)      # 累計 300 > 280

    def test_non_lump_sum_unit_is_not_blocked(self):
        """非「式」單位不擋——超挖／超做是實務常態，且契約資料本身不可靠。"""
        task = self._task('M3', 10.0, '6')
        line = self._line(self._sheet('2026-08-01'), task, 999.0)
        self.assertEqual(line.daily_qty, 999.0)
        self.assertTrue(line.is_over_contract, '仍應標示為超出契約（只是不擋）')

    def test_zero_contract_qty_is_not_blocked(self):
        """契約量為 0（資料未匯入）不擋，否則會因資料問題卡住現場。"""
        task = self._task('式', 0.0, '7')
        line = self._line(self._sheet('2026-08-01'), task, 5.0)
        self.assertEqual(line.daily_qty, 5.0)
