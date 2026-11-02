# -*- coding: utf-8 -*-
"""從工程匯入成本分析要排除「不計入契約金額」的工項（B17，2026-11-02）。

原本取全部工項逐筆建明細，連 exclude_from_contract_amount 的「總計」列也建進去，
招標總價（只加總非彙總項明細）把總計列再算一次，約變兩倍。
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

TOTAL_EXPECTED = 200.0 + 600.0 + 500.0      # A + B + C
GRAND_TOTAL_ROW_AMOUNT = TOTAL_EXPECTED     # 總計列的單價 = 全部合計


@tagged('post_install', '-at_install', 'construction_cost_analysis')
class TestImportProjectExclude(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '成本分析匯入排除測試', 'code': 'CA-EXCL', 'company_id': cls.env.company.id})

    def _task(self, name, parent=None, qty=0.0, price=0.0, exclude=False, seq=10):
        return self.env['project.task'].create({
            'name': name, 'project_id': self.project.id, 'parent_id': parent.id if parent else False,
            'planned_qty': qty, 'unit_price': price, 'unit': '式', 'sequence': seq,
            'exclude_from_contract_amount': exclude})

    def _hierarchy(self):
        g1 = self._task('壹、土方', seq=10)
        a = self._task('土方 A', g1, 2.0, 100.0, seq=11)
        b = self._task('土方 B', g1, 3.0, 200.0, seq=12)
        g2 = self._task('貳、結構', seq=20)
        g21 = self._task('一、鋼筋', g2, seq=21)
        c = self._task('鋼筋 C', g21, 1.0, 500.0, seq=22)
        return g1, a, b, g2, g21, c

    def _import(self):
        wiz = self.env['cost.analysis.import.project.wizard'].create({
            'source_project_id': self.project.id, 'company_id': self.env.company.id,
            'planning_name': '匯入排除測試', 'total_budget': 0.0,
            'currency_id': self.env.company.currency_id.id})
        action = wiz.action_import()
        return self.env['cost.analysis'].browse(action['res_id'])

    def test_grand_total_leaf_row_is_skipped(self):
        self._hierarchy()
        self._task('總計', qty=1.0, price=GRAND_TOTAL_ROW_AMOUNT, exclude=True, seq=30)
        planning = self._import()
        self.assertNotIn('總計', planning.line_ids.mapped('name'), '不計入契約金額的列不該建成明細')
        self.assertEqual(planning.total_budget, TOTAL_EXPECTED)
        self.assertEqual(len(planning.line_ids), 6)

    def test_children_of_excluded_row_keep_a_valid_parent(self):
        """被略過列底下還有子項時，子項接到最近一層未被略過的上層（沒有就掛頂層），不能斷鏈。"""
        wrapper = self._task('總計（含子項）', exclude=True, seq=5)
        top = self._task('壹、外層', wrapper, seq=6)
        leaf = self._task('外層葉', top, 2.0, 50.0, seq=7)
        orphan = self._task('直屬總計的葉', wrapper, 1.0, 10.0, seq=8)
        planning = self._import()
        lines = {l.task_id.id: l for l in planning.line_ids}
        self.assertNotIn(wrapper.id, lines)
        self.assertFalse(lines[top.id].parent_id, '被略過列的子項掛到頂層')
        self.assertEqual(lines[leaf.id].parent_id, lines[top.id], '一般父子關係不受影響')
        self.assertFalse(lines[orphan.id].parent_id)
        self.assertEqual(planning.total_budget, 2.0 * 50.0 + 10.0)

    def test_load_button_skips_excluded_row(self):
        """畫面上的「載入工項」按鈕是另一條路，要和匯入精靈一樣略過總計列。"""
        self._hierarchy()
        self._task('總計', qty=1.0, price=GRAND_TOTAL_ROW_AMOUNT, exclude=True, seq=30)
        planning = self.env['cost.analysis'].create({
            'name': '載入工項排除測試', 'source_project_id': self.project.id,
            'company_id': self.env.company.id, 'state': 'draft'})
        planning.action_load_from_project()
        self.assertNotIn('總計', planning.line_ids.mapped('name'))
        self.assertEqual(planning.total_budget, TOTAL_EXPECTED)

    def test_nothing_left_after_filter_raises(self):
        self._task('只有總計', qty=1.0, price=1.0, exclude=True)
        with self.assertRaises(UserError) as cm:
            self._import()
        self.assertIn('沒有工項', str(cm.exception))
