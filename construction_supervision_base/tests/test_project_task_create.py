# -*- coding: utf-8 -*-
"""C6 — project.task 的兩個 create() 互相覆蓋，item_no 自動產生從來沒生效。

`class ProjectTask` 內定義了兩個 `def create`（原始碼第 679、903 行）。
Python 後定義的會取代前者，所以第 679 行那個負責自動產生 `item_no` 與 `sequence`
的版本是**死碼、從未執行**。而 `item_no` 是 `required=True`（DB NOT NULL），
於是任何沒有明確給 `item_no` 的建立都會炸。

實務上一直沒被發現，是因為匯入管線與表單都會明確帶 `item_no`。
但 Odoo core 建立 `res.company` 時會自動建一個「內部專案」與其 task
（`hr_timesheet` 的 `_create_internal_project_task()`），core 當然不知道要填
`item_no` → NotNullViolation → **建不了新公司**。多租戶佈建就卡在這裡。
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestProjectTaskCreate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'C6 測試工程',
            'code': 'C6-TEST',
            'project_type': 'general',
        })

    def test_item_no_auto_generated_when_missing(self):
        """沒給 item_no 就要自動產生，不能讓 NOT NULL 擋下來。"""
        task = self.env['project.task'].create({
            'name': 'C6 未給編號的工項',
            'project_id': self.project.id,
        })
        self.assertTrue(task.item_no, 'item_no 未自動產生')

    def test_sequence_auto_calculated_when_missing(self):
        """sequence 同樣要自動計算（與 item_no 在同一段死碼裡）。"""
        task = self.env['project.task'].create({
            'name': 'C6 未給排序的工項',
            'project_id': self.project.id,
        })
        self.assertTrue(task.sequence, 'sequence 未自動計算')

    def test_explicit_item_no_is_respected(self):
        """有給就照給的用，不可被自動產生蓋掉。"""
        task = self.env['project.task'].create({
            'name': 'C6 指定編號',
            'project_id': self.project.id,
            'item_no': '9.87',
        })
        self.assertEqual(task.item_no, '9.87')

    def test_version_record_still_created(self):
        """合併兩個 create() 後，原本第二個 create 的建版行為不可遺失。"""
        task = self.env['project.task'].create({
            'name': 'C6 有數量單價的工項',
            'project_id': self.project.id,
            'item_no': '1.1',
            'planned_qty': 5.0,
            'unit_price': 100.0,
        })
        versions = self.env['project.task.version'].search([('task_id', '=', task.id)])
        self.assertEqual(len(versions), 1, '應建立 v1 版本記錄')
        self.assertEqual(versions.version, 1)
        self.assertEqual(versions.planned_qty, 5.0)
        self.assertEqual(versions.unit_price, 100.0)

    def test_no_version_when_no_qty_and_price(self):
        """無數量也無單價時不建版本（既有行為）。"""
        task = self.env['project.task'].create({
            'name': 'C6 無數量單價',
            'project_id': self.project.id,
            'item_no': '1.2',
        })
        self.assertFalse(
            self.env['project.task.version'].search([('task_id', '=', task.id)]))

    def test_res_company_can_be_created(self):
        """C6 的實際症狀：建立公司會連帶建內部專案 task，不能因此失敗。

        多租戶佈建（tools/tenant_provisioning/）就是走這條路。
        """
        company = self.env['res.company'].create({'name': 'C6 測試公司'})
        self.assertTrue(company.id)
