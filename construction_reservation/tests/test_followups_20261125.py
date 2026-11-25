# -*- coding: utf-8 -*-
"""W5 乙組：預約式檢查項目獨立表單不可直接改 check_result（E2-3，2026-11-25）。

結果欄位不是「合格／缺失／無此項目」的表，check_result 由勾選換算；
一般式的清單用 parent.result_layout 做唯讀，獨立表單沒有 parent，改用項目自己的 result_layout。
view 的 readonly 只是畫面層（與一般式同一層級，不另外在伺服器擋）。
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged

ITEM_MODEL = 'reservation.self.inspection.item'
FORM_VIEW = 'construction_reservation.view_reservation_self_inspection_item_form_reservation'


@tagged('post_install', '-at_install', 'construction_reservation')
class TestItemFormCheckResultReadonly(TransactionCase):

    def _form_field(self, name):
        view = self.env.ref(FORM_VIEW)
        arch = self.env[ITEM_MODEL].get_view(view.id, 'form')['arch']
        nodes = etree.fromstring(arch).xpath('//field[@name="%s"]' % name)
        self.assertTrue(nodes, '獨立表單裡找不到欄位 %s' % name)
        return nodes[0]

    def test_check_result_readonly_unless_standard_layout(self):
        field = self._form_field('check_result')
        readonly = field.get('readonly') or ''
        self.assertIn('result_layout', readonly, '勾選樣式時 check_result 要唯讀（依 result_layout）')
        self.assertIn('standard', readonly)

    def test_result_layout_available_to_the_form(self):
        self.assertIn('result_layout', self.env[ITEM_MODEL]._fields)
        self._form_field('result_layout')  # 表單裡要有它，前端才求得出唯讀條件

    def test_mark_editable_in_form_for_non_standard_layout(self):
        field = self._form_field('mark')
        self.assertIn('result_layout', field.get('invisible') or '')
