# -*- coding: utf-8 -*-
"""監造方與其他使用者：ir.rule._compute_domain 回傳值與覆寫前完全相同（合約 §0b-1、§1-3）。

證明方式：直接呼叫核心類別 odoo.addons.base.models.ir_rule.IrRule._compute_domain（不經本模組覆寫），
對 registry 每個模型 × 讀寫建刪 4 種模式，與經過覆寫的結果逐一比對。
"""
from odoo.addons.base.models.ir_rule import IrRule as CoreIrRule
from odoo.tests import tagged

from .test_scope_rules import DashScopeCase

MODES = ('read', 'write', 'create', 'unlink')
SUPERVISION_ORG = 'construction_supervision_base.group_supervision_org'
PORTAL_USER = 'construction_supervision_base.group_portal_user'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestSupervisionUnchanged(DashScopeCase):

    def _unaffected_users(self):
        portal_sup = self._user('dash_portal_sup', [PORTAL_USER], company=self.co_s, companies=self.co_s,
                                extra={'is_supervision_org': True})
        users = self.sup | portal_sup | self.env.ref('base.user_admin') | self.env.ref('base.public_user')
        operator = self.env['res.users'].search(
            [('groups_id', 'in', self.env.ref('construction_supervision_base.group_operator').id),
             ('company_id.company_type', '!=', 'contractor')], limit=1)
        return users | operator

    def test_identity_judgment(self):
        self.assertTrue(self.sup._is_supervision_side())
        self.assertTrue(self.env.ref('base.user_admin')._is_supervision_side())
        for user in (self.mgr_a, self.portal_a, self.portal_blank, self.console):
            self.assertFalse(user._is_supervision_side(), user.login)
        self.assertTrue(self.mgr_a._dash_is_contractor_side())
        self.assertTrue(self.portal_a._dash_is_contractor_side())
        self.assertFalse(self.console._dash_is_contractor_side())
        self.assertTrue(self.console._dash_is_console_reader())

    def test_compute_domain_identical_to_core_for_unaffected_users(self):
        users = self._unaffected_users()
        self.assertGreaterEqual(len(users), 4)
        names = sorted(self.env.registry)
        compared = differ = 0
        diffs = []
        for user in users:
            self.assertFalse(user._dash_is_restricted(), user.login)   # 前提：不是受限帳號（fix2-P：與 kind 同一份判斷）
            rule = self.env['ir.rule'].with_user(user)
            for name in names:
                for mode in MODES:
                    got = rule._compute_domain(name, mode)
                    core = CoreIrRule._compute_domain(rule, name, mode)
                    compared += 1
                    if got != core:
                        differ += 1
                        if len(diffs) < 10:
                            diffs.append((user.login, name, mode, got, core))
        self.assertGreater(compared, len(names), '比對數不可為 0')
        self.assertEqual(differ, 0, f'監造方與其他使用者的規則條件必須與核心相同：{diffs}')

    def test_core_comparison_is_not_vacuous(self):
        """反證：同樣的比對對營造廠主管會出現差異（否則上面那支可能比的是同一個東西）。"""
        rule = self.env['ir.rule'].with_user(self.mgr_a)
        differ = [n for n in ('project.project', 'construction.meeting.record', 'project.task')
                  if n in self.env and rule._compute_domain(n, 'read') != CoreIrRule._compute_domain(rule, n, 'read')]
        self.assertTrue(differ)

    def test_supervision_can_still_write(self):
        """監造方後台帳號照常建立、修改營造廠層級單據（歸屬照預設帶入）。"""
        env = self.env(user=self.sup)
        defect = env['general.defect.improvement'].create(self._doc_vals('general.defect.improvement', self.p_a))
        self.assertEqual(defect.contractor_company_id, self.co_a)
        defect.write({'defect_description': 'DASH 監造方改寫'})
        self.assertEqual(defect.defect_description, 'DASH 監造方改寫')
