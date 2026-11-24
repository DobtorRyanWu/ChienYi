# -*- coding: utf-8 -*-
"""公司儀表板「統計圖表」頁的資料（models/dashboard_charts.py；淞源 2026-11-10 會議 C9）。

淞源技師要「馬上抓得到總共抽查了多少」、老闆答應做圓餅／雷達／柱狀的檢視模組。這裡鎖住的是數字：
* 件數類資料集的 total＝同一組條件的 search_count（看的人自己的權限）；
* 期望值由測試依自己造的資料寫死，不是拿實作再算一次；
* 營造廠主管只數得到自家的；指定了看不到的工程＝什麼都沒有，不能退回「全部」；
* 讀不到模型、帳號被預設拒絕 → 標「無權限」，不給 0；
* 兩支方法在方法閘門的放行清單（受限帳號才叫得到）。

沿用 test_dashboard_indicators 的資料（營造廠 A、B；工程 PA 只有 A、PS 共用、PB 只有 B、PR 預約式…）。
"""
from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.dashboard_charts import MAX_CHART_CATEGORIES, MONTHLY_DEFAULT_MONTHS, OTHER_KEY
from ..models.method_gate import DASHBOARD_METHODS, gate_verdict
from .test_dashboard_indicators import (
    FOUND_DATE, FROZEN_NOW, PA_ACTUAL_TODAY, PA_PLANNED_TODAY, DashIndicatorCase,
)
from .test_scope_rules import require_totp

GENERAL = 'general.self.inspection'
RESERVATION = 'reservation.self.inspection'
INSPECTION_DAY = date(2026, 10, 20)
OLD_DAY = date(2026, 8, 5)
PERIOD = ('2026-10-01', '2026-11-30')
CHART_METHODS = ('get_dash_chart_catalog', 'get_dash_chart_data')


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestDashboardCharts(DashIndicatorCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Type = env['self.inspection.type']
        cls.type_form = Type.create({'name': 'DASHB 模板組立'})
        cls.type_rebar = Type.create({'name': 'DASHB 鋼筋綁紮'})
        # PA（只有 A）：模板 2 張（合格、不合格）、鋼筋 1 張（沒有檢查項目）、草稿 1 張（不算）、8 月 1 張（期間外）
        cls._insp(cls.pa, cls.type_form, 'inspected', result='pass')
        cls._insp(cls.pa, cls.type_form, 'confirmed', result='defect')
        cls._insp(cls.pa, cls.type_rebar, 'inspected')
        cls._insp(cls.pa, cls.type_form, 'draft', result='pass')
        cls._insp(cls.pa, cls.type_rebar, 'inspected', result='pass', day=OLD_DAY)
        # PS（共用）：A、B 各一張鋼筋（合格）
        cls._insp(cls.ps, cls.type_rebar, 'inspected', result='pass', company=cls.co_a)
        cls._insp(cls.ps, cls.type_rebar, 'inspected', result='pass', company=cls.co_b)
        # PB（只有 B）：模板 1 張（合格）
        cls._insp(cls.pb, cls.type_form, 'inspected', result='pass')
        # PR（預約式、只有 A）：模板 1 張（合格）
        slip = env['reservation.notification.slip'].search([('project_id', '=', cls.pr.id)], limit=1)
        cls._insp(cls.pr, cls.type_form, 'inspected', result='pass', model=RESERVATION, slip=slip)
        cls.fixture_projects = cls.pa | cls.ps | cls.pb | cls.pr | cls.pn | cls.pe

    @classmethod
    def _insp(cls, project, itype, state, result=None, day=INSPECTION_DAY, company=None, model=GENERAL, slip=None):
        vals = {'inspection_type_id': itype.id, 'inspection_date': day, 'sub_project_name': 'DASHB 檢查'}
        if model == GENERAL:
            vals['project_id'] = project.id
        else:
            vals['slip_id'] = slip.id
        if company:
            vals['contractor_company_id'] = company.id
        insp = cls.env[model].create(vals)
        insp.checklist_ids.unlink()
        if result:
            cls.env[model + '.item'].create({'inspection_id': insp.id, 'check_item': '題目', 'check_result': result})
        if state != 'draft':
            insp.write({'state': state})
        return insp

    def _chart(self, user, dataset, projects=None, period=PERIOD):
        Project = self.env['project.project'].with_user(user)
        ids = (projects if projects is not None else self.fixture_projects).ids
        return Project.get_dash_chart_data(dataset, ids, *(period or (False, False)))

    @staticmethod
    def _table(data):
        """{類別標籤: 第一條數列的值}"""
        return dict(zip([c['label'] for c in data['categories']], data['series'][0]['values']))

    def _count(self, user, model, domain):
        return self.env[model].with_user(user).with_context(active_test=False).search_count(domain)

    # ── 目錄 ────────────────────────────────────────────────────────────
    def test_catalog_lists_every_dataset_with_chart_types(self):
        catalog = self.env['project.project'].with_user(self.sup).get_dash_chart_catalog()
        keys = [entry['key'] for entry in catalog]
        self.assertEqual(keys, ['inspection_type', 'inspection_result', 'defect_state', 'test_result',
                                'monthly', 'progress'])
        for entry in catalog:
            self.assertTrue(entry['chart_types'], entry['key'])
            self.assertTrue(set(entry['chart_types']) <= {'bar', 'pie', 'radar'}, entry['key'])
            # 每個目錄裡的資料集都真的算得出來（不是只列名字）
            self.assertEqual(self._chart(self.sup, entry['key'])['status'], 'ok', entry['key'])
        # 多數列的資料集不能給圓餅
        for key in ('monthly', 'progress'):
            self.assertNotIn('pie', next(e for e in catalog if e['key'] == key)['chart_types'])

    # ── 自主檢查 ────────────────────────────────────────────────────────
    def test_inspection_by_type_exact_and_equals_search_count(self):
        data = self._chart(self.sup, 'inspection_type')
        self.assertEqual(data['status'], 'ok')
        # 模板：PA 2＋PB 1＋PR 1＝4；鋼筋：PA 1＋PS 2＝3（草稿、8 月那張不算）；多的排前面
        self.assertEqual(self._table(data), {'DASHB 模板組立': 4, 'DASHB 鋼筋綁紮': 3})
        self.assertEqual([c['label'] for c in data['categories']], ['DASHB 模板組立', 'DASHB 鋼筋綁紮'])
        self.assertEqual(data['total'], 7)
        domain = [('state', '!=', 'draft'), ('inspection_date', '>=', PERIOD[0]), ('inspection_date', '<=', PERIOD[1]),
                  ('project_id', 'in', self.fixture_projects.ids)]
        self.assertEqual(data['total'], self._count(self.sup, GENERAL, domain) + self._count(self.sup, RESERVATION, domain))
        self.assertEqual(data['unit'], '件')
        self.assertEqual((data['date_from'], data['date_to']), PERIOD)

    def test_inspection_result_exact(self):
        data = self._chart(self.sup, 'inspection_result')
        self.assertEqual(self._table(data), {'合格': 5, '條件合格': 0, '不合格': 1, '未判定': 1})
        self.assertEqual(data['total'], 7)
        roles = {c['label']: c['role'] for c in data['categories']}
        self.assertEqual(roles, {'合格': 'good', '條件合格': 'warning', '不合格': 'critical', '未判定': 'neutral'})

    def test_period_filters_both_ends_and_no_period_means_all(self):
        self.assertEqual(self._chart(self.sup, 'inspection_type', period=('2026-08-01', '2026-08-31'))['total'], 1)
        self.assertEqual(self._chart(self.sup, 'inspection_type', period=('2026-10-21', '2026-11-30'))['total'], 0)
        self.assertEqual(self._chart(self.sup, 'inspection_type', period=('2026-10-20', '2026-10-20'))['total'], 7)
        everything = self._chart(self.sup, 'inspection_type', period=None)
        self.assertEqual(everything['total'], 8)
        self.assertEqual((everything['date_from'], everything['date_to']), (False, False))

    def test_single_project_filter(self):
        self.assertEqual(self._table(self._chart(self.sup, 'inspection_type', projects=self.pa)),
                         {'DASHB 模板組立': 2, 'DASHB 鋼筋綁紮': 1})
        self.assertEqual(self._chart(self.sup, 'inspection_type', projects=self.pr)['total'], 1, '預約式的也要算')

    def test_many_types_fold_into_other_and_total_kept(self):
        Type = self.env['self.inspection.type']
        extra = MAX_CHART_CATEGORIES + 3
        for index in range(extra):
            self._insp(self.pe, Type.create({'name': f'DASHB 其他類型 {index:02d}'}), 'inspected')
        data = self._chart(self.sup, 'inspection_type', projects=self.pe)
        self.assertEqual(len(data['categories']), MAX_CHART_CATEGORIES + 1)
        self.assertEqual(data['categories'][-1]['key'], OTHER_KEY)
        self.assertEqual(data['series'][0]['values'][-1], 3)
        self.assertEqual(data['total'], extra)

    # ── 缺失、檢試驗 ────────────────────────────────────────────────────
    def test_defect_state_exact_and_equals_search_count(self):
        data = self._chart(self.sup, 'defect_state')
        # 基底資料：PA 草稿 1、已通知 2、已改善 1、已驗證 1、結案 1；PS 已通知 3；PB 已通知 1；PR 已通知 1
        self.assertEqual(self._table(data), {'草稿': 1, '已通知': 7, '改善中': 0, '已改善': 1, '已驗證': 1, '結案': 1})
        self.assertEqual(data['total'], 11)
        total = 0
        for model in ('general.defect.improvement', 'reservation.defect.improvement'):
            total += self._count(self.sup, model, [
                ('project_id', 'in', self.fixture_projects.ids),
                ('found_date', '>=', PERIOD[0]), ('found_date', '<=', PERIOD[1])])
        self.assertEqual(data['total'], total)
        self.assertEqual(self._chart(self.sup, 'defect_state', period=('2026-11-01', '2026-11-30'))['total'], 0,
                         '發現日都在 %s，11 月沒有' % FOUND_DATE)

    def test_test_result_exact(self):
        # 基底資料：PA 尚未檢驗 2、合格 1，都沒有進場日 → 要看「全部期間」才數得到
        data = self._chart(self.sup, 'test_result', period=None)
        self.assertEqual(self._table(data), {'合格': 1, '不合格': 0, '檢驗中': 0, '尚未檢驗': 2, '待判定': 0})
        self.assertEqual(data['total'], self._count(self.sup, 'supervision.test.record',
                                                    [('project_id', 'in', self.fixture_projects.ids)]))
        self.assertEqual(self._chart(self.sup, 'test_result')['total'], 0, '沒有進場日的不在任何期間內')

    # ── 每月件數、進度 ──────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_monthly_exact(self):
        data = self._chart(self.sup, 'monthly', period=('2026-08-01', '2026-11-30'))
        self.assertEqual([c['label'] for c in data['categories']], ['2026-08', '2026-09', '2026-10', '2026-11'])
        by_key = {series['key']: series['values'] for series in data['series']}
        self.assertEqual(by_key, {'inspection': [1, 0, 7, 0], 'defect': [0, 0, 11, 0], 'test': [0, 0, 0, 0]})
        self.assertEqual(data['total'], 19)

    @freeze_time(FROZEN_NOW)
    def test_monthly_without_period_shows_last_months_only(self):
        data = self._chart(self.sup, 'monthly', period=None)
        labels = [c['label'] for c in data['categories']]
        self.assertEqual(len(labels), MONTHLY_DEFAULT_MONTHS)
        self.assertEqual((labels[0], labels[-1]), ('2025-12', '2026-11'))
        # 合計只含畫面上列得出來的月份（開始日＝第一個月的 1 日）
        self.assertEqual(data['date_from'], '2025-12-01')
        self.assertEqual(data['total'], sum(sum(series['values']) for series in data['series']))

    @freeze_time(FROZEN_NOW)
    def test_progress_uses_same_numbers_as_overview(self):
        data = self._chart(self.sup, 'progress')
        labels = [c['label'] for c in data['categories']]
        self.assertIn(self.pa.name, labels)
        self.assertNotIn(self.pb.name, labels, '沒有進度表的工程不列')
        index = labels.index(self.pa.name)
        by_key = {series['key']: series['values'][index] for series in data['series']}
        pa = self.pa.with_user(self.sup)
        self.assertEqual(by_key, {'planned': round(pa.dash_progress_planned, 2), 'actual': round(pa.dash_progress_actual, 2)})
        self.assertEqual(by_key, {'planned': PA_PLANNED_TODAY, 'actual': PA_ACTUAL_TODAY})
        self.assertIsNone(data['total'], '百分比不能加總')
        self.assertEqual(data['unit'], '%')
        # 落後最多的排前面（差＝實際－預定，由小到大）
        gaps = [actual - planned for planned, actual in zip(data['series'][0]['values'], data['series'][1]['values'])]
        self.assertEqual(gaps, sorted(gaps))
        self.assertFalse(data['note'], '夾具的工程不到上限，不需要說明')

    @freeze_time(FROZEN_NOW)
    def test_progress_lists_most_behind_when_too_many(self):
        extra = MAX_CHART_CATEGORIES + 2
        projects = self.env['project.project']
        for index in range(extra):
            project = self._project(f'DASHB 進度多 {index:02d}', f'DASHB-PM{index:02d}', [(6, 0, self.co_a.ids)],
                                    date(2026, 11, 2), date(2026, 11, 30))
            # 預定 50、實際 index：index 越小落後越多
            self._schedule(project, [(date(2026, 11, 2), date(2026, 11, 4), 50.0, float(index))])
            projects |= project
        data = self._chart(self.sup, 'progress', projects=projects)
        self.assertEqual(len(data['categories']), MAX_CHART_CATEGORIES)
        self.assertEqual([c['label'] for c in data['categories']][:2], ['DASHB 進度多 00', 'DASHB 進度多 01'])
        self.assertIn(str(extra), data['note'])
        self.assertIn(str(MAX_CHART_CATEGORIES), data['note'])
        # 進度表全是 0 的工程不列（PE 沒有進度表、另建一個全 0 的）
        zero = self._project('DASHB 進度全零', 'DASHB-PZ', [(6, 0, self.co_a.ids)], date(2026, 11, 2), date(2026, 11, 30))
        self._schedule(zero, [(date(2026, 11, 2), date(2026, 11, 30), 0.0, 0.0)])
        self.assertEqual(self._chart(self.sup, 'progress', projects=zero)['categories'], [])

    # ── 權限 ────────────────────────────────────────────────────────────
    def test_manager_counts_only_own_contractor(self):
        """營造廠 A 的主管：PA 全部、PS 只有 A 的那張、PR；PB 與 PS 上 B 的那張數不到。"""
        data = self._chart(self.mgr, 'inspection_type')
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(self._table(data), {'DASHB 模板組立': 3, 'DASHB 鋼筋綁紮': 2})
        domain = [('state', '!=', 'draft'), ('inspection_date', '>=', PERIOD[0]), ('inspection_date', '<=', PERIOD[1])]
        self.assertEqual(data['total'], self._count(self.mgr, GENERAL, domain) + self._count(self.mgr, RESERVATION, domain))
        # 缺失：PA 6＋PS 上 A 的 1＋PR 1（B 的、未歸屬的看不到）
        self.assertEqual(self._chart(self.mgr, 'defect_state')['total'], 8)

    def test_selected_project_out_of_scope_gives_nothing_not_everything(self):
        data = self._chart(self.mgr, 'inspection_type', projects=self.pb)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual((data['total'], data['categories']), (0, []))

    def test_no_read_access_marked_not_zero(self):
        """只有內部使用者群組的帳號讀不到自主檢查、缺失、檢試驗 → 無權限、沒有數字。"""
        for dataset in ('inspection_type', 'inspection_result', 'defect_state', 'test_result', 'monthly'):
            data = self._chart(self.plain, dataset)
            self.assertEqual(data['status'], 'no_access', dataset)
            self.assertTrue(data['message'], dataset)
            self.assertIsNone(data['total'], dataset)
            self.assertEqual(data['series'], [], dataset)

    @require_totp
    def test_blocked_account_gets_reason_not_numbers(self):
        data = self._chart(self.mgr_nototp, 'inspection_type')
        self.assertEqual(data['status'], 'no_access')
        self.assertIn('兩步驟驗證', data['message'])
        self.assertIsNone(data['total'])

    def test_methods_are_on_the_gate_allowlist(self):
        for method in CHART_METHODS:
            self.assertIn(('project.project', method), DASHBOARD_METHODS)
            self.assertEqual(gate_verdict(self.env(user=self.mgr), 'project.project', method), [],
                             f'營造廠主管要叫得到 {method}')

    # ── 輸入檢查 ────────────────────────────────────────────────────────
    def test_invalid_inputs_raise_user_error(self):
        Project = self.env['project.project'].with_user(self.sup)
        with self.assertRaises(UserError):
            Project.get_dash_chart_data('no_such_dataset')
        with self.assertRaises(UserError):
            Project.get_dash_chart_data('inspection_type', [], 'not-a-date', False)
        with self.assertRaises(UserError):
            Project.get_dash_chart_data('inspection_type', [], '2026-11-30', '2026-11-01')
        # 不是整數的工程 id 一律不當成條件（布林、字串、巢狀清單）
        data = Project.get_dash_chart_data('inspection_type', [True, 'x', [1]], *PERIOD)
        self.assertEqual(data['status'], 'ok')
