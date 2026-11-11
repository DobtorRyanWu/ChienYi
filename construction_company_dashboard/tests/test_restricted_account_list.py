# -*- coding: utf-8 -*-
"""S3-C（受限帳號唯一清單）與 S3-B（解除安裝硬擋），2026-11-11。

C：res.users.dash_restricted_account_logins()——hook、換版工具 qd.py、runbook 共用的唯一清單。
   判斷只有一個：res.users._dash_is_restricted()（全系統唯一一份；含前台營造帳號）。超級使用者排除；含已封存。
   fail-closed（S3 fix1，主迴圈 11-11 決定）：5 個受限群組的 xmlid 任一個找不到 → UserError（判斷函式靠它們認人，
   少一個就認不全，不可以回一份殘缺的清單讓人以為可以解除安裝／降版）。
   內部受限（控台讀取、監造方角色帳號）、前台營造帳號、已封存的各被列出；非系統管理者呼叫一律 AccessError；
   系統管理者經 HTTP call_kw 拿得到。
B：construction_company_dashboard 的 uninstall_hook：清單非空就 raise UserError（不封存、直接拒絕），
   訊息分兩段列 login、寫 runbook 路徑；清單本身 raise（xmlid 不完整）時也拒絕。**絕不真的解除安裝**：直接呼叫 hook 函式。
期望值由夾具獨立寫出（不 import 實作的群組清單；群組 xmlid 在這裡另寫一份）。
"""
import json
import os
from contextlib import closing, contextmanager
from unittest.mock import patch

import odoo
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_manifest, get_module_path
from odoo.tests import HttpCase, TransactionCase, tagged

from .test_scope_rules import CONSOLE_GROUP, PORTAL_LEADER, SUPERVISOR_ADMIN

MODULE = 'construction_company_dashboard'
ROLE_BOSS = f'{MODULE}.group_role_boss'
ROLE_SUPERVISION = f'{MODULE}.group_role_supervision'
# 5 個受限群組（測試獨立寫一份；實作用 res_users_guard.CARRIER_GROUP_XMLIDS）：任一個 xmlid 不見都要 raise
CARRIER_XMLIDS = (
    f'{MODULE}.group_contractor_manager', f'{MODULE}.group_console_reader',
    f'{MODULE}.group_role_boss', f'{MODULE}.group_role_manager', f'{MODULE}.group_role_supervision',
)
INCOMPLETE_HINT = '受限群組定義不完整'
METHOD = 'dash_restricted_account_logins'
RUNBOOK = f'{MODULE}/README_ROLE_ACCOUNTS.md'
RUNBOOK_FILE = 'README_ROLE_ACCOUNTS.md'
CANCEL_HINT = '這次解除安裝已取消'
SECTION_INTERNAL = '內部受限帳號'
SECTION_PORTAL = '前台營造帳號'
PASSWORD = 'S3-list-pass1'
SUPERUSER_LOGIN = '__system__'


class RestrictedListCase(TransactionCase):
    """夾具：內部受限（控台讀取、監造方角色帳號）、前台營造帳號、已封存的各一，另加一般內部、工程後台使用者、系統管理者。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_c = Company.create({'name': 'S3C 營造', 'company_type': 'contractor'})
        cls.co_s = Company.create({'name': 'S3C 監造', 'company_type': 'supervision'})
        # 前台營造帳號（share）
        cls.portal = cls._mk('s3c_portal', [PORTAL_LEADER], cls.co_c, cls.co_c | cls.co_s,
                             is_contractor_org=True, dash_scope_company_id=cls.co_c.id)
        # 內部受限：控台讀取帳號、監造方角色帳號
        cls.console = cls._mk('s3c_console', [CONSOLE_GROUP], cls.co_s, cls.co_s)
        cls.role_sb = cls._mk('s3c_role_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s, cls.co_s)
        # 已封存的前台營造帳號（清單要含已封存）
        cls.portal_archived = cls._mk('s3c_portal_arch', [PORTAL_LEADER], cls.co_c, cls.co_c | cls.co_s,
                                      is_contractor_org=True, dash_scope_company_id=cls.co_c.id)
        cls.portal_archived.sudo().write({'active': False})
        # 已封存的受限內部帳號
        cls.archived = cls._mk('s3c_archived', [CONSOLE_GROUP], cls.co_s, cls.co_s)
        cls.archived.sudo().write({'active': False})
        # 不受限的
        cls.plain = cls._mk('s3c_plain', ['base.group_user'], cls.co_s, cls.co_s)
        cls.staff = cls._mk('s3c_staff', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s, cls.co_s)
        cls.sysadmin = cls._mk('s3c_sysadmin', ['base.group_user', 'base.group_system'], cls.co_s, cls.co_s)
        env.flush_all()
        env.registry.clear_cache()

    @classmethod
    def _mk(cls, login, groups, company, companies, **extra):
        return cls.env['res.users'].with_context(no_reset_password=True).create(dict({
            'name': login, 'login': login, 'password': PASSWORD,
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
            'company_id': company.id, 'company_ids': [(6, 0, companies.ids)]}, **extra))

    def _list(self):
        result = getattr(self.env['res.users'], METHOD)()
        self.assertEqual(set(result), {'internal', 'portal'}, '回傳格式：{"internal": [...], "portal": [...]}')
        return result

    @contextmanager
    def _without_xmlid(self, xmlid):
        """在一個一定回滾的 savepoint 裡刪掉群組的 xmlid（群組本身還在）。"""
        module, name = xmlid.split('.')
        data = self.env['ir.model.data'].sudo().search([('module', '=', module), ('name', '=', name)])
        self.assertEqual(len(data), 1, f'夾具：{xmlid} 要恰好一筆')
        try:
            with closing(self.env.cr.savepoint()):
                data.unlink()
                self.env.registry.clear_cache()
                self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False), f'夾具：{xmlid} 要真的不見')
                yield
        finally:
            self.env.invalidate_all()
            self.env.registry.clear_cache()


@tagged('post_install', '-at_install', MODULE)
class TestRestrictedAccountList(RestrictedListCase):

    def test_each_kind_listed_in_its_bucket(self):
        result = self._list()
        internal, portal = set(result['internal']), set(result['portal'])
        for user in (self.console, self.role_sb, self.archived):
            self.assertIn(user.login, internal, f'{user.login} 要列在 internal')
            self.assertNotIn(user.login, portal, user.login)
        self.assertIn(self.portal.login, portal, '前台營造帳號要列在 portal')
        self.assertIn(self.portal_archived.login, portal, '已封存的前台營造帳號也要列在 portal')
        self.assertNotIn(self.portal.login, internal)
        for user in (self.plain, self.staff, self.sysadmin):
            self.assertNotIn(user.login, internal | portal, f'{user.login} 不是受限帳號')
        self.assertFalse(internal & portal, '同一個帳號不可兩邊都列')
        self.assertEqual(result['internal'], sorted(result['internal']), 'internal 依 login 排序')
        self.assertEqual(result['portal'], sorted(result['portal']), 'portal 依 login 排序')
        self.assertEqual(len(result['internal']), len(internal), '不可重複')

    def test_carrier_xmlid_missing_raises(self):
        """fail-closed：5 個受限群組的 xmlid 任一個不見（半套解除安裝、手動刪）→ UserError，不回殘缺的清單。

        每個 xmlid 各在自己的 savepoint 裡刪、斷言、回滾；刪之前先證明清單照常（rig 有效）。
        """
        self.assertIn(self.console.login, self._list()['internal'], '夾具：xmlid 齊全時清單照常')
        for xmlid in CARRIER_XMLIDS:
            with self.subTest(xmlid=xmlid), self._without_xmlid(xmlid):
                with self.assertRaises(UserError) as ctx:
                    self._list()
                self.assertIn(INCOMPLETE_HINT, str(ctx.exception))
                self.assertIn(xmlid, str(ctx.exception), '訊息要指出哪一個找不到')
        self.assertIn(self.console.login, self._list()['internal'], '回滾後清單照常（rig 有效）')

    def test_superuser_excluded(self):
        """超級使用者（uid 1）即使在受限群組裡也不列（search 的排除條件）。"""
        group = self.env.ref(CONSOLE_GROUP)
        self.env.cr.execute('INSERT INTO res_groups_users_rel (gid, uid) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                            [group.id, odoo.SUPERUSER_ID])
        self.env.registry.clear_cache()
        self.env.invalidate_all()
        result = self._list()
        self.assertNotIn(SUPERUSER_LOGIN, result['internal'] + result['portal'], '超級使用者排除')
        self.assertIn(self.console.login, result['internal'], '同一群組的其他人照列（rig 有效）')

    def test_non_admin_access_error(self):
        for user in (self.staff, self.plain, self.console, self.portal):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    getattr(self.env['res.users'].with_user(user), METHOD)()
        # 系統管理者（非超級使用者）可以
        result = getattr(self.env['res.users'].with_user(self.sysadmin), METHOD)()
        self.assertIn(self.console.login, result['internal'])


@tagged('post_install', '-at_install', MODULE)
class TestUninstallHook(RestrictedListCase):

    def _hook(self):
        from odoo.addons.construction_company_dashboard import hooks
        return hooks.uninstall_hook

    def test_manifest_declares_hook_and_runbook_exists(self):
        """L1⑭：驗現在磁碟上的 manifest 與套件，不是上一次產生的東西。"""
        self.assertEqual(get_manifest(MODULE).get('uninstall_hook'), 'uninstall_hook')
        package = __import__(f'odoo.addons.{MODULE}', fromlist=['uninstall_hook'])
        self.assertIs(getattr(package, 'uninstall_hook', None), self._hook())
        self.assertTrue(os.path.isfile(os.path.join(get_module_path(MODULE), RUNBOOK_FILE)), 'runbook 要存在')

    def test_hook_passes_when_no_restricted_account(self):
        empty = {'internal': [], 'portal': []}
        with patch.object(type(self.env['res.users']), METHOD, lambda self: empty):
            self.assertIsNone(self._hook()(self.env))

    def test_hook_refuses_each_kind(self):
        before = dict(self.env['res.users'].sudo().with_context(active_test=False).search([]).mapped(
            lambda u: (u.id, u.active)))
        with self.assertRaises(UserError) as ctx:
            self._hook()(self.env)
        message = str(ctx.exception)
        head, _sep, portal_part = message.partition(SECTION_PORTAL)
        self.assertIn(SECTION_INTERNAL, head)
        for user in (self.console, self.role_sb, self.archived):
            self.assertIn(user.login, head, f'{user.login} 要列在內部受限帳號段')
        self.assertIn(self.portal.login, portal_part, '前台營造帳號列在前台段')
        self.assertIn(f'{self.portal_archived.login}（已封存）', portal_part, '已封存的標明')
        self.assertIn(RUNBOOK, message)
        self.assertIn(CANCEL_HINT, message)
        after = dict(self.env['res.users'].sudo().with_context(active_test=False).search([]).mapped(
            lambda u: (u.id, u.active)))
        self.assertEqual(after, before, 'hook 只拒絕、不封存任何帳號')
        # 只有一種的情況也各自拒絕（hook 的判斷本身；清單由上面那支真的算）
        for result, login in (({'internal': ['only_internal'], 'portal': []}, 'only_internal'),
                              ({'internal': [], 'portal': ['only_portal']}, 'only_portal')):
            with self.subTest(login=login), patch.object(type(self.env['res.users']), METHOD, lambda self, r=result: r):
                with self.assertRaises(UserError) as one:
                    self._hook()(self.env)
                self.assertIn(login, str(one.exception))

    def test_hook_refuses_when_list_incomplete(self):
        """清單本身 raise（受限群組 xmlid 不完整）→ hook 也拒絕（例外原樣往上丟，這次解除安裝回滾）。"""
        with self._without_xmlid(CARRIER_XMLIDS[1]):
            with self.assertRaises(UserError) as ctx:
                self._hook()(self.env)
            self.assertIn(INCOMPLETE_HINT, str(ctx.exception))


@tagged('post_install', '-at_install', MODULE)
class TestRestrictedListHttp(HttpCase):
    """method gate 對系統管理者經 HTTP call_kw 放行；非系統管理者經 HTTP 拿到 AccessError。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        co = env['res.company'].create({'name': 'S3C HTTP 監造', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups):
            return Users.create({'name': login, 'login': login, 'password': PASSWORD,
                                 'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                                 'company_id': co.id, 'company_ids': [(6, 0, co.ids)]})
        cls.sysadmin = user('s3c_http_sysadmin', ['base.group_user', 'base.group_system'])
        cls.staff = user('s3c_http_staff', ['base.group_user', SUPERVISOR_ADMIN])
        cls.console = user('s3c_http_console', [CONSOLE_GROUP])

    def _call(self, user):
        self.authenticate(user.login, PASSWORD)
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': 'res.users', 'method': METHOD, 'args': [], 'kwargs': {}}}
        response = self.url_open(f'/web/dataset/call_kw/res.users/{METHOD}', data=json.dumps(payload),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def test_call_kw(self):
        body = self._call(self.sysadmin)
        self.assertNotIn('error', body, body.get('error'))
        self.assertIn(self.console.login, body['result']['internal'])
        for user in (self.staff, self.console):
            with self.subTest(user=user.login):
                body = self._call(user)
                self.assertIn('error', body)
                self.assertEqual(body['error']['data']['name'], 'odoo.exceptions.AccessError')
