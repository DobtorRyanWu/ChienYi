# -*- coding: utf-8 -*-
"""「儀表板」App 的兩個入口（合約 §0b-32）：試算表儀表板的資料與可見群組、App 裡的「公司儀表板」選單。

斷言打在使用者看得到的結果：哪個帳號 search 得到這張儀表板、哪個帳號看得到選單；
樞紐表定義用的模型／欄位要真的存在而且查得動（o-spreadsheet 載入壞掉的定義只會在畫面上顯示 #ERROR，伺服器不會紅）。
"""
import ast
import json

from odoo import fields
from odoo.tests import tagged
from odoo.tools import file_open

from .test_scope_rules import SUPERVISOR_ADMIN, DashScopeCase

DASHBOARD_XMLID = 'construction_company_dashboard.spreadsheet_dashboard_company_kpi'
GROUP_XMLID = 'construction_company_dashboard.spreadsheet_dashboard_group_construction'
APP_MENU_XMLID = 'construction_company_dashboard.menu_company_dashboard_app'
APP_ROOT_MENU_XMLID = 'spreadsheet_dashboard.spreadsheet_dashboard_menu_root'
KANBAN_MENU_XMLID = 'construction_company_dashboard.menu_company_dashboard'
KANBAN_ACTION_XMLID = 'construction_company_dashboard.action_company_dashboard'
JSON_PATH = 'construction_company_dashboard/data/files/company_dashboard.json'
EXPECTED_PIVOTS = 9                      # 與 odoo18-docker/tools/dashboard/build_company_spreadsheet_dashboard.py 同步
COUNT_MEASURE = '__count'
TODAY_EXPR = "context_today().strftime('%Y-%m-%d')"      # 產生器寫進字串 domain 的「今天」
TOTP_FIXTURE_SECRET = 'JBSWY3DPEHPK3PXP'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestSpreadsheetDashboard(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mgr_a.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        cls.dash = cls.env.ref(DASHBOARD_XMLID)
        with file_open(JSON_PATH) as fh:
            cls.data = json.load(fh)
        # 沒有「工程後台使用者」群組的監造公司內部帳號：隔離「擋的是 group_ids」用
        cls.plain = cls._user('dash_plain', ['base.group_user'], company=cls.co_s, companies=cls.co_s)

    @staticmethod
    def _domain_as_list(domain, today):
        """字串 domain（含 context_today()）換成今天的日期後解析成清單；清單 domain 原樣回。"""
        if isinstance(domain, str):
            return ast.literal_eval(domain.replace(TODAY_EXPR, repr(fields.Date.to_string(today))))
        return domain

    def _visible(self, user):
        return self.dash.id in self.env['spreadsheet.dashboard'].with_user(user).search([]).ids

    def _visible_menus(self, user):
        # su=True：核心 load_menus 本來就在 sudo 下呼叫；判定仍看 env.user（同 test_menu_allowlist）
        return self.env(user=user, su=True)['ir.ui.menu']._visible_menu_ids()

    # ── 資料檔 ──────────────────────────────────────────────────────────
    def test_record_loaded_from_data_file(self):
        self.assertEqual(self.dash.dashboard_group_id, self.env.ref(GROUP_XMLID))
        self.assertTrue(self.dash.is_published)
        self.assertEqual(self.dash.group_ids, self.env.ref(SUPERVISOR_ADMIN), '可見群組要明寫，不能留核心預設的所有內部使用者')
        result = self.dash.with_user(self.sup).get_readonly_dashboard()
        self.assertNotIn('is_sample', result, '不該退回樣本資料')
        snapshot = result['snapshot']
        self.assertEqual(len(snapshot['pivots']), EXPECTED_PIVOTS)
        self.assertEqual(snapshot['pivots'], self.data['pivots'], 'DB 裡的定義要等於 data 檔（-u 重載）')
        self.assertEqual(len(self.data['globalFilters']), 2)

    def test_pivots_reference_existing_stored_fields(self):
        """模型消失、欄位改名、量測改成非儲存欄位，這支就紅。"""
        filter_ids = {f['id'] for f in self.data['globalFilters']}
        today = fields.Date.context_today(self.sup)
        for pid, pivot in self.data['pivots'].items():
            self.assertEqual(pivot['type'], 'ODOO', pid)
            self.assertIn(pivot['model'], self.env, f'樞紐 {pid} 的模型不存在：{pivot["model"]}')
            info = self.env[pivot['model']].fields_get(attributes=['store', 'groupable'])
            measures = [m['fieldName'] for m in pivot['measures'] if m['fieldName'] != COUNT_MEASURE]
            self.assertTrue(measures or any(m['fieldName'] == COUNT_MEASURE for m in pivot['measures']), pid)
            for name in measures:
                self.assertIn(name, info, f'樞紐 {pid} 的量測欄位不存在：{name}')
                self.assertTrue(info[name]['store'], f'樞紐 {pid} 的量測欄位要是儲存欄位：{name}')
            groupbys = [g['fieldName'] for g in pivot['rows'] + pivot['columns']]
            self.assertTrue(groupbys, f'樞紐 {pid} 沒有分組')
            for name in groupbys:
                self.assertIn(name, info, f'樞紐 {pid} 的分組欄位不存在：{name}')
                self.assertTrue(info[name]['groupable'], f'樞紐 {pid} 的分組欄位不能分組：{name}')
            if isinstance(pivot['domain'], str):
                self.assertIn(TODAY_EXPR, pivot['domain'], f'樞紐 {pid} 用字串 domain 卻沒有動態「今天」，應改成清單')
            # 條件先解析成清單再取欄位名：用正規式抓會把 not in (…) 的值當成欄位（11-06 第一版就踩到）
            domain = self._domain_as_list(pivot['domain'], today)
            names = [leaf[0] for leaf in domain if isinstance(leaf, (list, tuple)) and len(leaf) == 3]
            self.assertTrue(names, f'樞紐 {pid} 的條件裡沒有欄位')
            for name in names:
                self.assertIn(name, info, f'樞紐 {pid} 的條件欄位不存在：{name}')
            for filter_id, match in pivot['fieldMatching'].items():
                self.assertIn(filter_id, filter_ids, f'樞紐 {pid} 對到不存在的全域篩選')
                self.assertIn(match['chain'], info, f'樞紐 {pid} 的篩選對應欄位不存在：{match["chain"]}')

    def test_pivot_queries_run_as_supervisor(self):
        """每個樞紐的查詢以監造方帳號真的跑得動（量測、分組、條件都被伺服器接受）。"""
        today = fields.Date.context_today(self.sup)
        for pid, pivot in self.data['pivots'].items():
            domain = self._domain_as_list(pivot['domain'], today)
            aggregates = [COUNT_MEASURE if m['fieldName'] == COUNT_MEASURE else f"{m['fieldName']}:{m['aggregator']}"
                          for m in pivot['measures']]
            groupby = [g['fieldName'] for g in pivot['rows']]
            rows = self.env[pivot['model']].with_user(self.sup)._read_group(domain, groupby, aggregates)
            self.assertIsInstance(rows, list, pid)

    # ── 誰看得到 ─────────────────────────────────────────────────────────
    def test_visible_only_to_supervisor_admin_group(self):
        self.assertTrue(self._visible(self.sup), '工程後台使用者要看得到')
        self.assertFalse(self._visible(self.plain), '沒有該群組的內部帳號看不到')
        self.assertFalse(self._visible(self.mgr_a), '營造廠主管看不到')
        self.assertFalse(self._visible(self.console), '控台讀取帳號看不到')
        # fail-then-pass：放寬到所有內部使用者，沒群組的監造方帳號就看得到 → 擋他的是 group_ids
        self.dash.sudo().write({'group_ids': [(4, self.env.ref('base.group_user').id)]})
        self.assertTrue(self._visible(self.plain))
        # 營造廠主管與控台讀取帳號就算群組放寬也看不到：擋他們的是範圍規則（合約 §3.2「其餘讀取一律拒」）
        self.assertFalse(self._visible(self.mgr_a))
        self.assertFalse(self._visible(self.console))

    # ── App 裡的選單入口 ────────────────────────────────────────────────
    def test_app_menu_entry(self):
        menu = self.env.ref(APP_MENU_XMLID)
        root = self.env.ref(APP_ROOT_MENU_XMLID)
        self.assertEqual(menu.parent_id, root)
        self.assertEqual(menu.action, self.env.ref(KANBAN_ACTION_XMLID), '開的是同一個看板 action')
        visible_sup = self._visible_menus(self.sup)
        self.assertIn(root.id, visible_sup)
        self.assertIn(menu.id, visible_sup)
        visible_mgr = self._visible_menus(self.mgr_a)
        self.assertNotIn(menu.id, visible_mgr, '營造廠主管不列入允許清單（合約 §0b-32）')
        self.assertNotIn(root.id, visible_mgr, '營造廠主管看不到「儀表板」App')
        self.assertIn(self.env.ref(KANBAN_MENU_XMLID).id, visible_mgr, '原本「工程管理」下的入口照舊')
