# -*- coding: utf-8 -*-
"""公司儀表板總覽頁的期限待辦、近期行事曆、每月估驗（models/dashboard_deadlines.py；淞源 2026-11-10 會議 C5、C7）。

老闆：主管儀表板要有依期限排序的待辦、快到期就亮燈；每個月的錢要看得到；行事曆在電腦上一打開就看到。
清單怎麼排、燈號怎麼分在 construction_portal 的 test_project_deadline 鎖住；這裡鎖的是「誰看得到什麼」和數字：
* 營造廠主管只看得到自家範圍內的期限（別家工程的送審、另一方的公文與行事曆不列）；
* 監造方合計＝庫裡既有資料＋測試資料的確切件數；
* 帳號被預設拒絕 → 標「無權限」，不給 0；讀不到的來源標出來；
* 每月估驗：最近 12 個月、不含草稿、最後一列＝卡片「本月估驗」的同一個數字；
* 三支方法在方法閘門的放行清單。
送審管制（construction_review）、公文與行事曆（construction_office）是選裝的：沒裝的那幾筆不建、期望值跟著少。
期望值依夾具寫死，不是拿實作再算一次。
"""
from datetime import date, datetime

from freezegun import freeze_time

from odoo.tests import tagged

from ..models.dashboard_deadlines import DEADLINE_LIST_LIMIT, MONTHLY_ESTIMATE_MONTHS
from ..models.method_gate import DASHBOARD_METHODS, gate_verdict
from .test_dashboard_indicators import FROZEN_NOW, DashIndicatorCase
from .test_scope_rules import require_totp

PLAN_MODEL = 'supervision.plan.control'           # construction_review（選裝）
OFFICIAL_DOC_MODEL = 'construction.official.doc'  # construction_office（選裝）
EVENT_MODEL = 'construction.calendar.event'       # construction_office（選裝）
DOCUMENT_MODEL = 'supervision.document'
ESTIMATE_MODEL = 'payment.estimate'
DEADLINE_METHODS = ('get_dash_deadline_items', 'get_dash_week_calendar', 'get_dash_monthly_estimates')
PLENTY = 500
# 「有期限、還沒辦完」的條件，由測試獨立寫一份（模型、到工程的欄位、條件）
OPEN_CONDITIONS = (
    (PLAN_MODEL, [('deadline_date', '!=', False), ('first_submit_date', '=', False)]),
    (DOCUMENT_MODEL, [('due_date', '!=', False), ('state', '=', 'draft')]),
    ('general.defect.improvement', [('deadline', '!=', False),
                                    ('state', 'not in', ('improved', 'verified', 'closed'))]),
    ('reservation.defect.improvement', [('deadline', '!=', False),
                                        ('state', 'not in', ('improved', 'verified', 'closed'))]),
    (OFFICIAL_DOC_MODEL, [('reply_deadline', '!=', False), ('state', '=', 'pending')]),
    (EVENT_MODEL, [('event_type', '=', 'deadline'), ('state', '=', 'planned')]),
)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestDashboardDeadlines(DashIndicatorCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # 選裝模組比本模組晚裝時，ACL 要再同步一次才有（optional_access.py 的已知限制）
        env['ir.model.access']._dash_sync_optional_manager_access()
        cls.fixture_projects = cls.pa | cls.ps | cls.pb | cls.pr | cls.pn | cls.pe
        cls.has_review = PLAN_MODEL in env
        cls.has_office = OFFICIAL_DOC_MODEL in env and EVENT_MODEL in env
        # 夾具原有的缺失（今天 11-05）：逾期 5（PA 11-04、PS 三筆 11-01〔A、B、未歸屬〕、PR 11-01）、今天到期 1（PA）
        # 應交文件：PA 剩 2 天、PB 剩 5 天、PA 已上傳（不列）
        category = env['supervision.document.category'].create({'name': 'DASHB 文件分類'})
        cls.doc_pa = cls._document(cls.pa, category, 'DASHB 施工計畫書', date(2026, 11, 7))
        cls.doc_pb = cls._document(cls.pb, category, 'DASHB B 的文件', date(2026, 11, 10))
        cls._document(cls.pa, category, 'DASHB 已上傳', date(2026, 11, 1), state='uploaded')
        if cls.has_review:
            # 送審管制：PA 剩 4 天、PB 剩 1 天、PA 剩 15 天、PA 已送審（不列）
            Plan = env[PLAN_MODEL]
            cls.plan_pa = Plan.create({'name': 'DASHB 整體施工計畫', 'project_id': cls.pa.id,
                                       'deadline_date': date(2026, 11, 9)})
            cls.plan_pb = Plan.create({'name': 'DASHB B 的品質計畫', 'project_id': cls.pb.id,
                                       'deadline_date': date(2026, 11, 6)})
            cls.plan_far = Plan.create({'name': 'DASHB 分項計畫', 'project_id': cls.pa.id,
                                        'deadline_date': date(2026, 11, 20)})
            Plan.create({'name': 'DASHB 已送審', 'project_id': cls.pa.id, 'deadline_date': date(2026, 11, 3),
                         'first_submit_date': date(2026, 11, 2)})
        if cls.has_office:
            # 公文（屬於所屬公司）：監造 S 的剩 7 天、營造 A 的逾期 3 天、監造 S 已辦的（不列）
            Doc = env[OFFICIAL_DOC_MODEL]
            cls.odoc_s = Doc.create({'subject': 'DASHB 監造的公文', 'company_id': cls.co_s.id,
                                     'project_id': cls.pa.id, 'reply_deadline': date(2026, 11, 12)})
            cls.odoc_a = Doc.create({'subject': 'DASHB 營造 A 的公文', 'company_id': cls.co_a.id,
                                     'project_id': cls.pa.id, 'reply_deadline': date(2026, 11, 2)})
            Doc.create({'subject': 'DASHB 已辦', 'company_id': cls.co_s.id, 'project_id': cls.pa.id,
                        'reply_deadline': date(2026, 11, 6), 'state': 'done'})
            # 行事曆：監造 S 的送件期限（台灣 11-08，剩 3 天）、營造 A 的送件期限（台灣 11-10，剩 5 天）、
            # 監造 S 的會議（台灣 11-06 14:00；不是期限，只進行事曆區塊）
            Event = env[EVENT_MODEL]
            cls.event_s = Event.create({
                'name': 'DASHB 送監造計畫', 'event_type': 'deadline', 'company_id': cls.co_s.id,
                'project_id': cls.pa.id, 'start': datetime(2026, 11, 8, 1, 0), 'responsible_user_id': cls.sup.id})
            cls.event_a = Event.create({
                'name': 'DASHB 送施工計畫', 'event_type': 'deadline', 'company_id': cls.co_a.id,
                'project_id': cls.pa.id, 'start': datetime(2026, 11, 10, 1, 0), 'responsible_user_id': cls.mgr.id})
            # 營造 A 的會議，但掛在只有 B 承攬的工程、權責人是監造方人員：營造廠主管看得到這件事（所屬公司＝A），
            # 可是那個工程、那位監造方人員他都讀不到（2026-11-13 權限審查的重現案例）
            cls.meeting_a_on_pb = Event.create({
                'name': 'DASHB A 的會議掛在 B 的工程', 'event_type': 'meeting', 'company_id': cls.co_a.id,
                'project_id': cls.pb.id, 'start': datetime(2026, 11, 7, 1, 0), 'responsible_user_id': cls.sup.id})
            cls.meeting_s = Event.create({
                'name': 'DASHB 工務會議', 'event_type': 'meeting', 'company_id': cls.co_s.id,
                'project_id': cls.pa.id, 'start': datetime(2026, 11, 6, 6, 0), 'stop': datetime(2026, 11, 6, 7, 30),
                'responsible_user_id': cls.sup.id, 'location': 'DASHB 會議室'})

    @classmethod
    def _document(cls, project, category, name, due, state='draft'):
        return cls.env[DOCUMENT_MODEL].create({
            'name': name, 'project_id': project.id, 'document_category_id': category.id,
            'due_date': due, 'state': state})

    def _fixture_data(self, user):
        """只看測試工程的期限清單（以 user 的權限）。"""
        return self.env['project.project'].with_user(user)._cy_deadline_data(
            projects=self.fixture_projects, limit=PLENTY)

    @staticmethod
    def _listed(data, model):
        return {item['res_id'] for item in data['items'] if item['model'] == model}

    def _open_outside_fixture(self, user):
        """user 看得到、不屬於測試工程的「有期限、還沒辦完」筆數（庫裡既有的真實資料；條件由測試獨立寫）。"""
        total = 0
        for model, condition in OPEN_CONDITIONS:
            if model in self.env and self.env[model].with_user(user).has_access('read'):
                # 已封存工程的事項不算待辦；沒掛工程的照算
                total += self.env[model].with_user(user).search_count(condition + [
                    ('project_id', 'not in', self.fixture_projects.ids),
                    '|', ('project_id', '=', False), ('project_id.active', '=', True)])
        return total

    # ── 期限待辦：監造方 ────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_supervisor_fixture_counts_exact(self):
        data = self._fixture_data(self.sup)
        expected = {'overdue': 5, 'urgent': 2, 'soon': 1, 'normal': 0}     # 缺失 5＋1；文件 PA（緊急）、PB（快到了）
        if self.has_review:
            expected['urgent'] += 1         # PB 剩 1 天
            expected['soon'] += 1           # PA 剩 4 天
            expected['normal'] += 1         # PA 剩 15 天
        if self.has_office:
            expected['soon'] += 1           # 監造 S 的公文剩 7 天
            expected['urgent'] += 1         # 監造 S 的送件期限剩 3 天
        expected['total'] = sum(expected.values())
        self.assertEqual(data['counts'], expected)
        self.assertEqual(data['denied'], [])
        self.assertEqual(len(data['items']), expected['total'])
        deadlines = [item['deadline'] for item in data['items']]
        self.assertEqual(deadlines, sorted(deadlines), '期限由近到遠（逾期的在最前面）')
        self.assertEqual(self._listed(data, DOCUMENT_MODEL), set((self.doc_pa | self.doc_pb).ids))
        if self.has_office:
            # 監造方帳號的允許公司只有監造 S：營造 A 的公文與行事曆不列；會議不是期限
            self.assertEqual(self._listed(data, OFFICIAL_DOC_MODEL), set(self.odoc_s.ids))
            self.assertEqual(self._listed(data, EVENT_MODEL), set(self.event_s.ids))

    @freeze_time(FROZEN_NOW)
    def test_supervisor_dashboard_total_is_fixture_plus_existing(self):
        result = self.env['project.project'].with_user(self.sup).get_dash_deadline_items()
        self.assertEqual((result['status'], result['message'], result['today']), ('ok', False, '2026-11-05'))
        fixture_total = self._fixture_data(self.sup)['counts']['total']
        self.assertGreater(fixture_total, 0)
        self.assertEqual(result['counts']['total'], fixture_total + self._open_outside_fixture(self.sup))
        self.assertEqual(result['counts']['total'],
                         sum(result['counts'][level] for level in ('overdue', 'urgent', 'soon', 'normal')))
        self.assertLessEqual(len(result['items']), DEADLINE_LIST_LIMIT)
        self.assertEqual(len(result['items']), min(DEADLINE_LIST_LIMIT, result['counts']['total']))
        self.assertEqual((result['site_days'], result['manager_days']), (7, 3))

    # ── 期限待辦：營造廠主管 ────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_manager_sees_only_own_scope(self):
        """營造廠主管（範圍＝營造 A）：別家工程（PB）的文件與送審、共用工程上 B 的與未歸屬的缺失、
        監造公司的公文與行事曆都不列。庫裡沒有營造 A 的其他資料，所以整份清單就是測試資料。"""
        result = self.env['project.project'].with_user(self.mgr).get_dash_deadline_items()
        self.assertEqual(result['status'], 'ok')
        expected = {'overdue': 3, 'urgent': 2, 'soon': 0, 'normal': 0}     # 缺失：PA 11-04、PS（A 的）、PR；PA 今天、文件 PA
        if self.has_review:
            expected['soon'] += 1           # PA 剩 4 天
            expected['normal'] += 1         # PA 剩 15 天
        if self.has_office:
            expected['overdue'] += 1        # 營造 A 的公文逾期 3 天
            expected['soon'] += 1           # 營造 A 的送件期限剩 5 天
        expected['total'] = sum(expected.values())
        self.assertEqual(result['counts'], expected)
        self.assertEqual(result['denied'], [])
        self.assertEqual(len(result['items']), expected['total'])
        self.assertEqual(self._listed(result, DOCUMENT_MODEL), set(self.doc_pa.ids))
        if self.has_review:
            self.assertEqual(self._listed(result, PLAN_MODEL), set((self.plan_pa | self.plan_far).ids))
        if self.has_office:
            self.assertEqual(self._listed(result, OFFICIAL_DOC_MODEL), set(self.odoc_a.ids))
            self.assertEqual(self._listed(result, EVENT_MODEL), set(self.event_a.ids))
        # 第一筆是逾期最久的；每筆帶工程名稱（主管本來就看得到這些工程）
        self.assertEqual(result['items'][0]['level'], 'overdue')
        self.assertTrue(all(item['project_name'] for item in result['items']))

    @freeze_time(FROZEN_NOW)
    @require_totp
    def test_blocked_account_gets_no_numbers(self):
        """未啟用兩步驟驗證的營造廠主管（強制時）：三個區塊都是「無權限」並附原因，不給 0、不給清單。"""
        Project = self.env['project.project'].with_user(self.mgr_nototp)
        deadlines = Project.get_dash_deadline_items()
        self.assertEqual((deadlines['status'], deadlines['counts'], deadlines['items']), ('no_access', None, []))
        self.assertTrue(deadlines['message'])
        monthly = Project.get_dash_monthly_estimates()
        self.assertEqual((monthly['status'], monthly['months'], monthly['total_count'], monthly['total_amount']),
                         ('no_access', [], None, None))
        self.assertTrue(monthly['message'])
        if self.has_office:
            calendar = Project.get_dash_week_calendar()
            self.assertEqual((calendar['status'], calendar['count'], calendar['items']), ('no_access', None, []))

    @freeze_time(FROZEN_NOW)
    def test_unreadable_sources_are_named(self):
        """只有內部使用者群組的帳號：讀不到缺失 → 列在「未列入的來源」，不報錯。"""
        result = self.env['project.project'].with_user(self.plain).get_dash_deadline_items()
        self.assertEqual(result['status'], 'ok')
        self.assertIn('缺失改善', result['denied'])
        self.assertFalse(self._listed(result, 'general.defect.improvement'))

    def test_methods_are_on_the_gate_allowlist(self):
        for method in DEADLINE_METHODS:
            self.assertIn(('project.project', method), DASHBOARD_METHODS)
            self.assertEqual(gate_verdict(self.env(user=self.mgr), 'project.project', method), [],
                             f'營造廠主管要叫得到 {method}')

    # ── 近期行事曆 ──────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_week_calendar_by_viewer(self):
        Project = self.env['project.project']
        if not self.has_office:
            result = Project.with_user(self.sup).get_dash_week_calendar()
            self.assertEqual((result['installed'], result['status'], result['items']), (False, 'ok', []))
            return
        mine = (self.event_s | self.event_a | self.meeting_s).ids
        sup = Project.with_user(self.sup).get_dash_week_calendar()
        self.assertEqual((sup['installed'], sup['status'], sup['today'], sup['days']), (True, 'ok', '2026-11-05', 7))
        rows = [item for item in sup['items'] if item['id'] in mine]
        # 監造方：自家公司的會議（11-06）、送件期限（11-08），由早到晚；營造 A 的那件（11-10）不在允許公司內，看不到
        self.assertEqual([(item['id'], item['day'], item['when'], item['type_label']) for item in rows], [
            (self.meeting_s.id, '2026-11-06', '14:00–15:30', '會議'),
            (self.event_s.id, '2026-11-08', '09:00–10:00', '送件期限'),
        ])
        self.assertEqual((rows[0]['location'], rows[0]['project_name'], rows[0]['responsible']),
                         ('DASHB 會議室', self.pa.name, self.sup.name))
        self.assertGreaterEqual(sup['count'], 2)
        # 營造廠主管：只有營造 A 的兩件（監造公司的會議與送件期限看不到）
        mgr = Project.with_user(self.mgr).get_dash_week_calendar()
        self.assertEqual(mgr['status'], 'ok')
        self.assertEqual([item['id'] for item in mgr['items']], [self.meeting_a_on_pb.id, self.event_a.id])
        self.assertEqual(mgr['count'], 2)
        rows = {item['id']: item for item in mgr['items']}
        # 自己範圍內的工程、自己的名字照帶
        self.assertEqual((rows[self.event_a.id]['project_name'], rows[self.event_a.id]['responsible']),
                         (self.pa.name, self.mgr.name))
        # 讀不到的工程名稱、讀不到的人的姓名不帶（修改前兩個都用 sudo 帶出來）
        self.assertFalse(self.env['project.project'].with_user(self.mgr).search([('id', '=', self.pb.id)]))
        self.assertFalse(self.env['res.users'].with_user(self.mgr).search([('id', '=', self.sup.id)]),
                         '前提：營造廠主管讀不到監造方人員')
        self.assertEqual((rows[self.meeting_a_on_pb.id]['project_name'], rows[self.meeting_a_on_pb.id]['responsible']),
                         ('', ''))
        self.assertNotIn(self.pb.name, str(mgr))
        self.assertNotIn(self.sup.name, str(mgr))

    # ── 每月估驗 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_monthly_estimates_manager_exact(self):
        """營造廠主管只看得到 PA 的估驗：10 月 1 期（已核定）、11 月 1 期（已歸檔；11/04 那期是草稿不算）。"""
        est = self.est
        self.assertTrue(all(e.subtotal > 0 for e in est.values()), '前提：每期都有金額（防恆真）')
        Project = self.env['project.project'].with_user(self.mgr)
        result = Project.get_dash_monthly_estimates()
        self.assertEqual(result['status'], 'ok')
        months = result['months']
        self.assertEqual(len(months), MONTHLY_ESTIMATE_MONTHS)
        self.assertEqual([months[0]['month'], months[-2]['month'], months[-1]['month']],
                         ['2025-12', '2026-10', '2026-11'])
        self.assertEqual([row['month'] for row in months], sorted(row['month'] for row in months), '由舊到新')
        by_month = {row['month']: (row['count'], row['amount']) for row in months}
        self.assertEqual(by_month['2026-10'][0], 1)
        self.assertAlmostEqual(by_month['2026-10'][1], est['oct'].subtotal)
        self.assertEqual(by_month['2026-11'][0], 1)
        self.assertAlmostEqual(by_month['2026-11'][1], est['nov3'].subtotal)
        self.assertEqual(sum(row['count'] for row in months[:-2]), 0, '其餘月份沒有估驗')
        self.assertEqual(result['total_count'], 2)
        self.assertAlmostEqual(result['total_amount'], est['oct'].subtotal + est['nov3'].subtotal)
        self.assertAlmostEqual(result['max_amount'], max(est['oct'].subtotal, est['nov3'].subtotal))
        self.assertEqual((result['date_from'], result['date_to']), ('2025-12-01', '2026-11-30'))
        # 最後一列＝卡片「本月估驗」的同一個數字
        kpi = Project.with_context(active_test=False).get_dash_company_kpis()['kpis']['month_estimate']
        self.assertEqual((months[-1]['count'], months[-1]['amount']), (kpi['count'], kpi['amount']))
        # 草稿提出（待核定）後就算進來
        est['nov4'].sudo().write({'state': 'pending_approval'})
        self.env.invalidate_all()
        after = Project.get_dash_monthly_estimates()
        self.assertEqual(after['months'][-1]['count'], 2)
        self.assertAlmostEqual(after['months'][-1]['amount'], est['nov3'].subtotal + est['nov4'].subtotal)
        self.assertEqual(after['total_count'], 3)

    @freeze_time(FROZEN_NOW)
    def test_monthly_estimates_window_edges(self):
        """12 個月的窗：2025-12-01 算、2025-11-30 不算；本月稍後的日子（11-20）也算（和卡片一樣算到月底）。"""
        Estimate = self.env[ESTIMATE_MODEL]

        def estimate(day):
            # 2026-11-20：新增日期早於已核定期別的估驗會被擋（夾具已有 11-03 核定的那張）；
            # 這支測的是儀表板依月份彙總，不是核定順序，所以先建、再補日期、直接標核定
            est = Estimate.create({'project_id': self.pa.id})
            est.write({'estimate_date': day})
            self.env['payment.estimate.line'].create({
                'estimate_id': est.id, 'task_id': self.task.id, 'estimate_qty': 1.0, 'unit_price': 100.0})
            est.sudo().write({'state': 'approved'})
            return est

        estimate(date(2025, 11, 30))
        first = estimate(date(2025, 12, 1))
        later = estimate(date(2026, 11, 20))
        self.env.invalidate_all()
        result = self.env['project.project'].with_user(self.mgr).get_dash_monthly_estimates()
        by_month = {row['month']: (row['count'], row['amount']) for row in result['months']}
        self.assertNotIn('2025-11', by_month)
        self.assertEqual(by_month['2025-12'][0], 1)
        self.assertAlmostEqual(by_month['2025-12'][1], first.subtotal)
        self.assertEqual(by_month['2026-11'][0], 2)
        self.assertAlmostEqual(by_month['2026-11'][1], self.est['nov3'].subtotal + later.subtotal)
        self.assertEqual(result['total_count'], 4)

    @freeze_time(FROZEN_NOW)
    def test_monthly_estimates_supervisor_is_fixture_plus_existing(self):
        """監造方看得到庫裡既有的估驗：每個月＝既有的（測試獨立查）＋測試資料的確切數字。"""
        result = self.env['project.project'].with_user(self.sup).get_dash_monthly_estimates()
        self.assertEqual(result['status'], 'ok')
        Estimate = self.env[ESTIMATE_MODEL].with_user(self.sup).with_context(active_test=False)
        fixture = {'2026-10': (1, self.est['oct'].subtotal), '2026-11': (1, self.est['nov3'].subtotal)}
        total_count = 0
        for row in result['months']:
            year, month = (int(part) for part in row['month'].split('-'))
            first = date(year, month, 1)
            last = date(year + (month == 12), month % 12 + 1, 1)
            existing = Estimate.search([
                ('project_id', '!=', False), ('project_id', 'not in', self.fixture_projects.ids),
                ('estimate_date', '>=', first), ('estimate_date', '<', last), ('state', '!=', 'draft')])
            count, amount = fixture.get(row['month'], (0, 0.0))
            self.assertEqual(row['count'], len(existing) + count, row['month'])
            self.assertAlmostEqual(row['amount'], sum(existing.mapped('subtotal')) + amount, msg=row['month'])
            total_count += row['count']
        self.assertEqual(result['total_count'], total_count)
        self.assertAlmostEqual(result['max_amount'], max(row['amount'] for row in result['months']))
