# -*- coding: utf-8 -*-
"""S2（2026-11-11）前台的兩條：F（jt 共用庫的跨公司寫入）、G（工程編號重複不帶出別家工程）。

F：工程資訊存檔（/construction/<id>/update）以 sudo 寫 company_id、承攬廠商、使用者 id；新增工程（/project/create）
   以 sudo 建立。這些 id 必須在帳號的允許公司內（承攬廠商照舊前台規則：公司類型是營造廠），不在就 AccessError、
   不寫任何東西。前台帳號、後台角色帳號、代操作員都適用。編輯頁的下拉與驗證是同一份（_project_edit_options）。
G：工程編號重複時只說「已被使用」，不帶出那個工程的名稱與公司（sudo 查到的可能是別家的工程）。

後台角色帳號的群組在 construction_company_dashboard；沒裝時角色帳號那幾格略過，其餘照跑。
"""
import unittest

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    MANAGER_TOTP_SECRET, SUPERVISION_USER_VALS, make_contractor)

DASH = 'construction_company_dashboard'
ROLE_BOSS = f'{DASH}.group_role_boss'
ROLE_SUPERVISION = f'{DASH}.group_role_supervision'
P_BOSS = 'construction_supervision_base.group_portal_subscriber'
OPERATOR = 'construction_supervision_base.group_operator'
COMPANY_TYPE_SUPERVISION = 'supervision'


@tagged('post_install', '-at_install', 'construction_portal')
class TestProjectWriteCompanyScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        Company = env['res.company']
        cls.co_s = Company.create({'name': 'F 監造 S', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.co_other = Company.create({'name': 'F 別家監造', 'company_type': COMPANY_TYPE_SUPERVISION})
        cls.co_a = make_contractor(env, 'F 營造 A')
        cls.co_b = make_contractor(env, 'F 營造 B')
        cls.project = env['project.project'].create({
            'name': 'F 草稿工程', 'code': 'F-DRAFT', 'project_type': 'general', 'state': 'draft',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        cls.other_project = env['project.project'].create({
            'name': 'F 別家的機密工程', 'code': 'F-SECRET', 'company_id': cls.co_other.id})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, company=None, **extra):
            company = company or cls.co_s
            return Users.create({'name': login, 'login': login, 'company_id': company.id,
                                 'company_ids': [(6, 0, company.ids)],
                                 'groups_id': [(6, 0, [env.ref(g).id for g in groups])], **extra})
        cls.portal_boss = user('f_portal_boss', [P_BOSS], **SUPERVISION_USER_VALS)
        cls.operator = user('f_operator', ['base.group_user', OPERATOR])
        cls.staff_s = user('f_staff_s', ['base.group_user'])
        cls.staff_other = user('f_staff_other', ['base.group_user'], company=cls.co_other)
        cls.writers = cls.portal_boss | cls.operator
        cls.role_boss = None
        if env.ref(ROLE_BOSS, raise_if_not_found=False):
            cls.role_boss = user('f_role_sb', [ROLE_SUPERVISION, ROLE_BOSS])
            cls.role_boss.sudo().write({'totp_secret': MANAGER_TOTP_SECRET})
            cls.writers |= cls.role_boss
        for account in cls.writers:
            env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': account.id})

    def _post(self, user, **post):
        self.env.flush_all()
        self.env.invalidate_all()
        with MockRequest(self.env(user=user)) as req:
            # 承攬廠商是多選勾選框：路由從原始表單 getlist 讀
            req.httprequest.form.getlist.side_effect = lambda key: list(post.get(key) or [])
            return self.ctrl.portal_construction_project_update(self.project.id, **post)

    WATCHED_FIELDS = ['name', 'company_id', 'contractor_company_ids', 'site_manager_id', 'supervision_engineer_id',
                      'notes']

    def _assert_rejected(self, user, label, **post):
        before = self.project.read(self.WATCHED_FIELDS)[0]
        with self.assertRaises(AccessError, msg=f'{user.login} × {label}'):
            self._post(user, name='F 改名', notes='F 改備註', **post)
        self.env.invalidate_all()
        self.assertEqual(self.project.read(self.WATCHED_FIELDS)[0], before,
                         f'{user.login} × {label}：沒有寫進任何東西（含名稱）')

    def test_update_rejects_ids_outside_allowed(self):
        for user in self.writers:
            self._assert_rejected(user, '別家監造公司', company_id=str(self.co_other.id))
            self._assert_rejected(user, '工地主任是別家的人', site_manager_id=str(self.staff_other.id))
            self._assert_rejected(user, '監造工程師是別家的人', supervision_engineer_id=str(self.staff_other.id))
            if self.role_boss:
                self._assert_rejected(user, '監造工程師不是後台人員', supervision_engineer_id=str(self.role_boss.id))
            # 承攬廠商：不是營造廠的公司（這裡是監造公司）不能填
            with self.assertRaises(AccessError, msg=f'{user.login} × 承攬廠商填監造公司'):
                self._post(user, _edit_form='1', **{'contractor_company_ids': [str(self.co_other.id)]})
            self.env.invalidate_all()
            self.assertEqual(self.project.contractor_company_ids, self.co_a)

    def test_update_accepts_allowed_ids(self):
        for index, user in enumerate(self.writers):
            notes = f'F 正常存檔 {index}'
            response = self._post(user, notes=notes, company_id=str(self.co_s.id),
                                  site_manager_id=str(self.staff_s.id), supervision_engineer_id=str(self.staff_s.id))
            self.assertIn('message=updated', response.headers.get('Location', ''), user.login)
            self.env.invalidate_all()
            self.assertIn(notes, self.project.notes or '')   # Html 欄位：存成 <p>…</p>
            self.assertEqual(self.project.site_manager_id, self.staff_s)
            self.assertEqual(self.project.supervision_engineer_id, self.staff_s)

    def test_edit_dropdowns_match_validation(self):
        """編輯頁的下拉＝驗證的可選值（畫面與後端同一份）：別家公司、別家的人不出現在下拉。"""
        for user in self.writers:
            captured = []
            with MockRequest(self.env(user=user)) as req:
                req.render = lambda template, values=None, **kw: captured.append(values) or ''
                self.ctrl.portal_construction_project_edit(project_id=self.project.id)
            self.assertEqual(len(captured), 1, f'{user.login}：編輯頁有渲染')
            values = captured[0]
            self.assertNotIn(self.co_other, values['supervision_companies'], user.login)
            self.assertIn(self.co_s, values['supervision_companies'], user.login)
            self.assertNotIn(self.staff_other, values['all_users'], user.login)
            self.assertIn(self.staff_s, values['all_users'], user.login)
            self.assertIn(self.co_b, values['contractor_companies'], '承攬廠商照舊前台規則：所有營造廠')

    def test_create_company_is_current_allowed_company(self):
        for index, user in enumerate(self.writers):
            name = f'F 新工程 {index}'
            with MockRequest(self.env(user=user)):
                self.ctrl.portal_construction_project_create(name=name)
            created = self.env['project.project'].search([('name', '=', name)])
            self.assertEqual(created.company_id, self.co_s, f'{user.login}：建在自己的公司')
            # 選了允許公司以外的公司（cids）：核心 Environment.company 先擋，不會建到別家
            bad = f'F 跨公司新工程 {index}'
            with self.assertRaises(AccessError, msg=user.login):
                with MockRequest(self.env(user=user), context={'allowed_company_ids': [self.co_other.id]}):
                    self.ctrl.portal_construction_project_create(name=bad)
            self.assertFalse(self.env['project.project'].search_count([('name', '=', bad)]))

    def test_code_duplicate_message_hides_other_project(self):
        """G：撞到別家工程的編號，訊息不帶出那個工程的名稱與公司。"""
        for user in self.writers:
            with MockRequest(self.env(user=user)):
                result = self.ctrl.portal_construction_project_code_update(self.project.id, code='F-SECRET')
            self.assertFalse(result['success'], user.login)
            self.assertIn('已被使用', result['error'])
            self.assertNotIn(self.other_project.name, result['error'], user.login)
            self.assertNotIn(self.co_other.name, result['error'], user.login)
        self.assertEqual(self.project.code, 'F-DRAFT')
