# -*- coding: utf-8 -*-
"""施工日誌明細的 14 天鎖定守衛（2026-11-16）：鎖定日誌的明細不能新增／修改／刪除，也不能退回編輯。

測試全在同一個交易裡，守衛把「本交易剛建立的日誌」視為未鎖定（補登舊日期用），
所以要模擬「以前就建好的日誌」得把 create_date 往前移（_created_earlier）。
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
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
        env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.task = env['project.task'].create({
            'name': '明細鎖定工項', 'project_id': cls.project.id, 'item_no': 'LL-001',
            'unit': '式', 'planned_qty': 100.0, 'unit_price': 0.0})
        # 搬移測試用的第二個工項：同一張日誌同一工項不能重複（_check_unique_work_item），
        # 若搬移的列跟目標日誌既有的列同工項，會先被那個約束擋下，測不到鎖定守衛
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

    def _locked(self):
        """回傳 (日誌, 明細)：日誌 20 天前、以前就建好、未解鎖。"""
        sheet = self._sheet(20)
        line = self._line(sheet)
        self._created_earlier(sheet)
        self.assertTrue(sheet._is_edit_locked(), '前提：日誌已鎖定')
        return sheet, line

    def test_write_qty_on_locked_sheet_blocked(self):
        _sheet, line = self._locked()
        with self.assertRaises(UserError):
            line.write({'daily_qty': 99.0})
        line.invalidate_recordset()
        self.assertEqual(line.daily_qty, 5.0)

    def test_unlink_on_locked_sheet_blocked(self):
        _sheet, line = self._locked()
        with self.assertRaises(UserError):
            line.unlink()
        self.assertTrue(line.exists())

    def test_remove_from_sheet_button_blocked(self):
        _sheet, line = self._locked()
        with self.assertRaises(UserError):
            line.action_remove_from_sheet()
        self.assertTrue(line.exists())

    def test_create_on_locked_sheet_blocked(self):
        sheet, _line = self._locked()
        with self.assertRaises(UserError):
            self._line(sheet, qty=1.0, entry_type='extra', work_item_id=False, custom_name='新增項')

    def test_create_with_default_sheet_context_blocked(self):
        """sheet_id 來自 context 的 default_sheet_id（RPC／with_context 直接呼叫）也要擋。

        審查 2026-11-16 重現：守衛原本只看建立前的 vals，default_sheet_id 在 super().create() 裡才補上，看不到。"""
        sheet, _line = self._locked()
        with self.assertRaisesRegex(UserError, '已鎖定'):
            self.env['daily.log.line'].with_context(default_sheet_id=sheet.id).create({
                'name': '預設日誌繞過測試', 'entry_type': 'extra', 'custom_name': '預設日誌繞過測試',
                'date': sheet.log_date})
        sheet.invalidate_recordset(['line_ids'])
        self.assertEqual(len(sheet.line_ids), 1, '鎖定日誌不能多出明細')

    def test_move_line_in_or_out_of_locked_sheet_blocked(self):
        # 兩張各自的鎖定日誌（不同天，避開同一人同一天的檢查）；搬去的目標日誌都沒有同工項、
        # 日期一併改成目標日誌的日期 → 能擋下來的只剩鎖定守衛。斷言訊息確認是它擋的（ValidationError 也是 UserError）
        locked_out, out_line = self._locked()               # 20 天前，工項 LL-001
        empty_target = self._sheet(2)                       # 沒有明細
        with self.assertRaisesRegex(UserError, '已鎖定'):    # 搬出鎖定日誌
            out_line.write({'sheet_id': empty_target.id, 'date': empty_target.log_date})
        self.assertEqual(out_line.sheet_id, locked_out)

        locked_in = self._created_earlier(self._sheet(21))  # 21 天前，沒有明細
        self.assertTrue(locked_in._is_edit_locked(), '前提：日誌已鎖定')
        young = self._sheet(1)
        young_line = self._line(young, qty=2.0, work_item_id=self.task_move.id)
        with self.assertRaisesRegex(UserError, '已鎖定'):    # 搬進鎖定日誌
            young_line.write({'sheet_id': locked_in.id, 'date': locked_in.log_date})
        self.assertEqual(young_line.sheet_id, young)

    def test_revert_to_draft_blocked_when_locked(self):
        """含「滿 14 天、state 仍是 filled、排程還沒跑」：不能看 state。"""
        sheet, _line = self._locked()
        sheet.write({'state': 'filled'})
        with self.assertRaises(UserError):
            sheet.action_revert_to_draft()
        self.assertEqual(sheet.state, 'filled')
        sheet.write({'state': 'auto_locked'})
        with self.assertRaises(UserError):
            sheet.action_revert_to_draft()
        self.assertEqual(sheet.state, 'auto_locked')

    def test_valid_temp_unlock_allows_everything(self):
        sheet, line = self._locked()
        sheet.write({'is_unlocked': True, 'unlock_expires_at': fields.Datetime.now() + timedelta(hours=2)})
        line.write({'daily_qty': 7.0})
        self.assertEqual(line.daily_qty, 7.0)
        self._line(sheet, qty=1.0, entry_type='extra', work_item_id=False, custom_name='解鎖後新增')
        line.unlink()
        sheet.write({'state': 'filled'})
        sheet.action_revert_to_draft()
        self.assertEqual(sheet.state, 'draft')

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

    def test_cumulative_recompute_not_blocked_on_locked_sheet(self):
        """在較新日誌補一列時，鎖定日誌舊列的累計重算不被守衛擋下。"""
        locked, line_old = self._locked()
        young = self._sheet(1)
        self._line(young, qty=10.0)
        line_old.invalidate_recordset(['cumulative_qty'])
        self.assertEqual(line_old.cumulative_qty, 5.0)
        young_earlier = self._sheet(25)   # 較早日期的新日誌（同交易，放行）
        self._line(young_earlier, qty=3.0)
        line_old.invalidate_recordset(['cumulative_qty'])
        self.assertEqual(line_old.cumulative_qty, 8.0)
