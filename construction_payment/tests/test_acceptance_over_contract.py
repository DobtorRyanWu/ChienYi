# -*- coding: utf-8 -*-
"""M3.0 #3 回歸測試 — 超約警告 chatter 不得在每次存檔時重複洗版。

原始 bug（稽核 M3.0 #3）：`work.acceptance.line._check_over_contract` 是
`@api.constrains`，卻在其中對 `acceptance_id` 執行 `message_post`（副作用）。
constrains 每次寫入受監控欄位都會觸發 → 只要該明細維持「累計 > 契約」，
每存一次檔就再貼一則相同警告，chatter 被洗版。

正確設計：把警告移出 constrains，改在 create/write 只於「未超約 → 超約」的
轉變時發一次。本測試鎖定：(1) 維持超約狀態重複存檔不重貼；(2) 新跨越門檻仍會發警告。
"""

from odoo.tests.common import TransactionCase, tagged

WARN_MARK = '超過契約數量'


@tagged('post_install', '-at_install', 'construction_payment')
class TestAcceptanceOverContract(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '驗收超約測試工程',
            'code': 'ACC-OVER',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.task = cls.env['project.task'].create({
            'name': '驗收工項Y',
            'project_id': cls.project.id,
            'item_no': 'Y-1',
            'unit': '式',
            'planned_qty': 10.0,
            'unit_price': 10.0,
        })

    def _make_acceptance(self, accepted_qty, contract_qty=10.0, completed_qty=20.0):
        acc = self.env['work.acceptance'].create({
            'project_id': self.project.id,
            'contractor_company_id': self.env.company.id,
        })
        line = self.env['work.acceptance.line'].create({
            'acceptance_id': acc.id,
            'task_id': self.task.id,
            'contract_qty': contract_qty,
            'previous_accepted_qty': 0.0,
            'completed_qty': completed_qty,
            'accepted_qty': accepted_qty,
            'unit_price': 10.0,
        })
        return acc, line

    def _warn_count(self, acc):
        return len(acc.message_ids.filtered(
            lambda m: m.body and WARN_MARK in m.body
        ))

    def test_over_contract_warning_not_duplicated_on_resave(self):
        """維持超約狀態重複存檔，警告只發一次（M3.0 #3 核心）。"""
        acc, line = self._make_acceptance(accepted_qty=15.0)  # 累計 15 > 契約 10
        self.assertEqual(
            self._warn_count(acc), 1,
            "建立超約明細應發一則警告",
        )
        # 再次寫入受 constrains 監控的欄位、但仍維持超約（15 → 16）
        line.write({'accepted_qty': 16.0})
        self.assertEqual(
            self._warn_count(acc), 1,
            "M3.0#3：維持超約狀態的重複存檔不應再貼相同警告（constrains 副作用洗版）",
        )

    def test_over_contract_warning_fires_on_new_crossing(self):
        """由未超約寫成超約時，仍要發出一次警告（確認搬離 constrains 後功能不遺失）。"""
        acc, line = self._make_acceptance(accepted_qty=5.0)  # 累計 5 <= 契約 10，不超約
        self.assertEqual(
            self._warn_count(acc), 0,
            "未超約不應有警告",
        )
        line.write({'accepted_qty': 12.0})  # 5 → 12，新跨越門檻
        self.assertEqual(
            self._warn_count(acc), 1,
            "新跨越契約門檻應發出一次警告",
        )
