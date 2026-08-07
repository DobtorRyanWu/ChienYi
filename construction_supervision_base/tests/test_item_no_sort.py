# -*- coding: utf-8 -*-
"""A1 / A9 — 契約項次是字串排序，1 之後跳到 10、100 才輪到 11。

代操 2026-08-06 回報「契約項目順序有誤」，截圖是編號欄依序
1, 10, 100, 101 … 108, 11。根因是 `project.task.item_no` 為 Char，
list 的 `default_order="sequence,item_no"` 在 sequence 相同時就退化成字串比較。

同一根因也造成 A9「日誌詳細表各大項未區隔」——那是 many2one 的下拉，
順序只吃模型的 `_order`，view 上無法個別指定。

修法：新增 stored 的 `item_no_sort`，把項次路徑每一段的數字補零對齊，
並把模型 `_order` 與 list 的 `default_order` 都改用它。
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestItemNoSort(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'A1 測試工程',
            'code': 'A1-TEST',
            'project_type': 'general',
        })

    def _task(self, item_no, parent=None):
        return self.env['project.task'].create({
            'name': '工項 %s' % item_no,
            'project_id': self.project.id,
            'item_no': item_no,
            'parent_id': parent.id if parent else False,
        })

    def test_arabic_numbers_sort_numerically(self):
        """1 < 2 < 11 < 100，不是字串序的 1 < 100 < 11。"""
        for no in ('11', '100', '2', '1'):
            self._task(no)
        tasks = self.env['project.task'].search([('project_id', '=', self.project.id)])
        self.assertEqual(tasks.mapped('item_no'), ['1', '2', '11', '100'])

    def test_chinese_numbers_sort_numerically(self):
        """中文數字也要照數值排：壹 < 貳 < 拾壹。"""
        for no in ('拾壹', '貳', '壹'):
            self._task(no)
        tasks = self.env['project.task'].search([('project_id', '=', self.project.id)])
        self.assertEqual(tasks.mapped('item_no'), ['壹', '貳', '拾壹'])

    def test_parenthesised_chinese_is_parsed(self):
        """實務上會包括號，如「(一)」，要能解析出 1。"""
        task = self._task('(一)')
        self.assertEqual(task.item_no_sort, '000001')

    def test_hierarchy_path_is_padded_per_segment(self):
        """階層路徑逐段補零：父 1 底下的 10 → '000001.000010'。"""
        parent = self._task('1')
        child = self._task('10', parent=parent)
        self.assertEqual(child.item_no_sort, '000001.000010')

    def test_children_sort_under_parent(self):
        """子工項在同一父項下依數值排序。"""
        parent = self._task('1')
        for no in ('11', '2', '1'):
            self._task(no, parent=parent)
        children = self.env['project.task'].search([('parent_id', '=', parent.id)])
        self.assertEqual(children.mapped('item_no'), ['1', '2', '11'])

    def test_unparseable_segment_does_not_break(self):
        """解析不出數字的段落補 0，不得拋例外。"""
        task = self._task('N/A')
        self.assertEqual(task.item_no_sort, '000000')

    def test_sort_key_follows_item_no_change(self):
        """改了 item_no，排序鍵要跟著重算（stored compute 的 depends 要對）。"""
        task = self._task('5')
        self.assertEqual(task.item_no_sort, '000005')
        task.item_no = '50'
        self.assertEqual(task.item_no_sort, '000050')
