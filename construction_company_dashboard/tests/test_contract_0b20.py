# -*- coding: utf-8 -*-
"""合約 §0b-20（線 F1）：檢試驗預警歸工程層級；營造方看得到卻點了會 403 的入口藏起來。

1. `supervision.test.warning`：營造方（後台營造廠主管、前台營造帳號）看得到所屬工程的營造廠含範圍公司的預警，
   別家工程的看不到（兩個方向逐筆比）；單一工程頁「檢試驗」區塊對營造廠主管不再是「無權限查看」，
   未處理預警數＝夾具真值。
2. 前台右側抽屜「意見回饋」（construction_helpdesk 裝了是真入口、沒裝是佔位）：營造方看不到，監造方照舊。
3. `/my` 首頁的 dobtor「文件」「試算表」入口卡（後台帳號才看得到卡片牆）：營造廠主管看不到，監造方照舊。
   卡片模板是核心 portal 的，dobtor 沒裝時那兩張卡本來就沒有（只驗「藏」的方向不會恆真：見各測試的反證）。

斷言打在畫面 HTML 裡有沒有那個網址（同一個畫面對兩種人各渲染一次）。
"""
import re

from odoo.addons.website.tools import MockRequest
from odoo.tests import tagged

from .test_portal_dashboard import PortalDashCase
from .test_scope_rules import DashScopeCase

WARNING = 'supervision.test.warning'
HELPDESK_DRAWER_VIEW = 'construction_helpdesk.portal_drawer_feedback'
FEEDBACK_URL = '/construction/feedback'
FEEDBACK_PLACEHOLDER = 'data-cy-drawer-todo="意見回饋即將推出"'
# 同一個抽屜裡營造方仍看得到的佔位項目（證明抽屜真的有渲染，不是整塊沒出來）
DRAWER_STILL_THERE = 'data-cy-drawer-todo="使用說明即將推出"'
# dobtor 兩張入口卡：模組 → (入口卡模板 xmlid, 網址)
DOBTOR_CARDS = {
    'dobtor_doc_editor': ('dobtor_doc_editor.portal_my_home_documents', '/my/documents'),
    'dobtor_spreadsheet_editor': ('dobtor_spreadsheet_editor.portal_my_home_spreadsheet', '/my/spreadsheets'),
}
CARD_WALL = 'o_portal_docs'
HREF = re.compile(r'href="([^"]+)"')


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestTestWarningProjectLevel(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Warning_ = cls.env[WARNING]
        cls.warnings = {}
        for project in (cls.p_shared, cls.p_a, cls.p_b):
            cls.warnings[project] = Warning_.create({
                'project_id': project.id, 'task_id': cls.tasks[project].id,
                'warning_type': 'completion', 'state': 'pending'})
        # PA 另一筆已處理：區塊只數未處理的
        cls.done_on_pa = Warning_.create({
            'project_id': cls.p_a.id, 'task_id': cls.tasks[cls.p_a].id,
            'warning_type': 'completion', 'state': 'done'})

    def test_contractor_sees_own_project_warnings_only(self):
        all_ids = [w.id for w in self.warnings.values()] + [self.done_on_pa.id]
        expected = {self.warnings[self.p_shared].id, self.warnings[self.p_a].id, self.done_on_pa.id}
        for user in (self.mgr_a, self.portal_a):
            seen = self._visible_ids(user, WARNING, [('id', 'in', all_ids)])
            self.assertEqual(seen, expected, f'{user.login}：P、PA 的預警看得到，PB（只有 B）的看不到')
        # 範圍公司空白的營造方：預設拒絕
        self.assertEqual(self._visible_ids(self.portal_blank, WARNING, [('id', 'in', all_ids)]), set())
        # 監造方照舊全部看得到
        self.assertEqual(self._visible_ids(self.sup, WARNING, [('id', 'in', all_ids)]), set(all_ids))

    def test_single_project_test_block_readable_by_manager(self):
        project = self._env_of(self.mgr_a)['project.project'].browse(self.p_a.id)
        block = project.get_project_dashboard_data()['test_summary']
        self.assertEqual(block.get('status'), 'ok', f'檢試驗區塊不可再是無權限：{block}')
        self.assertEqual(block['pending_warning_count'], 1, 'PA 只有一筆未處理預警')


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestContractorHiddenEntries(PortalDashCase):

    def _drawer_html(self, user):
        vals, html = self._drive(user, self.portal.portal_construction_project_info, self.pa.id)
        self.assertIsNotNone(vals, f'{user.login}：工程資訊頁應渲染而不是被導走：{html}')
        self.assertIn(DRAWER_STILL_THERE, html, f'{user.login}：抽屜沒有渲染')
        return html

    def test_drawer_feedback_hidden_for_contractors(self):
        helpdesk = self.env.ref(HELPDESK_DRAWER_VIEW, raise_if_not_found=False)
        needle = FEEDBACK_URL if helpdesk and helpdesk.active else FEEDBACK_PLACEHOLDER
        self.assertIn(needle, self._drawer_html(self.sup_leader), '監造方應看得到意見回饋入口')
        for user in (self.boss_a, self.leader_a):
            html = self._drawer_html(user)
            self.assertNotIn(FEEDBACK_URL, html, f'營造方 {user.login} 不應看到意見回饋入口')
            self.assertNotIn(FEEDBACK_PLACEHOLDER, html, f'營造方 {user.login} 不應看到意見回饋佔位')

    def _drive_home(self, user):
        """同 _drive，但 MockRequest 帶一個啟用中的語言：/my 的版型有語言選單，MockRequest 預設 en_US，
        這個庫沒啟用 en_US 時語言名稱是 False，選單渲染會 AttributeError（與本案無關）。"""
        lang = self.env['res.lang'].search([('active', '=', True)], limit=1).code
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user, context=dict(self.env.context, lang=lang))
        seen = {}
        with MockRequest(env, context={'lang': lang}) as req:
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = self.portal.home()
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    def _my_home_hrefs(self, user):
        vals, html = self._drive_home(user)
        self.assertIsNotNone(vals, f'{user.login}：/my 應渲染卡片牆而不是被導走：{html}')
        self.assertIn(CARD_WALL, html, f'{user.login}：沒有渲染卡片牆')
        return set(HREF.findall(html))

    def test_my_home_dobtor_cards_hidden_for_contractor_manager(self):
        installed = {name: url for name, (view, url) in DOBTOR_CARDS.items()
                     if self.env.ref(view, raise_if_not_found=False)}
        if not installed:
            self.skipTest('這個庫沒有裝 dobtor 文件／試算表')
        sup_hrefs = self._my_home_hrefs(self.sup)
        mgr_hrefs = self._my_home_hrefs(self.mgr)
        for name, url in installed.items():
            self.assertIn(url, sup_hrefs, f'監造方應看得到 {name} 入口卡')
            self.assertNotIn(url, mgr_hrefs, f'營造廠主管不應看到 {name} 入口卡')
        # 反證：營造廠主管的卡片牆不是整個空的（只藏那兩張）
        self.assertIn('/my/account', mgr_hrefs)
