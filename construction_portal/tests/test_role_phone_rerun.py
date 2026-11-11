# -*- coding: utf-8 -*-
"""S2（2026-11-11）規格 I：既有的手機測試，把前台老闆／主管換成同方別、同層級的後台角色帳號再跑一次。

只換夾具（建帳號的那一支 classmethod）與例外期望；測試本體不複製。期望值照「必守的差異」調整的，寫在各覆寫上。
基底類別以模組屬性引用（不在本模組命名空間綁類別名，免得看起來像是這個檔的測試）；Odoo 18 的載入器只收
「定義在這個檔」的類別、而且預設只收類別自己寫的 test_*，所以子類別要設 allow_inherited_tests_method。
後台角色帳號的群組在 construction_company_dashboard；沒裝就整個略過（沒有角色帳號可換）。
"""
from unittest import SkipTest

from odoo.tests.common import tagged

from odoo.addons.construction_portal.tests import test_contractor_scope_portal as scope_tests
from odoo.addons.construction_portal.tests import test_role_guards as guard_tests
from odoo.addons.construction_portal.tests.dash_fixtures import MANAGER_TOTP_SECRET

DASH = 'construction_company_dashboard'
CONTRACTOR_MARKER = f'{DASH}.group_contractor_manager'
ROLE_BOSS = f'{DASH}.group_role_boss'
ROLE_MANAGER = f'{DASH}.group_role_manager'
ROLE_SUPERVISION = f'{DASH}.group_role_supervision'
P_BOSS = 'construction_supervision_base.group_portal_subscriber'
P_LEADER = 'construction_supervision_base.group_portal_leader'
# 前台角色 → 後台層級群組（同層級）
LEVEL_GROUP = {P_BOSS: ROLE_BOSS, P_LEADER: ROLE_MANAGER}


def _role_account(env, login, portal_group, side_vals, companies):
    """把「前台老闆／主管＋方別」換成同方別、同層級的後台角色帳號（開 TOTP，範圍合格）。

    營造方（side_vals 有範圍公司）：營造方標記＋層級，允許公司＝監造公司＋營造廠；監造方：監造方標記＋層級。
    """
    scope = side_vals.get('dash_scope_company_id')
    marker = CONTRACTOR_MARKER if scope else ROLE_SUPERVISION
    vals = {'name': login, 'login': login, 'company_id': env.company.id,
            'company_ids': [(6, 0, companies.ids)],
            'groups_id': [(6, 0, [env.ref(marker).id, env.ref(LEVEL_GROUP[portal_group]).id])]}
    if scope:
        vals['dash_scope_company_id'] = scope
    user = env['res.users'].with_context(no_reset_password=True).create(vals)
    user.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
    return user


def _require_dashboard(env):
    if not env.ref(ROLE_BOSS, raise_if_not_found=False):
        raise SkipTest('construction_company_dashboard 沒裝：沒有後台角色帳號')


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalRoleGuardsAsRoleAccounts(guard_tests.TestPortalRoleGuards):
    """test_role_guards：主管（營造方前台主管）換成營造方角色主管。閱覽者、現場人員沒有對應的角色帳號，照舊。"""
    # Odoo 18 的測試載入器只收類別自己 __dict__ 裡的 test_*；要跑繼承來的測試方法得明講（odoo/tests/loader.py）
    allow_inherited_tests_method = True

    @classmethod
    def _mk_user(cls, login, group_xmlid, side_vals):
        _require_dashboard(cls.env)   # setUpClass 建帳號時才有 cls.env
        if group_xmlid not in LEVEL_GROUP:
            return super()._mk_user(login, group_xmlid, side_vals)
        return _role_account(cls.env, login, group_xmlid, side_vals,
                             cls.env.company | cls.env['res.company'].browse(side_vals['dash_scope_company_id']))


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalRoleGuardsTableAsRoleAccounts(guard_tests.TestPortalRoleGuardsTable):
    """test_role_guards 表驅動（P5／P6／P7）：監造方前台主管換成監造方角色主管，逐路由驗「主管全部通過」；
    閱覽者、現場人員（營造方前台帳號）照舊。"""
    allow_inherited_tests_method = True

    @classmethod
    def _mk_user(cls, login, group_xmlid, side_vals):
        _require_dashboard(cls.env)
        if group_xmlid not in LEVEL_GROUP:
            return super()._mk_user(login, group_xmlid, side_vals)
        return _role_account(cls.env, login, group_xmlid, side_vals, cls.env.company)


@tagged('post_install', '-at_install', 'construction_portal')
class TestContractorScopePortalAsRoleAccounts(scope_tests.TestContractorScopePortal):
    """test_contractor_scope_portal：營造廠 A 的前台老闆、主管換成營造方角色老闆、主管；監造方前台主管換成監造方角色主管。

    現場人員、閱覽者、範圍空白的前台帳號、營造廠主管、監造方後台員工與代操照舊（它們不是被換的對象）。
    """
    allow_inherited_tests_method = True
    ROLE_LOGINS = {
        'a2_boss_a': P_BOSS,
        'a2_leader_a': P_LEADER,
        'a2_sup_leader': P_LEADER,
    }

    @classmethod
    def _user(cls, login, groups, side_vals, companies=None):
        _require_dashboard(cls.env)   # 基底 setUpClass 沒裝儀表板時已先 SkipTest；這裡再保險一次
        portal_group = cls.ROLE_LOGINS.get(login)
        if not portal_group:
            return super()._user(login, groups, side_vals, companies=companies)
        scope = side_vals.get('dash_scope_company_id')
        allowed = cls.env.company | (cls.env['res.company'].browse(scope) if scope else cls.env['res.company'])
        return _role_account(cls.env, login, portal_group, side_vals, allowed)

    # ── 例外期望 ──────────────────────────────────────────────────────────
    def test_project_domain_supervision_unchanged(self):
        """例外期望：監造方前台主管換成角色帳號後，前台工程條件走 S1 的角色帳號分支（以本人身分經後台範圍規則查到的
        id；supervision_project.py _get_portal_projects_domain_for_role_account），條件的寫法不是依角色的公式——
        但看得到的工程集合與舊前台監造主管相同（基底的第二個斷言照留）。後台員工、代操照基底逐字比。"""
        from odoo.addons.website.tools import MockRequest
        for user in (self.sup_internal, self.sup_operator):
            Project = self.env['project.project'].with_user(user)
            with MockRequest(self.env(user=user)):
                self.assertEqual(Project._get_portal_projects_domain(user.partner_id),
                                 Project._get_portal_projects_domain_by_role(user), user.login)
        self.assertTrue(self.sup_leader._is_role_account(), '前提：被換成角色帳號')
        self.assertEqual(self._domain_ids(self.sup_leader), set(self.projects.ids))
