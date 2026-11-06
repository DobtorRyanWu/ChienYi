# -*- coding: utf-8 -*-
"""控台取資料方法 dash_console_overview()（合約 §8.1、§1-5）。

鎖住三件事：
1. 非控台讀取帳號呼叫被拒（含別的帳號 sudo() 進來）；控台讀取帳號拿得到全部工程（含封存），筆數兩個方向都比。
2. 回傳不含人名、照片、明細：鍵是測試這邊獨立寫的白名單（多一個鍵就紅），夾具故意放人名標記，序列化後找不到。
3. project_count 用原生 SQL 另外數，與 ORM 那條路獨立：ORM 少拿一筆時兩個數字不同（上游據此拒寫）。

夾具沿用 test_scope_rules.DashScopeCase（營造廠 A／B、監造 S、四個工程、8 種單據、控台讀取帳號）。
"""
import json
import logging
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_scope_rules import DashScopeCase

# 測試這邊獨立寫一份（不 import 實作常數）：實作多回一個鍵，這裡就紅
EXPECT_TOP_KEYS = {'computed_at', 'project_count', 'projects'}
EXPECT_ROW_KEYS = {
    'remote_id', 'name', 'code', 'state', 'state_label', 'active', 'contractor_companies', 'supervision_company',
    'workday_elapsed', 'workday_total', 'workday_note', 'workday_state', 'workday_state_label',
    'log_today', 'log_today_label', 'today_photo_count',
    'open_defect_count', 'overdue_defect_count', 'pending_test_count',
    'latest_estimate_no', 'latest_estimate_date', 'estimate_cum_amount', 'estimate_month_amount',
    'progress_planned', 'progress_actual', 'progress_variance', 'has_schedule',
    'denied_keys', 'error_keys',
}
EXPECT_CONTRACTOR_KEYS = {'name', 'vat'}
DENY_TEXT = '控台取資料方法只限「控台讀取」帳號呼叫'
# 夾具放進各種「人名」欄位的標記字串（序列化後的回傳不可出現）
PERSON_MARKERS = {
    'employee': 'DASH人名標記甲員工',
    'pm_user': 'DASH人名標記乙專案經理',
    'customer': 'DASH人名標記丙聯絡人',
    'authority_contact': 'DASH人名標記丁機關承辦',
    'member': 'DASH人名標記戊成員',
}
VAT_A = '00501503'   # 統一編號（檢查碼合法的範例號）
VAT_S = '04595257'   # 監造公司 S 的統一編號（範例號）
DASHBOARD_LOGGER = 'odoo.addons.construction_company_dashboard.models.project_dashboard'
_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestConsoleOverview(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co_a.vat = VAT_A
        cls.co_s.vat = VAT_S
        # 第二家監造公司（jt 這種多家共用的庫）：PB 改掛它，控台要分得出 PB 不是 S 的
        cls.co_s2 = cls.env['res.company'].create({'name': 'DASH 監造 S2', 'company_type': 'supervision'})
        env = cls.env
        # 人名標記：日誌填表人、專案經理、客戶聯絡人、機關承辦人、成員帳號
        cls.employee.name = PERSON_MARKERS['employee']
        pm = cls._user('dash_pm_marker', ['base.group_user'], company=cls.co_s, companies=cls.co_s)
        pm.name = PERSON_MARKERS['pm_user']
        customer = env['res.partner'].create({'name': PERSON_MARKERS['customer']})
        member = cls._user('dash_member_marker', ['base.group_portal'], company=cls.co_s, companies=cls.co_s)
        member.name = PERSON_MARKERS['member']
        cls.p_shared.write({'user_id': pm.id, 'partner_id': customer.id,
                            'authority_contact_name': PERSON_MARKERS['authority_contact']})
        env['supervision.project.member'].create({'project_id': cls.p_shared.id, 'user_id': member.id})
        # 封存一個工程：控台也要看得到（未結事項要算，合約 §5.1）
        cls.p_b.active = False

    # ── 工具 ───────────────────────────────────────────────────────────
    def _overview(self, user, only_fixture=False):
        Project = self.env['project.project'].with_user(user)
        if not only_fixture:
            return Project.dash_console_overview()
        fixture_ids = self.projects.ids

        def fixture_only(model):
            return model.sudo().with_context(active_test=False).browse(fixture_ids)
        with patch.object(type(self.env['project.project']), '_dash_console_projects', fixture_only):
            return Project.dash_console_overview()

    def _sql_project_count(self):
        self.env.cr.execute('SELECT count(*) FROM project_project')
        return self.env.cr.fetchone()[0]

    # ── 1. 誰能呼叫 ─────────────────────────────────────────────────────
    def test_non_console_users_rejected(self):
        """監造方、營造廠主管、前台、管理者都被拒，訊息說明原因；別人 sudo() 進來也一樣（判定看 env.user）。"""
        admin = self.env.ref('base.user_admin')
        for user in (self.sup, self.mgr_a, self.portal_a, admin):
            with self.assertRaises(AccessError, msg=user.login) as ctx:
                self.env['project.project'].with_user(user).dash_console_overview()
            self.assertIn(DENY_TEXT, str(ctx.exception), user.login)
            with self.assertRaises(AccessError, msg=f'{user.login} sudo') as ctx:
                self.env['project.project'].with_user(user).sudo().dash_console_overview()
            self.assertIn(DENY_TEXT, str(ctx.exception), f'{user.login} sudo')

    def test_console_reader_gets_all_projects(self):
        """控台讀取帳號：全部工程（含封存）一筆不少、不多；直接讀工程仍是 0 筆（只能走這個方法）。"""
        result = self._overview(self.console)
        self.assertEqual(set(result), EXPECT_TOP_KEYS)
        all_ids = set(self.env['project.project'].sudo().with_context(active_test=False).search([]).ids)
        row_ids = [row['remote_id'] for row in result['projects']]
        self.assertEqual(len(row_ids), len(set(row_ids)), '工程不可重複')
        self.assertEqual(set(row_ids), all_ids, '全部工程都要有（少一筆、多一筆都不行）')
        self.assertIn(self.p_b.id, row_ids, '封存的工程也要回')
        self.assertEqual(result['project_count'], self._sql_project_count())
        self.assertEqual(result['project_count'], len(result['projects']))
        # 控台讀取帳號自己讀工程：0 筆（rule_scope 的 console 分支）
        self.assertEqual(self.env['project.project'].with_user(self.console).with_context(
            active_test=False).search_count([]), 0)

    def test_row_values_equal_indicators(self):
        """數字就是 §5.2 的同一組指標（不另算），並對夾具的真值：P 有 A、B 各一筆一般式缺失（待改 2）。"""
        result = self._overview(self.console, only_fixture=True)
        rows = {row['remote_id']: row for row in result['projects']}
        self.assertEqual(set(rows), set(self.projects.ids))
        shared = rows[self.p_shared.id]
        expected_open = self.env['general.defect.improvement'].sudo().search_count([
            ('project_id', '=', self.p_shared.id), ('state', 'not in', ('verified', 'closed'))])
        self.assertEqual(expected_open, 2, '夾具：P 有兩筆待改缺失')
        self.assertEqual(shared['open_defect_count'], expected_open)
        project = self.p_shared.sudo()
        self.assertEqual(
            (shared['pending_test_count'], shared['today_photo_count'], shared['workday_total'],
             shared['has_schedule'], shared['progress_planned']),
            (project.dash_pending_test_count, project.dash_today_photo_count, project.dash_workday_total,
             project.dash_has_schedule, project.dash_progress_planned))
        self.assertEqual((shared['state'], shared['state_label']), ('construction', '施工中'))
        self.assertEqual((shared['name'], shared['code']), (self.p_shared.name, 'DASH-P'))
        self.assertEqual(sorted((c['name'], c['vat']) for c in shared['contractor_companies']),
                         sorted([(self.co_a.name, VAT_A), (self.co_b.name, False)]))
        self.assertIs(rows[self.p_b.id]['active'], False)
        self.assertFalse(shared['error_keys'])
        self.assertFalse(shared['denied_keys'], 'sudo 計算不會有無權限的指標')

    def test_supervision_company_per_row(self):
        """每列帶工程的監造公司（名稱＋統編）；同一庫兩家監造公司時各列分得出來（兩個方向都比）。"""
        # 直接寫 SQL：工程的 company_id 改到 S2（ORM 改會牽動工程底下單據的公司一致性檢查，與本案無關）
        self.env.cr.execute('UPDATE project_project SET company_id = %s WHERE id = %s', [self.co_s2.id, self.p_b.id])
        self.env.invalidate_all()
        result = self._overview(self.console, only_fixture=True)
        rows = {row['remote_id']: row['supervision_company'] for row in result['projects']}
        expect_s = {'name': self.co_s.name, 'vat': VAT_S}
        expect_s2 = {'name': self.co_s2.name, 'vat': False}
        self.assertEqual(rows, {
            self.p_shared.id: expect_s, self.p_a.id: expect_s, self.r_shared.id: expect_s,
            self.p_b.id: expect_s2,
        })

    def test_error_keys_passed_through(self):
        """指標群組讀取失敗 → error_keys 帶出去（控台顯示「讀取失敗」，不把 0 當真）。"""
        def broken_fill(projects):
            raise RuntimeError('boom')
        # 一般函式而非 MagicMock（Odoo 掃描類別屬性的快取會把 MagicMock 當成鉤子）
        with patch.object(type(self.env['project.project']), '_dash_fill_defect', broken_fill), \
                self.assertLogs(DASHBOARD_LOGGER, 'ERROR'):
            result = self._overview(self.console, only_fixture=True)
        for row in result['projects']:
            self.assertIn('defect', (row['error_keys'] or '').split(','), row['code'])

    # ── 2. 不含人名、照片、明細 ─────────────────────────────────────────
    def test_no_person_names_photos_or_details(self):
        result = self._overview(self.console, only_fixture=True)
        self.assertEqual(set(result), EXPECT_TOP_KEYS)
        for row in result['projects']:
            self.assertEqual(set(row), EXPECT_ROW_KEYS, '每列只能有白名單的鍵')
            for company in row['contractor_companies'] + [row['supervision_company']]:
                self.assertEqual(set(company), EXPECT_CONTRACTOR_KEYS)
        dumped = json.dumps(result, ensure_ascii=False)
        # 標記確實在資料裡（否則下面恆真）
        self.assertEqual(self.p_shared.sudo().authority_contact_name, PERSON_MARKERS['authority_contact'])
        self.assertEqual(self.p_shared.sudo().user_id.name, PERSON_MARKERS['pm_user'])
        for kind, marker in PERSON_MARKERS.items():
            self.assertNotIn(marker, dumped, f'回傳含人名（{kind}）')
        for login in ('dash_mgr_a', 'dash_portal_a', 'dash_console', 'dash_sup'):
            self.assertNotIn(login, dumped)
        self.assertNotIn('supervision.photo', dumped)

    # ── 3. 原生 SQL 的筆數與 ORM 獨立 ───────────────────────────────────
    def test_project_count_independent_of_orm(self):
        """ORM 那條路少拿一筆 → projects 少一筆，而 project_count 仍是 SQL 真值（兩數不同，上游拒寫）。"""
        dropped = self.p_a

        def drop_one(model):
            return model.sudo().with_context(active_test=False).search([('id', '!=', dropped.id)], order='id')
        with patch.object(type(self.env['project.project']), '_dash_console_projects', drop_one):
            result = self.env['project.project'].with_user(self.console).dash_console_overview()
        truth = self._sql_project_count()
        self.assertEqual(result['project_count'], truth)
        self.assertEqual(len(result['projects']), truth - 1)
        self.assertNotIn(dropped.id, [row['remote_id'] for row in result['projects']])
