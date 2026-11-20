# -*- coding: utf-8 -*-
"""施工日誌明細在「滿 14 天的日誌」底下照樣能新增／修改／刪除／搬移（2026-11-20 回復原版）。

2026-11-16 這支測的是相反的事：鎖定日誌的明細不能動。1118 會議決定回到跟舊系統一樣，
舊系統的日誌沒有鎖定（前後端搜尋 鎖定／lock 都是 0 筆），所以 14 天鎖定整個拿掉，
這裡改成確認「以前會被擋的動作現在都做得成」。檔名沿用，方便對照歷史。

日誌的 create_date 往前移（_created_earlier）是為了模擬「以前就建好的日誌」：
舊守衛把本交易剛建立的日誌視為未鎖定，不往前移的話修改前這些測試也會過，就不算回歸測試了。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestLineLockGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.project = env['project.project'].create({
            'name': '明細鎖定測試工程', 'code': 'DL-LL', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        cls.employee = env['hr.employee'].create({'name': '明細鎖定測試員工', 'company_id': env.company.id})
        cls.task = env['project.task'].create({
            'name': '明細鎖定工項', 'project_id': cls.project.id, 'item_no': 'LL-001',
            'unit': '式', 'planned_qty': 100.0, 'unit_price': 0.0})
        # 搬移測試用的第二個工項：同一張日誌同一工項不能重複（_check_unique_work_item）
        cls.task_move = env['project.task'].create({
            'name': '明細鎖定工項（搬移用）', 'project_id': cls.project.id, 'item_no': 'LL-002',
            'unit': '式', 'planned_qty': 100.0, 'unit_price': 0.0})

    def _sheet(self, days_ago):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today() - timedelta(days=days_ago)})

    def _line(self, sheet, qty=5.0, **extra):
        vals = {'sheet_id': sheet.id, 'entry_type': 'contract', 'work_item_id': self.task.id,
                'daily_qty': qty, 'date': sheet.log_date}
        vals.update(extra)
        return self.env['daily.log.line'].create(vals)

    def _created_earlier(self, sheet):
        self.env.cr.execute(
            "UPDATE daily_log_sheet SET create_date = create_date - interval '30 days' WHERE id = %s", [sheet.id])
        sheet.invalidate_recordset(['create_date'])
        return sheet

    def _old(self):
        """回傳 (日誌, 明細)：日誌 20 天前、以前就建好——修改前這種日誌是鎖定的。"""
        sheet = self._sheet(20)
        line = self._line(sheet)
        self._created_earlier(sheet)
        self.assertFalse(sheet._is_edit_locked(), '滿 14 天的日誌不再鎖定')
        self.assertFalse(sheet.is_locked)
        return sheet, line

    def test_write_qty_on_old_sheet_allowed(self):
        _sheet, line = self._old()
        line.write({'daily_qty': 99.0})
        line.invalidate_recordset()
        self.assertEqual(line.daily_qty, 99.0)

    def test_unlink_on_old_sheet_allowed(self):
        _sheet, line = self._old()
        line.unlink()
        self.assertFalse(line.exists())

    def test_remove_from_sheet_button_allowed(self):
        _sheet, line = self._old()
        line.action_remove_from_sheet()
        self.assertFalse(line.exists())

    def test_create_on_old_sheet_allowed(self):
        sheet, _line = self._old()
        self._line(sheet, qty=1.0, entry_type='extra', work_item_id=False, custom_name='新增項')
        sheet.invalidate_recordset(['line_ids'])
        self.assertEqual(len(sheet.line_ids), 2)

    def test_create_with_default_sheet_context_allowed(self):
        """sheet_id 來自 context 的 default_sheet_id（RPC／with_context 直接呼叫）也一樣可以。"""
        sheet, _line = self._old()
        self.env['daily.log.line'].with_context(default_sheet_id=sheet.id).create({
            'name': '預設日誌測試', 'entry_type': 'extra', 'custom_name': '預設日誌測試', 'date': sheet.log_date})
        sheet.invalidate_recordset(['line_ids'])
        self.assertEqual(len(sheet.line_ids), 2)

    def test_move_line_in_or_out_of_old_sheet_allowed(self):
        old_out, out_line = self._old()                     # 20 天前，工項 LL-001
        empty_target = self._sheet(2)                       # 沒有明細
        out_line.write({'sheet_id': empty_target.id, 'date': empty_target.log_date})    # 搬出舊日誌
        self.assertEqual(out_line.sheet_id, empty_target)

        old_in = self._created_earlier(self._sheet(21))     # 21 天前，沒有明細
        young = self._sheet(1)
        young_line = self._line(young, qty=2.0, work_item_id=self.task_move.id)
        young_line.write({'sheet_id': old_in.id, 'date': old_in.log_date})              # 搬進舊日誌
        self.assertEqual(young_line.sheet_id, old_in)
        self.assertTrue(old_out.exists())

    def test_revert_to_draft_allowed_on_old_sheet(self):
        sheet, _line = self._old()
        sheet.write({'state': 'filled'})
        sheet.action_revert_to_draft()
        self.assertEqual(sheet.state, 'draft')
        # 舊資料可能還掛著「自動鎖定」「已鎖定」：一樣能退回編輯、能再標成已填寫
        for legacy_state in ('auto_locked', 'locked'):
            sheet.write({'state': legacy_state})
            sheet.action_revert_to_draft()
            self.assertEqual(sheet.state, 'draft', legacy_state)
            sheet.write({'state': legacy_state})
            sheet.action_mark_filled()
            self.assertEqual(sheet.state, 'filled', legacy_state)

    def test_old_sheet_itself_editable_and_deletable(self):
        sheet, line = self._old()
        sheet.write({'notes': '滿 14 天後補記'})
        self.assertEqual(sheet.notes, '滿 14 天後補記')
        sheet.unlink()
        self.assertFalse(sheet.exists())
        self.assertFalse(line.exists(), '明細跟著日誌一起刪')

    def test_backfilled_old_sheet_in_same_transaction_can_get_lines(self):
        """補登 20 天前的新日誌（前台／匯入）：日誌與明細同一交易建立，要能成功。"""
        sheet = self._sheet(20)
        line = self._line(sheet)
        line.write({'daily_qty': 6.0})
        self.assertEqual(line.daily_qty, 6.0)
        # 日誌連同 line_ids 一起建立
        s2 = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today() - timedelta(days=30),
            'line_ids': [(0, 0, {'entry_type': 'extra', 'custom_name': '同次建立', 'name': '施工記錄 - 同次建立'})]})
        self.assertEqual(len(s2.line_ids), 1)

    def test_young_sheet_unaffected(self):
        sheet = self._sheet(3)
        line = self._line(sheet)
        self._created_earlier(sheet)
        line.write({'daily_qty': 8.0})
        self._line(sheet, qty=1.0, entry_type='extra', work_item_id=False, custom_name='年輕日誌新增')
        sheet.write({'state': 'filled'})
        sheet.action_revert_to_draft()
        line.unlink()

    def test_line_without_sheet_does_not_crash(self):
        line = self.env['daily.log.line'].create({'name': '無日誌明細', 'entry_type': 'extra', 'custom_name': 'x'})
        line.write({'location': '甲'})
        line.unlink()

    def test_cumulative_recompute_across_old_and_new_sheets(self):
        """在較新、較早的日誌補列時，舊日誌那一列的累計照樣重算。"""
        _old_sheet, line_old = self._old()
        young = self._sheet(1)
        self._line(young, qty=10.0)
        line_old.invalidate_recordset(['cumulative_qty'])
        self.assertEqual(line_old.cumulative_qty, 5.0)
        young_earlier = self._sheet(25)
        self._line(young_earlier, qty=3.0)
        line_old.invalidate_recordset(['cumulative_qty'])
        self.assertEqual(line_old.cumulative_qty, 8.0)
