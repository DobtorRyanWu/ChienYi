# -*- coding: utf-8 -*-
"""後台畫面（合約 §6、§10 C 列）：看板 view、選單、單一工程頁各區塊的三種情況（無權限／出錯／正常）、例假日表單。

沿用線 B 的夾具（凍結在台灣 2026-11-05 12:00）：PA 今天有 8 張照片、1 張日誌、3 期估驗（含 1 期草稿）。
期望值由測試依資料寫死；斷言打在畫面會看到的區塊內容與狀態。
"""
import os
from unittest.mock import patch

from freezegun import freeze_time
from lxml import etree

from odoo.exceptions import AccessError
from odoo.modules.module import get_module_path
from odoo.tests import tagged

from odoo.addons.construction_progress.models.supervision_project import (
    SupervisionProjectProgress as ProgressProject,
)

from ..models.progress_dashboard_ext import KANBAN_PAGE_SIZE
from ..models.project_dashboard import TODAY_PHOTO_LIMIT, ProjectProject as DashProject
from .test_dashboard_indicators import FROZEN_NOW, DashIndicatorCase

MODULE = 'construction_company_dashboard'
# 單一工程頁的區塊（construction_progress 原本 7 個＋本模組 3 個）；測試這邊獨立寫一份，不從實作的清單推
ALL_BLOCKS = ['basic_info', 'duration_info', 'progress_summary', 'change_order_summary', 'defect_summary',
              'test_summary', 'review_summary', 'today_photos', 'today_log', 'estimate']
NO_ACCESS_MESSAGE = '無權限查看'
ERROR_MESSAGE = '讀取失敗'
PHOTO_COUNT_PA = 8
REST_DAY_FIELDS = ('rest_day_mon', 'rest_day_tue', 'rest_day_wed', 'rest_day_thu',
                   'rest_day_fri', 'rest_day_sat', 'rest_day_sun')


@tagged('post_install', '-at_install', MODULE)
class TestDashboardViews(DashIndicatorCase):

    # ── view 與選單 ─────────────────────────────────────────────────────
    def _kanban_arch(self):
        view = self.env.ref(f'{MODULE}.view_company_dashboard_kanban')
        return etree.fromstring(view.get_combined_arch())

    def test_kanban_view_loads_and_is_a_new_view(self):
        """看板是新 view（不是改 supervision.project.kanban）；欄位都在模型上；每頁筆數＝常數。"""
        arch = self._kanban_arch()
        self.assertEqual(arch.get('js_class'), 'company_dashboard_kanban')
        self.assertEqual(int(arch.get('limit')), KANBAN_PAGE_SIZE)
        Project = self.env['project.project']
        for node in arch.iter('field'):
            self.assertIn(node.get('name'), Project._fields, node.get('name'))
        # 真的能以 kanban 取 view（會跑完整的欄位與 modifiers 驗證）
        result = Project.with_user(self.sup).get_view(self.env.ref(f'{MODULE}.view_company_dashboard_kanban').id,
                                                      'kanban')
        self.assertIn('dash_progress_svg', result['arch'])
        old = self.env.ref('construction_supervision_base.view_supervision_project_kanban')
        self.assertNotIn('dash_', old.arch_db, '舊的工程看板不能被改')

    def test_kanban_card_shows_reason_for_every_failable_group(self):
        """卡片上每個可能無權限／失敗的指標群組，都有「無權限查看」「讀取失敗」的文字路徑（不是空白）。"""
        arch = etree.tostring(self._kanban_arch(), encoding='unicode')
        for group in ('workday', 'progress', 'log', 'defect', 'test', 'estimate', 'photo'):
            self.assertIn(f"failed.includes('{group}')", arch, group)
        for group in ('progress', 'log', 'defect', 'test', 'estimate', 'photo'):
            self.assertIn(f"denied.includes('{group}')", arch, group)
        self.assertIn('無權限查看', arch)
        self.assertIn('讀取失敗', arch)

    def test_action_defaults_to_active_construction_projects(self):
        action = self.env.ref(f'{MODULE}.action_company_dashboard')
        self.assertEqual(action.res_model, 'project.project')
        self.assertEqual(action.view_mode, 'kanban')
        self.assertIn("'search_default_construction': 1", action.context)
        search = etree.fromstring(self.env.ref(f'{MODULE}.view_company_dashboard_search').arch_db)
        flt = search.xpath("//filter[@name='construction']")[0]
        self.assertIn("('state', '=', 'construction')", flt.get('domain'))
        self.assertIn("('active', '=', True)", flt.get('domain'))
        self.assertTrue(search.xpath("//filter[@name='archived']"), '要能切到封存的工程')
        # 預設條件下只列有效且施工中的；拿掉篩選能看到全部（含未開始、封存）
        Project = self.env['project.project'].with_user(self.sup)
        scope = [('id', 'in', (self.pa | self.pn | self.pb).ids)]
        self.pb.write({'active': False})
        default = Project.search(scope + [('state', '=', 'construction'), ('active', '=', True)])
        self.assertEqual(default, self.pa)
        self.assertEqual(Project.with_context(active_test=False).search(scope), self.pa | self.pn | self.pb)

    def test_menu_placement(self):
        menu = self.env.ref(f'{MODULE}.menu_company_dashboard')
        self.assertEqual(menu.parent_id, self.env.ref('construction_supervision_base.menu_project_overview'))
        self.assertEqual(menu.sequence, 5)
        self.assertEqual(menu.action, self.env.ref(f'{MODULE}.action_company_dashboard'))

    def test_menu_visible_to_supervision_and_manager_only_allowlist(self):
        """真選單：監造方看得到；營造廠主管看得到它與進度表圖表，看不到工程案件。"""
        Menu = self.env['ir.ui.menu']
        menu = self.env.ref(f'{MODULE}.menu_company_dashboard')
        cases = ((self.sup, True), (self.mgr, True))
        for user, expected in cases:
            visible = Menu.with_user(user).sudo(False).with_env(self.env(user=user, su=True))._visible_menu_ids()
            self.assertEqual(menu.id in visible, expected, user.login)
        mgr_visible = Menu.with_env(self.env(user=self.mgr, su=True))._visible_menu_ids()
        self.assertNotIn(self.env.ref('construction_supervision_base.menu_supervision_project').id, mgr_visible)
        self.assertIn(self.env.ref('construction_progress.menu_progress_chart_dashboard').id, mgr_visible)

    def test_assets_declared_and_exist(self):
        """manifest 的前端檔案都在磁碟上（打錯路徑 → 整個後台載入失敗）。"""
        manifest = self.env['ir.module.module'].get_module_info(MODULE)
        base = get_module_path(MODULE)
        for path in manifest['assets']['web.assets_backend']:
            self.assertTrue(os.path.isfile(os.path.join(base, path.split('/', 1)[1])), path)

    # ── 單一工程頁各區塊 ─────────────────────────────────────────────────
    def _data(self, user, project=None):
        self.env.invalidate_all()
        return (project or self.pa).with_user(user).get_project_dashboard_data()

    def test_block_list_comes_from_progress_module(self):
        """合約 §0b-18：區塊清單只有 construction_progress 的 _dashboard_blocks() 一份——那邊加一個區塊，
        公司儀表板的單一工程頁就跟著有（本模組沒有另外複製清單），而且照本模組的錯誤處理包好。"""
        original = ProgressProject._dashboard_blocks

        def with_probe(project):
            return original(project) + [('g_probe_block', lambda: {'value': 1})]

        with patch.object(ProgressProject, '_dashboard_blocks', with_probe):
            data = self._data(self.sup)
        self.assertEqual(data.get('g_probe_block'), {'value': 1, 'status': 'ok'})
        self.assertEqual(sorted(set(data) - {'g_probe_block'}), sorted(ALL_BLOCKS))

    @freeze_time(FROZEN_NOW)
    def test_blocks_normal(self):
        """正常：每個區塊都有 status=ok；新三區塊的數字與卡片同一份。"""
        data = self._data(self.sup)
        self.assertEqual(sorted(data), sorted(ALL_BLOCKS))
        for key in ('basic_info', 'duration_info', 'progress_summary', 'defect_summary', 'test_summary',
                    'today_photos', 'today_log', 'estimate'):
            self.assertEqual(data[key]['status'], 'ok', key)
        photos = data['today_photos']
        self.assertEqual((photos['count'], len(photos['photos']), photos['limit']),
                         (PHOTO_COUNT_PA, TODAY_PHOTO_LIMIT, TODAY_PHOTO_LIMIT))
        log = data['today_log']
        self.assertEqual((log['log_state'], len(log['sheets'])), ('filled', 1))
        self.assertEqual(log['sheets'][0]['id'], self.log_today.id)
        est = data['estimate']
        latest = max(self.est.values(), key=lambda e: e.estimate_no)
        self.assertEqual(latest, self.est['nov4'], '前提：草稿那期的期數最大')
        # 合約 §0b-17（11-05 定案）：最近一期也排除草稿 → 草稿以外期數最大的 11/03 那期（原本斷言含草稿的 11/04）
        self.assertEqual(est['latest']['id'], self.est['nov3'].id)
        self.assertEqual(est['cumulative_amount'], self.est['oct'].subtotal + self.est['nov3'].subtotal)
        self.assertEqual(est['month_amount'], self.est['nov3'].subtotal)
        self.assertGreater(est['cumulative_amount'], 0)
        card = self._as(self.sup, self.pa)
        self.assertEqual(est['cumulative_amount'], card.dash_estimate_cum_amount)
        self.assertEqual(photos['count'], card.dash_today_photo_count)

    @freeze_time(FROZEN_NOW)
    def test_today_log_missing_and_estimate_none(self):
        """沒填日誌 → 「今日未填」；沒有任何估驗 → latest 為 False（畫面「尚無估驗」），金額 0 是真的 0。"""
        data = self._data(self.sup, self.ps)
        self.assertEqual(data['today_log']['log_state'], 'missing')
        self.assertEqual(data['today_log']['sheets'], [])
        self.assertEqual(data['estimate']['latest'], False)
        self.assertEqual(data['estimate']['status'], 'ok')

    @freeze_time('2016-06-01 04:00:00')
    def test_today_log_missing_calendar_message(self):
        data = self._data(self.sup, self.ps)
        self.assertEqual(data['today_log']['log_state'], 'no_calendar')
        self.assertEqual(data['today_log']['message'], '缺 2016 年政府辦公日曆')

    @freeze_time(FROZEN_NOW)
    def test_blocks_no_access_are_separate(self):
        """讀取權不足：只有那個區塊回「無權限查看」，其他區塊照常（不是整頁掛掉，也不是 0）。"""
        Access = self.env['ir.model.access'].sudo()
        for model in ('payment.estimate', 'supervision.photo'):
            Access.search([('model_id.model', '=', model)]).unlink()
        self.env.registry.clear_cache()
        data = self._data(self.sup)
        for key in ('estimate', 'today_photos'):
            self.assertEqual(data[key], {'status': 'no_access', 'message': NO_ACCESS_MESSAGE}, key)
        for key in ('basic_info', 'duration_info', 'progress_summary', 'defect_summary', 'today_log'):
            self.assertEqual(data[key]['status'], 'ok', key)
        # 與卡片一致：卡片也標這兩組無權限
        self.assertEqual(set(self._as(self.sup, self.pa).dash_denied_keys.split(',')), {'estimate', 'photo'})

    @freeze_time(FROZEN_NOW)
    def test_legacy_block_no_access_not_none(self):
        """舊區塊沒權限：不再被吞成 None（None 在畫面是「模組未安裝」）。"""
        Access = self.env['ir.model.access'].sudo()
        Access.search([('model_id.model', '=', 'supervision.test.record')]).unlink()
        self.env.registry.clear_cache()
        data = self._data(self.sup)
        self.assertEqual(data['test_summary'], {'status': 'no_access', 'message': NO_ACCESS_MESSAGE})
        self.assertEqual(data['defect_summary']['status'], 'ok')

    @freeze_time(FROZEN_NOW)
    def test_blocks_error_are_separate(self):
        """其他例外：該區塊「讀取失敗」，其他區塊照常。"""
        with patch.object(type(self.pa), '_dashboard_defect_summary', side_effect=ValueError('boom')):
            data = self._data(self.sup)
        self.assertEqual(data['defect_summary'], {'status': 'error', 'message': ERROR_MESSAGE})
        for key in ('basic_info', 'progress_summary', 'test_summary', 'today_photos', 'today_log', 'estimate'):
            self.assertEqual(data[key]['status'], 'ok', key)

    @freeze_time(FROZEN_NOW)
    def test_new_block_error_when_indicator_group_failed(self):
        """B 線算指標出錯（dash_error_keys 有 photo）→ 今日照片區塊「讀取失敗」，不拿 0 張冒充。"""
        with patch.object(DashProject, '_dash_fill_photo', side_effect=RuntimeError('boom')):
            data = self._data(self.sup)
        self.assertEqual(data['today_photos'], {'status': 'error', 'message': ERROR_MESSAGE})
        self.assertEqual(data['estimate']['status'], 'ok')

    @freeze_time(FROZEN_NOW)
    def test_module_not_installed_stays_none(self):
        with patch.object(type(self.pa), '_dashboard_review_summary', return_value=None):
            data = self._data(self.sup)
        self.assertIsNone(data['review_summary'])

    @freeze_time(FROZEN_NOW)
    def test_manager_blocks_for_own_project_and_not_others(self):
        """營造廠主管（已啟用 TOTP）：自己承攬的工程各區塊正常；別家的工程整頁 AccessError。"""
        data = self._data(self.mgr)
        self.assertEqual(data['today_photos']['count'], PHOTO_COUNT_PA)
        self.assertEqual(data['today_log']['log_state'], 'filled')
        # 別家的工程：整頁無權限（AccessError，前端顯示「無權限查看」），不是各區塊顯示 0 張照片、尚無估驗
        with self.assertRaises(AccessError):
            self._data(self.mgr, self.pb)

    # ── 工程表單的例假日 ─────────────────────────────────────────────────
    def test_rest_days_in_form_and_readonly_flag(self):
        form = self.env['project.project'].with_user(self.sup).get_view(
            self.env.ref('construction_supervision_base.view_supervision_project_form').id, 'form')
        arch = etree.fromstring(form['arch'])
        for name in REST_DAY_FIELDS:
            node = arch.xpath(f"//field[@name='{name}']")
            self.assertEqual(len(node), 1, name)
        self.assertTrue(self.mgr.sudo()._dash_is_contractor_side())
        self.assertTrue(self.pa.with_user(self.mgr).dash_rest_days_readonly)
        self.assertFalse(self.pa.with_user(self.sup).dash_rest_days_readonly)

    def test_rest_days_supervision_can_write_contractor_cannot(self):
        self.pa.with_user(self.sup).write({'rest_day_mon': True})
        self.assertTrue(self.pa.rest_day_mon)
        with self.assertRaises(AccessError):
            self.pa.with_user(self.mgr).write({'rest_day_tue': True})
        self.assertFalse(self.pa.rest_day_tue)
