# -*- coding: utf-8 -*-
"""營造方與控台讀取帳號的讀取範圍、拒寫（合約 §3.2–§3.4、§0b-1）。

自己造資料：營造廠 A、B、監造公司 S；共用工程 P（A＋B）、只有 A 的工程 PA、只有 B 的工程 PB、
預約式共用工程 R（A＋B）；8 種營造廠層級單據在 P／R 各給 A、B 一筆，PA 給 A 一筆、PB 給 B 一筆。
帳號：A 的營造廠主管（後台）、A 的前台營造帳號、範圍公司空白的前台營造帳號、監造方後台帳號、控台讀取帳號。

斷言打在使用者看得到的結果（筆數、看得到哪幾筆、被拒＋訊息），筆數兩個方向都比。
"""
import base64
import importlib.util
import logging
import os

from odoo import fields
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.module import get_module_path
from odoo.osv import expression
from odoo.tests import TransactionCase, tagged

from odoo.addons.construction_company_dashboard.models.rule_scope import (
    CORE_PARENT_CTX, CORE_PARENT_TOKEN, DENY_NOTE_CONSOLE, DENY_NOTE_CONTRACTOR,
)

MANAGER_GROUP = 'construction_company_dashboard.group_contractor_manager'
CONSOLE_GROUP = 'construction_company_dashboard.group_console_reader'
PORTAL_LEADER = 'construction_supervision_base.group_portal_leader'
SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'
OPERATOR = 'construction_supervision_base.group_operator'
PNG_B64 = base64.b64encode(
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
    b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
DENIED = [('id', '=', 0)]
# 庫裡沒有某模型的紀錄時，拒寫測試拿來驗的不存在的 id（int4 上限，不會撞到真的紀錄）
MISSING_RECORD_ID = 2 ** 31 - 1
# 夾具用的 TOTP 密鑰（base32，只用來讓 totp_enabled 為真）
TOTP_FIXTURE_SECRET = 'JBSWY3DPEHPK3PXP'
_logger = logging.getLogger(__name__)

# 合約 §3.2 的白名單，在測試這邊獨立寫一份（不 import 實作的常數，常數寫錯才測得出來）：
# 營造廠層級：模型 → 所屬工程欄位
EXPECT_CONTRACTOR_LEVEL = {
    'daily.log.sheet': 'supervision_project_id',
    'supervision.photo': 'project_id',
    'general.defect.improvement': 'project_id',
    'reservation.defect.improvement': 'project_id',
    'supervision.test.record': 'project_id',
    'general.self.inspection': 'project_id',
    'reservation.self.inspection': 'project_id',
    'payment.estimate': 'project_id',
}
# 明細：模型 → (父單欄位, 父單的工程欄位)
EXPECT_LINES = {
    'daily.log.line': ('sheet_id', 'supervision_project_id'),
    'payment.estimate.line': ('estimate_id', 'project_id'),
}
# 工程層級：模型 → 工程路徑（'' 表示本身）
EXPECT_PROJECT_LEVEL = {
    'project.project': '',
    'project.task': 'project_id',
    'progress.schedule': 'project_id',
    'progress.schedule.line': 'schedule_id.project_id',
    'construction.weekly.schedule': 'supervision_project_id',
    'construction.weekly.schedule.line': 'schedule_id.supervision_project_id',
    'supervision.test.task.statistics': 'project_id',
    'reservation.notification.slip': 'project_id',
    'reservation.notification.slip.line': 'slip_id.project_id',
    'reservation.notification.slip.suspension': 'slip_id.project_id',
    # 合約 §0b-20（線 F1）：檢試驗預警改歸工程層級
    'supervision.test.warning': 'project_id',
}
EXPECT_NARROW_COMPANY = ('hr.employee.public', 'hr.employee', 'hr.department', 'resource.resource')
EXPECT_NARROW_OTHER = ('res.users', 'res.partner')
# 框架照舊（讀取不加條件）與使用者自有狀態（可寫）——合約 §3.2、§3.3
EXPECT_FRAMEWORK = frozenset({
    'ir.ui.menu', 'ir.ui.view', 'ir.model', 'ir.actions.report', 'report.paperformat',
    'ir.filters', 'ir.embedded.actions', 'ir.attachment', 'mail.message', 'mail.notification',
    'discuss.channel', 'discuss.channel.member', 'bus.bus', 'bus.presence',
    'res.lang', 'res.currency', 'res.currency.rate', 'res.country', 'res.country.state',
    'res.company', 'uom.uom', 'uom.category',
    'res.users.settings', 'res.users.settings.volumes',
    'res.users.apikeys', 'res.device', 'res.device.log', 'auth_totp.device',
})
EXPECT_USER_OWNED = frozenset({
    'bus.presence', 'discuss.channel', 'discuss.channel.member', 'mail.message',
    'mail.notification', 'res.users.settings', 'res.users.settings.volumes', 'ir.filters',
})
# 線 A2 加進白名單的（合約 §0b-6 改判的三個工程層級；§3.6 前台會以本人身分讀到的營造廠層級子表），
# 與線 A3 加的前台工程文件（合約 §0b-10）。筆數與 A／B 隔離的測試（含營造廠主管，§0b-10 補了讀取 ACL）
# 在 construction_portal/tests/test_contractor_scope_portal.py。
EXPECT_PROJECT_LEVEL_A2 = ('supervision.folder', 'supervision.test.standard', 'contract.change.order',
                           'supervision.document')
EXPECT_LINES_A2 = (
    'daily.log.material', 'daily.log.weather', 'daily.log.specific.item', 'daily.log.man.machine.detail',
    'general.self.inspection.item', 'general.self.inspection.measure.line',
    'reservation.self.inspection.item', 'reservation.self.inspection.measure.line',
    'payment.estimate.extra.line',
)
# 線 G：自主檢查樣板與其明細（全域＋可見工程的＋可見工程的檢查用到的；前台工程首頁以本人身分讀樣板名稱）
EXPECT_INSPECTION_TEMPLATE = ('self.inspection.type', 'self.inspection.type.item', 'self.inspection.type.stage',
                              'self.inspection.type.timing', 'self.inspection.type.measure')
WHITELIST = (set(EXPECT_CONTRACTOR_LEVEL) | set(EXPECT_LINES) | set(EXPECT_PROJECT_LEVEL)
             | set(EXPECT_NARROW_COMPANY) | set(EXPECT_NARROW_OTHER)
             | set(EXPECT_PROJECT_LEVEL_A2) | set(EXPECT_LINES_A2) | set(EXPECT_INSPECTION_TEMPLATE))


def contractor_definition(model, scope_id):
    """營造廠層級／明細的定義條件（合約 §3.2），由測試獨立寫出。"""
    if model in EXPECT_CONTRACTOR_LEVEL:
        path = EXPECT_CONTRACTOR_LEVEL[model]
        return [('contractor_company_id', '=', scope_id), (f'{path}.contractor_company_ids', 'in', [scope_id])]
    parent, path = EXPECT_LINES[model]
    return [(f'{parent}.contractor_company_id', '=', scope_id),
            (f'{parent}.{path}.contractor_company_ids', 'in', [scope_id])]


def project_definition(model, scope_id):
    """工程層級的定義條件：所屬工程的營造廠含範圍公司。"""
    path = EXPECT_PROJECT_LEVEL[model]
    field = f'{path}.contractor_company_ids' if path else 'contractor_company_ids'
    return [(field, 'in', [scope_id])]


class DashScopeCase(TransactionCase):
    """共用資料（本類別沒有測試；test_attribution、test_supervision_unchanged 也繼承它）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_a = Company.create({'name': 'DASH 營造 A', 'company_type': 'contractor'})
        cls.co_b = Company.create({'name': 'DASH 營造 B', 'company_type': 'contractor'})
        cls.co_c = Company.create({'name': 'DASH 營造 C（不在任何工程）', 'company_type': 'contractor'})
        cls.co_s = Company.create({'name': 'DASH 監造 S', 'company_type': 'supervision'})
        both = [(6, 0, (cls.co_a | cls.co_b).ids)]
        cls.p_shared = cls._project('DASH-P', 'general', both)
        cls.p_a = cls._project('DASH-PA', 'general', [(6, 0, cls.co_a.ids)])
        cls.p_b = cls._project('DASH-PB', 'general', [(6, 0, cls.co_b.ids)])
        cls.r_shared = cls._project('DASH-R', 'reservation', both)
        cls.projects = cls.p_shared | cls.p_a | cls.p_b | cls.r_shared
        cls.itype = env['self.inspection.type'].create({'name': 'DASH 檢查類型'})
        cls.employee = env['hr.employee'].create({'name': 'DASH 填表人', 'company_id': cls.co_s.id})
        cls.tasks = {p: env['project.task'].create({
            'name': f'{p.code} 工項', 'project_id': p.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': 100.0}) for p in cls.projects}

        # 帳號
        cls.mgr_a = cls._user('dash_mgr_a', [MANAGER_GROUP], company=cls.co_s,
                              companies=cls.co_s | cls.co_a, scope=cls.co_a)
        # 前台營造帳號的允許公司要含工程的監造公司（核心工程規則 company_id in company_ids；dev 帳號 17 同此）
        # 範圍公司明寫：夾具不依賴「建帳號預帶」（預帶由 test_user_scope_prefill_and_constraint 單獨驗）
        # 營造廠主管必須啟用兩步驟驗證才看得到資料（A1' 合約 §13-6）；夾具先啟用，期望值不變。
        # 沒啟用的情境由 test_account_setup.py 單獨驗。
        cls.mgr_a.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        cls.portal_a = cls._user('dash_portal_a', [PORTAL_LEADER], company=cls.co_a,
                                 companies=cls.co_a | cls.co_s, scope=cls.co_a, extra={'is_contractor_org': True})
        cls.portal_blank = cls._user('dash_portal_blank', [PORTAL_LEADER], company=cls.co_a,
                                     companies=cls.co_a | cls.co_s, scope=cls.co_a,
                                     extra={'is_contractor_org': True})
        cls.sup = cls._user('dash_sup', ['base.group_user', SUPERVISOR_ADMIN], company=cls.co_s,
                            companies=cls.co_s)
        cls.console = cls._user('dash_console', [CONSOLE_GROUP], company=cls.co_s, companies=cls.co_s)
        # 範圍公司空白的營造方帳號：約束不准建立，所以照「既有帳號不符」的樣子用 SQL 清掉（合約 §2）
        env.cr.execute('UPDATE res_users SET dash_scope_company_id = NULL WHERE id = %s', [cls.portal_blank.id])
        cls.portal_blank.invalidate_recordset(['dash_scope_company_id'])
        env.registry.clear_cache()
        for user in (cls.portal_a, cls.portal_blank):
            for project in cls.projects:
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})

        # 8 種營造廠層級單據：P、R 各給 A、B 一筆；PA 給 A、PB 給 B
        cls.docs = {}   # (model, company) → recordset
        placements = [(cls.p_shared, cls.co_a), (cls.p_shared, cls.co_b), (cls.p_a, cls.co_a),
                      (cls.p_b, cls.co_b)]
        res_placements = [(cls.r_shared, cls.co_a), (cls.r_shared, cls.co_b)]
        cls._slip_no = 0
        for model in EXPECT_CONTRACTOR_LEVEL:
            is_res = model.startswith('reservation.')
            for project, company in (res_placements if is_res else placements):
                rec = cls._make_doc(model, project, company)
                cls.docs[(model, company)] = cls.docs.get((model, company), env[model]) | rec
        # 明細
        cls.lines = {}
        for model, (parent_field, _path) in EXPECT_LINES.items():
            parent_model = 'daily.log.sheet' if model == 'daily.log.line' else 'payment.estimate'
            for company in (cls.co_a, cls.co_b):
                recs = env[model]
                for parent in cls.docs[(parent_model, company)]:
                    recs |= cls._make_line(model, parent)
                cls.lines[(model, company)] = recs

    # ── 資料工廠 ────────────────────────────────────────────────────────
    @classmethod
    def _project(cls, code, ptype, contractors):
        project = cls.env['project.project'].create({
            'name': f'{code} 公司儀表板測試工程', 'code': code, 'project_type': ptype,
            'state': 'construction', 'company_id': cls.co_s.id, 'contractor_company_ids': contractors})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        return project

    @classmethod
    def _user(cls, login, groups, company, companies, scope=None, extra=None):
        vals = {
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
            'company_id': company.id, 'company_ids': [(6, 0, companies.ids)],
        }
        if scope:
            vals['dash_scope_company_id'] = scope.id
        vals.update(extra or {})
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    @classmethod
    def _slip(cls, project):
        cls._slip_no += 1
        slip = cls.env['reservation.notification.slip'].create({
            'project_id': project.id, 'location': 'DASH 地點', 'slip_no': cls._slip_no})
        slip.sudo().write({'state': 'in_progress'})
        return slip

    @classmethod
    def _doc_vals(cls, model, project):
        """各模型的最少欄位（照既有測試的寫法）。"""
        env = cls.env
        today = fields.Date.today()
        defect = {'record_type': 'supervision', 'check_type': 'construction',
                  'defect_category': 'workmanship', 'defect_description': 'DASH 缺失',
                  'defect_location': 'B1', 'source_type': 'daily_check', 'state': 'notified'}
        if model == 'daily.log.sheet':
            # 同工程同填表人同日會撞唯一，日期錯開
            cls._log_day = getattr(cls, '_log_day', 0) + 1
            return {'supervision_project_id': project.id, 'employee_id': cls.employee.id,
                    'log_date': fields.Date.subtract(today, days=cls._log_day)}
        if model == 'supervision.photo':
            att = env['ir.attachment'].create({
                'name': 'dash.png', 'datas': PNG_B64, 'mimetype': 'image/png', 'public': False,
                'res_model': 'supervision.photo'})
            return {'project_id': project.id, 'attachment_id': att.id}
        if model == 'general.defect.improvement':
            return dict(defect, project_id=project.id)
        if model == 'reservation.defect.improvement':
            return dict(defect, project_id=project.id, slip_id=cls._slip(project).id)
        if model == 'supervision.test.record':
            standard = env['supervision.test.standard'].create({
                'name': 'DASH 抗壓', 'material': '預拌混凝土', 'project_id': project.id})
            return {'project_id': project.id, 'standard_id': standard.id}
        if model == 'general.self.inspection':
            return {'project_id': project.id, 'name': 'DASH-INSP', 'inspection_type_id': cls.itype.id,
                    'sub_project_name': 'DASH', 'inspection_date': today}
        if model == 'reservation.self.inspection':
            return {'slip_id': cls._slip(project).id, 'inspection_type_id': cls.itype.id,
                    'sub_project_name': 'DASH', 'inspection_date': today}
        if model == 'payment.estimate':
            cls._est_day = getattr(cls, '_est_day', 0) + 1
            return {'project_id': project.id, 'estimate_date': fields.Date.subtract(today, days=cls._est_day)}
        raise AssertionError(model)

    @classmethod
    def _make_doc(cls, model, project, company):
        vals = cls._doc_vals(model, project)
        vals['contractor_company_id'] = company.id
        return cls.env[model].create(vals)

    @classmethod
    def _make_line(cls, model, parent):
        task = cls.tasks[parent[EXPECT_CONTRACTOR_LEVEL[parent._name]]]
        if model == 'daily.log.line':
            return cls.env[model].create({
                'sheet_id': parent.id, 'date': parent.log_date, 'entry_type': 'contract',
                'work_item_id': task.id, 'daily_qty': 1.0})
        return cls.env[model].create({
            'estimate_id': parent.id, 'task_id': task.id, 'estimate_qty': 1.0, 'unit_price': 100.0})

    # ── 量測 ────────────────────────────────────────────────────────────
    def _env_of(self, user):
        companies = user.sudo().company_ids
        return self.env(user=user, context={'active_test': False, 'allowed_company_ids': companies.ids})

    def _core_domain(self, user, model, mode='read'):
        """核心原本的規則條件（不套本模組覆寫，_inherits 父模型也用核心值）。"""
        env = self._env_of(user)
        return env['ir.rule'].with_context(**{CORE_PARENT_CTX: CORE_PARENT_TOKEN})._compute_domain(model, mode)

    def _visible_ids(self, user, model, domain=None):
        return set(self._env_of(user)[model].search(domain or []).ids)

    def _other_counts(self, user, exclude):
        """列舉 registry 全部非抽象、非暫存模型（排除 exclude），回傳 (看得到幾筆的, 列舉出錯的)。"""
        nonzero, errors = {}, {}
        for name in sorted(self.env.registry):
            model = self.env[name]
            if model._abstract or model._transient or name in exclude:
                continue
            try:
                count = self._env_of(user)[name].search_count([])
            except AccessError:
                count = 0   # ACL 就擋了：同樣是看不到
            except Exception as e:  # noqa: BLE001 — 列出來，不吞
                errors[name] = repr(e)[:200]
                continue
            if count:
                nonzero[name] = count
        return nonzero, errors

    def _expected_count(self, user, model, definition):
        """sudo 依「核心規則 AND 定義」數的期望筆數。"""
        core = self._core_domain(user, model)
        return self.env[model].sudo().with_context(active_test=False).search_count(
            expression.AND([core, definition]) if core else definition)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestScopeRules(DashScopeCase):

    # ── 營造廠主管 A：白名單筆數＝定義（多、少兩個方向）───────────────────
    def test_manager_contractor_level_exact_ids(self):
        """A 看得到自己在 P、PA、R 的單據（少不得），看不到 B 的（多不得），8 種單據＋2 種明細逐一比 id。"""
        for model in EXPECT_CONTRACTOR_LEVEL:
            own = self.docs[(model, self.co_a)]
            other = self.docs[(model, self.co_b)]
            test_ids = own | other
            seen = self._visible_ids(self.mgr_a, model, [('id', 'in', test_ids.ids)])
            self.assertTrue(own, model)
            self.assertEqual(seen, set(own.ids), f'{model}：A 應恰好看到自己的 {len(own)} 筆')
            self.assertFalse(seen & set(other.ids), f'{model}：A 不可看到 B 的單據')
        for model in EXPECT_LINES:
            own, other = self.lines[(model, self.co_a)], self.lines[(model, self.co_b)]
            seen = self._visible_ids(self.mgr_a, model, [('id', 'in', (own | other).ids)])
            self.assertTrue(own, model)
            self.assertEqual(seen, set(own.ids), f'{model}：明細走父單路徑')

    def test_manager_whitelist_count_equals_definition(self):
        """全庫筆數＝sudo 依「核心規則 AND 合約定義」算的期望值（含真實資料）；期望值必須 > 0（防恆真）。"""
        scope = self.co_a.id
        for model in list(EXPECT_CONTRACTOR_LEVEL) + list(EXPECT_LINES):
            expected = self._expected_count(self.mgr_a, model, contractor_definition(model, scope))
            actual = self._env_of(self.mgr_a)[model].search_count([])
            self.assertGreater(expected, 0, model)
            self.assertEqual(actual, expected, f'{model}：營造廠主管筆數與定義不符')
        for model in EXPECT_PROJECT_LEVEL:
            expected = self._expected_count(self.mgr_a, model, project_definition(model, scope))
            actual = self._env_of(self.mgr_a)[model].search_count([])
            self.assertEqual(actual, expected, f'{model}：營造廠主管筆數與定義不符')
        # 工程本身：P、PA、R 看得到，PB 看不到
        self.assertEqual(self._visible_ids(self.mgr_a, 'project.project', [('id', 'in', self.projects.ids)]),
                         set((self.p_shared | self.p_a | self.r_shared).ids))
        tasks = self.env['project.task'].browse([t.id for t in self.tasks.values()])
        self.assertEqual(self._visible_ids(self.mgr_a, 'project.task', [('id', 'in', tasks.ids)]),
                         set(tasks.filtered(lambda t: t.project_id != self.p_b).ids))

    def test_manager_real_company_counts(self):
        """真實資料：上溢營造（dev 唯一營造廠）的營造廠主管，筆數＝定義；同時記下被核心公司規則擋掉的筆數。"""
        real = self.env['res.company'].search([('company_type', '=', 'contractor'), ('id', 'not in', (
            self.co_a | self.co_b | self.co_c).ids)])
        real = real.filtered(lambda c: c.contracted_project_ids)[:1]
        if not real:
            self.skipTest('這個庫沒有承攬工程的營造廠')
        supervision = real.with_context(active_test=False).contracted_project_ids.company_id
        mgr = self._user('dash_mgr_real', [MANAGER_GROUP], company=supervision[:1],
                         companies=supervision | real, scope=real)
        mgr.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})   # 夾具：營造廠主管要啟用兩步驟驗證才看得到資料（A1'）
        for model in list(EXPECT_CONTRACTOR_LEVEL) + list(EXPECT_LINES):
            definition = contractor_definition(model, real.id)
            expected = self._expected_count(mgr, model, definition)
            actual = self._env_of(mgr)[model].search_count([])
            by_definition = self.env[model].sudo().with_context(active_test=False).search_count(definition)
            _logger.info('真實資料 %s 營造廠主管（%s）：看得到 %d、合約定義 %d（差額＝核心規則擋掉的）',
                         model, real.name, actual, by_definition)
            self.assertEqual(actual, expected, f'{model}：真實資料筆數與定義不符')
        projects = self._env_of(mgr)['project.project'].search_count([])
        self.assertEqual(projects, self.env['project.project'].with_context(active_test=False).search_count(
            [('contractor_company_ids', 'in', real.ids)]), '承攬工程應全部看得到（允許公司已含全部監造公司）')

    def test_revoked_contractor_loses_access(self):
        """工程的營造廠清單拿掉 A：A 在該工程的單據（歸屬欄位仍是 A）立刻看不到，PA 的照常看得到。"""
        self.p_shared.write({'contractor_company_ids': [(3, self.co_a.id)]})
        for model, project_field in EXPECT_CONTRACTOR_LEVEL.items():
            if model.startswith('reservation.'):
                continue    # 預約式在 R，不在 P
            own = self.docs[(model, self.co_a)]
            on_p = own.filtered(lambda r: r[project_field] == self.p_shared)
            self.assertTrue(on_p, model)
            self.assertEqual(on_p.contractor_company_id, self.co_a, model)
            seen = self._visible_ids(self.mgr_a, model, [('id', 'in', own.ids)])
            self.assertEqual(seen, set((own - on_p).ids), f'{model}：撤權的工程看不到、其他照常')
        for model, (parent_field, project_field) in EXPECT_LINES.items():
            own = self.lines[(model, self.co_a)]
            on_p = own.filtered(lambda r: r[parent_field][project_field] == self.p_shared)
            self.assertTrue(on_p, model)
            seen = self._visible_ids(self.mgr_a, model, [('id', 'in', own.ids)])
            self.assertEqual(seen, set((own - on_p).ids), f'{model}：明細跟著父單撤權')

    # ── 前台營造帳號 A：成員規則 AND 範圍 ─────────────────────────────────
    def test_portal_contractor_sees_only_own(self):
        for model in EXPECT_CONTRACTOR_LEVEL:
            own, other = self.docs[(model, self.co_a)], self.docs[(model, self.co_b)]
            seen = self._visible_ids(self.portal_a, model, [('id', 'in', (own | other).ids)])
            self.assertEqual(seen, set(own.ids), f'{model}：前台營造帳號 A 應只看到自己的')
        self.assertEqual(self._visible_ids(self.portal_a, 'project.project', [('id', 'in', self.projects.ids)]),
                         set((self.p_shared | self.p_a | self.r_shared).ids),
                         '前台 A 是四個工程的成員，但只看得到 A 承攬的三個')

    # ── 「其他」類：列舉 registry 全部非抽象、非暫存模型（_other_counts 在 DashScopeCase）─────
    def test_manager_other_models_all_zero(self):
        nonzero, errors = self._other_counts(self.mgr_a, WHITELIST | EXPECT_FRAMEWORK)
        self.assertEqual(errors, {}, '列舉時不可出錯')
        self.assertEqual(nonzero, {}, '營造廠主管在「其他」類的模型必須一筆都看不到')

    def test_optional_module_manager_read_acl(self):
        """合約 §0b-10：本模組沒依賴的模組裡的白名單模型（日誌人機明細在 construction_equipment），
        營造廠主管的 1,0,0,0 讀取 ACL 由安裝／升級時依 registry 建立（CSV 引用不到）；重跑不重複。"""
        model = 'daily.log.man.machine.detail'
        acl = self.env.ref('construction_company_dashboard.access_cm_daily_log_man_machine_detail',
                           raise_if_not_found=False)
        if model not in self.env:
            self.assertFalse(acl, '沒裝那個模組就不建')
            return
        group = self.env.ref(MANAGER_GROUP)
        self.assertTrue(acl, '安裝／升級本模組時要建好')
        self.assertEqual(
            (acl.model_id.model, acl.group_id, acl.perm_read, acl.perm_write, acl.perm_create, acl.perm_unlink),
            (model, group, True, False, False, False))
        self.env['ir.model.access']._dash_sync_optional_manager_access()
        self.assertEqual(self.env['ir.model.access'].search_count(
            [('model_id.model', '=', model), ('group_id', '=', group.id)]), 1, '重跑不重複')
        self.assertTrue(self.env['ir.model.access'].with_user(self.mgr_a).check(model, 'read', raise_exception=False))

    def test_console_reader_non_framework_all_zero(self):
        # 框架以外只剩本人的使用者與聯絡人（合約 §0b-16：登入、啟用兩步驟驗證、建 API key 以本人身分讀自己）
        self_only = {'res.users': 1, 'res.partner': 1}
        nonzero, errors = self._other_counts(self.console, EXPECT_FRAMEWORK)
        self.assertEqual(errors, {}, '列舉時不可出錯')
        self.assertEqual(nonzero, self_only, '控台讀取帳號除框架照舊與本人以外必須一筆都看不到')
        self.assertEqual(self._visible_ids(self.console, 'res.users'), {self.console.id}, '讀得到的那一筆是本人')
        self.assertEqual(self._visible_ids(self.console, 'res.partner'), {self.console.partner_id.id})
        # 就算控台帳號被設了合格的範圍公司（同時算營造方），仍以控台讀取為準：白名單也讀不到
        self.console.sudo().write({'company_ids': [(4, self.co_a.id)], 'dash_scope_company_id': self.co_a.id})
        self.assertTrue(self.console._dash_is_contractor_side())
        nonzero, errors = self._other_counts(self.console, EXPECT_FRAMEWORK)
        self.assertEqual((nonzero, errors), (self_only, {}), '控台讀取帳號有範圍公司也不可讀白名單模型')

    def test_enumeration_is_not_vacuous(self):
        """反證：同樣的列舉對監造方帳號會數到東西（否則上面兩支的 0 可能只是沒跑到）。"""
        nonzero, _errors = self._other_counts(self.sup, WHITELIST | EXPECT_FRAMEWORK)
        self.assertTrue(nonzero, '監造方在「其他」類應看得到資料')

    # ── 拒寫：營造廠主管與控台讀取有寫建刪 ACL 的每個模型 ───────────────
    def _write_acl_models(self, user):
        Access = self.env['ir.model.access'].with_user(user)
        result = []
        for name in sorted(self.env.registry):
            model = self.env[name]
            if model._abstract or model._transient or not model._auto:
                continue
            for op in ('write', 'create', 'unlink'):
                if Access.check(name, op, raise_exception=False):
                    result.append((name, op))
        return result

    def _assert_write_denied(self, user, note):
        pairs = self._write_acl_models(user)
        self.assertTrue(pairs, '應列得出有寫建刪 ACL 的模型（否則下面恆真）')
        allowed, own_message, message_skipped = [], set(), set()
        for name, op in pairs:
            env = self._env_of(user)
            rule_domain = env['ir.rule']._compute_domain(name, op)
            if name in EXPECT_USER_OWNED:
                self.assertNotEqual(rule_domain, DENIED, f'{name} {op}：使用者自有狀態不可被拒')
                allowed.append(name)
                continue
            self.assertEqual(rule_domain, DENIED, f'{name} {op}：規則應拒絕')
            rec_id = self.env[name].sudo().with_context(active_test=False).search([], limit=1).id
            placeholder = not rec_id
            rec_id = rec_id or MISSING_RECORD_ID
            try:
                with self.assertRaises(AccessError, msg=f'{name} {op}') as ctx:
                    env[name].browse(rec_id).check_access(op)
            except MissingError:
                if not placeholder:
                    raise
                # 庫裡沒有這個模型的紀錄（乾淨庫常見）才用不存在的 id。核心組「被拒」訊息時會讀紀錄本身
                # （ir_rule._make_access_error → _get_redirect_suggested_company；例 hr.leave 讀 holiday_status_id），
                # 對不存在的 id 丟 MissingError——那是夾具造出來的情境，真實使用者不會對不存在的紀錄收到訊息。
                # 這種只比「被拒」（_check_access 有回傳＝拒絕，不組訊息），訊息不比；有紀錄的照舊兩樣都比
                self.assertTrue(env[name].browse(rec_id)._check_access(op), f'{name} {op}：應被拒')
                message_skipped.add(name)
                continue
            if note not in str(ctx.exception):
                own_message.add(name)
        if message_skipped:
            _logger.info('拒寫測試（%s）：庫裡沒有紀錄、核心組不出訊息，只比「被拒」的模型：%s',
                         user.login, sorted(message_skipped))
        self.assertTrue(set(allowed) <= EXPECT_USER_OWNED)
        # 訊息沒帶本規則說明的，只能是自己覆寫了 _check_access、先用自己的訊息擋下的模型（例 mail.activity）
        base_check = type(self.env['base'])._check_access
        no_own_check = {n for n in own_message if type(self.env[n])._check_access is base_check}
        self.assertEqual(no_own_check, set(), '被規則擋下的寫入，訊息要說明是公司儀表板範圍規則')

    def test_manager_write_create_unlink_denied(self):
        self._assert_write_denied(self.mgr_a, DENY_NOTE_CONTRACTOR)

    def test_console_write_create_unlink_denied(self):
        self._assert_write_denied(self.console, DENY_NOTE_CONSOLE)

    def test_manager_real_writes_rejected(self):
        """實際寫入：會議紀錄（1111 且沒有規則）、附件、契約工項、標籤都被拒，訊息說明原因。"""
        env = self._env_of(self.mgr_a)
        task = self.tasks[self.p_a]
        with self.assertRaises(AccessError) as ctx:
            env['project.task'].browse(task.id).write({'name': '改掉'})
        self.assertIn(DENY_NOTE_CONTRACTOR, str(ctx.exception))
        with self.assertRaises(AccessError):
            env['ir.attachment'].create({'name': 'x.txt', 'raw': b'x', 'res_model': 'project.project',
                                         'res_id': self.p_a.id})
        with self.assertRaises(AccessError):
            env['project.tags'].create({'name': 'DASH 標籤'})
        if 'construction.meeting.record' in self.env:
            meeting = self.env['construction.meeting.record'].search([], limit=1)
            if meeting:
                with self.assertRaises(AccessError) as ctx:
                    env['construction.meeting.record'].browse(meeting.id).write({'name': '改掉'})
                self.assertIn(DENY_NOTE_CONTRACTOR, str(ctx.exception))
        # 讀得到的營造廠層級單據也不能寫
        log = self.docs[('daily.log.sheet', self.co_a)][:1]
        with self.assertRaises(AccessError):
            env['daily.log.sheet'].browse(log.id).write({'safety_other_matters': '改掉'})

    def test_manager_user_owned_state_still_writable(self):
        """使用者自有狀態照常可寫：篩選、個人設定、對話。"""
        env = self._env_of(self.mgr_a)
        env['ir.filters'].create({'name': 'DASH 篩選', 'model_id': 'project.project', 'user_id': self.mgr_a.id})
        settings = env['res.users.settings']._find_or_create_for_user(self.mgr_a)
        settings.write({'is_discuss_sidebar_category_chat_open': False})
        self.assertFalse(settings.is_discuss_sidebar_category_chat_open)

    def test_manager_login_and_chat_smoke(self):
        """近似「真實登入開一次系統列對話」：選單、上線狀態、自己的聯絡人、開對話發訊息、已讀，都不報錯。"""
        env = self._env_of(self.mgr_a)
        # load_menus 會讀選單圖示檔，dash_a 複本沒有 filestore；改驗可見選單與讀取
        self.assertTrue(env['ir.ui.menu']._visible_menu_ids(False))
        env['ir.ui.menu'].search_read([], ['name', 'action'], limit=50)
        env['res.users'].browse(self.mgr_a.id).read(['name', 'partner_id', 'company_id'])
        env['res.partner'].browse(self.mgr_a.partner_id.id).read(['name'])
        env['bus.presence']._update_presence(inactivity_period=0, identity_field='user_id',
                                            identity_value=self.mgr_a.id)
        channel = env['discuss.channel'].channel_get([self.mgr_a.partner_id.id])
        message = channel.message_post(body='DASH 測試訊息', message_type='comment',
                                       subtype_xmlid='mail.mt_comment')
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == self.mgr_a.partner_id)
        member._mark_as_read(message.id)
        self.assertEqual(message.author_id, self.mgr_a.partner_id)

    # ── 範圍公司空白 → 全拒；改範圍公司 → 同一程序立即生效 ───────────────
    def test_blank_scope_sees_nothing_then_scope_takes_effect(self):
        user = self.portal_blank
        self.assertFalse(user.sudo().dash_scope_company_id)
        self.assertTrue(user._dash_is_contractor_side())
        for model in ('project.project', 'project.task', 'daily.log.sheet', 'supervision.photo',
                      'self.inspection.type'):
            self.assertEqual(self._env_of(user)[model].search_count([]), 0, f'{model}：範圍空白應全拒')
        # 合約 §0b-16（11-05 定案）：範圍不合格仍讀得到「本人」的使用者與聯絡人（登入、偏好設定要用），
        # 別人的一筆都沒有。原本（A1）這兩個模型也斷言 0。
        self.assertEqual(self._visible_ids(user, 'res.users'), {user.id}, 'res.users：只剩本人')
        self.assertEqual(self._visible_ids(user, 'res.partner'), {user.partner_id.id}, 'res.partner：只剩本人')
        user.sudo().write({'dash_scope_company_id': self.co_a.id})
        self.assertEqual(self._visible_ids(user, 'project.project', [('id', 'in', self.projects.ids)]),
                         set((self.p_shared | self.p_a | self.r_shared).ids),
                         '改範圍公司後同一程序應立即生效（規則快取已清）')

    # ── 自主檢查樣板（線 G）─────────────────────────────────────────────
    def test_inspection_templates_global_own_and_used(self):
        """看得到：全域樣板、A 可見工程的樣板、A 可見工程的檢查用到的樣板（樣板屬於別的工程）；
        看不到：只屬於 B 工程、A 的工程也沒在用的樣板。明細（項目、段落、檢查時機、量測區塊）跟著樣板。
        兩個方向都比；「用到的」那條拿掉使用就看不到（證明它真的在作用）。"""
        Type = self.env['self.inspection.type']
        t_pa = Type.create({'name': 'DASH 樣板 PA', 'project_id': self.p_a.id})
        t_pb = Type.create({'name': 'DASH 樣板 PB', 'project_id': self.p_b.id})
        t_used = Type.create({'name': 'DASH 樣板 PB（PA 的檢查在用）', 'project_id': self.p_b.id})
        for t in (self.itype, t_pa, t_pb, t_used):
            self.env['self.inspection.type.item'].create({
                'type_id': t.id, 'name': f'{t.name} 項目', 'stage_id': t.stage_ids[:1].id})
            self.env['self.inspection.type.measure'].create({
                'type_id': t.id, 'name': f'{t.name} 量測', 'template': '丈量___位置'})
        insp = self.env['general.self.inspection'].create(
            dict(self._doc_vals('general.self.inspection', self.p_a), inspection_type_id=t_used.id))
        everything = self.itype | t_pa | t_pb | t_used
        self.assertFalse(self.itype.project_id, '前提：夾具的樣板是全域的')
        cases = (('self.inspection.type', 'id'),) + tuple(
            (m, 'type_id') for m in EXPECT_INSPECTION_TEMPLATE if m != 'self.inspection.type')

        def expect(visible_types):
            for model, field in cases:
                recs = self.env[model].sudo().search([(field, 'in', everything.ids)])
                own = recs.filtered(lambda r: (r if field == 'id' else r[field]) in visible_types)
                self.assertTrue(own and recs - own, f'前提：{model} 兩邊都有資料（防恆真）')
                for user in (self.mgr_a, self.portal_a):
                    seen = self._visible_ids(user, model, [('id', 'in', recs.ids)])
                    self.assertEqual(seen, set(own.ids), f'{user.login} {model}')

        expect(self.itype | t_pa | t_used)
        self.assertEqual(self._env_of(self.portal_blank)['self.inspection.type'].search_count([]), 0, '範圍空白全拒')
        insp.write({'inspection_type_id': t_pa.id})
        expect(self.itype | t_pa)

    def test_company_type_change_takes_effect(self):
        """範圍公司改成不是營造廠 → 同一程序立即全拒（res.company 改 company_type 清快取）。"""
        before = self._visible_ids(self.mgr_a, 'project.project', [('id', 'in', self.projects.ids)])
        self.assertEqual(len(before), 3)
        self.co_a.write({'company_type': 'supervision'})
        self.assertEqual(self._env_of(self.mgr_a)['project.project'].search_count([]), 0)

    def test_scope_change_moves_visibility(self):
        """範圍公司由 A 改 B：看到的單據立刻換成 B 的（不是 A∪B）。"""
        self.mgr_a.sudo().write({'company_ids': [(4, self.co_b.id)], 'dash_scope_company_id': self.co_b.id})
        model = 'general.defect.improvement'
        own_b = self.docs[(model, self.co_b)]
        all_test = own_b | self.docs[(model, self.co_a)]
        self.assertEqual(self._visible_ids(self.mgr_a, model, [('id', 'in', all_test.ids)]), set(own_b.ids))

    # ── 個資收窄 ─────────────────────────────────────────────────────────
    def test_personal_data_narrowed(self):
        env = self._env_of(self.mgr_a)
        users = set(env['res.users'].search([]).ids)
        same_scope = set(self.env['res.users'].with_context(active_test=False).search(
            [('dash_scope_company_id', '=', self.co_a.id)]).ids)
        self.assertTrue(users <= same_scope | {self.mgr_a.id}, '只看得到自己與同範圍公司的帳號')
        self.assertIn(self.mgr_a.id, users)
        self.assertIn(self.portal_a.id, users, '看得到同範圍公司的帳號')
        self.assertNotIn(self.sup.id, users, '看不到監造方帳號')
        partners = set(env['res.partner'].search([]).ids)
        self.assertNotIn(self.sup.partner_id.id, partners, '看不到監造方聯絡人')
        self.assertNotIn(self.co_s.partner_id.id, partners, '看不到監造公司本身的聯絡人')
        self.assertTrue({self.mgr_a.partner_id.id, self.co_a.partner_id.id, self.portal_a.partner_id.id} <= partners)
        emp_a = self.env['hr.employee'].create({'name': 'DASH A 員工', 'company_id': self.co_a.id})
        public = set(env['hr.employee.public'].search([]).ids)
        self.assertIn(emp_a.id, public)
        self.assertNotIn(self.employee.id, public, '看不到監造公司員工')
        self.assertEqual(set(env['hr.employee'].search([]).ids), public, 'hr.employee 轉查 public 也要同一個條件')
        dept_s = self.env['hr.department'].create({'name': 'DASH S 部門', 'company_id': self.co_s.id})
        self.assertNotIn(dept_s.id, env['hr.department'].search([]).ids)

    # ── 範圍公司：建帳號預帶、必填約束、migration 回填（合約 §2）──────────────
    def test_user_scope_prefill_and_constraint(self):
        """範圍公司可空白（空白＝預設拒絕）、有值必須是營造廠；主要公司是營造廠就預帶（合約 §0b-4）。"""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        portal = [(6, 0, [self.env.ref(PORTAL_LEADER).id])]
        # 主要公司是營造廠 → 範圍公司自動帶入
        u = Users.create({'name': 'dash_new_a', 'login': 'dash_new_a', 'groups_id': portal,
                          'company_id': self.co_a.id, 'company_ids': [(6, 0, (self.co_a | self.co_s).ids)],
                          'is_contractor_org': True})
        self.assertEqual(u.sudo().dash_scope_company_id, self.co_a)
        # 主要公司是監造公司的前台帳號（既有程式預設成營造組織）照常建得起來，範圍空白 → 什麼都看不到
        blank = Users.create({'name': 'dash_new_y', 'login': 'dash_new_y', 'groups_id': portal,
                              'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)]})
        self.assertTrue(blank._dash_is_contractor_side())
        self.assertFalse(blank.sudo().dash_scope_company_id)
        self.assertEqual(self._env_of(blank)['project.project'].search_count([]), 0)
        # 後台營造廠主管沒填範圍公司：A1' 的群組約束（合約 §3.1「帶營造廠主管就必須範圍公司合格」）改成建不起來。
        # 原本（A1）是「建得起來、但預設拒絕」；預設拒絕那一半改用「既有帳號範圍被清空」的樣子驗（SQL 清掉）。
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                Users.create({'name': 'dash_new_m', 'login': 'dash_new_m',
                              'groups_id': [(6, 0, [self.env.ref(MANAGER_GROUP).id])],
                              'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)]})
        mgr = self._user('dash_new_m', [MANAGER_GROUP], company=self.co_s, companies=self.co_s, scope=self.co_a)
        mgr.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        self.env.flush_all()
        self.env.cr.execute('UPDATE res_users SET dash_scope_company_id = NULL WHERE id = %s', [mgr.id])
        mgr.invalidate_recordset(['dash_scope_company_id'])
        self.env.registry.clear_cache()
        self.assertEqual(self._env_of(mgr)['project.project'].search_count([]), 0)
        # 範圍公司不是營造廠 → 報錯
        with self.assertRaises(ValidationError) as ctx:
            self.mgr_a.sudo().write({'dash_scope_company_id': self.co_s.id})
        self.assertIn('不是營造廠', str(ctx.exception))

    def test_company_contractor_marker_and_durable_scope(self):
        """主要公司是營造廠、沒有其他標記 → 營造方（§0b-5）；回填後把主要公司改成監造公司仍是營造方。"""
        user = self._user('dash_co_only', ['base.group_user'], company=self.co_a,
                          companies=self.co_a | self.co_s, scope=self.co_a)
        self.env.flush_all()
        self.env.cr.execute('UPDATE res_users SET dash_scope_company_id = NULL WHERE id = %s', [user.id])
        self.env.invalidate_all()
        self.env.registry.clear_cache()
        self.assertFalse(user.is_contractor_org)
        self.assertFalse(self.env.ref(MANAGER_GROUP) in user.groups_id)
        self.assertTrue(user._dash_is_contractor_side(), '主要公司是營造廠就算營造方')
        self.assertFalse(user._is_supervision_side())
        self.assertEqual(self._env_of(user)['project.project'].search_count([]), 0, '範圍空白 → 預設拒絕')
        self._load_migration().migrate(self.env.cr, '18.0.6.2.6')
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(user.sudo().dash_scope_company_id, self.co_a, 'migration 回填主要公司')
        # 使用者自己把主要公司切到監造公司（company_id 在可自改欄位內）
        user.with_user(user).write({'company_id': self.co_s.id})
        self.assertEqual(user.company_id, self.co_s)
        self.assertTrue(user._dash_is_contractor_side(), '回填後範圍公司是耐久標記，改主要公司仍是營造方')
        self.assertEqual(self._visible_ids(user, 'project.project', [('id', 'in', self.projects.ids)]),
                         set((self.p_shared | self.p_a | self.r_shared).ids))

    def test_supervision_account_creation_unaffected(self):
        """監造方建帳號流程不受影響：後台內部帳號、勾監造組織的前台帳號，主要公司是監造公司都照常建立。"""
        Users = self.env['res.users'].with_context(no_reset_password=True)
        internal = Users.create({'name': 'dash_sup_new', 'login': 'dash_sup_new',
                                 'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
                                 'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)]})
        self.assertFalse(internal.sudo().dash_scope_company_id)
        self.assertTrue(internal._is_supervision_side())
        portal_sup = Users.create({'name': 'dash_psup_new', 'login': 'dash_psup_new',
                                   'groups_id': [(6, 0, [self.env.ref(PORTAL_LEADER).id])],
                                   'company_id': self.co_s.id, 'company_ids': [(6, 0, self.co_s.ids)],
                                   'is_supervision_org': True})
        self.assertFalse(portal_sup._dash_is_contractor_side())

    def _load_migration(self):
        path = os.path.join(get_module_path('construction_supervision_base'),
                            'migrations', '18.0.6.3.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('dash_scope_post_migrate', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def test_migration_backfills_only_contractor_company(self):
        """18.0.6.3.0 post-migrate：營造方帳號主要公司是營造廠才回填（含只有主要公司這個標記的），其他留空。"""
        migration = self._load_migration()
        flagged = self._user('dash_mig_a', [PORTAL_LEADER], company=self.co_a, companies=self.co_a | self.co_s,
                             scope=self.co_a, extra={'is_contractor_org': True})
        company_only = self._user('dash_mig_co', ['base.group_user'], company=self.co_a,
                                  companies=self.co_a | self.co_s, scope=self.co_a)
        blank = self._user('dash_mig_s', [PORTAL_LEADER], company=self.co_s, companies=self.co_a | self.co_s,
                           extra={'is_contractor_org': True})
        not_contractor = self._user('dash_mig_sup', ['base.group_user'], company=self.co_s,
                                    companies=self.co_a | self.co_s)
        self.env.flush_all()
        # 模擬升級前：欄位都是空的
        self.env.cr.execute('UPDATE res_users SET dash_scope_company_id = NULL WHERE id IN %s',
                            [tuple((flagged | company_only | blank | not_contractor).ids)])
        self.env.invalidate_all()
        self.env.registry.clear_cache()
        self.assertTrue(blank._dash_is_contractor_side())
        self.assertFalse(not_contractor._dash_is_contractor_side())
        migration.migrate(self.env.cr, '18.0.6.2.6')
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(flagged.sudo().dash_scope_company_id, self.co_a)
        self.assertEqual(company_only.sudo().dash_scope_company_id, self.co_a, '只有主要公司是營造廠也要回填')
        self.assertFalse(blank.sudo().dash_scope_company_id, '營造方但主要公司不是營造廠 → 留空（預設拒絕）')
        self.assertFalse(not_contractor.sudo().dash_scope_company_id, '不是營造方 → 不填')
