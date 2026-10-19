# -*- coding: utf-8 -*-
"""契約工項估驗明細的「累計估驗金額」＝ 前期各期的本期金額相加 ＋ 本期金額。

原本的寫法是 `單價 × 前期累計數量 ＋ 本期金額`，它假設「前面每一期的錢 ＝
這一期的單價 × 前期數量」。三種情況下這個假設不成立，而且都不會報錯：

1. 單價欄是 0 的工項（自主品管費、稅什費這類整包項／比例項）：
   契約金額放在 xml_amount、單價是 0，每一期只能填手動金額 →
   累計 ＝ 0 × 前期數量 ＋ 本期 ＝ **只剩本期**（淡五第 9 期七 自主管理費
   應為 331,621、顯示 55,442）。
2. 前期填了手動金額：前期的錢是手動值，不是 單價 × 數量。
   「式」工項每期數量都填 1、金額另填的案子（111-09-AEG 3.1）會變成
   單價 × 5 ＋ 本期，**多算好幾倍**。
3. 單價中途改過（契約變更）：改動前的期別要照**當時**的單價，改動後才用
   新單價（使用者裁示 2026-10-19）。估驗明細的單價是建列當下抄的快照，
   所以「各期本期金額相加」自然就是這個意思。

前期的範圍跟「前期已核定累計數量」同一套：排在本期之前（_estimates_before，
與畫面上的「第N次」同一個順序）、而且已核定或已歸檔。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEstimateCumulativeAmount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '累計估驗金額測試工程',
            'code': 'EST-CUMAMT',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']
        cls.root = Task.create({
            'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹',
            'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
        })
        cls.normal = Task.create({
            'name': '一般工項', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '一', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 10.0,
        })
        cls.lump = Task.create({
            'name': '自主品管費', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '二', 'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
            'xml_amount': 500000.0, 'is_lump_sum': True,
        })
        cls.d0 = fields.Date.today() - timedelta(days=90)

    # === 工具 ===
    def _estimate(self, days):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': self.d0 + timedelta(days=days),
        })
        Line = self.env['payment.estimate.line']
        vals = Line._prepare_line_vals(self.root, 1)
        vals['estimate_id'] = est.id
        Line.create(vals)
        return est

    def _line(self, est, task, qty, price=None, amount=None):
        Line = self.env['payment.estimate.line']
        vals = Line._prepare_line_vals(task, 10)
        vals.update({'estimate_id': est.id, 'estimate_qty': qty})
        if price is not None:
            vals['unit_price'] = price
        if amount is not None:
            # create() 會把它標成手動金額（後台輸入與匯入步驟 14 同一條路）
            vals['estimate_amount'] = amount
        return Line.create(vals)

    def _approve(self, *ests):
        for est in ests:
            est.action_submit_estimate()
            est.action_approve()
        self.env.invalidate_all()

    def _summary(self, est):
        return est.line_ids.filtered(lambda l: l.task_id == self.root)

    # === 1. 單價 0 的整包項 ===
    def test_lump_sum_zero_price(self):
        e1, e2, e3 = self._estimate(0), self._estimate(30), self._estimate(60)
        self._line(e1, self.lump, 0.2, amount=100000.0)
        self._line(e2, self.lump, 0.1, amount=50000.0)
        l3 = self._line(e3, self.lump, 0.05, amount=25000.0)
        self._approve(e1, e2)
        self.assertEqual(l3.unit_price, 0.0, '測資前提：整包項單價是 0')
        self.assertAlmostEqual(
            l3.cumulative_estimate_amount, 175000.0, places=2,
            msg='整包項（單價 0）的累計只剩本期金額，前幾期不見了')
        self.assertAlmostEqual(l3.previous_approved_amount, 150000.0, places=2)
        self.assertAlmostEqual(
            self._summary(e3).cumulative_estimate_amount, 175000.0, places=2,
            msg='彙總項的累計沒有把整包項的前期算進去')

    # === 2. 前期手動金額 ===
    def test_previous_manual_amount(self):
        e1, e2 = self._estimate(0), self._estimate(30)
        self._line(e1, self.normal, 5.0, amount=88.0)      # 10 × 5 ＝ 50，表上填 88
        l2 = self._line(e2, self.normal, 3.0)
        self._approve(e1)
        self.assertAlmostEqual(
            l2.cumulative_estimate_amount, 118.0, places=2,
            msg='前期是手動金額 88，累計卻用 單價 × 前期數量 ＝ 50 去算')

    def test_lump_qty_one_each_period(self):
        """「式」工項每期數量都填 1、金額另填（111-09-AEG 3.1 的寫法）"""
        e1, e2, e3 = self._estimate(0), self._estimate(30), self._estimate(60)
        self._line(e1, self.normal, 1.0, price=1000.0, amount=100.0)
        self._line(e2, self.normal, 1.0, price=1000.0, amount=200.0)
        l3 = self._line(e3, self.normal, 1.0, price=1000.0, amount=300.0)
        self._approve(e1, e2)
        self.assertAlmostEqual(
            l3.cumulative_estimate_amount, 600.0, places=2,
            msg='每期數量填 1 的式工項，累計變成 單價 × 前期數量（多算好幾倍）')
        self.assertEqual(l3.cumulative_estimate_qty, 3.0, '累計數量維持原本的算法')

    # === 3. 單價中途改過：改動前照當時單價，改動後用新單價 ===
    def test_unit_price_changed(self):
        e1, e2, e3 = self._estimate(0), self._estimate(30), self._estimate(60)
        self._line(e1, self.normal, 5.0, price=10.0)       # 變更前：10 × 5 ＝ 50
        self._line(e2, self.normal, 2.0, price=12.0)       # 變更後：12 × 2 ＝ 24
        l3 = self._line(e3, self.normal, 3.0, price=12.0)  # 12 × 3 ＝ 36
        self._approve(e1, e2)
        self.assertAlmostEqual(
            l3.cumulative_estimate_amount, 110.0, places=2,
            msg='變更前的期別應照當時單價 10，不是用新單價 12 重算')

    # === 4. 不受影響的情況：結果跟原本完全一樣 ===
    def test_regression_plain_line(self):
        e1, e2 = self._estimate(0), self._estimate(30)
        self._line(e1, self.normal, 5.0)
        l2 = self._line(e2, self.normal, 3.0)
        self._approve(e1)
        self.assertEqual(l2.cumulative_estimate_amount, 80.0)
        self.assertEqual(
            l2.cumulative_estimate_amount,
            l2.unit_price * l2.cumulative_estimate_qty,
            '單價沒變、沒有手動金額時，應等於 單價 × 累計數量（原本的結果）')

    def test_unapproved_previous_not_counted(self):
        """前期沒核定不算，跟前期累計數量同一套"""
        e1, e2 = self._estimate(0), self._estimate(30)
        self._line(e1, self.lump, 0.2, amount=100000.0)
        l2 = self._line(e2, self.lump, 0.1, amount=50000.0)
        self.env.invalidate_all()
        self.assertEqual(l2.previous_approved_qty, 0.0)
        self.assertEqual(l2.previous_approved_amount, 0.0)
        self.assertAlmostEqual(l2.cumulative_estimate_amount, 50000.0, places=2)
        # 事後核定 → 重讀就反映（非儲存）
        self._approve(e1)
        self.assertAlmostEqual(l2.cumulative_estimate_amount, 150000.0, places=2)

    def test_archived_previous_counted(self):
        e1, e2 = self._estimate(0), self._estimate(30)
        self._line(e1, self.lump, 0.2, amount=100000.0)
        l2 = self._line(e2, self.lump, 0.1, amount=50000.0)
        self._approve(e1)
        e1.action_archive_estimate()
        self.env.invalidate_all()
        self.assertAlmostEqual(l2.cumulative_estimate_amount, 150000.0, places=2)

    def test_same_day_estimates(self):
        """同一天的多期：前期依「第N次」的順序決定（_estimates_before）"""
        e1, e2 = self._estimate(10), self._estimate(10)
        self._line(e1, self.lump, 0.2, amount=100000.0)
        l2 = self._line(e2, self.lump, 0.1, amount=50000.0)
        self._approve(e1)
        self.assertLess(e1.estimate_no, e2.estimate_no)
        self.assertAlmostEqual(l2.cumulative_estimate_amount, 150000.0, places=2)

    def test_later_estimate_not_counted(self):
        """排在本期後面的期別即使已核定也不算"""
        e1, e2 = self._estimate(0), self._estimate(30)
        l1 = self._line(e1, self.lump, 0.2, amount=100000.0)
        self._line(e2, self.lump, 0.1, amount=50000.0)
        self._approve(e2)
        self.assertAlmostEqual(l1.cumulative_estimate_amount, 100000.0, places=2)

    def test_summary_mixed(self):
        """彙總項 ＝ 底下葉節點累計之和（一般工項＋整包項）"""
        e1, e2 = self._estimate(0), self._estimate(30)
        self._line(e1, self.normal, 5.0, amount=88.0)
        self._line(e1, self.lump, 0.2, amount=100000.0)
        self._line(e2, self.normal, 3.0)
        self._line(e2, self.lump, 0.1, amount=50000.0)
        self._approve(e1)
        self.assertAlmostEqual(
            self._summary(e2).cumulative_estimate_amount, 118.0 + 150000.0, places=2)
