# -*- coding: utf-8 -*-
"""雛型版三頁（合約 §0b-33）：選單指向新 client action、看板退場、單一工程頁的旗標區塊、log_filled 合計、
前端呼叫的方法都在閘門清單、每頁筆數常數前後端一致。

沿用線 B 的夾具（test_dashboard_indicators.DashIndicatorCase，時間凍結在台灣 2026-11-05 週四 12:00）：
PA 今天一張日誌、待改缺失 4（逾期 1：期限 11-04）、尚未檢驗 2、估驗 3 期；PS／PB／PR／PE 施工中沒日誌；PN 未開始。
期望值依夾具寫死；斷言打在畫面會看到的區塊內容與狀態。
"""
import os
import re
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.modules.module import get_module_path
from odoo.tests import tagged

from ..models import progress_dashboard_ext as ext
from ..models.method_gate import DASHBOARD_METHODS, ORM_READ_API
from ..models.progress_dashboard_ext import DASH_PAGE_SIZE, PAGE_BLOCKS_CONTEXT_KEY
from .test_dashboard_indicators import FROZEN_NOW, DashIndicatorCase
from .test_dashboard_views import ALL_BLOCKS
from .test_scope_rules import require_totp  # S2 fix2-Z

MODULE = 'construction_company_dashboard'
PAGE_BLOCKS = ['today_work', 'open_defects', 'pending_tests']
OVERVIEW_TAG = 'company_dashboard_page'
REMOVED_XMLIDS = ('action_company_dashboard', 'view_company_dashboard_kanban', 'view_company_dashboard_search')
REMOVED_VIEW_NAME = 'project.project.kanban.company.dashboard'
JS_DIR = os.path.join('static', 'src')
JS_COMMON = os.path.join(JS_DIR, 'dashboard_page', 'dash_common.js')
# orm.call("model" 或 常數, "method"：常數要能在同一檔的 const X = "…" 解出來
ORM_CALL = re.compile(r'orm\.call\(\s*([A-Za-z_][\w.]*|"[^"]+")\s*,\s*"([^"]+)"')
CONST_STRING = re.compile(r'(?:export\s+)?const\s+([A-Z_][A-Z0-9_]*)\s*=\s*"([^"]+)"')
JS_PAGE_SIZE = re.compile(r'DASH_PAGE_SIZE\s*=\s*(\d+)')
OVERDUE_DEADLINE = '2026-11-04'
OVERDUE_DAYS = 1                  # 11-04 到期、今天 11-05
PA_OPEN_DEFECTS = 4
PA_OVERDUE_DEFECTS = 1
PA_PENDING_TESTS = 2
FIXTURE_FILLED = 1                # PA
FIXTURE_MISSING_SUP = 4           # PS、PB、PR、PE（施工中、週四工作天、沒日誌）
FIXTURE_REQUIRED_SUP = 5          # 施工中的 5 個（PN 未開始不算）
FIXTURE_MISSING_MGR = 3           # A 的營造廠主管看不到 PB


@tagged('post_install', '-at_install', MODULE)
class TestDashboardPage(DashIndicatorCase):

    def _data(self, user, project=None, page=True):
        self.env.invalidate_all()
        record = (project or self.pa).with_user(user)
        if page:
            record = record.with_context(**{PAGE_BLOCKS_CONTEXT_KEY: True})
        return record.get_project_dashboard_data()

    def _fixture_count(self, user, key):
        """合計下鑽的工程 domain 裡屬於測試工程的筆數（監造方後台帳號看得到庫裡既有工程）。"""
        fixture = (self.pa | self.ps | self.pb | self.pr | self.pn | self.pe).ids
        action = self._as(user, self.env['project.project']).action_dash_drilldown(key, 'project.project')
        return self.env['project.project'].with_user(user).with_context(active_test=False).search_count(
            action['domain'] + [('id', 'in', fixture)])

    # ── ① 選單、action、看板退場 ──────────────────────────────────────────
    def test_menus_point_to_client_action_and_kanban_is_gone(self):
        action = self.env.ref(f'{MODULE}.action_company_dashboard_page')
        self.assertEqual(action._name, 'ir.actions.client')
        self.assertEqual(action.tag, OVERVIEW_TAG)
        for xmlid in ('menu_company_dashboard', 'menu_company_dashboard_app'):
            self.assertEqual(self.env.ref(f'{MODULE}.{xmlid}').action, action, xmlid)
        for xmlid in REMOVED_XMLIDS:
            self.assertIsNone(self.env.ref(f'{MODULE}.{xmlid}', raise_if_not_found=False), xmlid)
        self.assertFalse(self.env['ir.ui.view'].search([('name', '=', REMOVED_VIEW_NAME)]), '看板 view 要被 -u 收尾刪掉')

    def test_page_size_constant_matches_js(self):
        with open(os.path.join(get_module_path(MODULE), JS_COMMON), encoding='utf-8') as handle:
            match = JS_PAGE_SIZE.search(handle.read())
        self.assertTrue(match, 'dash_common.js 要有 DASH_PAGE_SIZE 常數')
        self.assertEqual(int(match.group(1)), DASH_PAGE_SIZE)

    def test_js_calls_only_gated_or_orm_read_methods(self):
        """前端每個 orm.call 的 (模型, 方法) 都在閘門清單（營造廠主管才叫得到）或 ORM 讀取 API；掃描器要真的掃到東西。"""
        base = get_module_path(MODULE)
        sources = {}
        for root, _dirs, files in os.walk(os.path.join(base, JS_DIR)):
            for name in files:
                if name.endswith('.js'):
                    with open(os.path.join(root, name), encoding='utf-8') as handle:
                        sources[name] = handle.read()
        # 模型常數可能定義在別的檔（dash_common.js 匯出 PROJECT_MODEL）：先把全模組的字串常數收齊
        constants = {}
        for source in sources.values():
            constants.update(dict(CONST_STRING.findall(source)))
        found = []
        for name, source in sources.items():
            if True:
                for model_ref, method in ORM_CALL.findall(source):
                    model = model_ref.strip('"') if model_ref.startswith('"') else constants.get(model_ref)
                    found.append((name, model, method))
                    if method in ORM_READ_API:
                        continue        # ORM 讀取 API 對任何模型都放行（閘門照名稱放行），模型是變數也沒關係
                    self.assertTrue(model, f'{name}: 解析不出 orm.call 的模型 {model_ref}')
                    self.assertIn((model, method), DASHBOARD_METHODS,
                                  f'{name}: {model}.{method} 不在 DASHBOARD_METHODS 也不是 ORM 讀取 API')
        self.assertGreaterEqual(len(found), 3, f'掃描器至少要掃到合計、下鑽、fields_get：{found}')

    # ── ② 區塊清單只在旗標下多三個 ─────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_page_blocks_only_with_context_flag(self):
        plain = self._data(self.sup, page=False)
        self.assertEqual(sorted(plain), sorted(ALL_BLOCKS), '舊「進度表圖表」頁不多抓')
        data = self._data(self.sup)
        self.assertEqual(sorted(data), sorted(ALL_BLOCKS + PAGE_BLOCKS))
        for key in PAGE_BLOCKS:
            self.assertEqual(data[key]['status'], 'ok', key)
            self.assertIsInstance(data[key]['rows'], list, key)
            self.assertIn('count', data[key], key)
            self.assertIn('limit', data[key], key)

    # ── ③ 今天做什麼 ────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_today_work_rows_are_today_lines_only(self):
        Line = self.env['daily.log.line']
        yesterday = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.pa.id), ('log_date', '=', date(2026, 11, 4))])
        self.assertEqual(len(yesterday), 1, '前提：夾具有昨天那張日誌')
        contract_line = Line.create({'sheet_id': self.log_today.id, 'entry_type': 'contract',
                                     'work_item_id': self.task.id, 'daily_qty': 2.5})
        extra_line = Line.create({'sheet_id': self.log_today.id, 'entry_type': 'extra',
                                  'custom_name': 'DASHB 自填工項', 'daily_qty': 1.0})
        Line.create({'sheet_id': yesterday.id, 'entry_type': 'extra', 'custom_name': 'DASHB 昨天的'})
        work = self._data(self.sup)['today_work']
        self.assertEqual(work['log_state'], 'filled')
        self.assertEqual(sorted(row['id'] for row in work['rows']), sorted([contract_line.id, extra_line.id]))
        self.assertEqual(work['count'], 2)
        by_id = {row['id']: row for row in work['rows']}
        self.assertEqual(by_id[contract_line.id]['name'], self.task.name)
        self.assertEqual(by_id[contract_line.id]['unit'], self.task.unit)
        self.assertEqual(by_id[contract_line.id]['daily_qty'], 2.5)
        self.assertEqual(by_id[extra_line.id]['name'], 'DASHB 自填工項')
        self.assertEqual(by_id[extra_line.id]['entry_type'], 'extra')
        # 沒填日誌的工程：rows 空、狀態 missing（畫面「今日未填」，不是 0 列冒充）
        work_ps = self._data(self.sup, self.ps)['today_work']
        self.assertEqual((work_ps['log_state'], work_ps['rows'], work_ps['count']), ('missing', [], 0))
        # 上限：只回前面的，count 是全部（上游說有幾筆就要有幾筆）
        with patch.object(ext, 'TODAY_WORK_LIMIT', 1):
            capped = self._data(self.sup)['today_work']
        self.assertEqual((len(capped['rows']), capped['count'], capped['limit']), (1, 2, 1))

    # ── ④ 待改缺失清單：逾期天數現算，不讀排程更新的儲存欄位 ─────────────────
    @freeze_time(FROZEN_NOW)
    def test_open_defects_overdue_days_computed_from_deadline(self):
        data = self._data(self.sup)['open_defects']
        self.assertEqual((data['count'], data['overdue_count']), (PA_OPEN_DEFECTS, PA_OVERDUE_DEFECTS))
        self.assertEqual(len(data['rows']), PA_OPEN_DEFECTS, '已驗證、結案的不在清單')
        overdue = [row for row in data['rows'] if row['is_overdue']]
        self.assertEqual([(row['deadline'], row['overdue_days']) for row in overdue], [(OVERDUE_DEADLINE, OVERDUE_DAYS)])
        for row in data['rows']:
            if not row['is_overdue']:
                self.assertEqual(row['overdue_days'], 0, row)
            self.assertTrue(row['state_label'], row)
        # 排序：期限早的在前、沒期限的最後
        deadlines = [row['deadline'] for row in data['rows']]
        dated = [d for d in deadlines if d]
        self.assertEqual(deadlines, sorted(dated) + [False] * (len(deadlines) - len(dated)))
        # 兩把尺一致：把儲存欄位清成「排程還沒跑」的樣子，清單仍算出 1 天（讀儲存欄位的實作會變 0 → 紅）
        self.env.cr.execute(
            'UPDATE general_defect_improvement SET overdue_days = 0, is_overdue = false WHERE project_id = %s',
            (self.pa.id,))
        self.env.invalidate_all()
        again = self._data(self.sup)['open_defects']
        self.assertEqual([row['overdue_days'] for row in again['rows'] if row['is_overdue']], [OVERDUE_DAYS])
        self.assertEqual(again['overdue_count'], PA_OVERDUE_DEFECTS, '卡片的逾期數同樣不信儲存欄位')

    # ── ⑤ 待補檢驗 ─────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_pending_tests_only_not_started(self):
        data = self._data(self.sup)['pending_tests']
        self.assertEqual((data['count'], len(data['rows'])), (PA_PENDING_TESTS, PA_PENDING_TESTS))
        self.assertNotIn(self.test_done.id, [row['id'] for row in data['rows']], '檢驗完成的不算待補')
        self.assertEqual({row['standard'] for row in data['rows']}, {'DASHB 抗壓'})

    # ── ⑥ 公司合計 log_filled ───────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_log_filled_kpi_counts_projects_not_sheets(self):
        Project = self._as(self.sup, self.env['project.project'])
        kpis = Project.get_dash_company_kpis()['kpis']
        self.assertEqual(kpis['log_filled']['status'], 'ok')
        self.assertEqual(kpis['log_filled']['parts'][0]['model'], 'project.project', '下鑽到工程清單')
        self.assertEqual(self._fixture_count(self.sup, 'log_filled'), FIXTURE_FILLED)
        self.assertEqual(self._fixture_count(self.sup, 'log_missing'), FIXTURE_MISSING_SUP)
        self.assertEqual(self._fixture_count(self.sup, 'log_filled') + self._fixture_count(self.sup, 'log_missing'),
                         FIXTURE_REQUIRED_SUP, '已填＋未填＝今天該填的工程數')
        # 張數 vs 工程數：log_today 下鑽到日誌（張數）、log_filled 下鑽到工程（雛型的「已填／應填」是工程數）
        # （同一工程同一天第二張日誌被 daily_log_sheet._check_overlapping_sheets 擋，所以用下鑽模型證明兩者不同）
        self.assertEqual(kpis['log_today']['parts'][0]['model'], 'daily.log.sheet')
        self.assertEqual(self._drill_count(self.sup, self.pa, 'log_today'), 1)
        self.assertEqual(self._drill_count(self.sup, self.pa, 'log_filled'), 1)
        self.assertEqual(self._drill_count(self.sup, self.ps, 'log_filled'), 0)
        # 營造廠主管只數自己範圍（看不到 PB）；未啟用兩步驟驗證 → 無權限
        mgr = self._as(self.mgr, self.env['project.project']).get_dash_company_kpis()['kpis']
        self.assertEqual((mgr['log_filled']['count'], mgr['log_missing']['count']), (FIXTURE_FILLED, FIXTURE_MISSING_MGR))
        blocked = self._as(self.mgr_nototp, self.env['project.project']).get_dash_company_kpis()['kpis']
        self.assertEqual(blocked['log_filled']['status'], 'no_access')

    # ── ⑦ 範圍：別家工程整頁 AccessError；自家工程旗標區塊正常 ─────────────────
    @freeze_time(FROZEN_NOW)
    def test_manager_page_blocks_own_project_and_not_others(self):
        data = self._data(self.mgr)
        for key in PAGE_BLOCKS:
            self.assertEqual(data[key]['status'], 'ok', key)
        self.assertEqual(data['open_defects']['count'], PA_OPEN_DEFECTS)
        with self.assertRaises(AccessError):
            self._data(self.mgr, self.pb)

    # ── ⑧ 新區塊的錯誤隔離 ─────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_page_block_error_is_isolated(self):
        with patch.object(type(self.pa), '_dashboard_pending_tests', side_effect=ValueError('boom')):
            data = self._data(self.sup)
        self.assertEqual(data['pending_tests'], {'status': 'error', 'message': '讀取失敗'})
        for key in ('today_work', 'open_defects', 'estimate', 'today_photos'):
            self.assertEqual(data[key]['status'], 'ok', key)
