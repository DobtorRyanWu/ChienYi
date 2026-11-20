# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：施工日誌不再因為超過 14 天而鎖定。

舊系統（EAGLE）的日誌沒有鎖定：前後端原始碼搜尋 鎖定／lock／unlock 都是 0 筆，
修改（PATCH /daily-record/:id）與刪除（DELETE）都不看日期。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（DL-05 ～ DL-12）。

這支測三件「拿掉鎖之後還要成立」的事：
1. 排程仍然會把滿 14 天還在編輯中的日誌標成已填寫（不然補登、匯入的舊日誌不會算進累計與可估驗數量），
   但標完還是能改。
2. 升級時既有「自動鎖定」的日誌改回「已填寫」、鎖定標記清掉；手動「已鎖定」不動。
3. 工項實際完成數量在狀態換成已填寫前後不變（兩種狀態在計算裡等價）。
明細、材料列的部分在 test_line_lock_guard.py、test_contract_material.py。
"""
import importlib.util
import os
from datetime import timedelta

from odoo import fields
from odoo.modules.module import get_module_path
from odoo.tests.common import TransactionCase, tagged

MIGRATION_VERSION = '18.0.2.15.0'
INSTALLED_VERSION = '18.0.2.14.0'      # 升級前資料庫裡的版本；migrate() 收到 None 代表新裝，直接跳過
CRON_XMLID = 'construction_daily_log.ir_cron_auto_lock_daily_logs'


def _load_migration():
    path = os.path.join(get_module_path('construction_daily_log'), 'migrations', MIGRATION_VERSION, 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('daily_log_unlock_post_migrate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestEagleParityNoLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.project = env['project.project'].create({
            'name': '回復原版－日誌不鎖定', 'code': 'EP-NOLOCK', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        cls.employee = env['hr.employee'].create({'name': '回復原版日誌員工', 'company_id': env.company.id})
        cls.task = env['project.task'].create({
            'name': '回復原版工項', 'project_id': cls.project.id, 'item_no': 'EP-001',
            'unit': 'M', 'planned_qty': 100.0, 'unit_price': 10.0})

    def _sheet(self, days_ago, **vals):
        return self.env['daily.log.sheet'].create(dict({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today() - timedelta(days=days_ago)}, **vals))

    def _force(self, sheet, **cols):
        """直接改資料庫欄位，做出升級前的舊資料（繞過 ORM，不觸發任何守衛或重算）。"""
        self.env.flush_all()
        sets = ', '.join('%s = %%s' % c for c in cols)
        self.env.cr.execute('UPDATE daily_log_sheet SET %s WHERE id = %%s' % sets, list(cols.values()) + [sheet.id])
        sheet.invalidate_recordset()

    # ------------------------------------------------------------------ 排程
    def test_cron_marks_old_drafts_filled_and_they_stay_editable(self):
        old_draft = self._sheet(20)
        young_draft = self._sheet(3)
        self.env['daily.log.sheet']._cron_auto_lock()
        self.assertEqual(old_draft.state, 'filled', '滿 14 天的編輯中日誌要自動標成已填寫')
        self.assertEqual(young_draft.state, 'draft', '未滿 14 天的不動')
        self.assertFalse(old_draft.is_locked)
        old_draft.write({'notes': '排程跑過之後還能改'})
        self.assertEqual(old_draft.notes, '排程跑過之後還能改')
        old_draft.action_revert_to_draft()
        self.assertEqual(old_draft.state, 'draft')

    def test_cron_leaves_filled_and_legacy_states_alone(self):
        filled = self._sheet(20, state='filled')
        legacy = self._sheet(21, state='locked')
        self.env['daily.log.sheet']._cron_auto_lock()
        self.assertEqual((filled.state, legacy.state), ('filled', 'locked'))

    # ------------------------------------------------------------------ 升級整理舊資料
    def test_migration_turns_auto_locked_into_filled(self):
        auto = self._sheet(30)
        manual = self._sheet(31)
        draft = self._sheet(2)
        line = self.env['daily.log.line'].create({
            'sheet_id': auto.id, 'entry_type': 'contract', 'work_item_id': self.task.id,
            'daily_qty': 7.0, 'date': auto.log_date})
        auto.write({'state': 'auto_locked'})          # 走 ORM：明細的狀態複本、工項實際完成數量都照舊規則算好
        self._force(auto, is_locked=True)
        self._force(manual, state='locked', state_sequence=4, is_locked=True)
        self.assertEqual((auto.state, auto.is_locked, line.sheet_state), ('auto_locked', True, 'auto_locked'),
                         '前提：做出升級前的資料')
        qty_before = self.task.actual_qty
        self.assertEqual(qty_before, 7.0, '前提：自動鎖定的日誌有算進工項實際完成數量')
        cron = self.env.ref(CRON_XMLID)
        cron.name = '施工日誌 - 自動鎖定（14天規則）'

        _load_migration().migrate(self.env.cr, INSTALLED_VERSION)
        self.env.invalidate_all()

        self.assertEqual((auto.state, auto.state_sequence, auto.is_locked), ('filled', 2, False))
        self.assertEqual((manual.state, manual.is_locked), ('locked', False), '手動「已鎖定」狀態不動，但不再鎖')
        self.assertEqual((draft.state, draft.is_locked), ('draft', False))
        self.assertNotIn('鎖定', cron.name)
        self.assertEqual(line.sheet_state, 'filled', '明細上的狀態複本要跟著改')
        self.assertEqual(line.cumulative_qty, 7.0)
        self.assertEqual(self.task.actual_qty, qty_before, '自動鎖定與已填寫在計算裡等價，升級前後不能變')
        # 升級後這張舊日誌可以改、可以刪
        auto.write({'notes': '升級後補記'})
        auto.unlink()
        self.assertFalse(auto.exists())

    def test_migration_skips_fresh_install(self):
        auto = self._sheet(30)
        self._force(auto, state='auto_locked', state_sequence=3, is_locked=True)
        _load_migration().migrate(self.env.cr, None)
        self.env.invalidate_all()
        self.assertEqual(auto.state, 'auto_locked', '新裝（version 是 None）時不動資料')


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestEagleParityDailyQty(TransactionCase):
    """DL-16：本日完成數量可以是負數（舊系統只夾上限、沒有下限）。"""

    def test_negative_daily_qty_allowed(self):
        env = self.env
        project = env['project.project'].create({
            'name': '回復原版日誌數量', 'code': 'EP-DL-Q', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        employee = env['hr.employee'].create({'name': '回復原版數量員工', 'company_id': env.company.id})
        task = env['project.task'].create({
            'name': '回復原版數量工項', 'project_id': project.id, 'item_no': 'EPQ-1',
            'unit': 'M', 'planned_qty': 100.0, 'unit_price': 10.0})
        sheet = env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': env.company.id,
            'employee_id': employee.id, 'log_date': fields.Date.today() - timedelta(days=1)})
        line = env['daily.log.line'].create({
            'sheet_id': sheet.id, 'entry_type': 'contract', 'work_item_id': task.id,
            'daily_qty': -3.0, 'date': sheet.log_date})
        env.flush_all()
        self.assertEqual(line.daily_qty, -3.0)
