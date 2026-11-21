# -*- coding: utf-8 -*-
"""回復原版（1118 會議 A1／A2）：舊系統沒有、新系統多擋的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的工程狀態是下拉自己選、選了直接存，開工沒有任何前置條件
（前端 views/PC/Information.vue 的 save('status')、後端 routes/project.js 的 PATCH /project/:id）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（編號 PJ-02、PJ-04）。

沒有契約工項不能開工（PJ-03）是對應舊系統「契約要先核定」，保留，所以這裡的工程都先建一個工項。
"""

from lxml import etree

from psycopg2 import IntegrityError

from odoo.tests import Form, TransactionCase, tagged
from odoo.tools import mute_logger


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

    def test_project_code_editable_after_start(self):
        """PJ-16（2026-11-22）：開工後後台也能改工程編號——舊系統工程編號隨時可改，前台老闆、主管本來就不看狀態。"""
        arch = etree.fromstring(self.env.ref('construction_supervision_base.view_supervision_project_form').arch)
        code = arch.xpath("//div[contains(@class, 'oe_title')]//field[@name='code']")
        self.assertEqual(len(code), 1)
        self.assertFalse(code[0].get('readonly'), '工程編號不該再因為開工而唯讀')
        project = self._project('EP-CODE', contract_start_date='2026-01-01')
        project.action_approve()
        with Form(project, 'construction_supervision_base.view_supervision_project_form') as form:
            form.code = 'EP-CODE-2'
        self.assertEqual(project.code, 'EP-CODE-2')


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestEagleParityInputChecks(TransactionCase):
    """CT-02：契約數量與單價正負不再檢查（舊系統前後端都沒有比對）。
    PJ-12（契約完工日不早於開工日）2026-11-22 使用者決定加回，當防呆。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版輸入值', 'code': 'EP-INPUT', 'project_type': 'general'})

    def test_contract_end_before_start_blocked(self):
        """PJ-12：完工日早於開工日要擋；同一天、或只填其中一個日期不擋。"""
        self.project.write({'contract_start_date': '2026-03-01', 'contract_end_date': '2026-03-01'})
        self.env.flush_all()
        self.project.write({'contract_start_date': False, 'contract_end_date': '2026-02-01'})
        self.env.flush_all()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.project.write({'contract_start_date': '2026-03-01', 'contract_end_date': '2026-02-01'})
            self.env.flush_all()          # 資料庫層的 CHECK 約束在 flush 時才會擋

    def test_negative_contract_qty_and_price_allowed(self):
        task = self.env['project.task'].create({'name': '回復原版負數工項', 'project_id': self.project.id})
        task.write({'planned_qty': -5.0, 'unit_price': -10.0})
        self.env.flush_all()
        self.assertEqual((task.planned_qty, task.unit_price), (-5.0, -10.0))


TASK_QTY = 100.0
TASK_PRICE = 10.0
TASK_SUM = TASK_QTY * TASK_PRICE          # 工項合計
MANUAL_AMOUNT = 8500000.0                 # 手填的契約金額（開口合約的上限金額）
PROJECT_FORM = 'construction_supervision_base.view_supervision_project_form'


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestEagleParityContractAmountManual(TransactionCase):
    """PJ-10：契約金額有工項之後、開工之後都可以手改。

    舊系統的發包金額是獨立欄位，隨時可改（components/resource/m_contract/Contract.vue 的 contract.budget）。
    修改前：有工項時寫契約金額 → UserError「已匯入工項，契約金額自動從工項計算，無法手動修改！」；
    開工後、沒有工項時寫 → UserError「只有未開始階段可以手動設定契約金額！」；後台表單開工後這一格唯讀。

    手改的金額和工項合計不一樣 → 記成「手動輸入」，之後工項再變也不覆蓋；取消勾選就改回工項合計。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '回復原版契約金額', 'code': 'EP-AMOUNT', 'project_type': 'reservation'})
        cls.task = cls.env['project.task'].create({
            'name': '回復原版契約金額工項', 'project_id': cls.project.id,
            'unit': 'M', 'planned_qty': TASK_QTY, 'unit_price': TASK_PRICE})
        cls.env.flush_all()

    def _state(self, project=None):
        """(契約金額, 是否手動輸入)，先 flush 讓待算的 compute 跑完。"""
        project = project or self.project
        self.env.flush_all()
        project.invalidate_recordset()
        return project.contract_amount, project.contract_amount_manual

    def test_amount_follows_tasks_until_edited(self):
        """守門：沒有人手改之前，契約金額照舊跟著工項合計走。"""
        self.assertEqual(self._state(), (TASK_SUM, False))
        self.task.planned_qty = TASK_QTY * 2
        self.assertEqual(self._state(), (TASK_SUM * 2, False))

    def test_manual_amount_with_tasks(self):
        """有工項也能手改契約金額，改完記成手動輸入。"""
        self.project.write({'contract_amount': MANUAL_AMOUNT})
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))

    def test_manual_amount_kept_when_tasks_change(self):
        """手改之後工項數量變了、又加了工項，契約金額都不能被蓋回工項合計。"""
        self.project.write({'contract_amount': MANUAL_AMOUNT})
        self.task.planned_qty = TASK_QTY * 2
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))
        self.env['project.task'].create({
            'name': '回復原版後來加的工項', 'project_id': self.project.id,
            'unit': 'M', 'planned_qty': TASK_QTY, 'unit_price': TASK_PRICE})
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))

    def test_untick_manual_goes_back_to_task_sum(self):
        """取消勾選「契約金額手動輸入」→ 改回當下的工項合計。"""
        self.project.write({'contract_amount': MANUAL_AMOUNT})
        self.task.planned_qty = TASK_QTY * 2
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))
        self.project.write({'contract_amount_manual': False})
        self.assertEqual(self._state(), (TASK_SUM * 2, False))

    def test_amount_equal_to_task_sum_is_not_manual(self):
        """填的數字剛好等於工項合計不算手動（前台存檔會把沒改的金額原樣送回來）。"""
        self.project.write({'contract_amount': TASK_SUM})
        self.assertEqual(self._state(), (TASK_SUM, False))
        self.task.planned_qty = TASK_QTY * 2
        self.assertEqual(self._state(), (TASK_SUM * 2, False), '沒被記成手動，所以還是跟著工項走')

    def test_manual_amount_after_start(self):
        """已開工也能手改契約金額。"""
        self.project.action_approve()
        self.assertEqual(self.project.state, 'construction')
        self.project.write({'contract_amount': MANUAL_AMOUNT})
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))

    def test_start_freezes_manual_amount_as_original(self):
        """開工前手改過金額：開工時原始契約金額要記手改的金額，不是先前工項合計自動記下的值。"""
        self.env.flush_all()
        self.assertEqual(self.project.original_contract_amount, TASK_SUM, '前提：工項合計已被自動記成原始金額')
        self.project.write({'contract_amount': MANUAL_AMOUNT})
        self.project.action_approve()
        self.assertEqual(self.project.original_contract_amount, MANUAL_AMOUNT)

    def test_start_keeps_original_when_amount_not_manual(self):
        """守門：沒有手改的工程，開工時已經有的原始契約金額照舊不動。"""
        self.env.flush_all()
        self.project.original_contract_amount = TASK_SUM * 3     # 例如匯入時就帶進來的原始金額
        self.project.action_approve()
        self.assertEqual(self.project.original_contract_amount, TASK_SUM * 3)

    def test_started_project_without_tasks_accepts_amount(self):
        """已開工、沒有工項：也能手填契約金額；之後有了工項，照舊改由工項合計帶入。"""
        project = self.env['project.project'].create({
            'name': '回復原版契約金額（無工項）', 'code': 'EP-AMOUNT-NOTASK',
            'project_type': 'reservation', 'state': 'construction'})
        project.write({'contract_amount': MANUAL_AMOUNT})
        self.assertEqual(self._state(project), (MANUAL_AMOUNT, False),
                         '沒有工項可比，手填的值就是契約金額，不必記成手動')
        self.env['project.task'].create({
            'name': '回復原版後來匯入的工項', 'project_id': project.id,
            'unit': 'M', 'planned_qty': TASK_QTY, 'unit_price': TASK_PRICE})
        self.assertEqual(self._state(project), (TASK_SUM, False))

    def test_backend_form_edit_and_untick_after_start(self):
        """後台表單：開工後這一格能改；一改就看得到「手動輸入」勾起來，取消勾選金額立刻改回工項合計。"""
        self.project.action_approve()
        with Form(self.project, view=PROJECT_FORM) as form:
            form.contract_amount = MANUAL_AMOUNT
            self.assertTrue(form.contract_amount_manual, '改了金額，表單上就要勾起「手動輸入」')
        self.assertEqual(self._state(), (MANUAL_AMOUNT, True))
        with Form(self.project, view=PROJECT_FORM) as form:
            form.contract_amount_manual = False
            self.assertEqual(form.contract_amount, TASK_SUM, '取消勾選，表單上的金額要改回工項合計')
        self.assertEqual(self._state(), (TASK_SUM, False))

    def test_form_field_not_readonly(self):
        arch = etree.fromstring(self.env.ref(PROJECT_FORM).arch)
        amount = arch.xpath("//field[@name='contract_amount']")
        self.assertTrue(amount)
        self.assertEqual(amount[0].get('readonly') or '', '', '契約金額在表單上不該再依狀態唯讀')
        self.assertTrue(arch.xpath("//field[@name='contract_amount_manual']"),
                        '表單上要看得到「契約金額手動輸入」，才有辦法取消')
