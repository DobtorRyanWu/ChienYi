# -*- coding: utf-8 -*-
"""呼叫端自己帶的 context 不能打開範圍規則（2026-11-06 主迴圈實測的 critical）。

背景：`ir.rule._compute_domain` 覆寫用 context 旗標 `dash_scope_core_parent` 標記「本模組自己呼叫核心」。
RPC（XML-RPC `execute_kw` 的 `context`、JSON-RPC `kwargs.context`）與前台都能讓呼叫端自帶 context；
原本用真假值判定，營造廠主管帶 `{dash_scope_core_parent: True}` 就讀到全庫（dev 複本：估驗 58→113、
聯絡人 9→88、工程成員 0→16）。修法：旗標值只認本模組的物件（`is` 比對），外部送不出那個物件。
範本群組推送旗標 `dash_template_group_propagation` 同一個寫法（帶了會讓群組寫入靜默略過受限帳號）。

鎖住：
1. ORM：營造廠主管、前台營造帳號、控台讀取帳號帶各種「看起來為真」的旗標值，看到的筆數與不帶時相同；
   反證（L2③）：用真的憑證算核心值時看得到更多——證明這個夾具真的分得出「被繞過」。
2. 真的 XML-RPC：前台營造帳號用 `execute_kw` 帶旗標搜尋工程，看不到別家營造廠的工程。
3. 帶範本推送旗標替營造廠主管加群組，照樣被群組允許清單擋下（不是靜默成功）。
"""
import xmlrpc.client

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.construction_company_dashboard.models.res_users_guard import TEMPLATE_PROPAGATION_CTX
from odoo.addons.construction_company_dashboard.models.rule_scope import CORE_PARENT_CTX, CORE_PARENT_TOKEN

from .test_scope_rules import PORTAL_LEADER, DashScopeCase

# 呼叫端可能送來的「為真」值（XML-RPC／JSON-RPC 能表達的型別）
SPOOF_VALUES = (True, 1, 'yes', [1], {'x': 1})
# 範圍外資料一定存在的模型（夾具建的）：工程、營造廠層級單據、工程成員
SPOOF_MODELS = ('project.project', 'daily.log.sheet', 'payment.estimate', 'supervision.project.member')
# 營造廠主管不可帶的群組（任選一個不在允許清單內的）
FORBIDDEN_EXTRA_GROUP = 'project.group_project_manager'
PASSWORD = 'Dash-spoof-pass1'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestContextFlagSpoof(DashScopeCase):

    def _ids(self, user, model, ctx=None):
        # 每次先清規則快取：快取鍵只記「是不是憑證」，偽造的請求會命中正常請求留下的快取，
        # 不清就測不到判定本身（突變實測：判定改回真假值，沒清快取時測試照綠）
        self.env.registry.clear_cache()
        env = self._env_of(user)
        Model = env[model].with_context(**(ctx or {}))
        try:
            return set(Model.search([]).ids)
        except AccessError:
            return 'AccessError'

    def test_caller_flag_does_not_bypass_scope(self):
        for user in (self.mgr_a, self.portal_a, self.portal_blank, self.console):
            for model in SPOOF_MODELS:
                normal = self._ids(user, model)
                for value in SPOOF_VALUES:
                    spoofed = self._ids(user, model, {CORE_PARENT_CTX: value})
                    self.assertEqual(spoofed, normal,
                                     f'{user.login} 帶 {CORE_PARENT_CTX}={value!r} 讀 {model}：筆數不可改變')

    def test_rig_distinguishes_bypass(self):
        """反證：真的憑證（本模組內部）算出的核心值看得到範圍外資料——上一支測試不是恆真。"""
        for model in ('project.project', 'payment.estimate'):
            normal = self._ids(self.mgr_a, model)
            core = self._ids(self.mgr_a, model, {CORE_PARENT_CTX: CORE_PARENT_TOKEN})
            self.assertIsInstance(normal, set)
            self.assertIsInstance(core, set)
            self.assertTrue(core > normal, f'{model}：核心值應比範圍規則多（夾具有別家營造廠的資料）')

    def test_caller_flag_does_not_bypass_write_deny(self):
        env = self._env_of(self.mgr_a)
        project = env['project.project'].browse(self.p_a.id).with_context(**{CORE_PARENT_CTX: True})
        with self.assertRaises(AccessError):
            project.write({'name': 'DASH 偽造旗標改名'})

    def test_template_flag_does_not_skip_group_guard(self):
        """帶範本推送旗標直接替營造廠主管加群組：照樣被允許清單擋下，不可靜默略過。"""
        group = self.env.ref(FORBIDDEN_EXTRA_GROUP)
        with self.assertRaises(ValidationError):
            self.mgr_a.with_context(**{TEMPLATE_PROPAGATION_CTX: True}).write({'groups_id': [(4, group.id)]})
        self.assertNotIn(group, self.mgr_a.groups_id)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestContextFlagSpoofRpc(HttpCase):
    """真的 XML-RPC：context 由呼叫端送進 call_kw。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_a = Company.create({'name': 'DASH 偽造 A', 'company_type': 'contractor'})
        cls.co_b = Company.create({'name': 'DASH 偽造 B', 'company_type': 'contractor'})
        cls.co_s = Company.create({'name': 'DASH 偽造 監造', 'company_type': 'supervision'})
        Project = env['project.project']
        cls.p_a = Project.create({'name': 'DASH-SPA 偽造測試', 'code': 'DASH-SPA', 'project_type': 'general', 'state': 'construction',
                                  'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        cls.p_b = Project.create({'name': 'DASH-SPB 偽造測試', 'code': 'DASH-SPB', 'project_type': 'general', 'state': 'construction',
                                  'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_b.ids)]})
        cls.user = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'dash_spoof_portal', 'login': 'dash_spoof_portal', 'password': PASSWORD,
            'groups_id': [(6, 0, [env.ref(PORTAL_LEADER).id])],
            'company_id': cls.co_a.id, 'company_ids': [(6, 0, (cls.co_a | cls.co_s).ids)],
            'is_contractor_org': True, 'dash_scope_company_id': cls.co_a.id})
        # 兩個工程都掛成員：核心前台成員規則兩個都放行，擋 PB 的只有範圍規則
        for project in (cls.p_a, cls.p_b):
            env['supervision.project.member'].create({'project_id': project.id, 'user_id': cls.user.id})

    def _search(self, ctx):
        # 同 TestContextFlagSpoof._ids：先清規則快取（HttpCase 的伺服器與測試同一個程序）
        self.env.registry.clear_cache()
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, self.user.login, PASSWORD, {})
        self.assertEqual(uid, self.user.id, '登入失敗')
        domain = [('id', 'in', (self.p_a | self.p_b).ids)]
        return set(self.xmlrpc_object.execute_kw(
            db, uid, PASSWORD, 'project.project', 'search', [domain], {'context': ctx}))

    def test_xmlrpc_context_flag_does_not_bypass(self):
        # 各種值都試（含 dict：曾讓快取鍵不可雜湊）；斷言都打在「看得到哪些工程」
        self.assertEqual(self._search({}), {self.p_a.id}, '前提：不帶旗標只看得到自家工程')
        try:
            spoofed = {repr(v): self._search({CORE_PARENT_CTX: v}) for v in SPOOF_VALUES}
        except xmlrpc.client.Fault as exc:
            self.fail(f'帶旗標的搜尋應照常回傳（只看得到自家），不是 fault：{exc.faultString[:200]}')
        for value, seen in spoofed.items():
            self.assertEqual(seen, {self.p_a.id}, f'XML-RPC 帶 {CORE_PARENT_CTX}={value} 不可看到別家營造廠的工程')
