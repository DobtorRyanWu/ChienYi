# -*- coding: utf-8 -*-
"""RPC 呼叫路徑（線 F1 第 0 項；線 E 端到端實證的 high）。

背景：Odoo 的 `call_kw`（XML-RPC `execute_kw` 與 JSON-RPC `/web/dataset/call_kw` 共用）看方法的 `_api`
決定「是 model 方法（不取 ids）」還是「recordset 方法（args[0] 是 ids）」；覆寫不會繼承父類別的 `_api`
（核心 `odoo/api.py` Meta 只傳 `_returns`）。`project.project.create` 覆寫少了 `@api.model_create_multi` 時，
任何帳號經 RPC 建工程都在權限檢查之前 TypeError——直接 ORM create 的單元測試測不出來。

鎖住兩件事：
1. 真的 XML-RPC：監造方帳號建得出工程（list 與單一 dict 兩種呼叫法）；控台讀取帳號被拒時是**權限錯誤**
   （fault 4），不是 TypeError——線 E 第一輪就是把 TypeError 當成「被拒」。控台建工程先被附帶建立的分析帳戶
   ACL 擋下（核心 project 建工程會建分析帳戶），所以這裡只斷言「走到權限層」；範圍規則本身的拒寫由
   test_scope_rules 逐模型鎖住。
2. 列舉 registry：本專案（`construction_*`）模組定義的公開方法，若祖先帶 `_api`，覆寫必須帶同一個 `_api`。
"""
import inspect
import xmlrpc.client

from odoo.tests import HttpCase, TransactionCase, tagged

CONSOLE_GROUP = 'construction_company_dashboard.group_console_reader'
PROJECT_MANAGER = 'project.group_project_manager'
SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'
PASSWORD = 'Dash-rpc-pass1'
# 本專案模組的 Python 模組路徑前綴（只檢查我們自己寫的覆寫；核心既有的不在範圍）
OUR_MODULE_PREFIX = 'odoo.addons.construction_'
# XML-RPC 的 AccessError fault code（核心 odoo/service/wsgi_server.py RPC_FAULT_CODE_ACCESS_ERROR）
RPC_FAULT_ACCESS_ERROR = 4
# 覆寫少裝飾器時 call_kw 會丟的 TypeError 片段
MISSING_ARG_TEXT = "missing 1 required positional argument"


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestRpcCreateProject(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_s = env['res.company'].create({'name': 'DASH RPC 監造', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.sup = Users.create({
            'name': 'dash_rpc_sup', 'login': 'dash_rpc_sup', 'password': PASSWORD,
            'groups_id': [(6, 0, [env.ref(g).id for g in ('base.group_user', SUPERVISOR_ADMIN, PROJECT_MANAGER)])],
            'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        cls.console = Users.create({
            'name': 'dash_rpc_console', 'login': 'dash_rpc_console', 'password': PASSWORD,
            'groups_id': [(6, 0, [env.ref(CONSOLE_GROUP).id])],
            'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})

    def _rpc(self, user, method, args, kw=None):
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, user.login, PASSWORD, {})
        self.assertEqual(uid, user.id, '登入失敗：%s' % user.login)
        return self.xmlrpc_object.execute_kw(db, uid, PASSWORD, 'project.project', method, args, kw or {})

    def _vals(self, code):
        return {'name': f'{code} RPC 建立的工程', 'code': code, 'project_type': 'general',
                'company_id': self.co_s.id}

    def test_supervision_user_creates_project_over_xmlrpc(self):
        # 新租戶開站（tools/supervision_plan_intake/import_plan.py:138）就是這樣呼叫：create('project.project', [vals])
        ids = self._rpc(self.sup, 'create', [[self._vals('DASH-RPC-1')]])
        self.assertIsInstance(ids, list)
        self.assertEqual(len(ids), 1)
        project = self.env['project.project'].browse(ids).exists()
        self.assertEqual(project.name, 'DASH-RPC-1 RPC 建立的工程')
        self.assertEqual(project.create_uid, self.sup)
        # 單一 dict 的呼叫法回單一 id
        pid = self._rpc(self.sup, 'create', [self._vals('DASH-RPC-2')])
        self.assertIsInstance(pid, int)
        self.assertEqual(self.env['project.project'].browse(pid).code, 'DASH-RPC-2')

    def test_console_reader_rejected_as_access_error_not_typeerror(self):
        before = self.env['project.project'].with_context(active_test=False).search_count([])
        with self.assertRaises(xmlrpc.client.Fault) as cm:
            self._rpc(self.console, 'create', [[self._vals('DASH-RPC-3')]])
        fault = cm.exception
        self.assertNotIn(MISSING_ARG_TEXT, fault.faultString)
        self.assertEqual(fault.faultCode, RPC_FAULT_ACCESS_ERROR, fault.faultString[:300])
        self.assertEqual(self.env['project.project'].with_context(active_test=False).search_count([]), before)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestOverrideKeepsRpcApi(TransactionCase):

    def test_public_overrides_keep_parent_api(self):
        mismatches, checked = [], 0
        for model_name in sorted(self.env.registry):
            cls = type(self.env[model_name])
            for name, final in inspect.getmembers(cls, inspect.isfunction):
                # 底線開頭的方法 RPC 叫不到（核心 get_public_method），只看公開的
                if name.startswith('_') or not final.__module__.startswith(OUR_MODULE_PREFIX):
                    continue
                parent_api = next((
                    base.__dict__[name]._api for base in cls.__mro__[1:]
                    if name in base.__dict__ and getattr(base.__dict__[name], '_api', None)), None)
                if not parent_api:
                    continue
                checked += 1
                if getattr(final, '_api', None) != parent_api:
                    mismatches.append(f'{model_name}.{name}（{final.__module__}）應為 {parent_api}')
        # 防恆真：本專案確實有帶裝飾器的 create 覆寫被檢查到（例：施工日誌、照片、工程）
        self.assertGreater(checked, 0, '沒有檢查到任何覆寫——列舉方式壞了')
        self.assertEqual(mismatches, [], '這些覆寫少了 @api 裝飾器，RPC 呼叫會在權限檢查前就壞掉')
