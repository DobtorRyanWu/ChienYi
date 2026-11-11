# -*- coding: utf-8 -*-
"""工程後台使用者自動有試算表使用者權限（2026-11-11 使用者決定「所有工程後台使用者都能用」）。

代操作員 imply 工程後台使用者，所以也有；只有 base.group_user 的內部帳號沒有；
公司儀表板的角色帳號群組（唯讀）不可以經由任何繼承拿到試算表權限。
"""
from odoo.tests.common import TransactionCase, tagged

SSE_GROUP = 'spreadsheet_oca.group_user'
ROLE_GROUPS = (
    'construction_company_dashboard.group_role_boss',
    'construction_company_dashboard.group_role_manager',
    'construction_company_dashboard.group_role_supervision',
)


@tagged('post_install', '-at_install', 'dobtor_spreadsheet_editor_chienyi')
class TestEngineeringGroupSpreadsheet(TransactionCase):

    def _user(self, login, *group_xmlids):
        return self.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [self.env.ref(x).id for x in ('base.group_user',) + group_xmlids])],
        })

    def test_engineering_user_has_spreadsheet_group(self):
        user = self._user('sse_engineer', 'construction_supervision_base.group_supervisor_admin')
        self.assertTrue(user.has_group(SSE_GROUP))

    def test_operator_has_spreadsheet_group(self):
        user = self._user('sse_operator', 'construction_supervision_base.group_operator')
        self.assertTrue(user.has_group(SSE_GROUP))

    def test_plain_internal_user_has_not(self):
        """對照組：證明上面兩支不是因為「所有內部帳號都有」才綠"""
        user = self._user('sse_plain')
        self.assertFalse(user.has_group(SSE_GROUP))

    def test_role_groups_do_not_imply_spreadsheet(self):
        sse = self.env.ref(SSE_GROUP)
        roles = [self.env.ref(x, raise_if_not_found=False) for x in ROLE_GROUPS]
        roles = [g for g in roles if g]
        if not roles:
            self.skipTest('construction_company_dashboard 沒裝：沒有角色帳號群組可驗')
        for group in roles:
            self.assertNotIn(sse, group.trans_implied_ids | group, '%s 經由繼承拿到試算表權限' % group.full_name)
