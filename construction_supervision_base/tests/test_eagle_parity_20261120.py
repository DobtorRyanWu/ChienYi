# -*- coding: utf-8 -*-
"""回復原版（1118 會議 A1／A2）：舊系統沒有、新系統多擋的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的工程狀態是下拉自己選、選了直接存，開工沒有任何前置條件
（前端 views/PC/Information.vue 的 save('status')、後端 routes/project.js 的 PATCH /project/:id）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（編號 PJ-02、PJ-04）。

沒有契約工項不能開工（PJ-03）是對應舊系統「契約要先核定」，保留，所以這裡的工程都先建一個工項。
"""

from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestEagleParityStart(TransactionCase):

    def _project(self, code, **vals):
        project = self.env['project.project'].create(dict({
            'name': '回復原版 %s' % code, 'code': code, 'project_type': 'reservation'}, **vals))
        self.env['project.task'].create({'name': '回復原版工項', 'project_id': project.id})
        return project

    def test_start_without_finishing_init_steps(self):
        """PJ-04：六項初始化都還是「未完成」也能開始施工。"""
        project = self._project('EP-INIT', contract_start_date='2026-01-01')
        self.assertFalse(project.all_init_done, '前提：初始化還沒做完')
        project.action_approve()
        self.assertEqual(project.state, 'construction')

    def test_start_without_contract_start_date(self):
        """PJ-02：沒填契約開工日也能開始施工。"""
        project = self._project('EP-NODATE')
        self.assertFalse(project.contract_start_date, '前提：沒有契約開工日')
        project.action_approve()
        self.assertEqual(project.state, 'construction')
        self.assertTrue(project.actual_start_date, '開始施工時仍要記下實際開工日')

    def test_start_button_not_hidden_by_init_steps(self):
        """PJ-04：「開始施工」按鈕不能再因為初始化沒做完而藏起來。"""
        view = self.env.ref('construction_supervision_base.view_supervision_project_form')
        arch = etree.fromstring(view.arch)
        buttons = arch.xpath("//button[@name='action_approve']")
        self.assertEqual(len(buttons), 1, '表單上要有一顆開始施工按鈕')
        self.assertNotIn('all_init_done', buttons[0].get('invisible') or '')

    def test_basic_fields_not_readonly_after_start(self):
        """PJ-09：開工後工程名稱、年份、主辦機關、地點、契約編號、實際日期、座標在表單上不再唯讀。

        工程類型維持開工後唯讀（舊系統建立後就不能改類型）；契約開工／完工日另有規則（PJ-08）。"""
        arch = etree.fromstring(self.env.ref('construction_supervision_base.view_supervision_project_form').arch)

        def readonly_of(name):
            nodes = arch.xpath("//field[@name='%s']" % name)
            self.assertTrue(nodes, name)
            return nodes[0].get('readonly') or ''

        for name in ('name', 'year', 'authority_name', 'location', 'management_company_name', 'contract_no',
                     'actual_start_date', 'actual_end_date', 'location_detail', 'latitude', 'longitude'):
            self.assertEqual(readonly_of(name), '', '%s 開工後不該唯讀' % name)
        for name in ('project_type', 'contract_start_date', 'contract_end_date'):
            self.assertIn("'construction'", readonly_of(name), '%s 開工後仍要唯讀' % name)


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestEagleParityInputChecks(TransactionCase):
    """PJ-12、CT-02：日期先後、數量與單價正負不再檢查（舊系統前後端都沒有比對）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版輸入值', 'code': 'EP-INPUT', 'project_type': 'general'})

    def test_contract_end_before_start_allowed(self):
        self.project.write({'contract_start_date': '2026-03-01', 'contract_end_date': '2026-02-01'})
        self.env.flush_all()          # 資料庫層的 CHECK 約束在 flush 時才會擋
        self.project.invalidate_recordset()
        self.assertLess(self.project.contract_end_date, self.project.contract_start_date)

    def test_negative_contract_qty_and_price_allowed(self):
        task = self.env['project.task'].create({'name': '回復原版負數工項', 'project_id': self.project.id})
        task.write({'planned_qty': -5.0, 'unit_price': -10.0})
        self.env.flush_all()
        self.assertEqual((task.planned_qty, task.unit_price), (-5.0, -10.0))
