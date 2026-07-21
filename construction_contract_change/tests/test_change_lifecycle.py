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
        cls.project = cls.env['project.project'].create({
            'name': 'H4 變更測試工程',
            'code': 'H4-CHG',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.task = cls.env['project.task'].create({
            'name': 'H4 待刪工項',
            'project_id': cls.project.id,
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


@tagged('post_install', '-at_install', 'construction_contract_change')
class TestContractChangeTotals(TransactionCase):
    """H5：變更前/後契約總額須含「未變更的頂層彙總群組」。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 遷移後 supervision.project 已併入 project.project（工程案件＝原生 project.project）
        cls.project = cls.env['project.project'].create({
            'name': 'H5 總額測試工程',
            'code': 'H5-TOT',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        Task = cls.env['project.task']
        pid = cls.project.id
        # 兩個頂層彙總群組，各含一葉子工項；各群組基底金額 = 1000，總契約 = 2000
        cls.grp_a = Task.create({'name': '群組A', 'project_id': pid, 'sequence': 10})
        cls.leaf_a = Task.create({
            'name': 'A1', 'project_id': pid, 'parent_id': cls.grp_a.id,
            'item_no': 'A-1', 'planned_qty': 10.0, 'unit_price': 100.0, 'sequence': 11,
        })
        cls.grp_b = Task.create({'name': '群組B', 'project_id': pid, 'sequence': 20})
        cls.leaf_b = Task.create({
            'name': 'B1', 'project_id': pid, 'parent_id': cls.grp_b.id,
            'item_no': 'B-1', 'planned_qty': 5.0, 'unit_price': 200.0, 'sequence': 21,
        })

    def test_before_total_includes_unchanged_group(self):
        """只變更群組A，變更前契約金額仍須含群組B（未變更）的基底 → 2000 而非 1000。"""
        # 前提：兩群組基底各 1000
        self.assertEqual(self.grp_a.planned_amount, 1000.0)
        self.assertEqual(self.grp_b.planned_amount, 1000.0)

        order = self.env['contract.change.order'].create({'project_id': self.project.id})
        wizard = self.env['contract.change.wizard'].create({
            'change_order_id': order.id, 'project_id': self.project.id,
        })
        WL = self.env['contract.change.wizard.line']

        def wline(task, change_type=False, new_qty=None, new_price=None, parent=None):
            return WL.create({
                'wizard_id': wizard.id, 'project_id': self.project.id,
                'task_id': task.id, 'item_name': task.name,
                'parent_task_id': parent.id if parent else False,
                'change_type': change_type,
                'new_qty': task.planned_qty if new_qty is None else new_qty,
                'new_unit_price': task.unit_price if new_price is None else new_price,
            })

        # 群組A / 群組B 兩張彙總列；A1 修改（新量12→A 群組變更），B1 不變
        wline(self.grp_a)
        wline(self.leaf_a, change_type='modify', new_qty=12.0, new_price=100.0, parent=self.grp_a)
        wline(self.grp_b)
        wline(self.leaf_b, parent=self.grp_b)  # 未變更

        wizard.action_confirm()

        self.assertEqual(
            order.original_contract_amount, 2000.0,
            "H5：變更前契約金額漏計未變更的群組B（應 2000，得 %s）"
            % order.original_contract_amount,
        )
