# -*- coding: utf-8 -*-
"""說明書發現問題的回歸（2026-11-02）。

- B3  施工排程新建未存檔時，麵包屑不能是「排程 #NewId_0x…」。
- P19 自主檢查排程提醒（活動 note 與收件匣訊息）：標籤要是真的標籤，
      工項名稱含 <script> 要被跳脫。
"""
from markupsafe import Markup

from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestManualFixes20261102(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '排程顯示測試', 'code': 'MF-WS',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})

    def test_b3_new_schedule_display_name(self):
        new = self.env['construction.weekly.schedule'].new({})
        self.assertNotIn('NewId', new.display_name)
        self.assertEqual(new.display_name, '新排程')

    def test_p19_inspection_reminder_is_markup_and_escapes_input(self):
        schedule = self.env['construction.weekly.schedule'].create({
            'supervision_project_id': self.project.id, 'week_start': '2026-11-02'})
        task = self.env['project.task'].create({
            'name': XSS, 'project_id': self.project.id, 'item_no': '1'})
        line = self.env['construction.weekly.schedule.line'].create({
            'schedule_id': schedule.id, 'task_id': task.id})
        # 勾選的限制要有檢查類型；這裡只驗訊息組裝，直接寫值略過 constrains
        line._write({'need_inspection': True})
        line.invalidate_recordset()
        self.assertTrue(schedule.line_ids.filtered('need_inspection'), '前置：明細要被勾選')
        schedule._create_inspection_activities()
        self.assertTrue(schedule.activity_ids, '應建立活動提醒')
        note = schedule.activity_ids[0].note
        body = self.env['mail.message'].search(
            [('model', '=', schedule._name), ('res_id', '=', schedule.id),
             ('message_type', '=', 'notification')], order='id desc', limit=1).body
        for label, html in (('活動 note', note), ('收件匣訊息', body)):
            self.assertTrue(html, '%s 找不到' % label)
            self.assertIsInstance(html, Markup)
            self.assertIn('<li>', html, '標籤要是真的標籤')
            self.assertNotIn('&lt;li&gt;', html, '標籤不可被當文字跳脫')
            self.assertNotIn('<script>', html, '工項名稱的 <script> 必須被跳脫')
            self.assertIn('&lt;script&gt;', html)

    def test_b29_contract_material_menu_visible_to_operator(self):
        """B29：契約材料清單掛在被選單設定檔關掉的「設定」底下，代操作員進不去。
        改掛「施工日誌」之下；用代操作員實際載入的選單樹確認看得到。"""
        operator = self.env['res.users'].create({
            'name': 'b29_operator', 'login': 'b29_operator',
            'groups_id': [(6, 0, [
                self.env.ref('construction_supervision_base.group_operator').id])],
        })
        menu = self.env.ref('construction_daily_log.menu_contract_material')
        self.assertEqual(
            menu.parent_id, self.env.ref('construction_supervision_base.menu_daily_log'))

        # load_menus 回傳 {id: 節點}，節點的 children 是 id 清單；從 root 走得到才算看得見
        tree = self.env['ir.ui.menu'].with_user(operator).load_menus(False)
        reachable, stack = set(), ['root']
        while stack:
            node_id = stack.pop()
            reachable.add(node_id)
            stack.extend(tree[node_id].get('children', []))
        self.assertIn(menu.id, reachable, '代操作員的選單樹要看得到契約材料清單')
