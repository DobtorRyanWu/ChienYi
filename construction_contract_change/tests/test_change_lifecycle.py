# -*- coding: utf-8 -*-
"""H4 回歸測試 — 契約變更「刪除」工項的生命週期。

H4：wizard 的 _create_change_order_line 在「草稿確認生成明細」當下就把 delete 型別
    的 project.task 封存（active=False），繞過 提送→審查→核定→套用，且駁回不復原。
    正確：封存應只發生在 action_apply（核定後套用）。
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestContractChangeDeleteLifecycle(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['supervision.project'].create({
            'name': 'H4 變更測試工程',
            'code': 'H4-CHG',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.task = cls.env['project.task'].create({
            'name': 'H4 待刪工項',
            'project_id': cls.project.project_id.id,
            'item_no': 'A-001',
            'planned_qty': 10.0,
            'unit_price': 100.0,
        })

    def _build_delete_wizard(self):
        order = self.env['contract.change.order'].create({
            'project_id': self.project.id,
        })
        wizard = self.env['contract.change.wizard'].create({
            'change_order_id': order.id,
            'project_id': self.project.id,
        })
        self.env['contract.change.wizard.line'].create({
            'wizard_id': wizard.id,
            'project_id': self.project.id,
            'task_id': self.task.id,
            'item_name': self.task.name,
            'change_type': 'delete',
        })
        return order, wizard

    def test_delete_not_archived_at_draft_confirm(self):
        """核心：wizard 確認生成明細（草稿）後，工項不得被封存。"""
        order, wizard = self._build_delete_wizard()
        wizard.action_confirm()
        self.assertTrue(
            self.task.active,
            "H4：delete 工項在草稿確認階段就被封存（應待核定後套用才封存）",
        )

    def test_delete_archived_only_after_apply(self):
        """護欄：走完 提送→審查→核定→套用 後，工項才被封存。"""
        order, wizard = self._build_delete_wizard()
        wizard.action_confirm()
        self.assertTrue(self.task.active, "套用前工項仍在")
        order.action_submit()
        order.action_review()
        order.action_approve()
        order.action_apply()
        self.assertFalse(
            self.task.active,
            "套用後 delete 工項應被封存",
        )
