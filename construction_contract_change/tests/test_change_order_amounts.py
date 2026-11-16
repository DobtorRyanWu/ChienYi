# -*- coding: utf-8 -*-
"""契約變更單的「變更前／變更後契約金額」（2026-11-16，18.0.2.5.0）。

正確的定義：
  已套用的單 —— 變更前＝這張單套用之前一刻的契約金額、變更後＝套用之後一刻；
                「之前」照變更編號（建立先後，同一天照建立先後）。
  還沒套用的單 —— 變更前＝工程現在的契約金額（已套用的都算進去）。

舊程式兩個錯（正式站 112-07-AEG、111-10-AEG、111-09-AEG 打出來的）：
  ① 算「變更前」時拿工程**今天**的累計調整、只扣掉自己這一張 →
     前面那張的數字被算進後面才發生的調整金額（不管匯入或畫面精靈都會）。
  ② 只調上限、工項不動的單由匯入工具建 —— 工具先套用、套用後才補
     「壹 發包工程費」那一列，補的時候不含調整金額 → 變更後少了那筆錢。
     匯入工具鎖住不改，所以由模組在套用時自己補那一列（含調整），
     工具看到已經有彙總列就跳過自己那一步。

下面五種情況（A～E）照 pg18 實驗（db_backups\\契約變更單金額分析_20261116\\exp_chg.py）寫成測試，
在舊程式上 A～E 會失敗、F 找不到 migration 也會失敗；G 是防退化（舊程式也過）。
"""

import importlib.util
import os

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

MIGRATION = os.path.join(os.path.dirname(__file__), '..', 'migrations',
                         '18.0.2.5.0', 'post-migrate.py')


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestChangeOrderAmounts(TransactionCase):

    # ── 共用 ────────────────────────────────────────────────────────
    def _project(self, code, base):
        project = self.env['project.project'].create({
            'name': '變更前後測試 ' + code, 'code': code,
            'project_type': 'general', 'state': 'construction',
            'company_id': self.env.company.id})
        Task = self.env['project.task']
        top = Task.create({'name': '發包工程費', 'project_id': project.id, 'item_no': '壹'})
        leaf = Task.create({'name': '工項A', 'project_id': project.id, 'item_no': '一',
                            'parent_id': top.id, 'planned_qty': 1.0, 'unit_price': base,
                            'unit': '式'})
        return project, top, leaf

    def _order(self, project, date, **vals):
        vals.update({'project_id': project.id, 'change_date': date,
                     'change_reason': 'other', 'other_reason_detail': '測試'})
        return self.env['contract.change.order'].create(vals)

    @staticmethod
    def _drive(order):
        order.action_submit()
        order.action_review()
        order.action_approve()
        order.action_apply()

    @staticmethod
    def _top_amount(project):
        tops = project.task_ids.filtered(lambda t: t.active and not t.parent_id)
        return round(tops.planned_amount, 2) if len(tops) == 1 else None

    def _engine_add_top(self, order, project, amount_before):
        """照抄鎖住的匯入工具 `3_匯入_引擎.py` 的 add_top_summary_line（AppsScript 法的
        addTopSummaryLine_ 同一套）：已經有彙總列就跳過；否則補一列，新金額＝套用後頂層工項金額。"""
        if order.line_ids.filtered('is_summary_line'):
            return 'skip'
        tops = project.task_ids.filtered(lambda t: t.active and not t.parent_id)
        top = tops
        self.env['contract.change.order.line'].create({
            'change_order_id': order.id, 'task_id': top.id,
            'item_no': top.item_no or '', 'item_name': top.name or '',
            'unit': top.unit or '', 'is_summary_line': True,
            'original_qty': 1.0, 'original_unit_price': round(amount_before, 2),
            'new_qty': 1.0, 'new_unit_price': round(top.planned_amount, 2)})
        return 'added'

    def _import_order(self, project, date, lump=0.0, lines=None):
        """照匯入工具步驟 8 的順序：建單 → 讀套用前頂層金額 → 套用 → 補頂層彙總列。"""
        vals = {'line_ids': lines or []}
        if lump:
            vals['lump_adjust_amount'] = lump
        order = self._order(project, date, **vals)
        before = self._top_amount(project)
        self._drive(order)
        return order, self._engine_add_top(order, project, before)

    def _wizard_order(self, project, leaf, date, new_qty=None, lump=0.0):
        """畫面上的精靈：匯入工程案件 → 改數量／填調整 → 確認 → 一路套用。"""
        order = self._order(project, date)
        wiz = self.env['contract.change.wizard'].create(
            {'change_order_id': order.id, 'project_id': project.id})
        wiz._onchange_project_id()
        if new_qty is not None:
            wl = wiz.wizard_line_ids.filtered(lambda l: l.task_id == leaf)
            wl.change_type = 'modify'
            wl.new_qty = new_qty
        if lump:
            wiz.lump_adjust_amount = lump
        wiz.action_confirm()
        self._drive(order)
        return order

    def _assert_amounts(self, project, expected):
        """expected：照變更編號排的 [(變更前, 變更後), …]；本次變更＝兩者相減。"""
        self.env.flush_all()
        orders = project.change_order_ids.sorted(lambda o: (o.change_no, o.id))
        self.assertEqual(len(orders), len(expected))
        for order, (before, after) in zip(orders, expected):
            label = '%s（第 %s 次，%s）' % (order.name, order.change_no, order.state)
            self.assertAlmostEqual(order.original_contract_amount, before, places=2,
                                   msg='%s 變更前應 %s，得 %s' % (label, before, order.original_contract_amount))
            self.assertAlmostEqual(order.new_contract_amount, after, places=2,
                                   msg='%s 變更後應 %s，得 %s' % (label, after, order.new_contract_amount))
            self.assertAlmostEqual(order.change_amount, after - before, places=2,
                                   msg='%s 本次變更應 %s，得 %s' % (label, after - before, order.change_amount))

    # ── A：112-07-AEG 的匯入路徑 ─────────────────────────────────────
    def test_a_import_items_then_lump_only(self):
        """第 1 次只新增不計入的項目、第 2 次只調上限 +3,500,000（工項不動），都照匯入工具建。

        舊程式：第 1 次 18,420,000 → 18,420,000（把第 2 次的調整算進去）、
                第 2 次 14,920,000 → 14,920,000、本次 0（調整沒有進那一列）。"""
        project, top, leaf = self._project('AMT-A', 14920000.0)
        o1, step1 = self._import_order(project, '2023-10-06', lines=[Command.create({
            'change_type': 'add', 'item_name': '試驗A', 'item_no': '1', 'unit': '組',
            'parent_task_id': top.id, 'new_qty': 1.0, 'new_unit_price': 800.0,
            'exclude_from_contract_amount': True})])
        o2, step2 = self._import_order(project, '2023-10-26', lump=3500000.0)
        self._assert_amounts(project, [(14920000.0, 14920000.0), (14920000.0, 18420000.0)])
        self.assertAlmostEqual(project.contract_amount, 18420000.0, places=2)
        # 模組自己補了「壹」那一列（含調整），匯入工具那一步因此跳過
        self.assertEqual((step1, step2), ('skip', 'skip'),
                         '套用時模組沒有自己補頂層彙總列，匯入工具又補了一列不含調整的')
        top2 = o2.line_ids.filtered(lambda l: l.item_level == 0 and l.is_summary_line)
        self.assertEqual(len(top2), 1)
        self.assertAlmostEqual(top2.original_amount, 14920000.0, places=2)
        self.assertAlmostEqual(top2.new_amount, 18420000.0, places=2,
                               msg='「壹 發包工程費」那一列的新金額要含調整 3,500,000')
        self.assertAlmostEqual(o2.cumulative_change_amount, 3500000.0, places=2,
                               msg='採購法 50% 累計變更要算到這 3,500,000')

    # ── B：111-09-AEG 的畫面路徑 ─────────────────────────────────────
    def test_b_form_lump_only_three_times(self):
        """三張都只在變更單表單填調整金額（沒有明細）。

        舊程式：第 1 次 12,710,000 → 16,580,000、第 2 次 16,370,000 → 16,580,000（只有最後一張對）。"""
        project, top, leaf = self._project('AMT-B', 8500000.0)
        for i, (date, lump) in enumerate([('2022-07-04', 3870000.0), ('2022-09-15', 210000.0),
                                          ('2022-11-15', 4000000.0)]):
            extra = {'is_limit_exempt': True, 'exempt_reason': '測試：依其他法源'} if i == 0 else {}
            self._drive(self._order(project, date, lump_adjust_amount=lump, **extra))
        self._assert_amounts(project, [(8500000.0, 12370000.0), (12370000.0, 12580000.0),
                                       (12580000.0, 16580000.0)])

    # ── C：畫面精靈路徑 ──────────────────────────────────────────────
    def test_c_wizard_items_then_lump(self):
        """第 1 次用精靈改工項 +1,000,000、第 2 次用精靈只調上限 +2,000,000。

        舊程式：第 1 次 12,000,000 → 13,000,000（第一個錯不是只有匯入的案子才有）。"""
        project, top, leaf = self._project('AMT-C', 10000000.0)
        self._wizard_order(project, leaf, '2024-01-01', new_qty=1.1)
        self._wizard_order(project, leaf, '2024-02-01', lump=2000000.0)
        self._assert_amounts(project, [(10000000.0, 11000000.0), (11000000.0, 13000000.0)])

    # ── D：只填表單的調整、之後別張單改了工項 ──────────────────────────
    def test_d_form_lump_then_wizard_items(self):
        """第 1 次只在表單調 +100,000（沒有明細）、第 2 次用精靈改工項 +200,000。

        舊程式：第 1 次 1,200,000 → 1,300,000（沒有明細可以記住當時的工項合計，跟著後面漂）。"""
        project, top, leaf = self._project('AMT-D', 1000000.0)
        self._drive(self._order(project, '2024-01-01', lump_adjust_amount=100000.0))
        self._wizard_order(project, leaf, '2024-02-01', new_qty=1.2)
        self._assert_amounts(project, [(1000000.0, 1100000.0), (1100000.0, 1300000.0)])

    # ── E：同一天兩張＋一張草稿 ────────────────────────────────────────
    def test_e_same_day_then_draft(self):
        """同一天兩張只調上限（+300,000、+200,000，匯入路徑），之後一張草稿 +50,000。

        同一天照建立先後排（＝變更編號）；草稿的變更前＝工程現在的契約金額。"""
        project, top, leaf = self._project('AMT-E', 2000000.0)
        self._import_order(project, '2024-03-01', lump=300000.0)
        self._import_order(project, '2024-03-01', lump=200000.0)
        self._order(project, '2024-04-01', lump_adjust_amount=50000.0)
        self._assert_amounts(project, [(2000000.0, 2300000.0), (2300000.0, 2500000.0),
                                       (2500000.0, 2550000.0)])

    # ── F：migration 會把存著的舊值重算 ───────────────────────────────
    def test_f_migration_recomputes_stored_values(self):
        """這四個金額存在資料庫裡，-u 不會自己重算 → migration 要把它們重算一次。"""
        project, top, leaf = self._project('AMT-F', 8500000.0)
        for i, (date, lump) in enumerate([('2022-07-04', 3870000.0), ('2022-09-15', 210000.0)]):
            extra = {'is_limit_exempt': True, 'exempt_reason': '測試：依其他法源'} if i == 0 else {}
            self._drive(self._order(project, date, lump_adjust_amount=lump, **extra))
        self.env.flush_all()
        ids = tuple(project.change_order_ids.ids)
        # 弄成升級前資料庫裡的樣子（舊程式算的值）
        self.env.cr.execute(
            'UPDATE contract_change_order SET original_contract_amount = 12710000, '
            'new_contract_amount = 16580000, change_amount = 3870000 WHERE id IN %s', [ids])
        self.env.invalidate_all()
        self.assertTrue(os.path.exists(MIGRATION), '找不到 migrations/18.0.2.5.0/post-migrate.py')
        spec = importlib.util.spec_from_file_location('chg_amount_post_migrate_250', MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '18.0.2.4.1')
        self.env.invalidate_all()
        self._assert_amounts(project, [(8500000.0, 12370000.0), (12370000.0, 12580000.0)])

    # ── G：精靈做的單不會多一列（防退化，舊程式也過）──────────────────
    def test_g_wizard_order_gets_no_extra_top_line(self):
        """精靈本來就會建「壹」那一列 → 套用時模組不可以再補一列。"""
        project, top, leaf = self._project('AMT-G', 10000000.0)
        o1 = self._wizard_order(project, leaf, '2024-01-01', new_qty=1.1)
        o2 = self._wizard_order(project, leaf, '2024-02-01', lump=2000000.0)
        for order in (o1, o2):
            tops = order.line_ids.filtered(lambda l: l.item_level == 0 and l.task_id == top)
            self.assertEqual(len(tops), 1, '%s 頂層彙總列應該只有 1 列，得 %s 列' % (order.name, len(tops)))
