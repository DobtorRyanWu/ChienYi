# -*- coding: utf-8 -*-
"""第 3 批：清單／表單畫面三項（2026-11-03）。

純畫面項目，斷言打在「使用者最後看到的 arch」（get_view 合併後的結果）：
  1. 一般式缺失清單的 is_overdue 只是 decoration 用的輔助欄位，要整欄隱藏
     （column_invisible）；寫成 invisible 只會清空儲存格，標題「已逾期」還在。
  2. 契約工項表單的工程案件必填、placeholder 寫「請選擇工程案件」，
     不能出現預設的「私人」（空著 = 私人工項）。
  3. 工程案件開出的契約工項清單順序由項次決定，不能放拖曳把手。
"""
from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestListViewsBatch3(TransactionCase):

    def _arch(self, model, view_type, view_xmlid=None):
        view_id = self.env.ref(view_xmlid).id if view_xmlid else False
        arch = self.env[model].get_view(view_id=view_id, view_type=view_type)['arch']
        return etree.fromstring(arch)

    def test_overdue_helper_column_is_fully_hidden(self):
        if 'general.defect.improvement' not in self.env:
            self.skipTest('construction_general 未安裝')
        tree = self._arch('general.defect.improvement', 'list')
        node = tree.xpath("//field[@name='is_overdue']")
        self.assertEqual(len(node), 1)
        self.assertTrue(node[0].get('column_invisible'),
                        '「已逾期」輔助欄位必須用 column_invisible 整欄隱藏')
        # 逾期天數欄仍要顯示
        days = tree.xpath("//field[@name='overdue_days']")
        self.assertEqual(len(days), 1)
        self.assertFalse(days[0].get('column_invisible'))

    def test_task_form_project_is_required_with_placeholder(self):
        form = self._arch('project.task', 'form')
        node = form.xpath("//div[@name='project']/field[@name='project_id'][@placeholder]")
        self.assertTrue(node, '契約工項表單找不到帶 placeholder 的工程案件欄位')
        self.assertEqual(node[0].get('placeholder'), '請選擇工程案件')
        self.assertIn(node[0].get('required'), ('1', 'True', 'true'))

    def test_project_task_list_has_no_drag_handle(self):
        tree = self._arch(
            'project.task', 'list',
            'construction_supervision_base.view_task_tree_project_specific')
        self.assertFalse(tree.xpath("//field[@widget='handle']"),
                         '順序由項次決定，拖曳把手拖了不會生效')
