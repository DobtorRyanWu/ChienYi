# -*- coding: utf-8 -*-
"""後台角色帳號（S1，2026-11-10）：營造老闆／營造主管／監造老闆／監造主管，後台唯讀看自己工程的四類資料。

夾具沿用 DashScopeCase（營造廠 A、B、C，監造公司 S——本檔當 S1；工程 P（A＋B）、PA、PB、預約式 R（A＋B），
8 種營造廠層級單據），再加：監造公司 S2、工程 PS2（S2，A）、PD（S1，A，未開始）、新分類
（契約變更單＋明細、進度報告＋明細、即時損益＋成本列、損益支出、成本分析＋明細）在各一般式工程各一筆，
估驗在 PS2、PD 各一筆，以及 PA 上一筆歸屬 B 的估驗（撤權後殘留；只有它能證明「損益支出要經由估驗的營造廠歸屬篩選」）。
（S1 規格寫「主公司 S1」；這裡沿用 DashScopeCase 新建的監造公司 S，避免主公司上的真實資料混進「兩個方向都比」的集合。）

帳號（都啟用兩步驟驗證）：營造老闆 A、營造主管 A（只加入 P）、監造老闆（允許公司只有 S1）、監造主管（只加入 PA）。
期望值由測試依夾具獨立寫出（不 import 實作的分類常數；只有 ACL 不變式那支刻意拿實作的分類常數與 ACL 資料互相對帳）。
斷言打在使用者看得到的結果：看得到哪幾筆（兩個方向都比）、被拒＋訊息、選單、畫面讀得起來、通知收不收得到。
"""
import base64
import json
import logging
import time
from unittest.mock import patch

from lxml import etree

from odoo import fields, http
from odoo.addons.auth_totp.models.totp import hotp
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression
from odoo.tests import HttpCase, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.base.models.ir_ui_menu import IrUiMenu as CoreIrUiMenu
from odoo.addons.construction_company_dashboard.models import rule_scope
from odoo.addons.construction_company_dashboard.models.method_gate import GATE_NOTE, gate_verdict
from odoo.addons.construction_company_dashboard.models.restricted_mail import DENY_AUTHOR_NOTE, DENY_POST_NOTE
from odoo.addons.construction_company_dashboard.models.rule_scope import DENY_NOTE_ROLE

from . import test_scope_rules as scope_tests
from .test_scope_rules import (
    CONSOLE_GROUP, DENIED, EXPECT_CONTRACTOR_LEVEL, EXPECT_FRAMEWORK, EXPECT_LINES, EXPECT_PROJECT_LEVEL,
    MANAGER_GROUP, SUPERVISOR_ADMIN, TOTP_FIXTURE_SECRET, WHITELIST, DashScopeCase, contractor_definition,
    project_definition, require_totp,
)

_logger = logging.getLogger(__name__)

MODULE = 'construction_company_dashboard'
ROLE_BOSS = f'{MODULE}.group_role_boss'
ROLE_MANAGER = f'{MODULE}.group_role_manager'
ROLE_SUPERVISION = f'{MODULE}.group_role_supervision'
# 自訂模組實作、回一個動作（無副作用）的方法：方法閘門要擋（同 test_method_gate_http.CUSTOM_METHOD）
CUSTOM_METHOD = ('project.project', 'action_view_photos')
# 角色帳號才讀得到的新分類（測試獨立寫一份）：模型 → 到工程的欄位路徑
EXPECT_ROLE_PROJECT_LEVEL = {
    'contract.change.order.line': 'change_order_id.project_id',
    'general.progress.report': 'project_id',
    'general.progress.report.line': 'report_id.project_id',
    'general.realtime.profit': 'project_id',
    'general.realtime.profit.cost': 'profit_id.project_id',
}
EXPECT_SINGLE_CONTRACTOR_ONLY = {'general.realtime.profit', 'general.realtime.profit.cost',
                                 'profit.loss.entry', 'cost.analysis', 'cost.analysis.line'}
EXPECT_ROLE_ONLY = set(EXPECT_ROLE_PROJECT_LEVEL) | {'profit.loss.entry', 'cost.analysis', 'cost.analysis.line'}
ROLE_WHITELIST = WHITELIST | EXPECT_ROLE_ONLY
# 角色帳號的選單（測試獨立寫一份；成本分析是選裝模組）
EXPECT_ROLE_MENUS = (
    'construction_company_dashboard.menu_company_dashboard',
    'construction_company_dashboard.menu_role_phone_home',      # S2：後台回手機首頁的「手機版」
    'construction_supervision_base.menu_estimate',
    'construction_cost_analysis.menu_cost_analysis',
    'construction_general.menu_general_realtime_profit',
    'construction_supervision_base.menu_supervision_task',
    'construction_contract_change.menu_contract_change_order',
    'construction_progress.menu_progress_schedule',
    'construction_progress.menu_progress_schedule_line',
    'construction_progress.menu_progress_chart_dashboard',
    'construction_general.menu_general_progress_report',
)
# 自主檢查樣板與明細（fix2-R：角色帳號兩方都照工程條件，主管含成員＋狀態）
EXPECT_TEMPLATE_MODELS = ('self.inspection.type', 'self.inspection.type.item')
# 估驗夾具改成「已核定」（即時損益只列非草稿的估驗）
ESTIMATE_STATE_APPROVED = 'approved'
# 損益支出夾具的金額
EXPENSE_AMOUNT = 1000.0
SMOKE_LIST_LIMIT = 20
# 本人以外讀不到東西時，框架以外只剩本人的使用者與聯絡人——內部受限帳號另外讀得到 OdooBot 的聯絡人
# （S2-D：核心第一次打開後台要讀它，rule_scope._dash_with_odoobot；_other_counts 不濾封存，所以封存的 OdooBot 也算一筆）
SELF_ONLY_COUNTS = {'res.users': 1, 'res.partner': 2}
# 驗證碼（RFC 6238 預設值，與 test_method_gate_http 相同）
# fix3-S：冒用作者被拒時訊息裡的字（測試獨立寫出，不 import 實作常數）
SPOOF_AUTHOR_DENY = '不能以別人的名義發訊息'

TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


def _fixture_admin(env, *companies):
    """S3（2026-11-11）：在夾具監造公司的估驗上貼訊息的 admin，要是那家公司的成員（交易內，測試結束回滾）。

    估驗等改成全域公司規則（紀錄所屬工程的公司要在使用者的允許公司裡）之後，admin（dev 只屬五家真實公司）讀不到
    夾具新建公司的估驗，貼不了訊息。真實站上貼訊息的人本來就屬於該監造公司；S3 之前估驗沒有公司規則才沒現形。
    """
    admin = env.ref('base.user_admin')
    admin.sudo().write({'company_ids': [(4, company.id) for company in companies]})
    return admin


class RoleMatrixCase(DashScopeCase):
    """共用夾具（本類別沒有測試）。"""

    # 拒寫檢查沿用 test_scope_rules（不把 TestScopeRules 類別本身匯入本檔，否則它的測試會在這裡再跑一次）
    _write_acl_models = scope_tests.TestScopeRules._write_acl_models
    _assert_write_denied = scope_tests.TestScopeRules._assert_write_denied

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        today = fields.Date.today()
        cls.co_s2 = env['res.company'].create({'name': 'ROLE 監造 S2', 'company_type': 'supervision'})
        cls.p_s2 = cls._role_project('ROLE-PS2', cls.co_s2, cls.co_a, 'construction')
        cls.p_draft = cls._role_project('ROLE-PD', cls.co_s, cls.co_a, 'draft')
        cls.p_term = cls._role_project('ROLE-PT', cls.co_s, cls.co_a, 'terminated')
        cls.general_projects = cls.p_shared | cls.p_a | cls.p_b | cls.p_s2 | cls.p_draft | cls.p_term
        cls.all_projects = cls.general_projects | cls.r_shared

        # ── 帳號 ───────────────────────────────────────────────────
        contractor_companies = cls.co_a | cls.co_s | cls.co_s2
        cls.cb = cls._role_user('role_cb_a', [MANAGER_GROUP, ROLE_BOSS], cls.co_s, contractor_companies, cls.co_a)
        cls.cm = cls._role_user('role_cm_a', [MANAGER_GROUP, ROLE_MANAGER], cls.co_s, contractor_companies, cls.co_a)
        cls.sb = cls._role_user('role_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s, cls.co_s)
        cls.sm = cls._role_user('role_sm', [ROLE_SUPERVISION, ROLE_MANAGER], cls.co_s, cls.co_s)
        cls.roles = cls.cb | cls.cm | cls.sb | cls.sm
        cls.contractor_roles = cls.cb | cls.cm
        env['supervision.project.member'].create({'project_id': cls.p_shared.id, 'user_id': cls.cm.id})
        env['supervision.project.member'].create({'project_id': cls.p_a.id, 'user_id': cls.sm.id})
        # fix1-C：兩個主管都加入一個未開始、一個終止的工程——工程本身與底下所有資料都要看不到
        for manager in (cls.cm, cls.sm):
            for project in (cls.p_draft, cls.p_term):
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': manager.id})
        # 每個角色看得到的工程（依夾具獨立寫出）
        cls.expect_projects = {
            cls.cb: cls.p_shared | cls.p_a | cls.p_s2 | cls.p_draft | cls.p_term | cls.r_shared,  # A 承攬的全部（含未開始、終止）
            cls.cm: cls.p_shared,                                                                  # 只有被加入、而且不是未開始／終止的
            cls.sb: cls.p_shared | cls.p_a | cls.p_b | cls.p_draft | cls.p_term | cls.r_shared,  # S1 的全部（不含 S2）
            cls.sm: cls.p_a,
        }

        # ── 估驗：PS2、PD 各一筆（A）；PA 上一筆歸屬 B 的（撤權後殘留，SQL 造） ─────────
        cls.extra_estimates = env['payment.estimate']
        for project in (cls.p_s2, cls.p_draft, cls.p_term):
            cls.extra_estimates |= cls._make_doc('payment.estimate', project, cls.co_a)
        cls.est_pa_b = cls._make_doc('payment.estimate', cls.p_a, cls.co_a)
        env.cr.execute('UPDATE payment_estimate SET contractor_company_id = %s WHERE id = %s',
                       [cls.co_b.id, cls.est_pa_b.id])
        cls.est_pa_b.invalidate_recordset(['contractor_company_id'])
        cls.estimates = (cls.docs[('payment.estimate', cls.co_a)] | cls.docs[('payment.estimate', cls.co_b)]
                         | cls.extra_estimates | cls.est_pa_b)
        cls.estimates.sudo().write({'state': ESTIMATE_STATE_APPROVED})

        # ── 新分類：每筆記下 (工程, 估驗的營造廠歸屬) ─────────────────────
        cls.meta = {}   # 模型 → {id: (工程, 歸屬營造廠或 None)}

        def note(record, project, contractor=None):
            cls.meta.setdefault(record._name, {})[record.id] = (project, contractor)

        for project in cls.general_projects:
            task = cls.tasks[project]
            order = env['contract.change.order'].create({'project_id': project.id})
            note(order, project)
            note(env['contract.change.order.line'].create({
                'change_order_id': order.id, 'item_name': 'ROLE 變更工項'}), project)
            report = env['general.progress.report'].create({
                'project_id': project.id, 'period_start': fields.Date.subtract(today, days=7), 'period_end': today})
            note(report, project)
            note(env['general.progress.report.line'].create({'report_id': report.id, 'task_id': task.id}), project)
            profit = env['general.realtime.profit'].create({
                'project_id': project.id, 'period_start': fields.Date.subtract(today, days=30), 'period_end': today})
            note(profit, project)
            note(env['general.realtime.profit.cost'].create({'profit_id': profit.id, 'cost_type': 'material'}), project)
        for estimate in cls.estimates:
            entry = env['profit.loss.entry'].create({
                'project_id': estimate.project_id.id, 'estimate_id': estimate.id, 'expense_amount': EXPENSE_AMOUNT})
            note(entry, estimate.project_id, estimate.contractor_company_id)
        cls.has_cost_analysis = 'cost.analysis' in env
        if cls.has_cost_analysis:
            for project in (cls.p_a, cls.p_shared, cls.p_b, env['project.project']):
                analysis = env['cost.analysis'].create({
                    'name': f'ROLE 成本分析 {project.code or "（沒有工程）"}', 'company_id': cls.co_s.id,
                    'source_project_id': project.id or False})
                note(analysis, project)
                note(env['cost.analysis.line'].create({'planning_id': analysis.id, 'name': 'ROLE 成本項目'}), project)
        # fix2-R：自主檢查樣板（與明細）掛在 PD、PT（兩個主管都加入，但未開始／終止）、PA（營造主管沒加入）、
        # P（監造主管沒加入）——主管都讀不到前兩個，各自讀不到沒加入的那個；老闆照工程範圍（不排除狀態）
        for project in (cls.p_draft, cls.p_term, cls.p_a, cls.p_shared):
            template = env['self.inspection.type'].create({
                'name': f'ROLE 樣板 {project.code}', 'project_id': project.id})
            note(template, project)
            note(env['self.inspection.type.item'].create({'type_id': template.id, 'name': 'ROLE 樣板項目'}), project)
        # 營造廠層級單據與明細：從 DashScopeCase 的夾具讀回 (工程, 歸屬)
        for (model, _company), records in cls.docs.items():
            for record in records:
                note(record, record[EXPECT_CONTRACTOR_LEVEL[model]], record.contractor_company_id)
        for estimate in cls.extra_estimates | cls.est_pa_b:
            note(estimate, estimate.project_id, estimate.contractor_company_id)
        for (model, _company), records in cls.lines.items():
            parent_field, project_field = EXPECT_LINES[model]
            for record in records:
                parent = record[parent_field]
                note(record, parent[project_field], parent.contractor_company_id)
        for project in cls.all_projects:
            note(project, project)
            if project in cls.tasks:
                note(cls.tasks[project], project)
            for schedule in project.with_context(active_test=False).schedule_ids:
                note(schedule, project)
        env.registry.clear_cache()

    # ── 夾具工廠 ─────────────────────────────────────────────────────
    @classmethod
    def _role_project(cls, code, company, contractor, state):
        project = cls.env['project.project'].create({
            'name': f'{code} 角色帳號測試工程', 'code': code, 'project_type': 'general', 'state': state,
            'company_id': company.id, 'contractor_company_ids': [(6, 0, contractor.ids)]})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.tasks[project] = cls.env['project.task'].create({
            'name': f'{code} 工項', 'project_id': project.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': 100.0})
        return project

    @classmethod
    def _role_user(cls, login, groups, company, companies, scope=None, totp=True):
        user = cls._user(login, groups, company=company, companies=companies, scope=scope)
        if totp:
            user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        return user

    # ── 期望值（依夾具獨立算）────────────────────────────────────────
    def _single_contractor(self, project):
        return len(project.sudo().contractor_company_ids) == 1

    def _expect_visible(self, user, model, project, contractor):
        """這筆紀錄（掛在 project、營造廠歸屬 contractor）這個角色該不該看得到。"""
        is_contractor = user in self.contractor_roles
        if model in EXPECT_TEMPLATE_MODELS:
            return not project or project in self.expect_projects[user]   # 全域樣板誰都看得到
        if model in ('cost.analysis', 'cost.analysis.line') and not project:
            return user == self.sb   # 沒有工程的成本分析只給監造老闆（夾具都是 S1 的）
        if project not in self.expect_projects[user]:
            return False
        if not is_contractor:
            return True
        if model in EXPECT_CONTRACTOR_LEVEL or model in EXPECT_LINES:
            return contractor == self.co_a
        if model in EXPECT_SINGLE_CONTRACTOR_ONLY:
            if model == 'profit.loss.entry' and contractor != self.co_a:
                return False
            return self._single_contractor(project)
        return True

    def _expected_ids(self, user, model):
        return {rid for rid, (project, contractor) in self.meta.get(model, {}).items()
                if self._expect_visible(user, model, project, contractor)}

    def _fixture_ids(self, model):
        return set(self.meta.get(model, {}))

    def _seen_ids(self, user, model):
        return self._visible_ids(user, model, [('id', 'in', list(self._fixture_ids(model)))])


@tagged('post_install', '-at_install', MODULE)
class TestRoleAccounts(RoleMatrixCase):

    # ── 判定 ─────────────────────────────────────────────────────────
    def test_identity_and_kind(self):
        Rule = self.env['ir.rule']
        for user, kind, level, side in ((self.cb, 'contractor', 'boss', 'contractor'),
                                        (self.cm, 'contractor', 'manager', 'contractor'),
                                        (self.sb, 'supervision_role', 'boss', 'supervision'),
                                        (self.sm, 'supervision_role', 'manager', 'supervision')):
            self.assertEqual(Rule.with_user(user)._dash_scope_kind(), kind, user.login)
            self.assertTrue(user._is_role_account(), user.login)
            self.assertEqual(user._role_level_raw(), level, user.login)
            self.assertEqual(user._role_side(), side, user.login)
            self.assertTrue(user._dash_scope_ok(), user.login)
            self.assertTrue(user._dash_is_restricted(), user.login)
            self.assertFalse(user._is_backend_staff(), user.login)
            self.assertFalse(user._is_supervision_side(), user.login)
            self.assertEqual(user._construction_org_side(), side, user.login)
        self.assertEqual(self.sb._role_supervision_company_ids(), [self.co_s.id])
        # 既有帳號不是角色帳號
        for user in (self.mgr_a, self.portal_a, self.console, self.sup):
            self.assertFalse(user._is_role_account(), user.login)
            self.assertIsNone(user._role_level_raw(), user.login)
        self.assertTrue(self.sup._is_backend_staff())

    # ── 1. 權限矩陣 ───────────────────────────────────────────────────
    def test_matrix_exact_ids_both_directions(self):
        models = sorted(self.meta)
        self.assertGreaterEqual(len(models), 20, '夾具應涵蓋 20 種以上模型（否則矩陣恆真）')
        checked = 0
        for user in self.roles:
            for model in models:
                expected = self._expected_ids(user, model)
                seen = self._seen_ids(user, model)
                self.assertEqual(seen, expected, f'{user.login} × {model}：看得到的 id 與期望不同 '
                                 f'（多：{sorted(seen - expected)}，少：{sorted(expected - seen)}）')
                checked += 1
        self.assertTrue(any(self._expected_ids(u, m) for u in self.roles for m in models), '期望值不可全空')
        _logger.info('角色帳號權限矩陣：%d 組（角色 × 模型）逐一比 id', checked)

    def test_matrix_spot_checks(self):
        """規格 §3-1 點名的幾件事（獨立於上面的期望函式再寫一次）。"""
        project_ids = lambda user: self._seen_ids(user, 'project.project')    # noqa: E731
        self.assertNotIn(self.p_a.id, project_ids(self.cm), '營造主管看不到沒被加入的 PA')
        self.assertIn(self.p_draft.id, project_ids(self.cb), '營造老闆看得到未開始的 PD')
        # 主管被加入了 PD（未開始）與 PT（終止）：工程本身與底下的估驗、工項、損益都看不到（fix1-C）
        for manager in (self.cm, self.sm):
            self.assertFalse(project_ids(manager) & {self.p_draft.id, self.p_term.id}, manager.login)
            for model in ('payment.estimate', 'project.task', 'general.progress.report', 'profit.loss.entry'):
                hidden = {rid for rid, (p, _c) in self.meta[model].items() if p in (self.p_draft | self.p_term)}
                self.assertTrue(hidden, f'前提：{model} 在 PD／PT 有夾具')
                self.assertFalse(self._seen_ids(manager, model) & hidden, f'{manager.login} × {model}：未開始／終止工程的資料')
        self.assertIn(self.p_term.id, project_ids(self.cb), '老闆照舊看得到終止的工程')
        self.assertNotIn(self.p_s2.id, project_ids(self.sb), '監造老闆看不到 S2 的工程')
        self.assertEqual(project_ids(self.sm), {self.p_a.id})
        shared_entries = {rid for rid, (p, _c) in self.meta['profit.loss.entry'].items() if p == self.p_shared}
        shared_profits = {rid for rid, (p, _c) in self.meta['general.realtime.profit'].items() if p == self.p_shared}
        self.assertTrue(shared_entries and shared_profits)
        for user in self.contractor_roles:
            self.assertFalse(self._seen_ids(user, 'profit.loss.entry') & shared_entries,
                             f'{user.login}：多營造廠共用的 P 的損益支出營造方看不到')
            self.assertFalse(self._seen_ids(user, 'general.realtime.profit') & shared_profits, user.login)
        self.assertTrue(self._seen_ids(self.sb, 'profit.loss.entry') & shared_entries, '監造老闆看得到 P 的損益支出')
        # B 的估驗與它的損益支出：營造方 A 看不到（含 PA 上歸屬 B 的那筆）
        b_entries = {rid for rid, (_p, c) in self.meta['profit.loss.entry'].items() if c == self.co_b}
        self.assertTrue(b_entries)
        self.assertFalse(self._seen_ids(self.cb, 'profit.loss.entry') & b_entries)
        pa_b_entry = self.env['profit.loss.entry'].search([('estimate_id', '=', self.est_pa_b.id)])
        self.assertIn(pa_b_entry.id, self._seen_ids(self.sb, 'profit.loss.entry'))
        if self.has_cost_analysis:
            no_project = {rid for rid, (p, _c) in self.meta['cost.analysis'].items() if not p}
            self.assertEqual(len(no_project), 1)
            for user in self.roles:
                self.assertEqual(bool(self._seen_ids(user, 'cost.analysis') & no_project), user == self.sb,
                                 f'{user.login}：沒有工程的成本分析只有監造老闆看得到')

    def test_existing_contractor_accounts_unchanged(self):
        """既有的營造廠主管與前台營造帳號：白名單模型的條件＝S1 之前的公式（測試獨立寫），角色帳號的新分類照拒。"""
        scope = self.co_a.id
        for user in (self.mgr_a, self.portal_a):
            rule = self._env_of(user)['ir.rule']
            for model in list(EXPECT_CONTRACTOR_LEVEL) + list(EXPECT_LINES) + list(EXPECT_PROJECT_LEVEL):
                definition = (contractor_definition(model, scope) if model not in EXPECT_PROJECT_LEVEL
                              else project_definition(model, scope))
                core = self._core_domain(user, model)
                expected = expression.AND([core, definition]) if core else definition
                self.assertEqual(rule._compute_domain(model, 'read'), expected, f'{user.login} × {model}')
            for model in EXPECT_ROLE_ONLY:
                if model in self.env:
                    self.assertEqual(rule._compute_domain(model, 'read'), DENIED, f'{user.login} × {model}')

    # ── 2. 「其他」類 0 筆 ─────────────────────────────────────────────
    def test_other_models_all_zero(self):
        for user in self.roles:
            # S2 fix2-W：監造方角色帳號讀得到意見回饋的類別、發生功能（設定資料）與自己的客服單——不算「其他」
            allowed = ROLE_WHITELIST | EXPECT_FRAMEWORK
            if user._role_side() == 'supervision':
                allowed = allowed | {rule_scope.ROLE_FEEDBACK_OWN} | rule_scope.ROLE_FEEDBACK_REFERENCE
            nonzero, errors = self._other_counts(user, allowed)
            self.assertEqual(errors, {}, f'{user.login}：列舉時不可出錯')
            self.assertEqual(nonzero, {}, f'{user.login}：「其他」類的模型必須一筆都看不到')

    # ── 3. 寫入全拒 ───────────────────────────────────────────────────
    def test_write_create_unlink_denied(self):
        for user in self.roles:
            self._assert_write_denied(user, DENY_NOTE_ROLE)

    def test_real_writes_rejected(self):
        own_estimate = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_a)
        entry = self.env['profit.loss.entry'].search([('estimate_id', '=', own_estimate.id)])
        self.assertTrue(own_estimate and entry)
        estimate_name, task_name = own_estimate.name, self.tasks[self.p_a].name
        for user in self.cb | self.sb:
            env = self._env_of(user)
            Access = env['ir.model.access']
            self.assertTrue(env['payment.estimate'].browse(own_estimate.id).read(['name']), '前提：讀得到')
            cases = (
                ('payment.estimate', lambda: env['payment.estimate'].browse(own_estimate.id).write({'name': 'ROLE 改掉'})),
                ('project.task', lambda: env['project.task'].browse(self.tasks[self.p_a].id).write({'name': 'ROLE 改掉'})),
                ('profit.loss.entry', lambda: env['profit.loss.entry'].browse(entry.id).write({'expense_amount': 1.0})),
                ('profit.loss.entry', lambda: env['profit.loss.entry'].create({
                    'project_id': self.p_a.id, 'estimate_id': own_estimate.id})),
            )
            for model, attempt in cases:
                with self.assertRaises(AccessError, msg=f'{user.login} × {model}') as ctx:
                    attempt()
                # ACL 有給寫入的（內部帳號 base.group_user 帶的）才走到範圍規則，訊息要帶本規則的說明；
                # ACL 就沒給的（角色群組只有讀取 ACL）由核心 ACL 先擋，訊息是核心的
                if Access.check(model, 'write', raise_exception=False):
                    self.assertIn(DENY_NOTE_ROLE, str(ctx.exception), f'{user.login} × {model}')
        self.assertEqual(entry.expense_amount, EXPENSE_AMOUNT)
        self.assertEqual(own_estimate.name, estimate_name)
        self.assertEqual(self.tasks[self.p_a].name, task_name)

    # ── 4. fail-closed ───────────────────────────────────────────────
    def _crafted(self, login, xmlids, companies=None, scope=None, contractor_flag=False):
        """用 SQL 直接寫 res_groups_users_rel 造出 ORM 約束不准的組合（模擬資料被改壞），都開 TOTP。"""
        companies = companies or self.co_s
        user = self._role_user(login, ['base.group_user'], self.co_s, companies, scope)
        for xmlid in xmlids:
            self.env.cr.execute(
                'INSERT INTO res_groups_users_rel (gid, uid) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                [self.env.ref(xmlid).id, user.id])
        if contractor_flag:
            self.env.cr.execute('UPDATE res_users SET is_contractor_org = TRUE WHERE id = %s', [user.id])
        self.env.invalidate_all()
        self.env.registry.clear_cache()
        return user

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_fail_closed_invalid_setups(self):
        cases = {
            'level_without_side': (self._crafted('ff_level', [ROLE_BOSS]), 'supervision_role'),
            'side_without_level': (self._crafted('ff_side', [ROLE_SUPERVISION]), 'supervision_role'),
            'two_sides': (self._crafted('ff_two', [MANAGER_GROUP, ROLE_SUPERVISION, ROLE_BOSS],
                                        companies=self.co_s | self.co_a, scope=self.co_a), 'contractor'),
            'supervision_with_contractor_flag': (self._crafted('ff_flag', [ROLE_SUPERVISION, ROLE_BOSS],
                                                               contractor_flag=True), 'contractor'),
            # 合法組合但沒開 TOTP（從 ORM 建，約束放行）
            'no_totp': (self._role_user('ff_nototp', [ROLE_SUPERVISION, ROLE_BOSS], self.co_s, self.co_s,
                                        totp=False), 'supervision_role'),
        }
        Rule = self.env['ir.rule']
        for name, (user, kind) in cases.items():
            self.assertTrue(user._is_role_account(), name)
            self.assertEqual(Rule.with_user(user)._dash_scope_kind(), kind, f'{name}：kind 絕不可是 None')
            self.assertFalse(user._dash_scope_ok(), name)
            self.assertFalse(user._is_backend_staff(), name)
            self.assertFalse(user._is_supervision_side(), name)
            nonzero, errors = self._other_counts(user, EXPECT_FRAMEWORK)
            self.assertEqual((nonzero, errors), (SELF_ONLY_COUNTS, {}), f'{name}：框架以外只剩本人')
            self.assertTrue(gate_verdict(self.env(user=user), *CUSTOM_METHOD), f'{name}：方法閘門要生效')
            domain = self.env['project.project'].with_user(user)._get_portal_projects_domain(user.partner_id)
            self.assertEqual(self.env['project.project'].sudo().search_count(domain), 0, f'{name}：前台工程清單是空的')
        self.assertEqual(cases['no_totp'][0].with_user(cases['no_totp'][0])._dash_totp_missing(), True)

    def test_constraints_block_invalid_setups(self):
        """從 ORM 設定不合法的組合直接擋下（ValidationError）。"""
        invalid = {
            'level_without_side': ([ROLE_BOSS], self.co_s, self.co_s, None),
            'side_without_level': ([ROLE_SUPERVISION], self.co_s, self.co_s, None),
            'two_sides': ([MANAGER_GROUP, ROLE_SUPERVISION, ROLE_BOSS], self.co_s, self.co_s | self.co_a, self.co_a),
            'extra_group': ([ROLE_SUPERVISION, ROLE_BOSS, SUPERVISOR_ADMIN], self.co_s, self.co_s, None),
            'console_and_role': ([CONSOLE_GROUP, ROLE_SUPERVISION, ROLE_BOSS], self.co_s, self.co_s, None),
            'supervision_only_contractor_companies': ([ROLE_SUPERVISION, ROLE_BOSS], self.co_a, self.co_a, None),
        }
        for name, (groups, company, companies, scope) in invalid.items():
            with self.assertRaises(ValidationError, msg=name):
                self._user(f'cv_{name}', groups, company=company, companies=companies, scope=scope)
        with self.assertRaises(ValidationError):
            self.sb.write({'is_contractor_org': True})
        with self.assertRaises(ValidationError):
            self.sm.write({'company_ids': [(6, 0, self.co_a.ids)], 'company_id': self.co_a.id})
        plain = self._user('cv_plain', ['base.group_user'], company=self.co_s, companies=self.co_s)
        with self.assertRaises(ValidationError):
            self.env.ref(ROLE_BOSS).write({'users': [(4, plain.id)]})   # 從群組那一側加人也擋
        # 反證：合法組合建得起來
        ok = self._user('cv_ok', [ROLE_SUPERVISION, ROLE_MANAGER], company=self.co_s, companies=self.co_s)
        self.assertTrue(ok._is_role_account())

    # ── 6. 監造方的人員與聯絡人範圍 ───────────────────────────────────
    def test_supervision_personal_data_scope(self):
        Partner = self.env['res.partner']
        outsider = Partner.create({'name': 'ROLE 外部聯絡人（公司空白）'})
        s1_staff = self._user('role_s1_staff', ['base.group_user'], company=self.co_s, companies=self.co_s)
        s2_staff = self._user('role_s2_staff', ['base.group_user'], company=self.co_s2, companies=self.co_s2)
        s1_emp = self.env['hr.employee'].create({'name': 'ROLE S1 員工', 'company_id': self.co_s.id})
        s2_emp = self.env['hr.employee'].create({'name': 'ROLE S2 員工', 'company_id': self.co_s2.id})
        self.assertFalse(outsider.company_id)
        for user in self.sb | self.sm:
            partners = self._visible_ids(user, 'res.partner', [('id', 'in', (
                outsider | s1_staff.partner_id | s2_staff.partner_id | user.partner_id | self.co_s.partner_id).ids)])
            self.assertNotIn(outsider.id, partners, f'{user.login}：公司空白的外部聯絡人讀不到')
            self.assertNotIn(s2_staff.partner_id.id, partners, f'{user.login}：S2 帳號的聯絡人讀不到')
            self.assertTrue({user.partner_id.id, s1_staff.partner_id.id, self.co_s.partner_id.id} <= partners,
                            f'{user.login}：自己、S1 帳號、S1 公司的聯絡人讀得到')
            users = self._visible_ids(user, 'res.users', [('id', 'in', (s1_staff | s2_staff | user).ids)])
            self.assertEqual(users, {s1_staff.id, user.id}, f'{user.login}：S2 的使用者讀不到')
            employees = self._visible_ids(user, 'hr.employee', [('id', 'in', (s1_emp | s2_emp).ids)])
            self.assertEqual(employees, {s1_emp.id}, user.login)
        # 反證：監造方後台人員讀得到那個外部聯絡人（上面的「讀不到」是範圍造成的，不是夾具讀不到）
        self.assertIn(outsider.id, self._visible_ids(self.sup, 'res.partner', [('id', '=', outsider.id)]))

    # ── 7. 選單 ──────────────────────────────────────────────────────
    def _allowed_menu_closure(self):
        Menu = self.env['ir.ui.menu'].sudo().with_context(**{'ir.ui.menu.full_list': True, 'active_test': False})
        ids = set()
        for xmlid in EXPECT_ROLE_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            node = menu
            while node:
                ids.add(node.id)
                node = node.parent_id
            ids.update(Menu.search([('id', 'child_of', menu.id)]).ids)
        return ids

    def test_menus_equal_core_visible_and_allowlist(self):
        """以帳號本人身分判定（fix1-E：su=True 時核心 ACL 檢查一律放行，ACL 漏給也不會紅；
        核心 _visible_menu_ids 的快取鍵是群組集合、不含 su，所以先清快取，避免別的測試以 su 算的結果汙染）。"""
        self.env.registry.clear_cache()
        allowed = self._allowed_menu_closure()
        must_see_xmlids = [
            'construction_supervision_base.menu_estimate', 'construction_general.menu_general_realtime_profit',
            'construction_general.menu_general_progress_report', 'construction_contract_change.menu_contract_change_order',
            'construction_supervision_base.menu_supervision_task', f'{MODULE}.menu_company_dashboard']
        if self.has_cost_analysis:
            must_see_xmlids.append('construction_cost_analysis.menu_cost_analysis')   # 選裝模組；ACL 由程式建
        must_see = [self.env.ref(x).id for x in must_see_xmlids]
        must_not_see = self.env.ref('construction_supervision_base.menu_supervision_project').id
        for user in self.roles:
            env = self.env(user=user)
            self.assertFalse(env.su)
            visible = env['ir.ui.menu']._visible_menu_ids()
            core = CoreIrUiMenu._visible_menu_ids(env['ir.ui.menu'])
            self.assertEqual(visible, core & allowed, f'{user.login}：可見選單＝核心可見 ∩ 白名單＋上層')
            self.assertGreater(len(core), len(visible), '前提：核心可見比白名單多')
            for menu_id in must_see:
                self.assertIn(menu_id, visible, f'{user.login}：選單 {menu_id} 要看得到（ACL 沒給就會漏）')
            self.assertNotIn(must_not_see, visible, f'{user.login}：工程案件選單不在白名單')

    # ── 8. 後台畫面冒煙 ───────────────────────────────────────────────
    def _spec_from_arch(self, model, node):
        """依 view arch 組 web_read 的 specification（只取這一層的欄位；x2many 有內嵌子檢視時遞迴）。"""
        spec = {}
        for field_node in node.iter('field'):
            if field_node.getparent() is not None and self._inside_subview(field_node, node):
                continue
            name = field_node.get('name')
            field = model._fields.get(name)
            if not field:
                continue
            if field.type == 'many2one':
                spec[name] = {'fields': {'display_name': {}}}
            elif field.type in ('one2many', 'many2many'):
                sub = next((child for child in field_node if child.tag in ('list', 'kanban', 'form')), None)
                comodel = model.env[field.comodel_name]
                spec[name] = {'fields': (self._spec_from_arch(comodel, sub) if sub is not None
                                         else {'display_name': {}})}
            else:
                spec[name] = {}
        return spec

    def _inside_subview(self, field_node, root):
        """field_node 是不是在 root 底下另一個 <field> 的內嵌子檢視裡。"""
        parent = field_node.getparent()
        while parent is not None and parent is not root:
            if parent.tag == 'field':
                return True
            parent = parent.getparent()
        return False

    def _action_domain(self, action, user):
        try:
            return safe_eval(action.domain or '[]', {'uid': user.id, 'context': {}, 'allowed_company_ids': []})
        except Exception:  # noqa: BLE001 — 動態 domain 算不出來就不帶（只影響篩選，不影響權限）
            return []

    def test_backend_smoke_every_allowlisted_window_action(self):
        actions = self.env['ir.actions.act_window']
        for xmlid in EXPECT_ROLE_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.action and menu.action._name == 'ir.actions.act_window':
                actions |= menu.action
        self.assertGreaterEqual(len(actions), 6, '白名單裡的視窗動作至少六個（估驗、工項、變更單、進度表三個…）')
        read_records = 0
        for user in self.roles:
            env = self.env(user=user, context={'allowed_company_ids': user.company_ids.ids})
            for action in actions:
                label = f'{user.login} × {action.name}（{action.res_model}）'
                Model = env[action.res_model]
                views = Model.get_views([(False, 'list'), (False, 'form'), (False, 'search')],
                                        {'toolbar': True, 'load_filters': True, 'action_id': action.id})
                list_spec = self._spec_from_arch(Model, etree.fromstring(views['views']['list']['arch']))
                form_spec = self._spec_from_arch(Model, etree.fromstring(views['views']['form']['arch']))
                result = Model.web_search_read(self._action_domain(action, user), list_spec, limit=SMOKE_LIST_LIMIT)
                ids = [row['id'] for row in result['records']]
                if ids:
                    Model.browse(ids[:3]).web_read(form_spec)
                    read_records += len(ids[:3])
                _logger.info('後台冒煙 %s：清單 %d 筆、表單讀 %d 筆', label, result['length'], len(ids[:3]))
        self.assertGreater(read_records, 0, '至少要真的讀到一些表單（否則只證明了空清單）')

    # ── 9. 即時損益 ───────────────────────────────────────────────────
    def test_profit_loss_scoped_readonly(self):
        Project = lambda user: self.env(user=user)['project.project']   # noqa: E731
        # 監造老闆看 PA：PA 的兩筆估驗（含歸屬 B 的那筆）都在、支出讀得到、唯讀
        data = Project(self.sb).get_profit_loss_data(self.p_a.id)
        pa_estimates = self.estimates.filtered(lambda e: e.project_id == self.p_a)
        self.assertEqual({e['estimate_id'] for e in data['estimates']}, set(pa_estimates.ids))
        self.assertTrue(all(e['entry_id'] and e['expense'] == EXPENSE_AMOUNT for e in data['estimates']))
        self.assertFalse(data['can_edit'])
        # 營造老闆看共用的 P：只有自己的估驗、支出看不到（多營造廠共用）
        data = Project(self.cb).get_profit_loss_data(self.p_shared.id)
        own = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_shared)
        self.assertEqual({e['estimate_id'] for e in data['estimates']}, set(own.ids))
        self.assertTrue(all(not e['entry_id'] for e in data['estimates']))
        self.assertFalse(data['can_edit'])
        # 範圍外：AccessError（不是空的冒充「沒有估驗」）
        for user, project in ((self.cb, self.p_b), (self.sm, self.p_b), (self.sb, self.p_s2)):
            with self.assertRaises(AccessError, msg=f'{user.login} × {project.code}'):
                Project(user).get_profit_loss_data(project.id)
        # 反證：監造方後台人員可以改
        self.assertTrue(Project(self.sup).get_profit_loss_data(self.p_a.id)['can_edit'])
        # 方法閘門：讀取方法放行、存支出照擋
        for user in self.roles:
            self.assertEqual(gate_verdict(self.env(user=user), 'project.project', 'get_profit_loss_data'), [])
            self.assertTrue(gate_verdict(self.env(user=user), 'project.project', 'save_profit_loss_expense'))

    # ── 10. 通知不外洩 ────────────────────────────────────────────────
    def test_internal_note_does_not_notify_restricted(self):
        estimate = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_a)
        note_subtype = self.env.ref('mail.mt_note')
        comment_subtype = self.env.ref('mail.mt_comment')
        followers = self.sm | self.mgr_a | self.sup
        estimate.message_subscribe(partner_ids=followers.partner_id.ids,
                                   subtype_ids=(note_subtype | comment_subtype).ids)
        author = _fixture_admin(self.env, self.co_s)
        poster = estimate.with_user(author)

        def notified(message):
            return set(message.sudo().notification_ids.res_partner_id.ids)

        note = poster.message_post(body='ROLE 內部備註', message_type='comment', subtype_xmlid='mail.mt_note')
        mention = poster.message_post(body='ROLE 內部備註 @ 提到', message_type='comment',
                                      subtype_xmlid='mail.mt_note', partner_ids=(self.sm | self.sup).partner_id.ids)
        comment = poster.message_post(body='ROLE 一般訊息', message_type='comment', subtype_xmlid='mail.mt_comment')
        for message in (note, mention):
            self.assertNotIn(self.sm.partner_id.id, notified(message), '監造主管（角色帳號）收不到內部備註')
            self.assertNotIn(self.mgr_a.partner_id.id, notified(message), '營造廠主管收不到內部備註')
            self.assertIn(self.sup.partner_id.id, notified(message), '反證：監造方後台人員照收')
        self.assertTrue({self.sm.partner_id.id, self.mgr_a.partner_id.id} <= notified(comment),
                        '反證：一般訊息照常通知（追蹤機制本身沒壞）')
        mails = self.env['mail.mail'].sudo().search([('mail_message_id', 'in', (note | mention).ids)])
        self.assertFalse(mails.recipient_ids & (self.sm | self.mgr_a).partner_id, '也不寄信')

    def test_restricted_cannot_switch_to_email(self):
        for user in (self.sm, self.cb, self.mgr_a):
            self.assertEqual(user.notification_type, 'inbox', f'前提：{user.login} 是站內通知')
            with self.assertRaises(ValidationError, msg=user.login):
                user.with_user(user).write({'notification_type': 'email'})      # 自己在偏好設定改
            with self.assertRaises(ValidationError, msg=user.login):
                user.write({'notification_type': 'email'})                      # 管理者改
            self.assertEqual(user.notification_type, 'inbox')
        # 反證：監造方後台人員可以改；前台帳號本來就是 email，寫 email 不受影響
        self.sup.write({'notification_type': 'email'})
        self.assertEqual(self.sup.notification_type, 'email')
        self.portal_a.write({'notification_type': 'email'})

    # ── 12. 前台工程清單＝後台看得到的工程 ─────────────────────────────
    def test_portal_projects_equal_backend(self):
        """前台工程清單對照期望集合（兩個方向）；角色帳號那一段條件就是「以本人身分經 ir.rule 查到的工程」
        （fix1-H：不再手抄一份後台的工程條件）。"""
        Project = self.env['project.project']
        for user in self.roles:
            domain = Project.with_user(user)._get_portal_projects_domain(user.partner_id)
            portal = set(Project.sudo().with_context(active_test=False).search(domain).ids)
            self.assertEqual(portal & set(self.all_projects.ids), set(self.expect_projects[user].ids), user.login)
            role_part = Project.with_user(user)._get_portal_projects_domain_for_role_account(user)
            backend = set(self._env_of(user)['project.project'].search([]).ids)
            self.assertEqual(len(role_part), 1, f'{user.login}：{role_part}')
            field, operator, ids = role_part[0]
            self.assertEqual((field, operator, set(ids)), ('id', 'in', backend), user.login)
            self.assertEqual(portal, backend, user.login)

    # ── ACL 不變式 ────────────────────────────────────────────────────
    def test_role_acl_models_all_categorized(self):
        """角色群組可讀的每個模型都在 rule_scope 的某個分類或框架照舊裡（否則畫面會報無權限）；反過來，
        角色帳號的新分類都有讀取 ACL；角色群組沒有任何寫建刪 ACL。（刻意拿實作的分類常數與 ACL 資料對帳）"""
        groups = self.env.ref(ROLE_MANAGER) | self.env.ref(ROLE_BOSS) | self.env.ref(ROLE_SUPERVISION)
        acls = self.env['ir.model.access'].sudo().search([('group_id', 'in', groups.ids)])
        readable = set(acls.filtered('perm_read').model_id.mapped('model'))
        self.assertGreaterEqual(len(readable), 44)
        categorized = (set(rule_scope.CONTRACTOR_LEVEL) | set(rule_scope.CONTRACTOR_LEVEL_LINES)
                       | set(rule_scope.PROJECT_LEVEL) | set(rule_scope.INSPECTION_TEMPLATE_LEVEL)
                       | set(rule_scope.ROLE_PROJECT_LEVEL) | set(rule_scope.ROLE_ESTIMATE_CHILD)
                       | set(rule_scope.ROLE_COST_ANALYSIS) | set(rule_scope.ROLE_SUPERVISION_ONLY_PROJECT_LEVEL)
                       | set(rule_scope.NARROW_BY_COMPANY)
                       | {rule_scope.NARROW_USERS, rule_scope.NARROW_PARTNERS} | set(rule_scope.FRAMEWORK_READ)
                       # S2 fix2-W：意見回饋（construction_helpdesk 有裝才有 ACL）
                       | {rule_scope.ROLE_FEEDBACK_OWN} | set(rule_scope.ROLE_FEEDBACK_REFERENCE))
        self.assertEqual(readable - categorized, set(), '有讀取 ACL 卻沒有範圍分類的模型')
        role_models = {m for m in EXPECT_ROLE_ONLY if m in self.env}
        self.assertEqual(role_models - readable, set(), '角色帳號的新分類缺讀取 ACL')
        self.assertFalse(acls.filtered(lambda a: a.perm_write or a.perm_create or a.perm_unlink))


    # ── fix1-G：「受限帳號」判斷只有一份 ──────────────────────────────────
    def test_restricted_judgment_single_definition(self):
        """_dash_is_restricted 只在 construction_supervision_base 定義一次；後台人員、kind 都由它推出（真值表）。"""
        owners = [cls.__module__ for cls in type(self.env['res.users']).mro() if '_dash_is_restricted' in vars(cls)]
        self.assertEqual(len(owners), 1, owners)
        self.assertTrue(owners[0].startswith('odoo.addons.construction_supervision_base.'), owners)
        Rule = self.env['ir.rule']
        users = (self.roles | self.mgr_a | self.portal_a | self.portal_blank | self.sup | self.console
                 | self.env.ref('base.user_admin') | self.env.ref('base.public_user'))
        for user in users:
            restricted = user._dash_is_restricted()
            self.assertEqual(user._is_backend_staff(), user._is_internal() and not restricted, user.login)
            self.assertEqual(Rule.with_user(user)._dash_scope_kind() is not None, restricted, user.login)
        self.assertTrue(all(u._dash_is_restricted() for u in self.roles | self.mgr_a | self.portal_a | self.console))
        self.assertFalse(self.sup._dash_is_restricted())

    # ── fix1-A：受限內部帳號不能在業務紀錄上發訊息、傳附件、通知別人 ─────────
    def _post_attempts(self, env, task, outsider, any_message):
        """會讓「訊息出現在單據上、或通知到別人」的 ORM 入口（等同 call_kw）。回傳 (名稱, 呼叫) 清單。

        message_notify 先通知站內帳號（監造方後台人員，inbox）：通知外部聯絡人時核心要以本人身分算 email 版面，
        受限帳號讀不到訊息子類型，會因為「別的原因」失敗（QWebException）——那不是這道防線擋的（M-B），
        只用 email 收件人會讓「拿掉防線」也照樣紅。"""
        Task = env['project.task'].browse(task.id)
        insider = self.sup.partner_id
        return [
            ('message_notify 站內帳號', lambda: Task.message_notify(
                body='ROLE 站內通知', subject='ROLE', partner_ids=[insider.id])),
            ('message_post 留言＋通知', lambda: Task.message_post(
                body='ROLE 留言', message_type='comment', subtype_xmlid='mail.mt_comment', partner_ids=[outsider.id])),
            ('message_post 預設類型', lambda: Task.message_post(body='ROLE 預設類型', partner_ids=[outsider.id])),
            ('message_post 附件', lambda: Task.message_post(
                body='ROLE 附件', attachments=[('role-evil.html', b'<b>role</b>')])),
            ('message_notify', lambda: Task.message_notify(
                body='ROLE 通知', subject='ROLE', partner_ids=[outsider.id])),
            ('mail.message 直接建（使用者通知）', lambda: env['mail.message'].create({
                'model': 'project.task', 'res_id': task.id, 'message_type': 'user_notification',
                'body': 'ROLE 直接建', 'partner_ids': [(4, outsider.id)]})),
            ('mail.message 直接建（沒有單據）', lambda: env['mail.message'].create({
                'message_type': 'comment', 'body': 'ROLE 沒有單據', 'partner_ids': [(4, outsider.id)]})),
            ('mail.notification 直接建', lambda: env['mail.notification'].create({
                'mail_message_id': any_message.id, 'res_partner_id': outsider.id, 'notification_type': 'inbox'})),
        ]

    def test_restricted_internal_cannot_post_or_notify(self):
        outsider = self.env['res.partner'].create({'name': 'ROLE 外部收件人', 'email': 'role-outsider@example.invalid'})
        cases = ((self.cb, self.tasks[self.p_a]), (self.cm, self.tasks[self.p_shared]), (self.sb, self.tasks[self.p_a]),
                 (self.sm, self.tasks[self.p_a]), (self.mgr_a, self.tasks[self.p_a]))
        for user, task in cases:
            task.sudo()._portal_ensure_token()
            existing = task.with_user(self.sup).message_post(body='ROLE 監造方留言', message_type='comment',
                                                             subtype_xmlid='mail.mt_comment')
            env = self._env_of(user)
            self.assertTrue(env['project.task'].browse(task.id).read(['name']), f'前提：{user.login} 讀得到工項')
            before = self.env['mail.message'].search_count([('model', '=', 'project.task'), ('res_id', '=', task.id)])
            for label, attempt in self._post_attempts(env, task, outsider, existing):
                with self.assertRaises(AccessError, msg=f'{user.login} × {label}'):
                    attempt()
            self.assertEqual(self.env['mail.message'].search_count(
                [('model', '=', 'project.task'), ('res_id', '=', task.id)]), before, f'{user.login}：沒有多出訊息')
            self.assertFalse(self.env['ir.attachment'].search_count([('name', '=', 'role-evil.html')]))
            # 路由 /mail/message/post、/mail/attachment/upload 先問「發訊息要什麼權限」再取單據（含存取權杖那條路）
            for Task in (env['project.task'], env['project.task'].sudo()):
                self.assertEqual(Task._get_mail_message_access([task.id], 'create'), 'write', user.login)
            self.assertFalse(env['project.task']._get_thread_with_access(task.id, mode='write', token=task.access_token),
                             f'{user.login}：帶存取權杖也不行')
            # 讀 chatter 照舊
            self.assertIn(existing.id, env['mail.message'].search(
                [('model', '=', 'project.task'), ('res_id', '=', task.id)]).ids, f'{user.login}：讀得到一般留言')
        # 對話（discuss.channel）照舊可以
        channel = self._env_of(self.sb)['discuss.channel'].channel_get([self.sb.partner_id.id])
        self.assertTrue(channel.message_post(body='ROLE 對話', message_type='comment', subtype_xmlid='mail.mt_comment'))
        # 反證：監造方後台人員同樣的呼叫都成功（呼叫本身是有效的）
        sup_env = self._env_of(self.sup)
        task = self.tasks[self.p_a]
        sup_task = sup_env['project.task'].browse(task.id)
        message = sup_task.message_post(body='ROLE 監造方', message_type='comment', subtype_xmlid='mail.mt_comment',
                                        partner_ids=[outsider.id], attachments=[('role-ok.txt', b'ok')])
        self.assertIn(outsider.id, message.sudo().notification_ids.res_partner_id.ids)
        self.assertTrue(sup_task.message_notify(body='ROLE 監造方通知', subject='ROLE', partner_ids=[outsider.id]))
        # 前台帳號（share）不受影響：取得發訊息權限的判斷與核心相同
        from odoo.addons.mail.models.mail_thread import MailThread
        portal_task = self.env(user=self.portal_a)['project.task']
        self.assertEqual(portal_task._get_mail_message_access([task.id], 'create'),
                         MailThread._get_mail_message_access(portal_task, [task.id], 'create'))

    # ── fix2-M：「受限的內部帳號」判斷只留一份 ─────────────────────────────────
    def test_restricted_internal_single_definition(self):
        owners = [cls.__module__ for cls in type(self.env['res.users']).mro()
                  if '_dash_is_restricted_internal' in vars(cls)]
        self.assertEqual(len(owners), 1, owners)
        self.assertTrue(owners[0].startswith('odoo.addons.construction_supervision_base.'), owners)
        from odoo.addons.construction_company_dashboard.models import restricted_mail
        self.assertFalse(hasattr(restricted_mail, '_restricted_internal'), '手寫版已刪')
        for user in self.roles | self.mgr_a | self.portal_a | self.sup | self.console | self.env.ref('base.user_admin'):
            self.assertEqual(user._dash_is_restricted_internal(), (not user.share) and user._dash_is_restricted(),
                             user.login)
        self.assertTrue(all(u._dash_is_restricted_internal() for u in self.roles | self.mgr_a | self.console))
        self.assertFalse(self.portal_a._dash_is_restricted_internal(), '前台帳號不算')

    # ── fix2-J：受限內部帳號發的訊息不寄 email、不通知對話成員以外的人 ─────────────
    def _mails_of(self, message):
        return self.env['mail.mail'].sudo().search([('mail_message_id', '=', message.id)])

    def _email_notified(self, message):
        """email 型的通知紀錄（寄成功、auto_delete 掉 mail.mail 之後還在；只看 mail.mail 會把「寄掉了」誤判成「沒寄」）。"""
        return set(message.sudo().notification_ids.filtered(lambda n: n.notification_type == 'email').res_partner_id.ids)

    def _notified(self, message):
        return set(message.sudo().notification_ids.res_partner_id.ids)

    def _j_targets(self, company, scope=None):
        """一個外部聯絡人（有 email、手機）＋一個頻道外的站內帳號，都讓那一方的帳號讀得到（ORM 才不會因讀不到而先失敗）。"""
        outsider = self.env['res.partner'].create({
            'name': f'ROLE J 外部 {company.name}', 'email': f'role-j-{company.id}@example.invalid',
            'mobile': '+886900000001', 'company_id': company.id})
        staff = self._user(f'role_j_staff_{company.id}', ['base.group_user'], company=self.co_s,
                           companies=self.co_s | company, scope=scope)
        return outsider, staff

    def _j_route_post(self, user, channel, targets, body):
        """照 /mail/attachment/upload＋/mail/message/post 的寫法：以 sudo 建附件、以 sudo 發訊息。"""
        env = self._env_of(user)
        post_access = env['discuss.channel'].sudo()._get_mail_message_access([channel.id], 'create')
        thread = env['discuss.channel']._get_thread_with_access(channel.id, mode=post_access)
        self.assertTrue(thread, f'前提：{user.login} 的對話照常')
        att = self.env(user=user.id, su=True)['ir.attachment'].create({
            'name': 'role-j-route.html', 'raw': b'<b>j</b>', 'res_model': 'discuss.channel', 'res_id': channel.id})
        return thread.sudo().message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_comment',
                                          partner_ids=targets, attachment_ids=[att.id])

    def _j_assert_quiet(self, label, message, members, outsiders, colleagues=frozenset()):
        """colleagues：私訊／群組對話裡讀得到的內部同事（S2 fix2-U，使用者 11-11 暫定：加進 partner_ids、只收站內通知）。"""
        self.assertFalse(self._mails_of(message), f'{label}：不可產生 mail.mail')
        self.assertFalse(self._email_notified(message), f'{label}：不可有 email 型的通知')
        self.assertTrue(set(message.sudo().partner_ids.ids) <= members | colleagues, f'{label}：不加入成員（與內部同事）以外的人')
        self.assertFalse(self._notified(message) & outsiders, f'{label}：不通知成員以外的人')

    @require_totp   # blocked_mgr＝沒開 TOTP 的營造廠主管（S2 fix2-Z 起預設不強制 TOTP，這裡驗強制時）
    def test_restricted_author_no_email_no_outsider(self):
        outsider_s, staff_s = self._j_targets(self.co_s)
        outsider_a, staff_a = self._j_targets(self.co_a, scope=self.co_a)
        blocked_mgr = self._user('role_j_blocked_mgr', [MANAGER_GROUP], company=self.co_s,
                                 companies=self.co_s | self.co_a, scope=self.co_a)   # 沒開 TOTP＝範圍不合格的營造廠主管
        self.assertFalse(blocked_mgr._dash_scope_ok())
        has_sms = 'sms.sms' in self.env
        sides = ((self.sb, outsider_s, staff_s, True), (self.cb, outsider_a, staff_a, True),
                 (self.mgr_a, outsider_a, staff_a, True), (blocked_mgr, outsider_a, staff_a, False))
        for user, outsider, staff, orm in sides:
            env = self._env_of(user)
            channel = env['discuss.channel'].sudo().browse(
                env['discuss.channel'].channel_get([user.partner_id.id]).id)   # 自己的對話（成員只有本人）
            members = set(channel.channel_member_ids.partner_id.ids)
            # 頻道外的站內帳號（讀得到的內部同事）：S2 fix2-U 起在私訊裡被 @ 會加進 partner_ids、收站內通知（不寄信）；
            # 外部聯絡人照舊拿掉
            outsiders, colleagues = {outsider.id}, {staff.partner_id.id}
            targets = list(outsiders | colleagues)
            label = user.login
            self._j_assert_quiet(f'{label} × 路由', self._j_route_post(user, channel, targets, 'ROLE J route'),
                                 members, outsiders, colleagues)
            if not orm:
                continue
            own_channel = env['discuss.channel'].browse(channel.id)
            self._j_assert_quiet(f'{label} × ORM message_post', own_channel.message_post(
                body='ROLE J ORM', message_type='comment', subtype_xmlid='mail.mt_comment',
                partner_ids=targets, attachments=[('role-j.txt', b'ROLE J')]), members, outsiders, colleagues)
            self._j_assert_quiet(f'{label} × message_notify', own_channel.message_notify(
                body='ROLE J notify', subject='ROLE J', partner_ids=targets), members, outsiders, colleagues)
            # 私訊對象就是外部聯絡人（建對話時把他加成成員）
            outsider_channel = env['discuss.channel'].channel_get([outsider.id])
            m4 = outsider_channel.message_post(body='ROLE J 外部成員', message_type='comment',
                                               subtype_xmlid='mail.mt_comment', partner_ids=[outsider.id])
            self.assertFalse(self._mails_of(m4) or self._email_notified(m4), f'{label}：成員是外部聯絡人也不寄信')
            if has_sms:   # sms 模組的 sms_numbers＝傳簡訊到任意號碼
                m5 = own_channel.message_post(body='ROLE J sms', message_type='comment', sms_numbers=['+886900000002'])
                self.assertFalse(self.env['sms.sms'].sudo().search([('mail_message_id', '=', m5.id)]), f'{label}：不發 SMS')
        # 成員之間的站內通知照常：監造老闆與監造方人員的私訊，@ 對方會收到站內通知
        # （核心的對話收件人 SQL 只取有 email 的聯絡人：discuss_channel.py _notify_get_recipients 的 partner.email != …）
        self.sup.partner_id.sudo().write({'email': 'role-j-member@example.invalid'})
        dm = self._env_of(self.sb)['discuss.channel'].channel_get([self.sup.partner_id.id])
        m = dm.message_post(body='ROLE J 成員', message_type='comment', subtype_xmlid='mail.mt_comment',
                            partner_ids=[self.sup.partner_id.id, outsider_s.id])
        self.assertIn(self.sup.partner_id.id, self._notified(m), '成員之間照常通知')
        self.assertFalse(self._mails_of(m) or self._email_notified(m))
        # 反證：監造方後台人員同樣的呼叫會寄信、會發簡訊（rig 有效）。照路由寫法以 sudo 發（核心以本人身分
        # 組 bus 酬載時會讀別人的通知而丟 AccessError；真的介面走 /mail/message/post，本來就是 sudo）
        channel = self._env_of(self.sup)['discuss.channel'].channel_get([self.sup.partner_id.id])   # 與上面同一種對話（自己的）
        rig = self._j_route_post(self.sup, channel, [outsider_s.id], 'ROLE J 監造方')
        self.assertIn(outsider_s.id, self._email_notified(rig), '反證：監造方 @ 外部聯絡人會寄 email')
        if has_sms:
            rig_sms = channel.sudo().message_post(body='ROLE J 監造方 sms', message_type='comment',
                                                  sms_numbers=['+886900000003'])
            self.assertTrue(self.env['sms.sms'].sudo().search([('mail_message_id', '=', rig_sms.id)]), '反證：SMS')

    # ── fix3-S：受限內部帳號不能冒用別人當作者（J 看作者，而作者由呼叫端指定）──────────────
    def _s_spoof_attempts(self, env, channel, author, outsider):
        """以別人（author）的名義發訊息的 ORM 入口（等同 call_kw，不經方法閘門：多庫 dbfilter 下閘門對 RPC 無效）。"""
        Channel = env['discuss.channel'].browse(channel.id)
        return [
            ('message_post author_id', lambda: Channel.message_post(
                body='ROLE S post', message_type='comment', subtype_xmlid='mail.mt_comment', author_id=author.id,
                partner_ids=[outsider.id], attachments=[('role-s.txt', b'ROLE S SECRET')])),
            ('message_post email_from（核心依 email 找作者）', lambda: Channel.message_post(
                body='ROLE S email_from', message_type='comment', subtype_xmlid='mail.mt_comment',
                email_from=author.email, partner_ids=[outsider.id])),
            ('message_notify author_id', lambda: Channel.message_notify(
                body='ROLE S notify', subject='ROLE S', author_id=author.id, partner_ids=[outsider.id])),
            ('mail.message.create author_id', lambda: env['mail.message'].create({
                'model': 'discuss.channel', 'res_id': channel.id, 'message_type': 'comment', 'body': 'ROLE S create',
                'author_id': author.id, 'partner_ids': [(4, outsider.id)]})),
            ('mail.message.create context default_author_id', lambda: env['mail.message'].with_context(
                default_author_id=author.id).create({
                    'model': 'discuss.channel', 'res_id': channel.id, 'message_type': 'comment',
                    'body': 'ROLE S default', 'partner_ids': [(4, outsider.id)]})),
        ]

    def _s_sides(self):
        """(帳號, 外部聯絡人, 冒用的作者)。冒用的作者要是那個帳號**讀得到**、不受限的聯絡人：讀不到的話
        relational_input_guard 會先擋下 author_id（那是別的防線，M-B）。都有 email，email_from 那條路才找得到他。"""
        outsider_s, _staff_s = self._j_targets(self.co_s)
        outsider_a, _staff_a = self._j_targets(self.co_a, scope=self.co_a)
        self.sup.partner_id.sudo().write({'email': 'role-s-staff@example.invalid'})   # 監造方後台人員
        contact_a = self.env['res.partner'].create({   # 營造廠 A 的聯絡人（沒有帳號）
            'name': 'ROLE S 冒用作者 A', 'email': 'role-s-contact-a@example.invalid', 'company_id': self.co_a.id})
        return ((self.sb, outsider_s, self.sup.partner_id), (self.cb, outsider_a, contact_a),
                (self.mgr_a, outsider_a, contact_a))

    def _s_spy_outgoing(self):
        """記下「建出來的」mail.mail 收件人與通知對象——之後就算整個呼叫 rollback 也看得到
        （測試模式下 email 在呼叫中途就送出、mail.mail 被 auto_delete；核心之後組 bus 酬載再丟 AccessError
        讓 savepoint 退回，只看資料庫會把「寄掉了」當成「沒寄」——M-A）。回傳 (patchers, 紀錄)。"""
        sent = {'mail': set(), 'notification': set()}
        Mail, Notification = type(self.env['mail.mail']), type(self.env['mail.notification'])
        mail_create, notification_create = Mail.create, Notification.create   # 先抓原件（L2②）

        def spy_mail(this, vals_list):
            for vals in (vals_list if isinstance(vals_list, list) else [vals_list]):
                for command in vals.get('recipient_ids') or []:
                    if isinstance(command, (list, tuple)) and command[0] == 4:
                        sent['mail'].add(command[1])
                    elif isinstance(command, (list, tuple)) and command[0] == 6:
                        sent['mail'].update(command[2] or [])
            return mail_create(this, vals_list)

        def spy_notification(this, vals_list):
            for vals in (vals_list if isinstance(vals_list, list) else [vals_list]):
                sent['notification'].add(vals.get('res_partner_id'))
            return notification_create(this, vals_list)
        return [patch.object(Mail, 'create', spy_mail), patch.object(Notification, 'create', spy_notification)], sent

    def test_restricted_spoofed_author_quiet(self):
        """規格 fix3-S 的結果：帶別人的 author_id 走 ORM message_post／message_notify／mail.message.create，
        外部聯絡人一封信、一則通知都沒有（呼叫失敗就整個 rollback，同 RPC）。"""
        patchers, sent = self._s_spy_outgoing()
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        sides = self._s_sides()
        for user, outsider, author in sides:
            env = self._env_of(user)
            channel = env['discuss.channel'].channel_get([user.partner_id.id])
            for label, attempt in self._s_spoof_attempts(env, channel, author, outsider):
                try:
                    with self.env.cr.savepoint():
                        attempt()
                except AccessError:
                    pass
                name = f'{user.login} × {label}'
                self.assertNotIn(outsider.id, sent['mail'], f'{name}：不可建出寄給外部聯絡人的 mail.mail')
                self.assertNotIn(outsider.id, sent['notification'], f'{name}：外部聯絡人沒有任何通知（含 email 型）')
        # 反證（spy 有效）：監造方後台人員 @ 外部聯絡人，spy 看得到寄出的信與通知
        outsider = sides[0][1]
        rig_channel = self._env_of(self.sup)['discuss.channel'].channel_get([self.sup.partner_id.id])
        self._j_route_post(self.sup, rig_channel, [outsider.id], 'ROLE S 反證')
        self.assertIn(outsider.id, sent['mail'] | sent['notification'], '反證：spy 記得到寄給外部聯絡人')

    def test_restricted_cannot_spoof_author(self):
        """fix3-S 保證 1（單獨隔離）：非 sudo 的受限內部帳號，訊息作者一定是本人——帶別人的作者一律 AccessError。"""
        for user, outsider, author in self._s_sides():
            env = self._env_of(user)
            channel = env['discuss.channel'].channel_get([user.partner_id.id])
            for label, attempt in self._s_spoof_attempts(env, channel, author, outsider):
                with self.assertRaises(AccessError, msg=f'{user.login} × {label}') as ctx:
                    attempt()
                self.assertIn(SPOOF_AUTHOR_DENY, str(ctx.exception), f'{user.login} × {label}：是作者檢查擋的')
            own = env['discuss.channel'].browse(channel.id).message_post(
                body='ROLE S own', message_type='comment', subtype_xmlid='mail.mt_comment', author_id=user.partner_id.id)
            self.assertEqual(own.sudo().author_id, user.partner_id, f'{user.login}：明寫自己當作者照常')
            with self.assertRaises(AccessError, msg=f'{user.login} × write author_id') as ctx:
                env['mail.message'].browse(own.id).write({'author_id': author.id})
            self.assertIn(SPOOF_AUTHOR_DENY, str(ctx.exception))
            self.assertEqual(own.sudo().author_id, user.partner_id)
        # 反證：系統以 sudo 代發（例：離開對話的「已離開」是以離開者為作者 sudo 發的）不受影響
        channel = self._env_of(self.sb)['discuss.channel'].channel_get([self.sb.partner_id.id])
        message = self.env(user=self.sb.id, su=True)['discuss.channel'].browse(channel.id).message_post(
            body='ROLE S sudo', message_type='comment', subtype_xmlid='mail.mt_comment', author_id=self.sup.partner_id.id)
        self.assertEqual(message.author_id, self.sup.partner_id)

    def test_restricted_caller_notify_quiet_even_if_author_spoofed(self):
        """fix3-S 保證 2（單獨隔離，繞過保證 1）：訊息若經某條保證 1 沒擋到的路、以別人當作者建了出來，
        非 sudo 的受限內部帳號觸發通知時，收件人照樣只留對話成員的站內類通知。"""
        outsider, _staff = self._j_targets(self.co_s)
        self.sup.partner_id.sudo().write({'email': 'role-s-staff@example.invalid'})
        dm = self._env_of(self.sup)['discuss.channel'].channel_get([self.sb.partner_id.id])

        def spoofed(body):
            # sudo 建＝保證 1 不管（它只管非 sudo）；作者是監造方人員，partner_ids 帶外部聯絡人
            return self.env(user=self.sb.id, su=True)['mail.message'].create({
                'model': 'discuss.channel', 'res_id': dm.id, 'message_type': 'comment', 'body': body,
                'subtype_id': self.env.ref('mail.mt_comment').id, 'author_id': self.sup.partner_id.id,
                'partner_ids': [(4, outsider.id)]})
        message = spoofed('ROLE S2 受限呼叫者')
        self.assertIn(outsider, message.partner_ids, '前提：外部聯絡人在 partner_ids 上（核心會寄 email 給他）')
        self._env_of(self.sb)['discuss.channel'].browse(dm.id)._notify_thread(message)
        self.assertFalse(self._mails_of(message) or self._email_notified(message), '受限呼叫者：不寄 email')
        self.assertNotIn(outsider.id, self._notified(message), '受限呼叫者：不通知成員以外的人')
        # 反證（rig 有效）：同一則訊息由系統以 sudo 通知（呼叫者不受限、作者也不受限）就會寄給外部聯絡人
        rig = spoofed('ROLE S2 反證')
        self.env['discuss.channel'].browse(dm.id).sudo()._notify_thread(rig)
        self.assertIn(outsider.id, self._email_notified(rig) | set(self._mails_of(rig).recipient_ids.ids),
                      '反證：不受限的呼叫會寄給外部聯絡人')

    # ── fix3-V：對話成員之間的推播照常 ─────────────────────────────────────
    def test_member_web_push_kept(self):
        """受限作者（監造老闆角色帳號、既有的營造廠主管）在與監造方人員的私訊發訊息：對方照常在核心的推播名單上；
        email、成員以外照樣剔除。觀察點＝核心挑推播對象的 _extract_partner_ids_for_notifications 的回傳值。"""
        outsider, _staff = self._j_targets(self.co_s)
        Channel = type(self.env['discuss.channel'])
        original = Channel._extract_partner_ids_for_notifications   # 先抓原件，spy 才不會遞迴（L2②）
        pushed = {}

        def spy(this, message, msg_vals, recipients_data):
            result = original(this, message, msg_vals, recipients_data)
            pushed.setdefault(message.id, set()).update(result)
            return result
        with patch.object(Channel, '_extract_partner_ids_for_notifications', spy):
            for author in (self.sb, self.mgr_a):
                dm = self._env_of(self.sup)['discuss.channel'].channel_get([author.partner_id.id])
                posts = [('路由（sudo）', self.env(user=author.id, su=True)['discuss.channel'].browse(dm.id))]
                if author == self.sb:
                    posts.append(('ORM', self._env_of(author)['discuss.channel'].browse(dm.id)))
                for label, channel in posts:
                    message = channel.message_post(body=f'ROLE V {author.login} {label}', message_type='comment',
                                                   subtype_xmlid='mail.mt_comment', partner_ids=[outsider.id])
                    name = f'{author.login} × {label}'
                    self.assertIn(self.sup.partner_id.id, pushed.get(message.id, set()), f'{name}：對話成員照常收推播')
                    self.assertNotIn(outsider.id, pushed.get(message.id, set()), f'{name}：成員以外不推播')
                    self.assertFalse(self._mails_of(message) or self._email_notified(message), f'{name}：不寄 email')
                    self.assertNotIn(outsider.id, self._notified(message), f'{name}：成員以外不通知')

    # ── fix2-K：受限內部帳號不能改、刪業務紀錄上的訊息，不能加表情回應 ─────────────
    def test_restricted_cannot_modify_business_messages(self):
        estimate = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_a)
        task = self.tasks[self.p_a]
        for user in (self.sb, self.cb, self.mgr_a):
            env = self._env_of(user)
            note = estimate.with_user(self.sup).message_post(
                body='ROLE K 內部備註 secret', message_type='comment', subtype_xmlid='mail.mt_note',
                partner_ids=[user.partner_id.id], attachments=[('role-k-note.txt', b'ROLE K NOTE')])
            comment = task.with_user(self.sup).message_post(body='ROLE K 留言', message_type='comment',
                                                            subtype_xmlid='mail.mt_comment')
            task.with_user(user).message_subscribe(partner_ids=[user.partner_id.id])   # 追蹤自己範圍內的單據（核心允許）
            Message = env['mail.message']
            self.assertFalse(Message.search([('id', '=', note.id)]), '前提：讀不到內部備註')
            with self.assertRaises(AccessError, msg=f'{user.login}：把內部備註改成一般訊息'):
                Message.browse(note.id).write({'is_internal': False, 'subtype_id': self.env.ref('mail.mt_comment').id})
            with self.assertRaises(AccessError, msg=f'{user.login}：改一般留言'):
                Message.browse(comment.id).write({'body': 'ROLE K 改掉'})
            with self.assertRaises(AccessError, msg=f'{user.login}：刪留言'):
                Message.browse(comment.id).unlink()
            for operation in ('create', 'write', 'unlink'):
                self.assertFalse(Message._get_with_access(comment.id, operation), f'{user.login} × {operation}')
            self.assertFalse(Message.search([('id', '=', note.id)]), f'{user.login}：內部備註還是讀不到')
            self.assertTrue(note.sudo().is_internal or note.sudo().subtype_id.internal)
            # 不能壞：讀 chatter、加星號、標為已讀
            self.assertTrue(Message.search([('id', '=', comment.id)]), f'{user.login}：讀得到一般留言')
            self.assertEqual(Message._get_with_access(comment.id, 'read'), Message.browse(comment.id))
            Message.browse(comment.id).toggle_message_starred()
            self.assertTrue(Message.browse(comment.id).starred, f'{user.login}：加星號照常')
            Message.mark_all_as_read()
        # 反證：監造方後台人員改得到
        comment = task.with_user(self.sup).message_post(body='ROLE K 監造方', message_type='comment',
                                                        subtype_xmlid='mail.mt_comment')
        self._env_of(self.sup)['mail.message'].browse(comment.id).write({'body': 'ROLE K 監造方改'})
        # 對話訊息照核心（本人改得到自己的對話訊息）
        channel = self._env_of(self.sb)['discuss.channel'].channel_get([self.sup.partner_id.id])
        own = channel.message_post(body='ROLE K 對話', message_type='comment', subtype_xmlid='mail.mt_comment')
        self._env_of(self.sb)['mail.message'].browse(own.id).write({'body': 'ROLE K 對話改'})

    # ── fix2-L：內部備註不通知受限帳號，判準＝NOT_INTERNAL_NOTE（同一個來源）──────────
    def test_notification_follows_internal_note_rule(self):
        """訊息類型 × 子類型是否內部 × is_internal 的矩陣：受限追蹤者「收到通知」⇔「讀得到這則訊息」。"""
        estimate = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_a)
        note_subtype, comment_subtype = self.env.ref('mail.mt_note'), self.env.ref('mail.mt_comment')
        estimate.message_subscribe(partner_ids=(self.sm | self.sup).partner_id.ids,
                                   subtype_ids=(note_subtype | comment_subtype).ids)
        poster = estimate.with_user(_fixture_admin(self.env, self.co_s))
        cases = []
        for message_type in ('comment', 'notification'):
            for subtype in ('mail.mt_note', 'mail.mt_comment'):
                for is_internal in (False, True):
                    message = poster.message_post(body=f'ROLE L {message_type} {subtype} {is_internal}',
                                                  message_type=message_type, subtype_xmlid=subtype,
                                                  is_internal=is_internal)
                    cases.append((f'{message_type}／{subtype}／is_internal={is_internal}', message))
        cases.append(('message_notify（user_notification）', poster.message_notify(
            body='ROLE L notify', subject='ROLE L', partner_ids=self.sm.partner_id.ids)))
        env = self._env_of(self.sm)
        some_hidden = some_visible = False
        for label, message in cases:
            visible = bool(env['mail.message'].search([('id', '=', message.id)]))
            notified = self.sm.partner_id.id in self._notified(message)
            self.assertEqual(notified, visible, f'{label}：收到通知（{notified}）必須等於讀得到（{visible}）')
            some_hidden |= not visible
            some_visible |= visible
        self.assertTrue(some_hidden and some_visible, '矩陣兩種結果都要有（否則恆真）')
        # 反證：監造方追蹤者照收內部備註
        self.assertIn(self.sup.partner_id.id, self._notified(cases[0][1]))

    # ── fix1-B：內部備註的附件，受限內部帳號讀不到 ───────────────────────────
    def _note_attachments(self, record):
        """在 record 上造四種附件：只掛內部備註、只掛一般留言、兩種都掛、單據本身（沒有訊息）。"""
        admin = _fixture_admin(self.env, self.co_s)
        poster = record.with_user(admin)
        note = poster.message_post(body='ROLE 內部備註附件', message_type='comment', subtype_xmlid='mail.mt_note',
                                   attachments=[('role-note-secret.txt', b'ROLE NOTE SECRET')])
        comment = poster.message_post(body='ROLE 一般留言附件', message_type='comment', subtype_xmlid='mail.mt_comment',
                                      attachments=[('role-comment.txt', b'ROLE COMMENT')])
        both = poster.message_post(body='ROLE 內部備註（兩邊都掛）', message_type='comment', subtype_xmlid='mail.mt_note',
                                   attachments=[('role-both.txt', b'ROLE BOTH')]).attachment_ids
        comment.sudo().write({'attachment_ids': [(4, both.id)]})
        doc = self.env['ir.attachment'].create({'name': 'role-doc.txt', 'raw': b'ROLE DOC',
                                                'res_model': record._name, 'res_id': record.id})
        return note.attachment_ids, comment.attachment_ids - both, both, doc

    def test_internal_note_attachments_hidden(self):
        estimate = self.docs[('payment.estimate', self.co_a)].filtered(lambda e: e.project_id == self.p_a)
        note_att, comment_att, both_att, doc_att = self._note_attachments(estimate)
        self.assertEqual(len(note_att | comment_att | both_att | doc_att), 4)
        everything = note_att | comment_att | both_att | doc_att
        for user in (self.cb, self.sb, self.sm, self.mgr_a):
            env = self._env_of(user)
            self.assertTrue(env['payment.estimate'].browse(estimate.id).read(['name']), f'前提：{user.login} 讀得到估驗')
            seen = set(env['ir.attachment'].search([('id', 'in', everything.ids)]).ids)
            self.assertEqual(seen, set((comment_att | both_att | doc_att).ids), f'{user.login}：只掛內部備註的附件看不到')
            for field in ('raw', 'datas'):
                with self.assertRaises(AccessError, msg=f'{user.login} × {field}'):
                    env['ir.attachment'].browse(note_att.id).read([field])
            chatter = env['payment.estimate'].browse(estimate.id)._get_mail_thread_data_attachments()
            self.assertNotIn(note_att.id, chatter.ids, f'{user.login}：chatter 附件欄')
            self.assertIn(comment_att.id, chatter.ids, f'{user.login}：一般留言的附件照常在 chatter 附件欄')
        # 反證：監造方後台人員四個都看得到
        self.assertEqual(set(self._env_of(self.sup)['ir.attachment'].search([('id', 'in', everything.ids)]).ids),
                         set(everything.ids))

    # ── fix1-I：畫面文字 ────────────────────────────────────────────────
    def test_gate_message_by_account_kind(self):
        from odoo.addons.construction_company_dashboard.models.method_gate import check_method_call
        for user in self.roles:
            with self.assertRaises(AccessError) as ctx:
                check_method_call(self.env(user=user), *CUSTOM_METHOD, via='test')
            message = str(ctx.exception)
            self.assertIn('後台唯讀帳號', message, user.login)
            self.assertNotIn('限監造單位使用', message, user.login)
            self.assertNotIn('請洽監造單位', message, user.login)
        with self.assertRaises(AccessError) as ctx:
            check_method_call(self.env(user=self.mgr_a), *CUSTOM_METHOD, via='test')
        self.assertIn('請洽監造單位', str(ctx.exception), '營造廠主管的訊息照舊')

    def test_totp_hint_points_to_real_menu(self):
        """選單實際叫「我的個人資料」（有裝人資模組）或「個人設定」（沒裝），分頁叫「帳戶安全性」。"""
        import os
        from odoo.modules.module import get_module_path
        from odoo.addons.construction_company_dashboard.models.res_users_guard import TOTP_SETUP_HINT
        base = get_module_path(MODULE)
        texts = {'TOTP_SETUP_HINT': TOTP_SETUP_HINT}
        for rel in ('static/src/backend/company_service_patch.js', 'static/src/dashboard_page/overview.xml'):
            with open(os.path.join(base, rel), encoding='utf-8') as handle:
                texts[rel] = handle.read()
        for name, text in texts.items():
            self.assertNotIn('我的偏好', text, name)
            for phrase in ('我的個人資料', '個人設定', '帳戶安全性'):
                self.assertIn(phrase, text, f'{name}：{phrase}')


@tagged('post_install', '-at_install', MODULE)
class TestRoleGateHttp(HttpCase):
    """規格 §3-9：存支出經 /web/dataset/call_kw 被方法閘門擋；讀取方法通過閘門（之後由範圍規則決定）。"""

    PASSWORD = 'Role-gate-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_a = env['res.company'].create({'name': 'ROLE 閘門 A', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'ROLE 閘門 監造', 'company_type': 'supervision'})
        cls.project = env['project.project'].create({
            'name': 'ROLE-GA 閘門測試', 'code': 'ROLE-GA', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        cls.estimate = env['payment.estimate'].create({
            'project_id': cls.project.id, 'estimate_date': fields.Date.today(), 'contractor_company_id': cls.co_a.id})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups):
            return Users.create({'name': login, 'login': login, 'password': cls.PASSWORD,
                                 'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                                 'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]})
        # 角色帳號不開 TOTP（瀏覽器登入不必過第二步；閘門不看 TOTP）
        cls.role = user('role_gate_sb', [ROLE_SUPERVISION, ROLE_BOSS])
        cls.sup = user('role_gate_sup', ['base.group_user', SUPERVISOR_ADMIN])

    def _call(self, user, method, args):
        scope_tests.login_as_browser(self, user.login, self.PASSWORD)   # S2 fix3-9：角色帳號非互動式只收 API key
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': 'project.project', 'method': method, 'args': args,
            'kwargs': {'context': {'allowed_company_ids': user.company_ids.ids}}}}
        body = self.url_open(f'/web/dataset/call_kw/project.project/{method}', data=json.dumps(payload),
                             headers={'Content-Type': 'application/json'}).json()
        if 'error' in body:
            data = body['error'].get('data', {})
            return 'error', data.get('name', ''), data.get('message', '')
        return 'ok', body.get('result')

    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_save_expense_blocked_read_passes_gate(self):
        Entry = self.env['profit.loss.entry'].sudo()
        args = [self.project.id, self.estimate.id, 123.0]
        result = self._call(self.role, 'save_profit_loss_expense', args)
        self.assertEqual(result[0], 'error')
        self.assertIn(GATE_NOTE, result[2], '存支出要被方法閘門擋下')
        self.assertFalse(Entry.search_count([('estimate_id', '=', self.estimate.id)]), '沒有寫進任何支出')
        # 讀取方法通過閘門：這個帳號沒開 TOTP，接著被範圍規則擋（AccessError，但不是閘門的訊息）
        result = self._call(self.role, 'get_profit_loss_data', [self.project.id])
        self.assertEqual(result[0], 'error')
        self.assertNotIn(GATE_NOTE, result[2], '讀取方法不該被閘門擋')
        self.assertIn('AccessError', result[1])
        # 反證：監造方後台人員存得進去
        result = self._call(self.sup, 'save_profit_loss_expense', args)
        self.assertEqual(result[0], 'ok', result)
        self.assertEqual(Entry.search([('estimate_id', '=', self.estimate.id)]).expense_amount, 123.0)


@tagged('post_install', '-at_install', MODULE)
class TestRoleMailHttp(HttpCase):
    """fix1-A／B 走真的 HTTP 路由；帳號自助（啟用 TOTP、偏好設定、改密碼、對話）照常。

    HttpCase.authenticate 直接設 session.uid（不走第二步驗證），所以已啟用 TOTP 的角色帳號也能登入測。
    """

    PASSWORD = 'Role-mail-pass1'
    NEW_PASSWORD = 'Role-mail-pass2'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_a = env['res.company'].create({'name': 'ROLE 留言 A', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'ROLE 留言 監造', 'company_type': 'supervision'})
        cls.project = env['project.project'].create({
            'name': 'ROLE-MH 留言測試', 'code': 'ROLE-MH', 'project_type': 'general', 'state': 'construction',
            'company_id': cls.co_s.id, 'contractor_company_ids': [(6, 0, cls.co_a.ids)]})
        cls.task = env['project.task'].create({'name': 'ROLE-MH 工項', 'project_id': cls.project.id})
        cls.task._portal_ensure_token()
        cls.estimate = env['payment.estimate'].create({
            'project_id': cls.project.id, 'estimate_date': fields.Date.today(), 'contractor_company_id': cls.co_a.id})
        cls.outsider = env['res.partner'].create({'name': 'ROLE 留言 外部', 'email': 'role-mh@example.invalid'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, companies, totp=True, **extra):
            record = Users.create(dict({
                'name': login, 'login': login, 'password': cls.PASSWORD,
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': cls.co_s.id, 'company_ids': [(6, 0, companies.ids)]}, **extra))
            if totp:
                record.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
            return record
        cls.sb = user('role_mh_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s)
        cls.cb = user('role_mh_cb', [MANAGER_GROUP, ROLE_BOSS], cls.co_s | cls.co_a, dash_scope_company_id=cls.co_a.id)
        cls.fresh = user('role_mh_fresh', [ROLE_SUPERVISION, ROLE_MANAGER], cls.co_s, totp=False)
        cls.sup = user('role_mh_sup', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s, totp=False)
        # 既有的營造廠主管（不是角色帳號；dev 的 kangyouchuan 這一型）
        cls.mgr = user('role_mh_mgr', [MANAGER_GROUP], cls.co_s | cls.co_a, dash_scope_company_id=cls.co_a.id)
        # 內部備註附件與一般留言附件（fix1-B）
        admin = _fixture_admin(env, cls.co_s)
        cls.note_att = cls.estimate.with_user(admin).message_post(
            body='ROLE 內部備註', message_type='comment', subtype_xmlid='mail.mt_note',
            attachments=[('role-mh-note.txt', b'ROLE MH NOTE')]).attachment_ids
        cls.comment_att = cls.estimate.with_user(admin).message_post(
            body='ROLE 一般留言', message_type='comment', subtype_xmlid='mail.mt_comment',
            attachments=[('role-mh-comment.txt', b'ROLE MH COMMENT')]).attachment_ids

    def _login(self, user, password=None):
        """已啟用 TOTP 的帳號：核心對「非互動式」登入只收 API 金鑰（auth_totp 的 _rpc_api_keys_only），
        HttpCase.authenticate 正是非互動式；真的瀏覽器登入是互動式（密碼＋驗證碼）。測試裡把它當互動式登入。"""
        with patch.object(type(self.env['res.users']), '_rpc_api_keys_only', lambda self: False):
            self.authenticate(user.login, password or self.PASSWORD)

    def _json(self, route, params):
        response = self.url_open(route, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def _call(self, model, method, args, kwargs=None):
        return self._json(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def _post(self, user, thread_model, thread_id, body, **extra):
        self._login(user)
        return self._json('/mail/message/post', dict({
            'thread_model': thread_model, 'thread_id': thread_id,
            'post_data': {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment',
                          'partner_ids': [self.outsider.id]}}, **extra))

    def _upload(self, user, name):
        self._login(user)
        return self.url_open('/mail/attachment/upload', data={
            'thread_id': self.task.id, 'thread_model': 'project.task', 'csrf_token': http.Request.csrf_token(self)},
            files={'ufile': (name, b'<b>role</b>', 'text/html')})

    def _messages(self, body):
        self.env.invalidate_all()
        return self.env['mail.message'].search([('model', '=', 'project.task'), ('res_id', '=', self.task.id),
                                                ('body', 'ilike', body)])

    def test_mail_routes_blocked_for_restricted_internal(self):
        for user in (self.sb, self.cb):
            for label, extra in (('一般', {}), ('帶存取權杖', {'token': self.task.access_token})):
                body = f'ROLE MH {user.login} {label}'
                result = self._post(user, 'project.task', self.task.id, body, **extra)
                self.assertIn('error', result, f'{user.login} {label}：/mail/message/post 要被擋')
                self.assertFalse(self._messages(body), f'{user.login} {label}：沒有寫進留言')
            response = self._upload(user, f'role-mh-{user.login}.html')
            self.env.invalidate_all()
            self.assertFalse(self.env['ir.attachment'].search_count([('name', '=', f'role-mh-{user.login}.html')]),
                             f'{user.login}：/mail/attachment/upload 沒有建出附件（{response.status_code}）')
        # 反證：監造方後台人員同樣兩條路都成功
        result = self._post(self.sup, 'project.task', self.task.id, 'ROLE MH 監造方')
        self.assertNotIn('error', result, result)
        self.assertTrue(self._messages('ROLE MH 監造方'))
        response = self._upload(self.sup, 'role-mh-sup.html')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.env['ir.attachment'].search_count([('name', '=', 'role-mh-sup.html')]))

    def test_internal_note_attachment_not_downloadable(self):
        self._login(self.sb)
        self.assertEqual(self.url_open(f'/web/content/{self.comment_att.id}').status_code, 200, '一般留言的附件照常下載')
        self.assertIn(self.url_open(f'/web/content/{self.note_att.id}').status_code, (403, 404),
                      '只掛內部備註的附件下載不到')
        self._login(self.sup)
        self.assertEqual(self.url_open(f'/web/content/{self.note_att.id}').status_code, 200, '反證：監造方下載得到')

    def test_self_service_still_works(self):
        """角色帳號自己：啟用 TOTP（身分確認 → 掃碼 → 驗證碼）、改偏好、改密碼、在對話裡發訊息。"""
        self._login(self.fresh)
        outcome = self._json('/web/dataset/call_button', {
            'model': 'res.users', 'method': 'action_totp_enable_wizard', 'args': [[self.fresh.id]], 'kwargs': {}})
        self.assertNotIn('error', outcome, outcome)
        check_id = outcome['result']['res_id']
        self.assertNotIn('error', self._call('res.users.identitycheck', 'web_save', [[check_id], {'password': self.PASSWORD}],
                                             {'specification': {}}))
        outcome = self._json('/web/dataset/call_button', {
            'model': 'res.users.identitycheck', 'method': 'run_check', 'args': [[check_id]], 'kwargs': {}})
        self.assertNotIn('error', outcome, outcome)
        wizard = self.env['auth_totp.wizard'].browse(outcome['result']['res_id'])
        key = base64.b32decode(wizard.secret.replace(' ', '').upper() + '=' * (-len(wizard.secret.replace(' ', '')) % 8))
        code = str(hotp(key, int(time.time() // TOTP_STEP_SECONDS))).zfill(TOTP_DIGITS)
        self.assertNotIn('error', self._call('auth_totp.wizard', 'web_save', [[wizard.id], {'code': code}],
                                             {'specification': {'code': {}}}))
        outcome = self._json('/web/dataset/call_button', {
            'model': 'auth_totp.wizard', 'method': 'enable', 'args': [[wizard.id]], 'kwargs': {}})
        self.assertNotIn('error', outcome, outcome)
        self.env.invalidate_all()
        self.assertTrue(self.fresh.totp_enabled, '啟用兩步驟驗證照常')
        # 偏好設定、改密碼（會寄安全通知信：核心以 sudo 建 mail.mail，不受留言封鎖影響）
        self._login(self.sb)
        self.assertNotIn('error', self._call('res.users', 'write', [[self.sb.id], {'tz': 'Asia/Taipei', 'signature': '<p>ROLE</p>'}]))
        result = self._call('res.users', 'change_password', [self.PASSWORD, self.NEW_PASSWORD])
        self.assertNotIn('error', result, result)
        # 對話照常
        channel = self.env['discuss.channel'].with_user(self.sb).channel_get([self.sb.partner_id.id])
        self._login(self.sb, self.NEW_PASSWORD)
        result = self._json('/mail/message/post', {'thread_model': 'discuss.channel', 'thread_id': channel.id,
                                                   'post_data': {'body': 'ROLE MH 對話', 'message_type': 'comment'}})
        self.assertNotIn('error', result, result)

    # ── fix5（使用者 11-11：受限帳號經 RPC 在對話發訊息要照常；fix2 起被方法閘門附帶擋下，審查 skeptic r3 F4）──
    @staticmethod
    def _error_message(result):
        return ((result.get('error') or {}).get('data') or {}).get('message') or ''

    def test_rpc_message_post_in_chat(self):
        """call_kw 的 discuss.channel.message_post／message_notify：受限內部帳號（角色帳號、既有營造廠主管）照常。
        帶別人當作者照樣被擋、業務紀錄照樣不能留言——擋下的是訊息守衛（fix3-S、fix1-A），不是方法閘門。"""
        for user in (self.sb, self.cb, self.mgr):
            # 監造角色帳號與監造方人員的私訊；營造方讀不到監造方人員的聯絡人（範圍規則），用自己的對話
            peer = self.sup.partner_id if user == self.sb else user.partner_id
            channel = self.env['discuss.channel'].with_user(user).channel_get([peer.id])
            self._login(user)
            body = f'ROLE RPC {user.login}'
            result = self._call('discuss.channel', 'message_post', [channel.id], {
                'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment'})
            self.assertNotIn('error', result, f'{user.login}：call_kw message_post 要照常：{self._error_message(result)}')
            self.env.invalidate_all()
            message = self.env['mail.message'].search([('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
                                                       ('body', 'ilike', body)])
            self.assertEqual(message.author_id, user.partner_id, f'{user.login}：訊息建出來、作者是本人')
            result = self._call('discuss.channel', 'message_notify', [channel.id], {
                'body': f'{body} notify', 'subject': 'ROLE RPC', 'partner_ids': peer.ids})
            self.assertNotIn('error', result, f'{user.login}：call_kw message_notify 要照常：{self._error_message(result)}')
            # 帶別人當作者：訊息守衛擋（fix3-S 保證 1）。冒用的對象要是本人讀得到的（否則先被讀取規則擋，測不到守衛）
            other = self.sup.partner_id if user == self.sb else self.co_a.partner_id
            self.assertEqual(self.env['res.partner'].with_user(user).search_count([('id', '=', other.id)]), 1,
                             f'前提：{user.login} 讀得到冒用的對象')
            result = self._call('discuss.channel', 'message_post', [channel.id], {
                'body': f'{body} spoof', 'author_id': other.id, 'message_type': 'comment',
                'subtype_xmlid': 'mail.mt_comment'})
            self.assertIn(DENY_AUTHOR_NOTE, self._error_message(result), f'{user.login}：冒用作者要被訊息守衛擋')
            # 業務紀錄照樣不能留言（fix1-A）
            result = self._call('payment.estimate', 'message_post', [self.estimate.id], {
                'body': f'{body} 業務', 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment'})
            self.assertIn(DENY_POST_NOTE, self._error_message(result), f'{user.login}：業務紀錄留言要被訊息守衛擋')
            self.env.invalidate_all()
            self.assertFalse(self.env['mail.message'].search_count([('body', 'ilike', f'{body} spoof')]))
            self.assertFalse(self.env['mail.message'].search_count([('body', 'ilike', f'{body} 業務')]))

    # ── fix2-J／K（真 HTTP）────────────────────────────────────────────
    def _upload_to(self, user, model, record_id, name):
        self._login(user)
        self.url_open('/mail/attachment/upload', data={
            'thread_id': record_id, 'thread_model': model, 'csrf_token': http.Request.csrf_token(self)},
            files={'ufile': (name, b'ROLE J HTTP', 'text/plain')})
        self.env.invalidate_all()
        return self.env['ir.attachment'].search([('name', '=', name)])

    def test_discuss_post_no_email_http(self):
        for user, expect_mail in ((self.sb, False), (self.sup, True)):
            channel = self.env['discuss.channel'].with_user(user).channel_get([user.partner_id.id])
            name = f'role-j-http-{user.login}.txt'
            attachment = self._upload_to(user, 'discuss.channel', channel.id, name)
            self.assertTrue(attachment, f'{user.login}：對話裡上傳附件照常')
            body = f'ROLE J HTTP {user.login}'
            result = self._json('/mail/message/post', {
                'thread_model': 'discuss.channel', 'thread_id': channel.id,
                'post_data': {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment',
                              'partner_ids': [self.outsider.id], 'attachment_ids': attachment.ids}})
            self.assertNotIn('error', result, f'{user.login}：對話照常發得出去')
            self.env.invalidate_all()
            message = self.env['mail.message'].search([('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
                                                       ('body', 'ilike', body)])
            self.assertTrue(message)
            mails = self.env['mail.mail'].sudo().search([('mail_message_id', '=', message.id)])
            # email 型通知紀錄：寄成功被 auto_delete 掉 mail.mail 之後還在（只看 mail.mail 會把「寄掉了」當成「沒寄」）
            emailed = message.sudo().notification_ids.filtered(lambda n: n.notification_type == 'email')
            self.assertEqual(bool(mails or emailed), expect_mail, f'{user.login}：寄 email（受限帳號不可有；監造方是反證）')
            self.assertEqual(self.outsider in message.partner_ids, expect_mail, f'{user.login}：外部聯絡人是否被加入')

    def test_message_write_routes_blocked_http(self):
        self.task.message_subscribe(partner_ids=self.sb.partner_id.ids)    # 追蹤者＝核心「建立」權限的另一條路
        comment = self.task.with_user(self.sup).message_post(body='ROLE K HTTP 留言', message_type='comment',
                                                             subtype_xmlid='mail.mt_comment')
        note = self.estimate.with_user(self.sup).message_post(body='ROLE K HTTP 備註', message_type='comment',
                                                              subtype_xmlid='mail.mt_note', is_internal=True,
                                                              partner_ids=self.sb.partner_id.ids)
        self.assertTrue(note.is_internal, '前提：備註的 is_internal 是 True（路由要把它改成 False）')
        self._login(self.sb)
        result = self._json('/mail/message/reaction', {'message_id': comment.id, 'content': '👍', 'action': 'add'})
        self.assertIn('error', result, '表情回應要被擋')
        result = self._json('/mail/update_is_internal', {'message_id': note.id, 'is_internal': False})
        self.assertIn('error', result, '把內部備註改成一般訊息要被擋')
        result = self._json('/mail/message/update_content', {'message_id': comment.id, 'body': 'ROLE K 改',
                                                             'attachment_ids': []})
        self.assertIn('error', result, '改訊息內容要被擋')
        # 不能壞：加星號、全部標為已讀
        self.assertNotIn('error', self._call('mail.message', 'toggle_message_starred', [[comment.id]]))
        self.assertNotIn('error', self._call('mail.message', 'mark_all_as_read', []))
        self.env.invalidate_all()
        self.assertFalse(self.env['mail.message.reaction'].search([('message_id', '=', comment.id)]))
        self.assertTrue(note.is_internal, '備註的 is_internal 沒有被改掉')
        self.assertEqual(comment.body, '<p>ROLE K HTTP 留言</p>')
        # 反證：監造方後台人員加得了表情回應
        self._login(self.sup)
        self.assertNotIn('error', self._json('/mail/message/reaction', {'message_id': comment.id, 'content': '👍',
                                                                        'action': 'add'}))
        self.env.invalidate_all()
        self.assertTrue(self.env['mail.message.reaction'].search([('message_id', '=', comment.id)]))
