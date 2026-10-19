# -*- coding: utf-8 -*-
"""「從工項產生試算表」的 J 欄（累計估驗金額）要跟後台一樣。

原本 J 欄是公式 =單價(F) × 累計數量(I)，不讀後台的值 → 前期是手動金額、
單價 0 的整包項、單價中途改過時都跟後台對不上（開發庫 111-20-AEF-V 第 13 期
8 列，例 1.39 試算表 239,530.18／後台 239,554.00）。
現在葉節點的 J 欄 ＝ 前期已核定累計金額（常數）＋ H（本期金額）。

測試用一個很小的公式求值器（只認本模組會產生的三種寫法）把 J 欄算出來，
跟後台的 cumulative_estimate_amount 比。
"""

import re
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_spreadsheet_editor_chienyi')
class TestEstimateWorkbook(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '估驗試算表測試工程',
            'code': 'SSE-CUMAMT',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']
        cls.root = Task.create({
            'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹',
            'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
        })
        cls.plain = Task.create({
            'name': '一般工項', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '一', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 10.0,
        })
        cls.manual_prev = Task.create({
            'name': '前期手動金額', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '二', 'unit': 'M3', 'planned_qty': 100.0, 'unit_price': 10.0,
        })
        cls.lump = Task.create({
            'name': '自主品管費', 'project_id': cls.project.id, 'parent_id': cls.root.id,
            'item_no': '三', 'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
            'xml_amount': 500000.0, 'is_lump_sum': True,
        })
        cls.d0 = fields.Date.today() - timedelta(days=60)

    def _estimate(self, days, rows):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': self.d0 + timedelta(days=days),
        })
        Line = self.env['payment.estimate.line']
        for seq, (task, qty, price, amount) in enumerate(
                [(self.root, 1.0, None, None)] + rows, start=1):
            vals = Line._prepare_line_vals(task, seq)
            vals.update({'estimate_id': est.id, 'estimate_qty': qty})
            if price is not None:
                vals['unit_price'] = price
            if amount is not None:
                vals['estimate_amount'] = amount
            Line.create(vals)
        return est

    # 只認本模組產生的寫法：數值、=F3*G3、=H3、=123.4+H3
    @staticmethod
    def _eval(cells, ref, depth=0):
        assert depth < 5, '公式遞迴太深'
        content = cells.get(ref, {}).get('content')
        if content is None:
            return 0.0
        if not isinstance(content, str) or not content.startswith('='):
            return float(content)
        expr = content[1:]
        m = re.fullmatch(r'([A-Z]+\d+)\*([A-Z]+\d+)', expr)
        if m:
            return (TestEstimateWorkbook._eval(cells, m.group(1), depth + 1)
                    * TestEstimateWorkbook._eval(cells, m.group(2), depth + 1))
        m = re.fullmatch(r'(-?[0-9.eE+-]+)\+([A-Z]+\d+)', expr)
        if m:
            return float(m.group(1)) + TestEstimateWorkbook._eval(cells, m.group(2), depth + 1)
        m = re.fullmatch(r'([A-Z]+\d+)', expr)
        if m:
            return TestEstimateWorkbook._eval(cells, m.group(1), depth + 1)
        raise AssertionError('測試不認得的公式：%s' % content)

    def test_cumulative_column_matches_backend(self):
        e1 = self._estimate(0, [
            (self.plain, 5.0, None, None),
            (self.manual_prev, 5.0, None, 88.0),        # 前期手動 88（≠ 10 × 5）
            (self.lump, 0.2, None, 100000.0),           # 單價 0 的整包項
        ])
        e2 = self._estimate(30, [
            (self.plain, 3.0, None, None),
            (self.manual_prev, 3.0, None, None),         # 本期不是手動
            (self.lump, 0.1, None, 50000.0),
        ])
        e1.action_submit_estimate()
        e1.action_approve()
        self.env.invalidate_all()

        cells = e2._build_estimate_workbook_data()['sheets'][0]['cells']
        lines = e2.line_ids.sorted(key=lambda r: (r.sequence or 0, r.id))
        expected = {'一': 80.0, '二': 118.0, '三': 150000.0}
        for r, line in enumerate(lines, start=3):
            if line.is_summary_item:
                continue
            got = self._eval(cells, 'J%d' % r)
            self.assertAlmostEqual(
                line.cumulative_estimate_amount, expected[line.item_no], places=2,
                msg='測資前提：後台累計金額（construction_payment 18.0.1.8.1）')
            self.assertAlmostEqual(
                got, line.cumulative_estimate_amount, places=2,
                msg='試算表 J%d（%s）%s ≠ 後台 %s' % (
                    r, line.item_no, cells.get('J%d' % r), line.cumulative_estimate_amount))

    def test_cumulative_column_follows_current_qty(self):
        """J 欄要參照 H 欄：在試算表裡改本期數量，累計會跟著重算（不是寫死的值）"""
        e1 = self._estimate(0, [(self.plain, 5.0, None, None)])
        e2 = self._estimate(30, [(self.plain, 3.0, None, None)])
        e1.action_submit_estimate()
        e1.action_approve()
        self.env.invalidate_all()
        cells = e2._build_estimate_workbook_data()['sheets'][0]['cells']
        r = 3 + list(e2.line_ids.sorted(key=lambda x: (x.sequence or 0, x.id))).index(
            e2.line_ids.filtered(lambda ln: ln.task_id == self.plain))
        self.assertEqual(cells['J%d' % r]['content'], '=50.0+H%d' % r)
        cells['G%d' % r] = {'content': '7.0'}            # 模擬在試算表裡把本期數量改成 7
        self.assertAlmostEqual(self._eval(cells, 'J%d' % r), 50.0 + 70.0, places=2)

    def test_first_period_and_summary_rows(self):
        """第一期（沒有前期）J ＝ H；彙總列維持原本寫法（算出 0，小計 SUM 才不會重複加總）"""
        e1 = self._estimate(0, [(self.plain, 5.0, None, None)])
        cells = e1._build_estimate_workbook_data()['sheets'][0]['cells']
        lines = list(e1.line_ids.sorted(key=lambda x: (x.sequence or 0, x.id)))
        for r, line in enumerate(lines, start=3):
            if line.is_summary_item:
                self.assertEqual(cells['J%d' % r]['content'], '=F%d*I%d' % (r, r))
                self.assertEqual(self._eval(cells, 'J%d' % r), 0.0)
            else:
                self.assertEqual(cells['J%d' % r]['content'], '=H%d' % r)
