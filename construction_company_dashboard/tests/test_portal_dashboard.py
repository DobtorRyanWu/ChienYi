# -*- coding: utf-8 -*-
"""前台公司儀表板 /construction/dashboard（合約 §7、§10 D 列）＋營造方看不到審核類按鈕（§3.6 寫入矩陣）。

沿用線 B 的夾具（DashIndicatorCase：營造廠 A、B、監造公司 S；工程 PA／PS／PB／PR／PN／PE；PA 有進度表、
缺失、照片、估驗），另加前台帳號。用 MockRequest 驅動真實路由並把模板真的渲染成 HTML（MockRequest 的
render 只回假字串，所以由測試自己渲染）。斷言打在使用者看得到的結果：哪幾張卡片、畫面上有什麼字、
按鈕的網址在不在 HTML 裡；筆數兩個方向都比（不能看到別家的，也不能自己的被擋掉）。
"""
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from freezegun import freeze_time

from odoo.addons.website.tools import MockRequest
from odoo.tests import tagged

from odoo.addons.construction_company_dashboard.controllers import portal_dashboard as dash_ctrl
from odoo.addons.construction_company_dashboard.controllers.portal_dashboard import ConstructionDashboard
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

from . import test_dashboard_indicators as ind

BOSS = 'construction_supervision_base.group_portal_subscriber'
LEADER = 'construction_supervision_base.group_portal_leader'
FIELD = 'construction_supervision_base.group_portal_user'
MODULE_DIR = Path(__file__).resolve().parent.parent
LOCKED_LOG_AGE_DAYS = 20          # 日誌超過 14 天鎖定（construction_daily_log LOCK_DAYS）
CARD_ID = re.compile(r'data-project-id="(\d+)"')
SVG_BLOCK = re.compile(r'<svg\b.*?</svg>', re.S)


class PortalDashCase(ind.DashIndicatorCase):
    """前台帳號夾具＋驅動路由的工具（不帶 tagged，只給下面的測試類別繼承）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        co_s = cls.co_s

        def front(login, group, member_of=(), scope=None, supervision=False):
            vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [env.ref(group).id])],
                    'company_id': co_s.id, 'company_ids': [(6, 0, co_s.ids)]}
            if scope:
                vals.update(is_contractor_org=True, dash_scope_company_id=scope.id)
            elif supervision:
                vals['is_supervision_org'] = True
            else:
                vals['is_contractor_org'] = True          # 範圍公司空白的營造方
            user = env['res.users'].with_context(no_reset_password=True).create(vals)
            for project in member_of:
                env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
            return user

        cls.boss_a = front('dpd_boss_a', BOSS, scope=cls.co_a)
        cls.boss_b = front('dpd_boss_b', BOSS, scope=cls.co_b)
        # PT：已終止的工程（只有 A）：可見性條件要把它排除（老闆照舊看全部狀態）；光靠 ir.rule 擋不掉它
        cls.pt = cls._project('DASHB 已終止', 'DASHB-PT', [(6, 0, cls.co_a.ids)], date(2026, 11, 2),
                              date(2026, 11, 30), state='terminated')
        cls.leader_a = front('dpd_leader_a', LEADER, (cls.pa, cls.ps, cls.pb, cls.pn, cls.pt), scope=cls.co_a)
        cls.field_a = front('dpd_field_a', FIELD, (cls.pb,), scope=cls.co_a)        # 只掛在 B 的工程上
        cls.blank = front('dpd_blank', LEADER, (cls.pa,))                           # 營造方、範圍公司空白
        cls.sup_boss = front('dpd_sup_boss', BOSS, supervision=True)
        cls.sup_leader = front('dpd_sup_leader', LEADER, (cls.pa, cls.pb), supervision=True)
        cls.dash = ConstructionDashboard()
        cls.portal = ConstructionPortal()

    # ── 驅動真實路由 ────────────────────────────────────────────────────
    def _drive(self, user, method, *args, params=None, **kw):
        """以 user 身分跑路由並把模板真的渲染。回傳 (values, html)；路由導走時 values 為 None、html 為 Location。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=user)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = params or {}
            req.params = params or {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args, **kw)
            if 'tpl' not in seen:
                return None, res.headers.get('Location', '')
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    def _dashboard(self, user, **params):
        return self._drive(user, self.dash.construction_dashboard, params=params, **params)

    def _card_ids(self, user, **params):
        vals, html = self._dashboard(user, **params)
        self.assertIsNotNone(vals, f'{user.login}：應渲染儀表板而不是被導走：{html}')
        ids = [card['id'] for card in vals['cards']]
        self.assertEqual(ids, [int(i) for i in CARD_ID.findall(html)], '畫面上的卡片要與資料一致')
        return ids


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestPortalDashboard(PortalDashCase):

    # ── 卡片＝其可見工程（兩個方向都比）────────────────────────────────
    def test_cards_equal_visible_projects_per_role(self):
        """各前台角色（與後台帳號）看到的卡片＝其可見工程。預設只列施工中；state=all 才含草稿的 PN。"""
        pa, ps, pb, pr, pn, pe = self.pa, self.ps, self.pb, self.pr, self.pn, self.pe
        cases = [
            # 老闆：看全庫，但營造方再 AND 承攬廠商含範圍公司（不能看到別家的 PB，也不能漏自家的）
            (self.boss_a, {pa, ps, pr, pe}, {pa, ps, pr, pe, pn, self.pt}),
            (self.boss_b, {ps, pb}, {ps, pb}),
            # 主管：只看被指派的成員工程；PB（別家）被營造方範圍擋掉、PN 草稿被排除
            (self.leader_a, {pa, ps}, {pa, ps}),
            # 現場：只掛在 B 的工程 → 空清單，沒有帳號被擋的原因，不報錯
            (self.field_a, set(), set()),
            # 監造方前台：看被指派的，兩家的都看得到
            (self.sup_leader, {pa, pb}, {pa, pb}),
            # 營造廠主管（後台）：看所屬公司的工程再 AND 範圍公司
            (self.mgr, {pa, ps, pr, pe}, {pa, ps, pr, pe, pn}),   # 已終止的 PT 被可見性條件排除
        ]
        for user, default_expected, all_expected in cases:
            self.assertCountEqual(self._card_ids(user), [p.id for p in default_expected], f'{user.login} 預設（施工中）')
            self.assertCountEqual(self._card_ids(user, state='all'), [p.id for p in all_expected],
                                  f'{user.login} state=all')

    def test_supervision_boss_sees_all_construction(self):
        """監造方前台老闆：不受營造方範圍影響，四家的施工中工程都在（至少含夾具的六個裡的施工中）。"""
        ids = set(self._card_ids(self.sup_boss, state='all'))
        self.assertTrue({p.id for p in (self.pa, self.ps, self.pb, self.pr, self.pn, self.pe)} <= ids)

    def test_blocked_accounts_get_reason_not_error(self):
        """範圍公司空白的營造方、未啟用兩步驟驗證的營造廠主管：空清單＋原因，不報錯、不顯示 0 冒充。"""
        for user, needle in ((self.blank, '範圍公司'), (self.mgr_nototp, '兩步驟驗證')):
            vals, html = self._dashboard(user)
            self.assertIsNotNone(vals, f'{user.login}：不能被導走或報錯')
            self.assertEqual(vals['cards'], [], user.login)
            self.assertIn(needle, vals['blocked_message'], user.login)
            self.assertIn('cy-dash-blocked', html, f'{user.login}：頁面上方要有「看不到資料」的說明框')
            self.assertIn(vals['blocked_message'], html, f'{user.login}：原因要印在畫面上')
            for item in vals['kpi_items']:
                self.assertFalse(item['ok'], f'{user.login}：{item["key"]} 不可顯示數字')
                self.assertEqual(item['message'], vals['blocked_message'])

    def test_unblocked_user_has_no_blocked_message(self):
        vals, html = self._dashboard(self.field_a)
        self.assertFalse(vals['blocked_message'])
        self.assertNotIn('目前看不到任何資料', html)
        self.assertIn('目前沒有符合條件的工程', html)

    def test_pagination(self):
        """分頁：每頁最多 CARDS_PER_PAGE 張；超過範圍夾到最後一頁、亂填頁碼回第一頁；各頁不重複、合起來不漏。"""
        with patch.object(dash_ctrl, 'CARDS_PER_PAGE', 2):
            seen = []
            for page in (1, 2):
                vals, _html = self._dashboard(self.boss_a, state='all', page=page)
                self.assertEqual((vals['page'], vals['pages'], vals['total']), (page, 3, 6))
                self.assertLessEqual(len(vals['cards']), 2)
                seen += [c['id'] for c in vals['cards']]
            vals, _html = self._dashboard(self.boss_a, state='all', page=999)
            self.assertEqual(vals['page'], 3)
            seen += [c['id'] for c in vals['cards']]
            self.assertCountEqual(seen, [p.id for p in (self.pa, self.ps, self.pr, self.pe, self.pn, self.pt)])
            vals, _html = self._dashboard(self.boss_a, state='all', page='abc')
            self.assertEqual(vals['page'], 1)

    # ── 公司合計與後台一致 ──────────────────────────────────────────────
    @freeze_time(ind.FROZEN_NOW)
    def test_company_totals_match_backend_method(self):
        """畫面上的合計＝後台同一個方法 get_dash_company_kpis 的數字；A 的營造廠主管看得到的待改缺失是確切數字。"""
        for user in (self.mgr, self.sup, self.boss_a):
            backend = self.env['project.project'].with_user(user).get_dash_company_kpis()
            vals, html = self._dashboard(user)
            shown = {item['key']: item for item in vals['kpi_items']}
            for key, entry in backend['kpis'].items():
                if entry['status'] == 'not_applicable':
                    self.assertNotIn(key, shown, f'{user.login}：不適用的不顯示')
                    continue
                self.assertTrue(shown[key]['ok'], f'{user.login} {key}')
                if key in dash_ctrl.KPI_AMOUNT_KEYS:
                    self.assertEqual(shown[key]['value'], dash_ctrl._money(entry['amount'], self.env.company.currency_id.symbol or ''))
                else:
                    self.assertEqual(shown[key]['value'], f"{entry['count']:,}", f'{user.login} {key}')
        # 期望值由夾具寫死：A 的待改缺失＝PA 4（草稿、已通知×2、已改善）＋PS 歸 A 的 1＋PR 1；逾期＝PA 1＋PS 1＋PR 1
        vals, _html = self._dashboard(self.mgr)
        shown = {item['key']: item['value'] for item in vals['kpi_items']}
        self.assertEqual((shown['open_defect'], shown['overdue_defect']), ('6', '3'))

    def test_kpi_items_never_show_zero_for_unreadable(self):
        """無權限、缺日曆、讀取失敗：顯示原因文字，不是 0；不適用的指標整格不顯示。"""
        kpis = {'kpis': {
            'a': {'label': 'A', 'status': 'no_access', 'message': '無權限查看', 'count': None, 'amount': None},
            'b': {'label': 'B', 'status': 'no_calendar', 'message': '缺 2015 年政府辦公日曆', 'count': None,
                  'amount': None},
            'c': {'label': 'C', 'status': 'error', 'message': False, 'count': None, 'amount': None},
            'd': {'label': 'D', 'status': 'not_applicable', 'message': '不適用', 'count': None, 'amount': None},
            'e': {'label': 'E', 'status': 'ok', 'message': False, 'count': 0, 'amount': None},
            'month_estimate': {'label': 'F', 'status': 'ok', 'message': False, 'count': 2, 'amount': 1234.5},
        }}
        items = {i['key']: i for i in ConstructionDashboard._kpi_items(kpis, 'NT$')}
        self.assertEqual(set(items), {'a', 'b', 'c', 'e', 'month_estimate'})
        self.assertEqual((items['a']['ok'], items['a']['message']), (False, '無權限查看'))
        self.assertEqual(items['b']['message'], '缺 2015 年政府辦公日曆')
        self.assertEqual(items['c']['message'], '讀取失敗')
        self.assertEqual((items['e']['ok'], items['e']['value']), (True, '0'), '真的 0 筆才顯示 0')
        self.assertEqual((items['month_estimate']['value'], items['month_estimate']['sub']), ('NT$1,234', '2 期'))

    def test_card_groups_show_reason_not_zero(self):
        """卡片各群組：無權限／讀取失敗／未建進度表／尚無估驗 都有文字，沒有 0 冒充。"""
        card = ConstructionDashboard
        for fn, group in ((card._counts, 'defect'), (card._counts, 'test')):
            self.assertEqual(fn(None, group, {group}, set()), {'text': '無權限查看', 'ok': False})
            self.assertEqual(fn(None, group, set(), {group}), {'text': '讀取失敗', 'ok': False})
        for fn, group in ((card._progress, 'progress'), (card._photos, 'photo')):
            self.assertEqual(fn(None, {group}, set())['text'], '無權限查看')
            self.assertEqual(fn(None, set(), {group})['text'], '讀取失敗')
        self.assertEqual(card._estimate(None, {'estimate'}, set(), '$')['text'], '無權限查看')
        self.assertEqual(card._estimate(None, set(), {'estimate'}, '$')['text'], '讀取失敗')
        no_estimate = SimpleNamespace(dash_latest_estimate_id=False)
        self.assertEqual(card._estimate(no_estimate, set(), set(), '$')['text'], '尚無估驗')
        no_schedule = SimpleNamespace(dash_has_schedule=False)
        self.assertEqual(card._progress(no_schedule, set(), set())['text'], '未建進度表')
        # 缺日曆：工作天欄不顯示數字，顯示備註原因
        missing = SimpleNamespace(dash_workday_state='no_calendar', dash_workday_note='缺 2015 年政府辦公日曆；x')
        self.assertEqual(card._workday(missing)['text'], '缺 2015 年政府辦公日曆；x')
        self.assertEqual(card._log(SimpleNamespace(dash_log_today='no_access'), set(), set())['text'], '無權限查看')
        self.assertEqual(card._log(SimpleNamespace(dash_log_today='no_calendar'), set(), set())['text'],
                         '缺政府辦公日曆')

    def test_page_shows_missing_calendar_and_unbuilt_schedule(self):
        """真實頁面：PE（2015 開工）顯示「缺 2015、2016 年政府辦公日曆」、PR（沒建進度表）顯示「未建進度表」。"""
        _vals, html = self._dashboard(self.mgr)
        self.assertIn('缺 2015、2016 年政府辦公日曆', html)
        self.assertIn('未建進度表', html)

    # ── SVG 與使用者字串 ────────────────────────────────────────────────
    def test_svg_in_page_has_no_user_strings_and_names_are_escaped(self):
        """頁面裡每一段 <svg> 都不含使用者字串；工程名稱（含 <script>）在頁面上被跳脫。"""
        vals, html = self._dashboard(self.mgr)
        svgs = SVG_BLOCK.findall(html)
        self.assertTrue(svgs, 'PA 有進度表，頁面要有小 S 曲線')
        for svg in svgs:
            for needle in (ind.USER_MARK, '<script', 'alert', 'DASHB'):
                self.assertNotIn(needle, svg)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('&lt;svg', html, 'SVG 要當標記輸出，不是被跳脫成文字')

    def test_thumbnails_use_permissioned_image_route(self):
        """縮圖走 /construction/img/<att_id>，不用 /web/image 也不用 public 網址；每張都是自己看得到的今日照片。"""
        with freeze_time(ind.FROZEN_NOW):
            vals, html = self._dashboard(self.mgr)
        tags = [t for t in re.findall(r'<img\b[^>]*>', html) if 'cy-dash-thumb' in t]
        urls = [re.search(r'src="([^"]+)"', t).group(1) for t in tags]
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(url.startswith('/construction/img/'), url)

    # ── 靜態守則 ────────────────────────────────────────────────────────
    def test_front_end_rules_static(self):
        """前台規範：CSS 只用 --wb-*（不出現 --cy-*）；模板沒有 OWL／jQuery／Chart.js；controller 不用 sudo。"""
        css = (MODULE_DIR / 'static/src/portal/dashboard.css').read_text(encoding='utf-8')
        self.assertNotIn('--cy-', css)
        self.assertTrue(re.search(r'var\(--wb-', css))
        xml = (MODULE_DIR / 'views/portal_dashboard_templates.xml').read_text(encoding='utf-8')
        for banned in ('owl', 'jquery', 'chart.js', '--cy-', '<script'):
            self.assertNotIn(banned, xml.lower(), banned)
        controller = (MODULE_DIR / 'controllers/portal_dashboard.py').read_text(encoding='utf-8')
        self.assertNotIn('sudo', controller)
        self.assertNotIn('date.today', controller)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestPortalApprovalButtons(PortalDashCase):
    """營造方不能做的審核類動作（合約 §3.6 寫入矩陣），前台畫面不再給按鈕；監造方照舊看得到。

    斷言打在 HTML 裡有沒有那顆按鈕的送出網址。同一個畫面對兩種人各渲染一次（兩個方向都比）；
    營造方「可以做」的（自主檢查確認）也要驗仍然看得到。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.defects = {state: cls._defect(cls.pa, state, company=cls.co_a, deadline=date(2026, 12, 1))
                       for state in ('draft', 'improved', 'verified')}
        itype = env['self.inspection.type'].create({'name': 'DPD 檢查類型'})
        cls.insp = {}
        for state in ('inspected', 'confirmed'):
            insp = env['general.self.inspection'].create({
                'project_id': cls.pa.id, 'name': f'DPD-{state}', 'inspection_type_id': itype.id,
                'sub_project_name': 'DPD', 'inspection_date': date(2026, 11, 5), 'inspection_location': 'L1',
                'contractor_company_id': cls.co_a.id})
            env['general.self.inspection.item'].create({'inspection_id': insp.id, 'check_item': 'DPD 項目'})
            insp.sudo().write({'state': state})
            cls.insp[state] = insp
        task = env['project.task'].create({'name': 'DPD 契約工項', 'project_id': cls.pr.id})
        cls.slips = {}
        for no, state in ((901, 'draft'), (902, 'in_progress')):
            slip = env['reservation.notification.slip'].create({
                'project_id': cls.pr.id, 'location': 'DPD 地點', 'slip_no': no})
            env['reservation.notification.slip.line'].create({
                'slip_id': slip.id, 'task_id': task.id, 'item_no': '1', 'unit': '式'})
            if state != 'draft':
                slip.sudo().write({'state': state})
            cls.slips[state] = slip
        cls.locked_log = env['daily.log.sheet'].create({
            'supervision_project_id': cls.pa.id, 'employee_id': cls.employee.id,
            'log_date': date.today() - timedelta(days=LOCKED_LOG_AGE_DAYS),
            'contractor_company_id': cls.co_a.id})

    # 每項：(說明, 路由, 參數, 按鈕要出現的網址／類別片段（同一個 <a> 或 <form> 標籤內全部出現才算）, 營造方是否應該看得到)
    def _cases(self):
        pid = self.pa.id
        d, i, s = self.defects, self.insp, self.slips
        slip_args = lambda state: (self.pr.id, s[state].id)           # noqa: E731
        return [
            ('缺失：通知改善', self.portal.portal_construction_defect_detail, (d['draft'].id,),
             (f'/construction/defect/{d["draft"].id}/notify',), False),
            ('缺失：驗證通過', self.portal.portal_construction_defect_detail, (d['improved'].id,),
             (f'/construction/defect/{d["improved"].id}/verify',), False),
            ('缺失：結案', self.portal.portal_construction_defect_detail, (d['verified'].id,),
             (f'/construction/defect/{d["verified"].id}/close',), False),
            ('自主檢查：確認（營造方可以）', self.portal.portal_construction_inspection_detail, (i['inspected'].id,),
             (f'/construction/inspection/{i["inspected"].id}/confirm',), True),
            ('自主檢查：結案', self.portal.portal_construction_inspection_detail, (i['confirmed'].id,),
             (f'/construction/inspection/{i["confirmed"].id}/close',), False),
            ('通報單：核定', self.portal.portal_construction_slip_detail, slip_args('draft'),
             (f'/slip/{s["draft"].id}/confirm',), False),
            ('通報單：結案', self.portal.portal_construction_slip_detail, slip_args('in_progress'),
             (f'/slip/{s["in_progress"].id}/close',), False),
            ('日誌：解鎖', self.portal.portal_construction_daily_log_detail, (pid, self.locked_log.id),
             (f'/daily-log/{self.locked_log.id}/unlock',), False),
            ('工程首頁快速新增：新增專案', self.portal.portal_construction_project_detail, (pid,),
             ('/construction/project/new', 'cy-quick-add-item'), False),
            ('工程首頁快速新增：工期展延', self.portal.portal_construction_project_detail, (pid,),
             (f'/construction/{pid}/schedule/extend', 'cy-quick-add-item'), False),
            ('右側抽屜：新增專案', self.portal.portal_construction_project_info, (pid,),
             ('/construction/project/new', 'cy-drawer-item'), False),
            # 不是審核按鈕，但營造方點了一定 403（水位歸「其他」類），入口也藏（線 G）
            ('右側抽屜：水位監測', self.portal.portal_construction_project_info, (pid,),
             (f'/construction/{pid}/water-level', 'cy-drawer-item'), False),
            ('工程資訊（草稿）：編輯', self.portal.portal_construction_project_info, (self.pn.id,),
             (f'/construction/{self.pn.id}/edit',), False),
        ]

    @staticmethod
    def _has_button(html, needles):
        return any(all(n in tag for n in needles) for tag in re.findall(r'<(?:a|form)\b[^>]*>', html))

    def _html(self, user, method, args):
        vals, html = self._drive(user, method, *args)
        self.assertIsNotNone(vals, f'{user.login}：應渲染畫面而不是被導走：{html}')
        return html

    def test_contractor_cannot_see_review_buttons_supervision_can(self):
        for label, method, args, fragment, contractor_may in self._cases():
            for user in (self.sup_boss, self.boss_a):
                has = self._has_button(self._html(user, method, args), fragment)
                if user is self.sup_boss or contractor_may:
                    self.assertTrue(has, f'{label}：{user.login} 應看得到按鈕 {fragment}')
                else:
                    self.assertFalse(has, f'{label}：營造方 {user.login} 不應看到按鈕 {fragment}')

    def test_contractor_leader_also_hidden(self):
        """主管角色的營造方帳號也一樣（按鈕原本給老闆／主管）。主管沒掛在預約式工程 PR 與草稿 PN 上，那幾項略過。"""
        skipped = 0
        for label, method, args, fragment, contractor_may in self._cases():
            if method == self.portal.portal_construction_slip_detail or '草稿' in label:
                skipped += 1
                continue
            has = self._has_button(self._html(self.leader_a, method, args), fragment)
            self.assertEqual(has, contractor_may, f'{label}：{self.leader_a.login}')
        self.assertLess(skipped, len(self._cases()) - 6, '略過的項目不能多到沒驗什麼')

    def test_server_side_guards_still_refuse(self):
        """藏按鈕不是守衛：路由本身仍然拒絕營造方（直接打網址）。"""
        from odoo.exceptions import AccessError
        with MockRequest(self.env(user=self.boss_a)):
            with self.assertRaises(AccessError):
                self.portal._require_not_contractor()


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestPortalInspectionTemplates(PortalDashCase):
    """線 G 真瀏覽器實證（線 D 回報 5-1）：營造方開「有草稿自主檢查」的工程首頁 403——模板以本人身分讀
    `inspection_type_id.name`，而樣板落在「其他」類被拒。全域樣板、工程自己的樣板、別的工程的樣板
    （被這個工程的檢查用到）都要讀得到名稱；三種營造方身分（前台老闆、前台主管、後台營造廠主管）各開一次。"""

    @freeze_time(ind.FROZEN_NOW)
    def test_project_home_with_draft_inspections_renders_for_contractors(self):
        Type = self.env['self.inspection.type']
        types = (
            Type.create({'name': 'DPD 全域樣板'}),
            Type.create({'name': 'DPD 甲工程樣板', 'project_id': self.pa.id}),
            Type.create({'name': 'DPD 乙工程樣板（甲的檢查在用）', 'project_id': self.pb.id}),
        )
        for itype in types:
            self.env['general.self.inspection'].create({
                'project_id': self.pa.id, 'name': 'DPD-INSP', 'inspection_type_id': itype.id,
                'sub_project_name': 'DPD 分項', 'inspection_date': date(2026, 11, 5)})
        for user in (self.boss_a, self.leader_a, self.mgr):
            vals, html = self._drive(user, self.portal.portal_construction_project_detail, self.pa.id)
            self.assertIsNotNone(vals, f'{user.login}：工程首頁應渲染而不是被導走：{html}')
            self.assertEqual(len(vals['draft_inspections']), len(types), f'{user.login}：三張草稿檢查都列出')
            for itype in types:
                self.assertIn(itype.name, html, f'{user.login}：看得到樣板名稱「{itype.name}」')
