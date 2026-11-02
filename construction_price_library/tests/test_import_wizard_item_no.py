# -*- coding: utf-8 -*-
"""價格庫匯入精靈：項次不可全是 1、回傳走契約工項動作（B7，2026-11-02）。

原本一次 create 整批 vals，沒帶 item_no，每筆都在「看不到彼此」的狀態下自動編號，
21 筆全是 1；回傳裸 project.task 清單，落到 Odoo 原生任務清單。
價格庫項目沒有層級欄位（只有分類），所以匯入的工項都是頂層，項次接在工程現有頂層之後。
"""
from odoo.tests.common import TransactionCase, tagged

ITEM_COUNT = 5
EXISTING_TOP_COUNT = 2


@tagged('post_install', '-at_install', 'construction_price_library')
class TestImportWizardItemNo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '價格庫匯入項次測試', 'code': 'PL-ITEMNO', 'company_id': company.id})
        category = cls.env['price.library.category'].create({'name': '項次測試分類', 'company_id': company.id})
        cls.items = cls.env['price.library.item'].create([{
            'name': '項次測試項目 %d' % i, 'unit': 'm2', 'unit_price': 10.0 * (i + 1),
            'company_id': company.id, 'category_id': category.id} for i in range(ITEM_COUNT)])

    def _import(self):
        wiz = self.env['price.library.import.wizard'].create({
            'project_id': self.project.id, 'item_ids': [(6, 0, self.items.ids)]})
        return wiz.action_import()

    def test_item_numbers_are_unique_and_sequential(self):
        action = self._import()
        tasks = self.env['project.task'].search(action['domain'])
        self.assertEqual(len(tasks), ITEM_COUNT)
        nos = tasks.sorted('sequence').mapped('item_no')
        self.assertEqual(nos, [str(i + 1) for i in range(ITEM_COUNT)], '項次要一個接一個，不是全部 1')
        self.assertEqual(len(set(tasks.mapped('sequence'))), ITEM_COUNT, '排序序號也不能撞')

    def test_does_not_collide_with_existing_tasks(self):
        Task = self.env['project.task']
        for i in range(EXISTING_TOP_COUNT):
            Task.create({'name': '既有頂層 %d' % i, 'project_id': self.project.id,
                         'item_no': str(i + 1), 'sequence': (i + 1) * 10})
        tasks = Task.search(self._import()['domain'])
        all_top = Task.search([('project_id', '=', self.project.id), ('parent_id', '=', False)])
        self.assertEqual(len(all_top), EXISTING_TOP_COUNT + ITEM_COUNT)
        self.assertEqual(len(set(all_top.mapped('item_no'))), len(all_top), '同層項次不可撞號')
        self.assertEqual(min(int(n) for n in tasks.mapped('item_no')), EXISTING_TOP_COUNT + 1)

    def test_returns_supervision_task_action_scoped_to_project(self):
        action = self._import()
        expected = self.env.ref('construction_supervision_base.action_supervision_task')
        self.assertEqual(action['id'], expected.id, '要回契約工項動作，不是裸 project.task 清單')
        self.assertEqual(action['context'].get('default_project_id'), self.project.id)
        self.assertNotIn('search_default_group_by_project', action['context'])
        tasks = self.env['project.task'].search(action['domain'])
        self.assertEqual(set(tasks.mapped('project_id').ids), {self.project.id})
