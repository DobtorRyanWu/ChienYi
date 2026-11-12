# -*- coding: utf-8 -*-
"""受限帳號對「公司自有的行政資料」的讀取範圍（rule_scope.COMPANY_OWNED_LEVEL；淞源 2026-11-10 會議 C10）。

公文（construction_office，選裝）屬於「所屬公司」，不是工程上每一方都能看：
* 營造方（營造廠主管、營造方角色帳號）只看所屬公司＝自己範圍公司的；
* 監造方角色帳號只看監造公司的；
* 後台主管（角色帳號 manager 層級）再限參與的工程（未開始／終止的不算；沒掛工程的看不到）；
* 控台讀取帳號一筆都看不到；受限帳號一律不能寫。
沒裝 construction_office 的庫整組略過。期望值依夾具獨立寫出。
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_role_accounts import RoleMatrixCase

DOC_MODEL = 'construction.official.doc'
OFFICE_MENU = 'construction_office.menu_official_doc'
MANAGER_ACL = 'construction_company_dashboard.access_cm_official_doc'
ROLE_ACL = 'construction_company_dashboard.access_role_official_doc'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestOfficeScope(RoleMatrixCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office_installed = DOC_MODEL in cls.env
        if not cls.office_installed:
            return
        # construction_office 比本模組晚裝時，ACL 要再同步一次才有（optional_access.py 的已知限制）
        cls.env['ir.model.access']._dash_sync_optional_manager_access()
        Doc = cls.env[DOC_MODEL]

        def doc(name, company, project=None):
            return Doc.create({'subject': f'OFFICE {name}', 'company_id': company.id,
                               'project_id': project.id if project else False})

        cls.d_a_shared = doc('A 共用工程', cls.co_a, cls.p_shared)
        cls.d_a_pa = doc('A 工程 PA', cls.co_a, cls.p_a)
        cls.d_a_none = doc('A 公司共通', cls.co_a)
        cls.d_a_draft = doc('A 未開始工程', cls.co_a, cls.p_draft)
        cls.d_b_shared = doc('B 共用工程', cls.co_b, cls.p_shared)
        cls.d_s_shared = doc('S 共用工程', cls.co_s, cls.p_shared)
        cls.d_s_pa = doc('S 工程 PA', cls.co_s, cls.p_a)
        cls.d_s_none = doc('S 公司共通', cls.co_s)
        cls.d_s2 = doc('S2 工程', cls.co_s2, cls.p_s2)
        cls.office_docs = (cls.d_a_shared | cls.d_a_pa | cls.d_a_none | cls.d_a_draft | cls.d_b_shared
                           | cls.d_s_shared | cls.d_s_pa | cls.d_s_none | cls.d_s2)

    def setUp(self):
        super().setUp()
        if not self.office_installed:
            self.skipTest('沒裝 construction_office')

    def _seen(self, user):
        Doc = self.env[DOC_MODEL].with_user(user).with_context(active_test=False)
        return Doc.search([('id', 'in', self.office_docs.ids)])

    def test_contractor_side_sees_only_own_company(self):
        own = self.d_a_shared | self.d_a_pa | self.d_a_none | self.d_a_draft
        self.assertEqual(self._seen(self.mgr_a), own, '營造廠主管：所屬公司＝A 的全部')
        self.assertEqual(self._seen(self.cb), own, '營造方老闆（角色帳號）：所屬公司＝A 的全部')
        # 營造方主管（角色帳號）：只加入共用工程（另有未開始、終止兩個，不算）→ 只有那一份；公司共通的看不到
        self.assertEqual(self._seen(self.cm), self.d_a_shared)

    def test_supervision_role_sees_only_supervision_company(self):
        self.assertEqual(self._seen(self.sb), self.d_s_shared | self.d_s_pa | self.d_s_none,
                         '監造方老闆：監造公司 S 的全部；營造廠 A、B 與另一家監造 S2 的看不到')
        self.assertEqual(self._seen(self.sm), self.d_s_pa, '監造方主管：只有參與的工程 PA')

    def test_console_reader_sees_nothing_and_backend_staff_unchanged(self):
        # 控台讀取帳號沒有公文的讀取 ACL（連查都不能查）；萬一之後有了 ACL，範圍規則也要讓它一筆都看不到
        try:
            seen = self._seen(self.console)
        except AccessError:
            seen = self.env[DOC_MODEL]
        self.assertFalse(seen)
        # 監造方後台人員不受本規則影響：照公文模組自己的規則（所屬公司在允許公司內）
        self.assertEqual(self._seen(self.sup), self.d_s_shared | self.d_s_pa | self.d_s_none)

    def test_restricted_accounts_cannot_write(self):
        for user in (self.mgr_a, self.cb, self.cm, self.sb, self.sm):
            readable = self._seen(user)
            self.assertTrue(readable, user.login)
            with self.assertRaises(AccessError, msg=user.login):
                readable[0].with_user(user).write({'subject': '被改了'})
            with self.assertRaises(AccessError, msg=user.login):
                self.env[DOC_MODEL].with_user(user).create({'subject': '受限帳號建的'})
            with self.assertRaises(AccessError, msg=user.login):
                readable[0].with_user(user).unlink()

    def test_read_acl_is_granted_by_sync_and_read_only(self):
        for xmlid in (MANAGER_ACL, ROLE_ACL):
            acl = self.env.ref(xmlid, raise_if_not_found=False)
            self.assertTrue(acl, f'{xmlid} 要由 _dash_sync_optional_manager_access 建好')
            self.assertEqual((acl.model_id.model, acl.perm_read, acl.perm_write, acl.perm_create, acl.perm_unlink),
                             (DOC_MODEL, True, False, False, False))

    def test_role_accounts_see_office_menu(self):
        menu = self.env.ref(OFFICE_MENU)
        for user in (self.cb, self.cm, self.sb, self.sm):
            visible = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
            self.assertIn(menu.id, visible, f'{user.login} 要看得到「公文」選單')
        # 營造廠主管（不是角色帳號）的選單照舊只有公司儀表板與進度表圖表
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(self.mgr_a)._visible_menu_ids())
