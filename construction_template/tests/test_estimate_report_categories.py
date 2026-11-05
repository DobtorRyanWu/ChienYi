# -*- coding: utf-8 -*-
"""工程估驗計價單的分類列與合計列（2026-11-05）。

原本：
  ・分類子項用 `item_no + "."` 前綴找——壹／一／(一)／1 這種每層重新編號的項次永遠對不到
    → 分類列全是 0（dev 的 380、388 也是）
  ・所有彙總列都列出來，大類和底下的子類混在一起；沒有彙總列的估驗單整段空白（500、503）
  ・累計欄寫死空白；「合計（僅合約項）」的本次金額用 subtotal（含非契約工項）
使用者要「照原系統」：EAGLE 正式版沒有產這張表，原始已填紙本只列最上層大類
（一列「發包工程費」，金額等於合計）→ 分類＝葉節點依工項樹的最上層祖先分組。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import estimate_report
from odoo.addons.construction_template.utils.formatters import money


@tagged('post_install', '-at_install', 'construction_template')
class TestEstimateReportCategories(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '估驗計價單分類測試', 'code': 'TPL-ESTCAT',
            'state': 'construction', 'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']

        def task(name, item_no, parent=None, qty=0.0, price=0.0, seq=10):
            return Task.create({
                'name': name, 'project_id': cls.project.id, 'item_no': item_no,
                'parent_id': parent.id if parent else False, 'unit': '式' if not price else 'M',
                'planned_qty': qty or 1.0, 'unit_price': price, 'sequence': seq,
            })
        # 壹 → 一 → (一) → 1：每層各自編號（前綴比對對不到的那種）
        cls.root = task('發包工程費', '壹', seq=1)
        cls.prep = task('整備工程', '一', cls.root, seq=2)
        cls.temp = task('假設工程', '(一)', cls.prep, seq=3)
        cls.leaf_a = task('施工圍籬', '1', cls.temp, qty=100.0, price=10.0, seq=4)
        cls.main = task('主體工程', '二', cls.root, seq=5)
        cls.leaf_b = task('混凝土', '1', cls.main, qty=50.0, price=20.0, seq=6)
        # 最上層的單一工項（像「營業稅」）：自己就是一個大類
        cls.tax = task('營業稅', '貳', qty=1.0, price=150.0, seq=7)
        cls.d0 = fields.Date.today() - timedelta(days=60)

    def _estimate(self, days, qtys, with_summary=True):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': self.d0 + timedelta(days=days),
        })
        Line = self.env['payment.estimate.line']
        tasks = self.env['project.task'].search(
            [('project_id', '=', self.project.id)], order='sequence, id')
        for seq, tsk in enumerate(tasks, start=1):
            if tsk.is_summary_item and not with_summary:
                continue                 # 匯入建的估驗單常只有葉節點（500／503）
            vals = Line._prepare_line_vals(tsk, seq)
            vals.update({'estimate_id': est.id,
                         'estimate_qty': 1.0 if tsk.is_summary_item else qtys.get(tsk, 0.0)})
            Line.create(vals)
        return est

    def _rows(self, est):
        return [(r['name'], r['contractAmount'], r['currentAmount'], r['totalAmount'])
                for r in estimate_report.build_context(est)['categories']]

    def test_top_level_categories_with_amounts(self):
        est = self._estimate(0, {self.leaf_a: 10.0, self.leaf_b: 5.0, self.tax: 1.0})
        rows = self._rows(est)
        self.assertEqual([r[0] for r in rows], ['發包工程費', '營業稅'],
                         '只列最上層大類（子層彙總列不列），最上層的單一工項自成一列')
        self.assertEqual(rows[0][1:3], (money(100 * 10 + 50 * 20), money(10 * 10 + 5 * 20)),
                         '大類金額要往下加到葉節點（每層重新編號的項次也要對得到）')
        self.assertEqual(rows[1][1:3], (money(150), money(150)))
        ctx = estimate_report.build_context(est)
        self.assertEqual(ctx['totalCurrentAmount'], money(est.contract_subtotal))
        self.assertEqual(est.contract_subtotal, 10 * 10 + 5 * 20 + 150,
                         '測資前提：各分類本次金額加總＝契約工項小計')

    def test_leaf_only_estimate_still_has_categories(self):
        est = self._estimate(0, {self.leaf_a: 10.0, self.leaf_b: 5.0},
                             with_summary=False)
        self.assertFalse(est.line_ids.filtered('is_summary_item'), '測資前提：沒有彙總列')
        rows = self._rows(est)
        self.assertEqual([r[0] for r in rows], ['發包工程費', '營業稅'])
        self.assertEqual(rows[0][2], money(200))

    def test_cumulative_columns(self):
        e1 = self._estimate(0, {self.leaf_a: 10.0, self.leaf_b: 5.0})
        e2 = self._estimate(30, {self.leaf_a: 20.0})
        e1.action_submit_estimate()
        e1.action_approve()
        self.env.invalidate_all()
        ctx = estimate_report.build_context(e2)
        first = ctx['categories'][0]
        self.assertEqual(first['currentAmount'], money(200))
        self.assertEqual(first['totalAmount'], money(200 + 200), '累計＝前期核定＋本期')
        self.assertEqual(first['totalPercent'], '%.2f' % (400 / 2000 * 100))
        self.assertEqual(ctx['totalCumulativeAmount'], money(400))

    def test_partial_estimate_keeps_earlier_items(self):
        """匯入建的估驗單只列「本期有填」的工項（3.5.4）：前期估過、本期沒列的工項
        不能從累計與契約金額裡消失。

        2026-11-05 審查實查：只加本張的列時，dev 500 第 30 期印出累計 22,744,239，
        全部工項的累計約 5.4 億；67 張裡 52 張各分類契約合計與合計列對不上。
        """
        e1 = self._estimate(0, {self.leaf_a: 10.0, self.leaf_b: 5.0})
        e1.action_submit_estimate()
        e1.action_approve()
        e2 = self._estimate(30, {self.leaf_a: 20.0}, with_summary=False)
        e2.line_ids.filtered(lambda ln: ln.task_id in (self.leaf_b | self.tax)).unlink()
        self.env.invalidate_all()
        self.assertEqual(e2.line_ids.task_id, self.leaf_a, '測資前提：本期只列了一個工項')
        ctx = estimate_report.build_context(e2)
        first = ctx['categories'][0]
        self.assertEqual(first['name'], '發包工程費')
        self.assertEqual(first['currentAmount'], money(200))
        self.assertEqual(first['totalAmount'], money(100 + 100 + 200),
                         '前期估過、本期沒列的「混凝土」累計不見了')
        self.assertEqual(first['contractAmount'], money(1000 + 1000),
                         '前期估過、本期沒列的「混凝土」契約金額不見了')
        self.assertEqual(ctx['totalCumulativeAmount'], money(400))

    def test_total_row_excludes_non_contract_items(self):
        est = self._estimate(0, {self.leaf_a: 10.0})
        item = self.env['payment.estimate.extra.item'].create({
            'project_id': self.project.id, 'code': 'PRICE-ADJ', 'name': '物價調整',
            'include_in_subtotal': True,
        })
        self.env['payment.estimate.extra.line'].create({
            'estimate_id': est.id, 'extra_item_id': item.id, 'name': '第1次估驗物價調整',
            'is_amount_manual': True, 'manual_estimate_amount': 999.0,
        })
        self.env.invalidate_all()
        self.assertGreater(est.subtotal, est.contract_subtotal, '測資前提：有計入總額的非契約工項')
        ctx = estimate_report.build_context(est)
        self.assertEqual(ctx['totalCurrentAmount'], money(est.contract_subtotal),
                         '「合計（僅合約項）」不能含非契約工項')

    def test_orphan_task_joins_its_prefix_category(self):
        """工項 parent 斷掉（500 有 97 個像 1.1.24 這樣的孤兒）：依項次第一段併回大類"""
        project = self.env['project.project'].create({
            'name': '孤兒工項測試', 'code': 'TPL-ESTORP',
            'state': 'construction', 'company_id': self.env.company.id,
        })
        Task = self.env['project.task']
        cat = Task.create({'name': '假設工程', 'project_id': project.id, 'item_no': '1',
                           'unit': '式', 'planned_qty': 1.0, 'sequence': 1})
        child = Task.create({'name': '圍籬', 'project_id': project.id, 'item_no': '1.1',
                             'parent_id': cat.id, 'unit': 'M', 'planned_qty': 10.0,
                             'unit_price': 10.0, 'sequence': 2})
        orphan = Task.create({'name': '安全標誌', 'project_id': project.id, 'item_no': '1.2',
                              'unit': '個', 'planned_qty': 5.0, 'unit_price': 20.0,
                              'sequence': 3})
        est = self.env['payment.estimate'].create({
            'project_id': project.id, 'estimate_date': self.d0})
        Line = self.env['payment.estimate.line']
        for seq, (tsk, qty) in enumerate([(cat, 1.0), (child, 2.0), (orphan, 1.0)], start=1):
            vals = Line._prepare_line_vals(tsk, seq)
            vals.update({'estimate_id': est.id, 'estimate_qty': qty})
            Line.create(vals)
        rows = self._rows(est)
        self.assertEqual([r[0] for r in rows], ['假設工程'], '孤兒工項要併回「1」那一類')
        self.assertEqual(rows[0][2], money(2 * 10 + 1 * 20))
        self.assertEqual(rows[0][1], money(10 * 10 + 5 * 20),
                         '併進來的孤兒工項契約金額也要算進該類')
