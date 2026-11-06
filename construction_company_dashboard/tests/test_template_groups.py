# -*- coding: utf-8 -*-
"""合約 §10 F 列的風險（線 A1' 提出、線 F1 在 dev 複本實測）：安裝「替範本使用者加群組」的模組。

核心在範本使用者（base.default_user）多了群組時，把新群組推給全部既有內部帳號
（odoo/addons/base/models/res_users.py write，dev 開了 base_setup.default_user_rights）。
營造廠主管與控台讀取帳號受群組允許清單約束，推給它們會讓整個安裝失敗（實測 hr_attendance：
「d_mgr_nototp 不可再帶其他群組：Attendances / Administrator」）。定案：受限帳號不接收範本推送，
其他內部帳號照核心行為接收；base.group_user 新隱含的群組照舊經隱含閉包加上（約束放行）。
"""
from odoo.tests import tagged

from .test_scope_rules import DashScopeCase

PROPAGATE_PARAM = 'base_setup.default_user_rights'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestTemplateGroupPropagation(DashScopeCase):

    def test_template_group_not_pushed_to_restricted_accounts(self):
        env = self.env
        env['ir.config_parameter'].sudo().set_param(PROPAGATE_PARAM, True)
        group = env['res.groups'].create({'name': 'DASH 範本新群組（模擬安裝模組）'})
        # 安裝模組時資料檔做的就是這一步；不可因群組允許清單約束失敗
        env.ref('base.default_user').write({'groups_id': [(4, group.id)]})
        env.invalidate_all()
        self.assertIn(group, self.sup.groups_id, '一般內部帳號照核心行為接收範本新群組（推送真的有發生）')
        for user in (self.mgr_a, self.console):
            self.assertNotIn(group, user.groups_id, f'{user.login}：受限帳號不接收範本推送')
            user._dash_check_account_setup()      # 仍合格（不丟例外）

    def test_group_user_new_implied_group_still_allowed(self):
        """base.group_user 新隱含一個群組（hr_attendance 的「讀自己的出勤」就是這樣）：受限帳號照核心加上、約束放行。"""
        env = self.env
        group = env['res.groups'].create({'name': 'DASH 內部帳號新隱含群組'})
        env.ref('base.group_user').write({'implied_ids': [(4, group.id)]})
        env.invalidate_all()
        for user in (self.sup, self.mgr_a, self.console):
            self.assertIn(group, user.groups_id, user.login)
        (self.mgr_a | self.console)._dash_check_account_setup()
