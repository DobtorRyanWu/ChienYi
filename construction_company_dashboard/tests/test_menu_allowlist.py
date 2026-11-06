# -*- coding: utf-8 -*-
"""營造廠主管的選單允許清單（合約 §3.7）。"""
from odoo.addons.base.models.ir_ui_menu import IrUiMenu as CoreIrUiMenu
from odoo.tests import tagged

from .test_scope_rules import DashScopeCase

PROGRESS_MENU = 'construction_progress.menu_progress_chart_dashboard'
DASHBOARD_MENU_XMLID_NAME = 'menu_company_dashboard'   # 線 C 建立（views/menu.xml）
DASHBOARD_MENU_MODULE = 'construction_company_dashboard'


def _ancestors_and_self(menu):
    ids = set()
    while menu:
        ids.add(menu.id)
        menu = menu.parent_id
    return ids


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestMenuAllowlist(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.mgr_a.sudo().write({'totp_secret': 'JBSWY3DPEHPK3PXP'})
        # 線 C 已建真選單（views/menu.xml）；測試用真的，不再自造同名 xmlid
        cls.dash_menu = env.ref(f'{DASHBOARD_MENU_MODULE}.{DASHBOARD_MENU_XMLID_NAME}')
        env.registry.clear_cache()
        cls.progress_menu = env.ref(PROGRESS_MENU)

    def _visible(self, user):
        # su=True：核心 load_menus 本來就在 sudo 下呼叫（一般內部帳號對 ir.ui.menu 沒有直接讀取 ACL）；判定仍看 env.user
        return self.env(user=user, su=True)['ir.ui.menu']._visible_menu_ids()

    def _core_visible(self, user):
        return CoreIrUiMenu._visible_menu_ids(self.env(user=user, su=True)['ir.ui.menu'])

    def test_manager_sees_only_allowlist_and_ancestors(self):
        visible = self._visible(self.mgr_a)
        allowed = _ancestors_and_self(self.progress_menu) | _ancestors_and_self(self.dash_menu)
        # 獨立算（沿 parent_id 往上走）：不能多
        self.assertLessEqual(visible, allowed, '營造廠主管看到允許清單以外的選單')
        # 不能少：核心本來就看得到的允許清單選單與其上層，一個都不能少
        self.assertEqual(visible, self._core_visible(self.mgr_a) & allowed)
        self.assertIn(self.dash_menu.id, visible, '公司儀表板選單必須看得到')
        core = self._core_visible(self.mgr_a)
        self.assertGreater(len(core), len(visible), '前提：核心的可見選單比允許清單多，過濾才有意義')

    def test_progress_menu_follows_core_acl(self):
        """進度表圖表：核心 ACL 讓他看得到就必須在清單內（若 ACL 沒給，回報線 A1 補讀取 ACL）。"""
        core = self._core_visible(self.mgr_a)
        self.assertEqual(self.progress_menu.id in self._visible(self.mgr_a), self.progress_menu.id in core)

    def test_other_users_unchanged(self):
        for user in (self.sup, self.console, self.portal_a):
            self.assertEqual(self._visible(user), self._core_visible(user), user.login)
        self.assertGreater(len(self._visible(self.sup)), len(self._visible(self.mgr_a)))
