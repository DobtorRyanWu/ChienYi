# -*- coding: utf-8 -*-
"""自訂方法閘門的 HTTP 層（合約 §0b-24；線 I）：四條外部呼叫路徑真的被攔下，正當用法照常。

* /web/dataset/call_kw、/web/dataset/call_button（web client）：前台營造帳號、營造廠主管、控台讀取帳號呼叫自訂模組的
  方法被拒（訊息帶閘門說明）；儀表板方法、ORM 讀取照常。監造方呼叫同一個自訂方法照常。
* 營造廠主管在偏好設定「啟用兩步驟驗證」的完整流程（全是官方模組的方法）經 call_button 照常走完。
* XML-RPC（/xmlrpc/2/object）、JSON-RPC（/jsonrpc）的 object 服務：控台讀取帳號呼叫自訂方法 → AccessError（fault 4）；
  帳密錯 → AccessDenied（fault 3，不是閘門訊息：沒登入的人不能拿它探測）；dash_console_overview 照常。
  營造廠主管（已啟用兩步驟驗證）用 API key 一樣被擋。
  S2 fix3-9（使用者 11-11）：受限內部帳號（控台讀取、營造廠主管）打程式介面只收 API key，這裡一律用 API key；
  密碼被拒那一面在 test_role_fix3.TestRestrictedRpcApiKeyOnlyHttp。web session 用 login_as_browser（當成瀏覽器登入）。
"""
import base64
import datetime
import json
import time
import xmlrpc.client

from odoo import fields
from odoo.addons.auth_totp.models.totp import hotp
from odoo.tests import HttpCase, tagged

from odoo.addons.construction_company_dashboard.models.method_gate import GATE_NOTE

from .test_scope_rules import (
    CONSOLE_GROUP, MANAGER_GROUP, PORTAL_LEADER, SUPERVISOR_ADMIN, login_as_browser, require_totp,
)

PASSWORD = 'Dash-gate-pass1'
RPC_FAULT_ACCESS_DENIED = 3       # 核心 base/controllers/rpc.py
RPC_FAULT_ACCESS_ERROR = 4
CUSTOM_METHOD = ('project.project', 'action_view_photos')     # construction_photo 實作、回一個動作（無副作用）
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


def _totp_code(secret_b32):
    key = base64.b32decode(secret_b32.replace(' ', '').upper() + '=' * (-len(secret_b32.replace(' ', '')) % 8))
    return str(hotp(key, int(time.time() // TOTP_STEP_SECONDS))).zfill(TOTP_DIGITS)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestMethodGateHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_a = Company.create({'name': 'DASH 閘門 A', 'company_type': 'contractor'})
        cls.co_s = Company.create({'name': 'DASH 閘門 監造', 'company_type': 'supervision'})
        cls.p_a = env['project.project'].create({
            'name': 'DASH-GA 閘門測試', 'code': 'DASH-GA', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, company, companies, **extra):
            return Users.create(dict({
                'name': login, 'login': login, 'password': PASSWORD,
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': company.id, 'company_ids': [(6, 0, companies.ids)]}, **extra))

        cls.portal = user('dash_gate_portal', [PORTAL_LEADER], cls.co_a, cls.co_a | cls.co_s,
                          is_contractor_org=True, dash_scope_company_id=cls.co_a.id)
        cls.mgr = user('dash_gate_mgr', [MANAGER_GROUP], cls.co_s, cls.co_s | cls.co_a, dash_scope_company_id=cls.co_a.id)
        cls.console = user('dash_gate_console', [CONSOLE_GROUP], cls.co_s, cls.co_s)
        cls.sup = user('dash_gate_sup', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s, cls.co_s)
        env['supervision.project.member'].create({'project_id': cls.p_a.id, 'user_id': cls.portal.id})

    # ── 工具 ──────────────────────────────────────────────────────────────
    def _web(self, user, route, model, method, args, kwargs=None, login=True):
        """以瀏覽器 session 打 /web/dataset/*；回 ('ok', 結果) 或 ('error', 例外名稱, 訊息)。
        login=False：沿用目前的 session（身分確認的時效記在 session 裡，多步驟流程要同一個 session）。"""
        if login:
            login_as_browser(self, user.login, PASSWORD)
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': model, 'method': method, 'args': args, 'kwargs': dict(kwargs or {}, context={
                'allowed_company_ids': user.company_ids.ids})}}
        response = self.url_open(route, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        body = response.json()
        if 'error' in body:
            data = body['error'].get('data', {})
            return 'error', data.get('name', ''), data.get('message', '')
        return 'ok', body.get('result')

    def _xmlrpc(self, user, secret, model, method, args, kw=None):
        db = self.env.cr.dbname
        return self.xmlrpc_object.execute_kw(db, user.id, secret, model, method, args, kw or {})

    def _api_key(self, user):
        """S2 fix3-9：受限內部帳號打程式介面只收 API key（密碼被拒）。"""
        return self.env['res.users.apikeys'].with_user(user)._generate(
            'rpc', 'DASH 閘門測試', fields.Datetime.now() + datetime.timedelta(days=1))

    def _assert_gate(self, outcome, who):
        self.assertEqual(outcome[0], 'error', f'{who}：自訂方法應被拒，卻回 {outcome!r}'[:300])
        self.assertIn('AccessError', outcome[1], who)
        self.assertIn(GATE_NOTE, outcome[2], who)

    # ── web client ───────────────────────────────────────────────────────
    def test_call_kw_and_call_button_gate(self):
        model, method = CUSTOM_METHOD
        for user in (self.portal, self.mgr, self.console):
            for route in ('/web/dataset/call_kw', '/web/dataset/call_button'):
                self._assert_gate(self._web(user, route, model, method, [[self.p_a.id]]), f'{user.login} {route}')
        # 監造方：同一個方法照常回動作
        outcome = self._web(self.sup, '/web/dataset/call_button', model, method, [[self.p_a.id]])
        self.assertEqual(outcome[0], 'ok', outcome)
        self.assertEqual(outcome[1]['res_model'], 'supervision.photo')

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_dashboard_and_read_api_still_work(self):
        """閘門放行儀表板方法與 ORM 讀取（資料本身由啟用 TOTP 的帳號在 test_xmlrpc_gate_api_key_manager 驗：
        HttpCase.authenticate 對啟用 TOTP 的帳號只收 API key，web session 只能用未啟用的帳號——看得到「請啟用」）。"""
        outcome = self._web(self.mgr, '/web/dataset/call_kw', 'project.project', 'get_dash_company_kpis', [])
        self.assertEqual(outcome[0], 'ok', outcome)
        self.assertEqual(outcome[1]['blocked_reason'], 'totp_missing', '未啟用 TOTP：方法照常執行、回「請啟用」')
        outcome = self._web(self.portal, '/web/dataset/call_kw', 'project.project', 'web_search_read', [],
                            {'domain': [], 'specification': {'name': {}}})
        self.assertEqual(outcome[0], 'ok', outcome)
        self.assertEqual([r['id'] for r in outcome[1]['records']], [self.p_a.id])
        outcome = self._web(self.portal, '/web/dataset/call_kw', 'project.project', 'get_project_dashboard_data',
                            [[self.p_a.id]])
        self.assertEqual(outcome[0], 'ok', outcome)
        # fields_get 被第三方 base_geoengine 覆寫，名稱照放行
        outcome = self._web(self.portal, '/web/dataset/call_kw', 'project.project', 'fields_get', [['name']])
        self.assertEqual(outcome[0], 'ok', outcome)

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_manager_enables_totp_through_gate(self):
        """偏好設定 →「啟用兩步驟驗證」：身分確認 → 掃碼 → 輸入驗證碼，全部經 call_button／call_kw 走完。"""
        self.assertFalse(self.mgr.totp_enabled)
        outcome = self._web(self.mgr, '/web/dataset/call_button', 'res.users', 'action_totp_enable_wizard',
                            [[self.mgr.id]])
        self.assertEqual(outcome[0], 'ok', outcome)
        action = outcome[1]
        self.assertEqual(action['res_model'], 'res.users.identitycheck', '先要求確認密碼')
        check_id = action['res_id']
        self.assertEqual(self._web(self.mgr, '/web/dataset/call_kw', 'res.users.identitycheck', 'web_save',
                                   [[check_id], {'password': PASSWORD}], {'specification': {}}, login=False)[0], 'ok')
        outcome = self._web(self.mgr, '/web/dataset/call_button', 'res.users.identitycheck', 'run_check', [[check_id]],
                            login=False)
        self.assertEqual(outcome[0], 'ok', outcome)
        wizard_action = outcome[1]
        self.assertEqual(wizard_action['res_model'], 'auth_totp.wizard')
        wizard = self.env['auth_totp.wizard'].browse(wizard_action['res_id'])
        code = _totp_code(wizard.secret)
        saved = self._web(self.mgr, '/web/dataset/call_kw', 'auth_totp.wizard', 'web_save',
                          [[wizard.id], {'code': code}], {'specification': {'code': {}}}, login=False)
        self.assertEqual(saved[0], 'ok', saved)
        self.assertEqual(saved[1][0]['code'], code, saved)
        outcome = self._web(self.mgr, '/web/dataset/call_button', 'auth_totp.wizard', 'enable', [[wizard.id]], login=False)
        self.assertEqual(outcome[0], 'ok', outcome)
        self.assertEqual((outcome[1] or {}).get('params', {}).get('type'), 'success', f'啟用結果：{outcome!r}'[:400])
        self.env.invalidate_all()
        self.assertTrue(self.mgr.totp_enabled, '營造廠主管照常啟用兩步驟驗證')

    # ── XML-RPC／JSON-RPC ─────────────────────────────────────────────────
    def test_xmlrpc_gate(self):
        model, method = CUSTOM_METHOD
        key = self._api_key(self.console)
        with self.assertRaises(xmlrpc.client.Fault) as ctx:
            self._xmlrpc(self.console, key, model, method, [[self.p_a.id]])
        self.assertEqual(ctx.exception.faultCode, RPC_FAULT_ACCESS_ERROR, ctx.exception.faultString[:300])
        self.assertIn(GATE_NOTE, ctx.exception.faultString)
        # 帳密錯：照核心回 AccessDenied，不洩漏閘門訊息
        with self.assertRaises(xmlrpc.client.Fault) as ctx:
            self._xmlrpc(self.console, 'wrong-password', model, method, [[self.p_a.id]])
        self.assertEqual(ctx.exception.faultCode, RPC_FAULT_ACCESS_DENIED)
        self.assertNotIn(GATE_NOTE, ctx.exception.faultString)
        # 控台取資料方法照常（控台實際也是用 API key：tools/console_agent/pull_overview.py）
        overview = self._xmlrpc(self.console, key, 'project.project', 'dash_console_overview', [])
        self.assertIn('projects', overview)
        # 監造方：同一個自訂方法照常
        result = self._xmlrpc(self.sup, PASSWORD, model, method, [[self.p_a.id]])
        self.assertEqual(result['res_model'], 'supervision.photo')

    def test_xmlrpc_gate_api_key_manager(self):
        """已啟用兩步驟驗證的營造廠主管只能用 API key 打 RPC：一樣被閘門擋，ORM 讀取照常。"""
        self.mgr.sudo().write({'totp_secret': 'JBSWY3DPEHPK3PXP'})
        key = self._api_key(self.mgr)
        model, method = CUSTOM_METHOD
        with self.assertRaises(xmlrpc.client.Fault) as ctx:
            self._xmlrpc(self.mgr, key, model, method, [[self.p_a.id]])
        self.assertEqual(ctx.exception.faultCode, RPC_FAULT_ACCESS_ERROR, ctx.exception.faultString[:300])
        self.assertIn(GATE_NOTE, ctx.exception.faultString)
        # ORM 讀取照常、範圍照舊（get_dash_company_kpis 回傳含 None，XML-RPC 送不回，不在這裡驗）
        self.assertEqual(self._xmlrpc(self.mgr, key, 'project.project', 'search', [[]]), [self.p_a.id])

    def test_jsonrpc_gate(self):
        model, method = CUSTOM_METHOD
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'service': 'object', 'method': 'execute_kw',
            'args': [self.env.cr.dbname, self.console.id, self._api_key(self.console), model, method, [[self.p_a.id]], {}]}}
        body = self.url_open('/jsonrpc', data=json.dumps(payload), headers={'Content-Type': 'application/json'}).json()
        self.assertIn('error', body, body)
        self.assertIn(GATE_NOTE, body['error']['data']['message'])
        payload['params']['args'][1:3] = [self.sup.id, PASSWORD]
        body = self.url_open('/jsonrpc', data=json.dumps(payload), headers={'Content-Type': 'application/json'}).json()
        self.assertEqual(body.get('result', {}).get('res_model'), 'supervision.photo', body)
