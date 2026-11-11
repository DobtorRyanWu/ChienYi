# -*- coding: utf-8 -*-
"""S3-A（2026-11-11）：估驗、變更、進度、損益類 18 個模型的全域公司隔離。

規則放在模型所屬的模組（construction_payment／contract_change／progress／general／supervision_base 的
security/company_rules.xml）；測試放這裡，因為要用 RoleMatrixCase 的兩家監造公司夾具（本模組依賴那五個模組）。

夾具：沿用 RoleMatrixCase（監造公司 S＝這裡的 A；監造公司 S2＝這裡的 B，工程 PS2），補請款、計量驗收＋明細、
非契約工項＋明細、進度表明細、B 的估驗明細、工項分析的「公司空白」列。

受測者（安全斷言一律以帳號的允許公司 company_ids 為準；切換器只選 A 是介面慣例，只當行為測試——red-team F8）：
* 工程後台使用者（group_supervisor_admin）只屬 A：主要受測者，18 個模型裡 17 個有讀取 ACL；它原本帶各模型的「(1=1)」
  群組規則，正是洞最大的那種人。
* 工程後台使用者 A＋B 兩家都屬（allowed_company_ids 全選）：兩家都讀得到。
* 同一人、allowed_company_ids 只選 A：讀不到 B（行為測試）。
* 一般內部帳號只屬 A：只測它有讀取 ACL 的 8 個模型（payment.*、work.acceptance(.line)、project.task.version）。
* 工項分析（report.project.task.user）：工程後台使用者沒有讀取 ACL（核心只給專案 User／Manager），
  另用「工程後台使用者＋專案 Manager」只屬 A 的帳號（Manager 的群組規則是 1=1，隔離出新規則）。
前台帳號不當受測者：前台路由都 sudo，前台營造帳號會先被 rule_scope 擋（skeptic F3）。

期望值：每筆紀錄掛哪個工程記在 iso_meta，工程屬哪家公司由夾具的建法獨立寫出（_fixture_company，L3）；
不 import 實作的常數（規則 xmlid 表在這裡獨立寫一份，照 test_scope_rules.py 的寫法）——唯一的例外是寫後檢查的欄位表
COMPANY_RULE_FIELDS：它是被測物，鎖定測試拿它跟「從資料庫規則推出來的表」比（期望值來自規則本身，不來自實作）。
每一個「讀不到 B」都先證明它本來讀得到（M-B）：同一支測試裡把那條規則 active=False → 讀得到 B → 恢復 → 讀不到 B
——這同時是 18 條規則的 mutation（不另走 harness）。

寫入面（S3 fix1，實作 construction_supervision_base/models/company_rule_write_guard.py）：核心 write 只在寫入前用舊值
檢查規則，所以另驗「改掛到別家公司的工程／父單會被拒、資料沒變」「有工程的估驗／變更單（明細）不能變成沒有工程」，
以及正當流程（匯入工程案件、契約變更精靈、同公司內改掛、sudo）照常。
S3 fix2：寫後檢查的欄位表以 test_write_guard_table_matches_rules 鎖住（從資料庫規則推、兩個方向比；表上每一格都要有
REPARENT_CELLS 的一格行為測試）；related 欄位（company_id 等）非 sudo 不能直接寫，連同屬兩家公司的帳號也一樣。
"""
from contextlib import closing

from odoo import fields
from odoo.addons.construction_supervision_base.models.company_rule_write_guard import COMPANY_RULE_FIELDS
from odoo.exceptions import AccessError, UserError
from odoo.models import LOG_ACCESS_COLUMNS
from odoo.osv import expression
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .test_role_accounts import RoleMatrixCase
from .test_scope_rules import SUPERVISOR_ADMIN

MODULE = 'construction_company_dashboard'
# 模型 → 本規格新增的全域規則 xmlid（測試獨立寫一份；L2⑨：資料庫裡的集合要與它兩個方向都相等）
EXPECT_COMPANY_MODELS = {
    'payment.claim': 'construction_payment.rule_company_global_payment_claim',
    'payment.estimate': 'construction_payment.rule_company_global_payment_estimate',
    'payment.estimate.line': 'construction_payment.rule_company_global_payment_estimate_line',
    'payment.estimate.extra.item': 'construction_payment.rule_company_global_payment_estimate_extra_item',
    'payment.estimate.extra.line': 'construction_payment.rule_company_global_payment_estimate_extra_line',
    'work.acceptance': 'construction_payment.rule_company_global_work_acceptance',
    'work.acceptance.line': 'construction_payment.rule_company_global_work_acceptance_line',
    'contract.change.order': 'construction_contract_change.rule_company_global_contract_change_order',
    'contract.change.order.line': 'construction_contract_change.rule_company_global_contract_change_order_line',
    'progress.schedule': 'construction_progress.rule_company_global_progress_schedule',
    'progress.schedule.line': 'construction_progress.rule_company_global_progress_schedule_line',
    'general.progress.report': 'construction_general.rule_company_global_general_progress_report',
    'general.progress.report.line': 'construction_general.rule_company_global_general_progress_report_line',
    'general.realtime.profit': 'construction_general.rule_company_global_general_realtime_profit',
    'general.realtime.profit.cost': 'construction_general.rule_company_global_general_realtime_profit_cost',
    'profit.loss.entry': 'construction_general.rule_company_global_profit_loss_entry',
    'project.task.version': 'construction_supervision_base.rule_company_global_project_task_version',
    'report.project.task.user': 'construction_supervision_base.rule_company_global_report_project_task_user',
}
# 本規格新增規則的 xmlid 前綴與所在模組（盤點用）
RULE_XMLID_PREFIX = 'rule_company_global_'
RULE_MODULES = ('construction_payment', 'construction_contract_change', 'construction_progress',
                'construction_general', 'construction_supervision_base')
# 一般內部帳號（只有 base.group_user）有讀取 ACL 的模型（dev ir_model_access 查得；其餘只給工程後台使用者等群組）
INTERNAL_USER_MODELS = frozenset({
    'payment.claim', 'payment.estimate', 'payment.estimate.line', 'payment.estimate.extra.item',
    'payment.estimate.extra.line', 'work.acceptance', 'work.acceptance.line', 'project.task.version',
})
# 工程後台使用者沒有讀取 ACL 的模型（核心 project 只給 Project User／Manager）
PROJECT_USER_ONLY_MODELS = frozenset({'report.project.task.user'})
# 核心 SQL 檢視（_auto=False，寫不了）：不在寫後檢查的欄位表上
SQL_VIEW_MODELS = frozenset({'report.project.task.user'})
PROJECT_MANAGER = 'project.group_project_manager'
# 寫入面：A 的紀錄改掛到 B 的哪一種目標（模型名＝B 的那一種父單）。S3 fix1 的 8 格（skeptic F1 的 6 個欄位＋估驗／變更單的
# 工程）；S3 fix2 補成「規則用得到的每一個欄位一格」（第二輪 skeptic F1：表上一半的欄位沒有行為測試）——
# test_write_guard_table_matches_rules 驗這張表的 (模型, 欄位) ＝ 從資料庫規則推出來的，兩個方向都比
TARGET_PROJECT = 'project'
TARGET_TASK = 'task'
TARGET_COMPANY = 'company'
REPARENT_CELLS = (
    ('payment.claim', 'project_id', TARGET_PROJECT),
    ('work.acceptance', 'project_id', TARGET_PROJECT),
    ('work.acceptance.line', 'acceptance_id', 'work.acceptance'),
    ('payment.estimate.extra.item', 'project_id', TARGET_PROJECT),
    ('general.progress.report.line', 'report_id', 'general.progress.report'),
    ('project.task.version', 'task_id', TARGET_TASK),
    ('payment.estimate', 'project_id', TARGET_PROJECT),
    ('contract.change.order', 'project_id', TARGET_PROJECT),
    # S3 fix2
    ('payment.estimate.line', 'estimate_id', 'payment.estimate'),
    ('payment.estimate.extra.line', 'estimate_id', 'payment.estimate'),
    ('payment.estimate.extra.line', 'project_id', TARGET_PROJECT),
    ('contract.change.order', 'company_id', TARGET_COMPANY),
    ('contract.change.order.line', 'change_order_id', 'contract.change.order'),
    ('contract.change.order.line', 'company_id', TARGET_COMPANY),
    ('progress.schedule', 'project_id', TARGET_PROJECT),
    ('progress.schedule', 'company_id', TARGET_COMPANY),
    ('progress.schedule.line', 'schedule_id', 'progress.schedule'),
    ('progress.schedule.line', 'company_id', TARGET_COMPANY),
    ('general.progress.report', 'project_id', TARGET_PROJECT),
    ('general.progress.report', 'company_id', TARGET_COMPANY),
    ('general.realtime.profit', 'project_id', TARGET_PROJECT),
    ('general.realtime.profit', 'company_id', TARGET_COMPANY),
    ('general.realtime.profit.cost', 'profit_id', 'general.realtime.profit'),
    ('profit.loss.entry', 'project_id', TARGET_PROJECT),
    ('profit.loss.entry', 'company_id', TARGET_COMPANY),
)
# related 欄位（company_id＝工程的公司、非契約工項明細的 project_id＝估驗的工程）非 sudo 不能直接寫：訊息片段（測試獨立寫出）
# 與格數（上游說有幾格就要有幾格，M-C）
RELATED_FIELD_HINT = '不能直接改'
RELATED_CELL_COUNT = 8
# 正當流程：同公司內改掛工程照常的模型（S3 fix1 那 5 格）
SAME_COMPANY_REPARENT_MODELS = frozenset({
    'payment.claim', 'work.acceptance', 'payment.estimate.extra.item', 'payment.estimate', 'contract.change.order'})
# 規則對工程空白放行建立者的兩種單（清空工程要被擋）
BLANK_FALLBACK_MODELS = ('payment.estimate', 'contract.change.order')
# 「有工程的單不能變成沒有工程」的訊息片段（測試獨立寫出）。只比例外型別不夠：核心 AccessError 是 UserError 的子類別，
# 拿掉這道檢查時寫後檢查的 AccessError 照樣讓 assertRaises(UserError) 綠（S3 fix1 mutation W2 第一輪實測，L2⑮ 第二形狀）
LOST_PROJECT_HINT = '不能改成沒有工程'
LUMP_ADJUST_AMOUNT = 1000.0
# 夾具數量
CLAIM_AMOUNT = 1000.0
ACCEPT_QTY = 1.0
SCHEDULE_DAYS = 6


@tagged('post_install', '-at_install', MODULE)
class TestCompanyIsolation(RoleMatrixCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        today = fields.Date.today()
        cls.co_iso_a, cls.co_iso_b = cls.co_s, cls.co_s2
        cls.p_iso_a, cls.p_iso_b = cls.p_a, cls.p_s2
        # 受測者
        sa = ['base.group_user', SUPERVISOR_ADMIN]
        cls.sa_a = cls._user('s3_sa_a', sa, company=cls.co_s, companies=cls.co_s)
        cls.sa_a2 = cls._user('s3_sa_a2', sa, company=cls.co_s, companies=cls.co_s)
        cls.sa_ab = cls._user('s3_sa_ab', sa, company=cls.co_s, companies=cls.co_s | cls.co_s2)
        cls.int_a = cls._user('s3_int_a', ['base.group_user'], company=cls.co_s, companies=cls.co_s)
        cls.rpt_a = cls._user('s3_rpt_a', sa + [PROJECT_MANAGER], company=cls.co_s, companies=cls.co_s)

        # 紀錄 → 工程（模型 → {id: 工程}）：從 RoleMatrixCase 的 meta 取 18 個模型裡有的，再補沒有的
        cls.iso_meta = {model: {} for model in EXPECT_COMPANY_MODELS}
        for model in EXPECT_COMPANY_MODELS:
            for rid, (project, _contractor) in cls.meta.get(model, {}).items():
                if project:
                    cls.iso_meta[model][rid] = project

        def note(records, project):
            for record in records:
                cls.iso_meta[record._name][record.id] = project

        for project, company in ((cls.p_iso_a, cls.co_iso_a), (cls.p_iso_b, cls.co_iso_b)):
            task = cls.tasks[project]
            estimate = cls.estimates.filtered(lambda e, p=project: e.project_id == p)[:1]
            assert estimate, f'夾具：{project.code} 應有估驗'
            note(env['payment.claim'].create({
                'project_id': project.id, 'company_id': company.id, 'claim_amount': CLAIM_AMOUNT}), project)
            acceptance = env['work.acceptance'].create({'project_id': project.id, 'contractor_company_id': cls.co_a.id})
            note(acceptance, project)
            note(env['work.acceptance.line'].create({
                'acceptance_id': acceptance.id, 'task_id': task.id,
                'completed_qty': ACCEPT_QTY, 'accepted_qty': ACCEPT_QTY}), project)
            item = env['payment.estimate.extra.item'].create({
                'project_id': project.id, 'code': f'S3X-{project.code}', 'name': 'S3 非契約工項'})
            note(item, project)
            note(env['payment.estimate.extra.line'].create({
                'estimate_id': estimate.id, 'extra_item_id': item.id, 'name': 'S3 非契約工項明細'}), project)
            schedule = project.with_context(active_test=False).schedule_ids[:1]
            assert schedule, f'夾具：{project.code} 應有進度表'
            note(env['progress.schedule.line'].with_context(allow_line_on_active_schedule=True).create({
                'schedule_id': schedule.id, 'sequence': 1, 'date_start': today,
                'date_end': fields.Date.add(today, days=SCHEDULE_DAYS), 'planned_progress': 0.0}), project)
            if not env['payment.estimate.line'].search_count([('estimate_id', '=', estimate.id)]):
                note(cls._make_line('payment.estimate.line', estimate), project)
            note(env['project.task.version'].search([('task_id', '=', task.id)]), project)
        # 工項分析（SQL 檢視，id＝工項 id）：A 用 PA 的工項（公司照常）；B 另建一個 PS2 的工項、用 SQL 把公司清空
        # ——dev 那 2924 列就是這個樣子（核心規則 91 放行公司空白），公司照常的 B 列會先被 91 擋（M-B）
        cls.task_b_blank = env['project.task'].create({'name': 'S3 公司空白工項', 'project_id': cls.p_iso_b.id})
        env.cr.execute('UPDATE project_task SET company_id = NULL WHERE id = %s', [cls.task_b_blank.id])
        cls.task_b_blank.invalidate_recordset(['company_id'])
        cls.iso_meta['report.project.task.user'] = {
            cls.tasks[cls.p_iso_a].id: cls.p_iso_a, cls.task_b_blank.id: cls.p_iso_b}
        env.flush_all()
        env.registry.clear_cache()

    # ── 期望值（夾具獨立寫出）──────────────────────────────────────────
    def _fixture_company(self, project):
        """夾具的工程屬哪家公司：DashScopeCase._project 與 RoleMatrixCase 都建在 S，只有 PS2 建在 S2。"""
        self.assertIn(project, self.all_projects, f'不認得的夾具工程 {project.code}')
        return self.co_s2 if project == self.p_s2 else self.co_s

    def _ids_of(self, model, company):
        return {rid for rid, project in self.iso_meta[model].items() if self._fixture_company(project) == company}

    def _seen(self, user, model, companies=None):
        companies = companies or user.sudo().company_ids
        env = self.env(user=user, context={'active_test': False, 'allowed_company_ids': companies.ids})
        return set(env[model].search([('id', 'in', list(self.iso_meta[model]))]).ids)

    def _subjects(self):
        """(標籤, 帳號, 選取的公司, 模型) × 期望看得到的公司。"""
        both = self.co_iso_a | self.co_iso_b
        sa_models = sorted(set(EXPECT_COMPANY_MODELS) - PROJECT_USER_ONLY_MODELS)
        return [
            ('工程後台使用者只屬 A', self.sa_a, self.co_iso_a, sa_models, self.co_iso_a),
            ('工程後台使用者 A＋B 全選', self.sa_ab, both, sa_models, both),
            ('工程後台使用者 A＋B 只選 A（行為測試）', self.sa_ab, self.co_iso_a, sa_models, self.co_iso_a),
            ('一般內部帳號只屬 A', self.int_a, self.co_iso_a, sorted(INTERNAL_USER_MODELS), self.co_iso_a),
            ('工程後台使用者＋專案 Manager 只屬 A', self.rpt_a, self.co_iso_a, sorted(EXPECT_COMPANY_MODELS), self.co_iso_a),
        ]

    # ── 1. 表驅動：看得到的 id 兩個方向都比 ─────────────────────────────
    def test_isolation_table(self):
        checked = 0
        for label, user, selected, models, visible_companies in self._subjects():
            for model in models:
                with self.subTest(subject=label, model=model):
                    own, other = self._ids_of(model, self.co_iso_a), self._ids_of(model, self.co_iso_b)
                    self.assertTrue(own and other, f'{model}：夾具兩家公司都要有紀錄（否則恆真）')
                    expected = set().union(*(self._ids_of(model, c) for c in visible_companies))
                    seen = self._seen(user, model, selected)
                    self.assertTrue(own <= seen, f'{label} × {model}：自己公司的紀錄要讀得到（排除 ACL 先擋），少了 {sorted(own - seen)}')
                    self.assertEqual(seen, expected, f'{label} × {model}：多 {sorted(seen - expected)}、少 {sorted(expected - seen)}')
                    checked += 1
        self.assertGreaterEqual(checked, len(EXPECT_COMPANY_MODELS), '表驅動檢查的組數過少')

    # ── 2. 每條規則：關掉 → 讀得到 B；打開 → 讀不到 B（M-B；18 條規則的 mutation）─────────
    def test_each_rule_is_what_hides_other_company(self):
        Rule = self.env['ir.rule'].sudo()
        for model, xmlid in EXPECT_COMPANY_MODELS.items():
            user = self.rpt_a if model in PROJECT_USER_ONLY_MODELS else self.sa_a
            with self.subTest(model=model):
                rule = self.env.ref(xmlid, raise_if_not_found=False)
                self.assertTrue(rule, f'{model}：找不到規則 {xmlid}')
                own, other = self._ids_of(model, self.co_iso_a), self._ids_of(model, self.co_iso_b)
                self.assertTrue(own and other, model)
                seen = self._seen(user, model)
                self.assertTrue(own <= seen, f'{model}：規則開著時自己公司的要讀得到')
                self.assertFalse(seen & other, f'{model}：規則開著時讀不到 B')
                Rule.browse(rule.id).write({'active': False})
                self.env.registry.clear_cache()
                try:
                    seen_off = self._seen(user, model)
                    self.assertTrue(other <= seen_off, f'{model}：關掉這條規則後 B 應讀得到（證明擋 B 的是這條，不是別道防線）')
                finally:
                    Rule.browse(rule.id).write({'active': True})
                    self.env.registry.clear_cache()
                self.assertFalse(self._seen(user, model) & other, f'{model}：規則恢復後又讀不到 B')

    # ── 3. 盤點：資料庫裡本規格新增的全域規則 ＝ 表（兩個方向都比，L2⑨）──────────
    def test_rule_inventory_matches_table(self):
        data = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'ir.rule'), ('module', 'in', list(RULE_MODULES)),
            ('name', '=like', RULE_XMLID_PREFIX + '%')])
        self.assertTrue(data, '一條都找不到（前綴或模組寫錯時這裡要紅，不是恆真）')
        found = {f'{d.module}.{d.name}' for d in data}
        self.assertEqual(found, set(EXPECT_COMPANY_MODELS.values()),
                         f'多 {sorted(found - set(EXPECT_COMPANY_MODELS.values()))}、'
                         f'少 {sorted(set(EXPECT_COMPANY_MODELS.values()) - found)}')
        rules = self.env['ir.rule'].sudo().with_context(active_test=False).browse(data.mapped('res_id'))
        self.assertEqual(sorted(rules.mapped('model_id.model')), sorted(EXPECT_COMPANY_MODELS),
                         '規則掛的模型集合要等於表（每個模型恰好一條）')
        for xmlid_model, xmlid in EXPECT_COMPANY_MODELS.items():
            rule = self.env.ref(xmlid)
            with self.subTest(model=xmlid_model):
                self.assertEqual(rule.model_id.model, xmlid_model)
                self.assertTrue(rule.active and rule['global'] and not rule.groups, f'{xmlid}：要啟用、全域、不掛群組')
                self.assertTrue(rule.perm_read and rule.perm_write and rule.perm_create and rule.perm_unlink,
                                f'{xmlid}：讀寫建刪都要套')
                self.assertIn('company_ids', rule.domain_force, xmlid)

    # ── 3b. 寫後檢查的欄位表＝從資料庫規則推出來的表（兩個方向都比；S3 fix2，第二輪 simplifier medium／skeptic F1）──
    def _rule_fields(self):
        """{模型: 規則用得到、寫得進去的欄位}，從資料庫裡的規則推：domain 每個 leaf 路徑的第一段，扣掉 LOG_ACCESS_COLUMNS
        （核心 write 會把它們拿掉，寫不進去），stored related 欄位再展開到它的來源欄位（related 的 readonly 只是畫面屬性，
        ORM write 寫得進去；改來源也會讓它跟著變）。SQL 檢視（_auto=False）寫不了，跳過。"""
        context = dict(self.env['ir.rule']._eval_context(), company_ids=[])
        derived = {}
        for model, xmlid in EXPECT_COMPANY_MODELS.items():
            Model = self.env[model]
            if not Model._auto:
                continue
            todo = [leaf[0].split('.', 1)[0]
                    for leaf in safe_eval(self.env.ref(xmlid).domain_force, context) if expression.is_leaf(leaf)]
            names = derived.setdefault(model, set())
            while todo:
                name = todo.pop()
                if name in LOG_ACCESS_COLUMNS or name in names:
                    continue
                names.add(name)
                field = Model._fields[name]
                if field.related and field.store:
                    todo.append(field.related.split('.', 1)[0])
        return derived

    def test_write_guard_table_matches_rules(self):
        """COMPANY_RULE_FIELDS 是規則 domain 的第二份：少一列（或一個欄位）寫入洞就悄悄打開，多一列只是多查。
        這裡把它鎖在資料庫的規則上；另外要求每一個 (模型, 欄位) 都有一格行為測試（REPARENT_CELLS）。"""
        derived = self._rule_fields()
        self.assertEqual(set(derived), set(EXPECT_COMPANY_MODELS) - SQL_VIEW_MODELS,
                         '推得出欄位的模型要是 18 個減 SQL 檢視（_auto 判斷壞掉時這裡要紅，不是兩邊都空而恆真）')
        table = {model: set(names) for model, names in COMPANY_RULE_FIELDS.items()}
        self.assertEqual(set(table), set(derived),
                         f'表上多 {sorted(set(table) - set(derived))}、少 {sorted(set(derived) - set(table))}')
        for model in sorted(derived):
            with self.subTest(model=model):
                self.assertTrue(derived[model], f'{model}：規則推不出任何欄位')
                self.assertEqual(table[model], derived[model],
                                 f'{model}：表上多 {sorted(table[model] - derived[model])}、少 {sorted(derived[model] - table[model])}')
        pairs = {(model, name) for model, names in derived.items() for name in names}
        cells = {(model, field) for model, field, _kind in REPARENT_CELLS}
        self.assertEqual(len(cells), len(REPARENT_CELLS), 'REPARENT_CELLS 有重複的格')
        self.assertEqual(cells, pairs, f'行為測試多 {sorted(cells - pairs)}、少 {sorted(pairs - cells)}')

    # ── 4. 工程空白的草稿（#2 估驗、#8 變更單、#9 變更明細）：本人存得進、讀得回；別人讀不到 ──
    def _make_blank_drafts(self, user):
        """以 user 本人身分（非 sudo）走畫面上的正當入口：先存工程空白的估驗、變更單，再在空工程變更單上加一筆明細。"""
        env = self.env(user=user, context={'allowed_company_ids': user.company_ids.ids})
        estimate = env['payment.estimate'].create({'estimate_date': fields.Date.today()})
        order = env['contract.change.order'].create({})
        line = env['contract.change.order.line'].create({'change_order_id': order.id, 'item_name': 'S3 空工程明細'})
        env.flush_all()
        return estimate, order, line

    def test_blank_project_draft_creator_can_save_and_read(self):
        estimate, order, line = self._make_blank_drafts(self.sa_a)
        self.assertFalse(estimate.sudo().project_id or order.sudo().project_id, '夾具：工程要是空白')
        for record in (estimate, order, line):
            with self.subTest(model=record._name):
                env = self.env(user=self.sa_a, context={'allowed_company_ids': self.sa_a.company_ids.ids})
                self.assertEqual(env[record._name].search([('id', '=', record.id)]).ids, record.ids,
                                 f'{record._name}：建立者要搜得到自己剛存的草稿')
                env[record._name].browse(record.id).read(['display_name'])
                env[record._name].browse(record.id).check_access('write')

    def test_blank_project_draft_hidden_from_others(self):
        estimate, order, line = self._make_blank_drafts(self.sa_a)
        for other in (self.sa_a2, self.sa_ab):
            env = self.env(user=other, context={'allowed_company_ids': other.company_ids.ids})
            for record in (estimate, order, line):
                with self.subTest(user=other.login, model=record._name):
                    self.assertFalse(env[record._name].search([('id', '=', record.id)]),
                                     f'{record._name}：別人（同公司的工程後台使用者也一樣）搜不到工程空白的草稿')
                    with self.assertRaises(AccessError):
                        env[record._name].browse(record.id).read(['display_name'])

    # ── 5. 寫入面（S3 fix1）：改掛到別家公司 → 被拒、資料沒變 ─────────────────
    def _env_of(self, user):
        return self.env(user=user, context={'allowed_company_ids': user.company_ids.ids})

    def _iso_one(self, model, project):
        """夾具裡掛在 project 的一筆（id 最小的，固定）。"""
        ids = [rid for rid, owner in self.iso_meta[model].items() if owner == project]
        self.assertTrue(ids, f'夾具：{model} 在 {project.code} 沒有紀錄')
        return self.env[model].browse(min(ids))

    def _target(self, kind, project):
        if kind == TARGET_PROJECT:
            return project
        if kind == TARGET_TASK:
            return self.tasks[project]
        if kind == TARGET_COMPANY:
            return self._fixture_company(project)
        return self._iso_one(kind, project)

    def _is_related(self, model, field):
        """欄位是不是 stored related（看模型的欄位定義，不看寫入面實作）。"""
        return bool(self.env[model]._fields[field].related)

    def _assert_unchanged(self, record, field, before):
        record.invalidate_recordset()
        self.assertEqual(record.sudo()[field], before, f'{record._name}.{field}：被拒之後資料不可以變')

    def test_reparent_to_other_company_refused(self):
        """只屬 A 的工程後台使用者把 A 的紀錄改掛到 B（每一個規則欄位一格）→ 被拒、資料沒變。

        每一格在自己的、一定回滾的 savepoint 裡跑：沒擋住時那一格寫進去的改動不會連累下一格。
        期望：related 欄位（8 格）→ UserError「不能直接改」（寫入前就拒）；其餘 17 格 → AccessError。
        擋下的不一定是寫後檢查：25 格裡只有 5 格（請款、計量驗收、非契約工項的工程，進度報告明細的報告，工項版本的工項）
        只靠它——拿掉寫後檢查（mutation W1）時正是這 5 格紅。另外 11 格的欄位由 relational_input_guard 守
        （呼叫端給的 id 自己要讀得到，B 的工程／父單讀不到），related 的 8 格由「不能直接改」擋；
        work.acceptance.line 那一格另有附帶的擋：work_acceptance.py 的 write 覆寫寫完後以本人身分算超約
        （_is_over_contract 讀新父單）→ 讀不到 B 的驗收就 AccessError——那是附帶效果、不是設計好的防線。
        拿掉表上任一列時，那一列至少有一格會紅（只有 relational_input_guard 守的欄位除外，那幾格靠鎖定測試）。
        """
        env = self._env_of(self.sa_a)
        for model, field, kind in REPARENT_CELLS:
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                before = record.sudo()[field]
                target = self._target(kind, self.p_iso_b)
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                if model == 'project.task.version':
                    # 版本號要避開目標工項已有的（唯一鍵 task_id＋version）：沒擋住時寫入要真的成功，紅的才是這道檢查
                    record.sudo().write({'version': max(target.sudo().version_ids.mapped('version') or [0]) + 1})
                # 寫前檢查過得了：被拒不是因為本來就不能寫這筆（M-B）
                env[model].browse(record.id).check_access('write')
                if self._is_related(model, field):
                    with self.assertRaises(UserError, msg=f'{model}.{field} 直接改成 B 要被拒') as ctx:
                        env[model].browse(record.id).write({field: target.id})
                        env.flush_all()
                    self.assertIn(RELATED_FIELD_HINT, str(ctx.exception), '擋下它的要是「related 不能直接改」')
                else:
                    with self.assertRaises(AccessError, msg=f'{model}.{field} 改掛到 B 要被拒'):
                        env[model].browse(record.id).write({field: target.id})
                        env.flush_all()
                self._assert_unchanged(record, field, before)

    def test_related_field_not_writable_even_for_two_company_user(self):
        """同屬 A＋B 的帳號把 A 工程單據的 related 欄位直接改成 B → UserError、資料沒變（第二輪 skeptic F2）。

        寫後檢查擋不到這種人：B 也在他的允許公司裡。沒擋時值就和工程脫鉤——只屬 A 的同事看不到、只屬 B 的人看得到。
        """
        env = self.env(user=self.sa_ab, context={'allowed_company_ids': (self.co_iso_a | self.co_iso_b).ids})
        checked = 0
        for model, field, kind in REPARENT_CELLS:
            if not self._is_related(model, field):
                continue
            with self.subTest(model=model, field=field), closing(self.env.cr.savepoint()):
                record = self._iso_one(model, self.p_iso_a)
                before = record.sudo()[field]
                target = self._target(kind, self.p_iso_b)
                self.assertNotEqual(before, target, '夾具：目標要是另一筆')
                env[model].browse(record.id).check_access('write')
                with self.assertRaises(UserError, msg=f'{model}.{field}：兩家都屬的帳號直接改成 B 也要被拒') as ctx:
                    env[model].browse(record.id).write({field: target.id})
                    env.flush_all()
                self.assertIn(RELATED_FIELD_HINT, str(ctx.exception), '擋下它的要是「related 不能直接改」')
                self._assert_unchanged(record, field, before)
                checked += 1
        self.assertEqual(checked, RELATED_CELL_COUNT, 'related 欄位的格數不對（欄位定義或表改了要回頭看）')

    # ── 6. 有工程的單不能變成沒有工程（估驗、變更單、變更明細的工程空白退路）──────
    def test_blank_project_cannot_be_reached_by_clearing_others(self):
        """同公司有寫入權的人清空別人的估驗／變更單的工程 → 被拒（red-team F1：改了就只剩建立者看得到）。"""
        env = self._env_of(self.sa_a)
        for model in BLANK_FALLBACK_MODELS:
            with self.subTest(model=model):
                record = self._iso_one(model, self.p_iso_a)
                self.assertNotEqual(record.sudo().create_uid, self.sa_a, '夾具：要是別人建的')
                env[model].browse(record.id).check_access('write')
                with self.assertRaises(UserError) as ctx:
                    env[model].browse(record.id).write({'project_id': False})
                self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
                self._assert_unchanged(record, 'project_id', self.p_iso_a)

    def test_blank_project_cannot_be_reached_by_clearing_own(self):
        """建立者清空自己的估驗／變更單的工程 → 也被拒（清了同事就看不到）。"""
        env = self._env_of(self.sa_a)
        today = fields.Date.today()
        own = {
            'payment.estimate': env['payment.estimate'].create({'estimate_date': today, 'project_id': self.p_iso_a.id}),
            'contract.change.order': env['contract.change.order'].create({'project_id': self.p_iso_a.id}),
        }
        for model, record in own.items():
            with self.subTest(model=model):
                self.assertEqual(record.sudo().create_uid, self.sa_a, '夾具：要是本人建的')
                with self.assertRaises(UserError) as ctx:
                    record.write({'project_id': False})
                self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
                self._assert_unchanged(record, 'project_id', self.p_iso_a)

    def test_line_cannot_move_to_own_blank_order(self):
        """有工程的變更明細改掛到自己建的空工程變更單 → 被拒（明細規則的建立者退路會放行它，但同事就看不到了）。"""
        env = self._env_of(self.sa_a)
        line = self._iso_one('contract.change.order.line', self.p_iso_a)
        before = line.sudo().change_order_id
        blank = env['contract.change.order'].create({})
        self.assertFalse(blank.project_id, '夾具：空工程變更單')
        env['contract.change.order.line'].browse(line.id).check_access('write')
        with self.assertRaises(UserError) as ctx:
            env['contract.change.order.line'].browse(line.id).write({'change_order_id': blank.id})
        self.assertIn(LOST_PROJECT_HINT, str(ctx.exception), '擋下它的要是「不能變成沒有工程」，不是別道檢查')
        self._assert_unchanged(line, 'change_order_id', before)

    # ── 7. 正當流程照常（W-3 grep 找到的兩個精靈、同公司內改掛、sudo）──────────
    def test_legit_import_wizard_sets_project_on_blank_estimate(self):
        """「匯入工程案件」：本人先存工程空白的估驗，精靈替它設工程並帶入明細。"""
        env = self._env_of(self.sa_a)
        today = fields.Date.today()
        estimate = env['payment.estimate'].create({'estimate_date': today})
        wizard = env['estimate.import.wizard'].create({
            'estimate_id': estimate.id, 'project_id': self.p_iso_a.id, 'estimate_date': today})
        wizard._load_tasks_from_project()
        self.assertTrue(wizard.line_ids, '夾具：工程要有契約工項可匯入')
        wizard.action_import()
        estimate.invalidate_recordset()
        self.assertEqual(estimate.project_id, self.p_iso_a)
        self.assertTrue(estimate.line_ids, '明細要帶進來')
        env['payment.estimate'].browse(estimate.id).check_access('write')

    def test_legit_change_wizard_sets_project_on_blank_order(self):
        """契約變更精靈：本人先存工程空白的變更單，精靈替它設工程（只調發包工程費、不動工項）。"""
        env = self._env_of(self.sa_a)
        order = env['contract.change.order'].create({})
        wizard = env['contract.change.wizard'].create({
            'change_order_id': order.id, 'project_id': self.p_iso_a.id, 'lump_adjust_amount': LUMP_ADJUST_AMOUNT})
        wizard.action_confirm()
        order.invalidate_recordset()
        self.assertEqual(order.project_id, self.p_iso_a)

    def test_legit_reparent_within_company_and_sudo(self):
        """同公司內改掛照常；sudo（系統內部流程）改掛到別家、清空工程也照常。"""
        env = self._env_of(self.sa_a)
        same_company = self.p_b
        self.assertEqual(self._fixture_company(same_company), self.co_iso_a, '夾具：同公司的另一個工程')
        for model, field, kind in REPARENT_CELLS:
            # S3 fix1 的 5 格（fix2 補的格不在這裡：related 欄位本來就不能直接寫，其餘另有唯一鍵等與本題無關的條件）
            if kind != TARGET_PROJECT or model not in SAME_COMPANY_REPARENT_MODELS:
                continue
            with self.subTest(model=model, mode='同公司'):
                record = self._iso_one(model, self.p_iso_a)
                env[model].browse(record.id).write({field: same_company.id})
                record.invalidate_recordset()
                self.assertEqual(record.sudo()[field], same_company)
        line = self._iso_one('work.acceptance.line', self.p_iso_a)
        other_acceptance = self.env['work.acceptance'].create({
            'name': 'S3 同公司另一張驗收', 'project_id': self.p_iso_a.id, 'contractor_company_id': self.co_a.id})
        with self.subTest(model='work.acceptance.line', mode='同公司'):
            env['work.acceptance.line'].browse(line.id).write({'acceptance_id': other_acceptance.id})
            line.invalidate_recordset()
            self.assertEqual(line.sudo().acceptance_id, other_acceptance)
        with self.subTest(mode='sudo'):
            claim = self._iso_one('payment.claim', self.p_iso_b)
            claim.sudo().write({'project_id': self.p_iso_a.id})
            estimate = self._iso_one('payment.estimate', self.p_iso_b)
            estimate.sudo().write({'project_id': False})
            self.env.invalidate_all()
            self.assertEqual(claim.sudo().project_id, self.p_iso_a)
            self.assertFalse(estimate.sudo().project_id)
