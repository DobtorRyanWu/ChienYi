# -*- coding: utf-8 -*-
"""標案地圖的定位與外部標案（models/project_geo.py、models/external_tender.py；淞源 2026-11-10 會議 C6）。

老闆想在地圖上「看得到附近有哪些標案」；使用者 2026-11-13 決定三件都做：地圖上點位置、用地點文字自動定位、
外部標案匯入後自己標位置。這裡鎖住後端：
* 地圖頁的額外資料：誰可以定位、外部標案圖層列哪些（「不追蹤」的不列）；
* 自動定位：只把「地點文字」送出去（不送工程名稱或編號）、查到的寫進座標並標成「自動定位」、
  查不到／不在臺灣／服務不通各有原因、一次有上限而且一秒只查一個、可以用系統參數停用；
* 受限帳號（營造廠主管）：沒有定位工具、看不到外部標案、叫自動定位會被拒、也寫不進工程座標；
* 兩支方法在方法閘門的清單上；匯入範本的欄名對得上欄位。
外部服務一律用假的回應（測試不連網）。
"""
from unittest.mock import MagicMock, patch

import requests

from odoo.addons.construction_supervision_base.models import company_rule_write_guard
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.models import LOG_ACCESS_COLUMNS
from odoo.modules.module import get_module_path
from odoo.osv import expression
from odoo.sql_db import db_connect
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from ..models import project_geo
from ..models.method_gate import DASHBOARD_METHODS, gate_verdict
from ..models.project_geo import GEOCODE_PARAM, GEOCODE_USER_AGENT, MAP_PAGE_TAG, geocode_candidates
from .test_dashboard_indicators import DashIndicatorCase
from .test_scope_rules import SUPERVISOR_ADMIN

TENDER_MODEL = 'construction.external.tender'
MAP_METHODS = ('get_dash_map_extras', 'action_dash_geocode')
TAIPEI = {'lat': '25.0478', 'lon': '121.5319'}
TOKYO = {'lat': '35.6812', 'lon': '139.7671'}


def fake_service(answers, calls):
    """假的地理編碼服務：answers＝{地點文字: 回應清單 或 例外}；每次呼叫記到 calls。"""
    def get(url, params=None, headers=None, timeout=None):
        calls.append({'url': url, 'params': dict(params or {}), 'headers': dict(headers or {}), 'timeout': timeout})
        answer = answers.get(params['q'], [])
        if isinstance(answer, Exception):
            raise answer
        response = MagicMock()
        response.json.return_value = answer
        response.raise_for_status.return_value = None
        return response
    return get


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestMapExtras(DashIndicatorCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tender = cls.env[TENDER_MODEL]
        cls.Project = cls.env['project.project']

    def _tender(self, name, **vals):
        return self.Tender.create({'name': 'MAPX %s' % name, 'company_id': self.co_s.id, **vals})

    def _geocode(self, user, kind, answers):
        calls, sleeps = [], []
        with patch.object(project_geo.requests, 'get', side_effect=fake_service(answers, calls)), \
                patch.object(project_geo.time, 'sleep', side_effect=sleeps.append):
            result = self.Project.with_user(user).action_dash_geocode(kind)
        return result, calls, sleeps

    # ── 地圖頁的額外資料 ────────────────────────────────────────────────
    def test_extras_for_supervisor_lists_external_tenders(self):
        located = self._tender('已定位', agency='MAPX 水利局', stage='open', budget_amount=12500000,
                               deadline_date='2026-11-30', location='MAPX 路一段', latitude=25.05, longitude=121.53)
        unlocated = self._tender('還沒定位', stage='watching', location='MAPX 路二段')
        dropped = self._tender('不追蹤的', stage='closed', latitude=25.06, longitude=121.54)
        extras = self.Project.with_user(self.sup).get_dash_map_extras()
        self.assertTrue(extras['can_locate'])
        self.assertTrue(extras['geocode_enabled'])
        external = extras['external']
        self.assertEqual((external['status'], external['can_edit']), ('ok', True))
        mine = {item['id']: item for item in external['items'] if item['name'].startswith('MAPX')}
        self.assertEqual(set(mine), {located.id, unlocated.id}, '「不追蹤」的不畫')
        self.assertNotIn(dropped.id, mine)
        self.assertEqual({key: mine[located.id][key] for key in (
            'name', 'agency', 'stage', 'stage_label', 'deadline', 'amount', 'location', 'lat', 'lng', 'geo_source')},
            {'name': 'MAPX 已定位', 'agency': 'MAPX 水利局', 'stage': 'open', 'stage_label': '招標中',
             'deadline': '2026-11-30', 'amount': 12500000.0, 'location': 'MAPX 路一段', 'lat': 25.05, 'lng': 121.53,
             'geo_source': False})
        self.assertEqual((mine[unlocated.id]['lat'], mine[unlocated.id]['lng'], mine[unlocated.id]['deadline']),
                         (False, False, False))
        self.assertEqual(external['count'], self.Tender.with_user(self.sup).search_count(
            [('stage', 'in', ('open', 'awarded', 'watching'))]))

    def test_restricted_manager_gets_no_tools_and_no_external(self):
        self._tender('營造廠主管不該看到', company_id=self.co_a.id, latitude=25.05, longitude=121.53)
        extras = self.Project.with_user(self.mgr).get_dash_map_extras()
        self.assertEqual((extras['can_locate'], extras['geocode_enabled']), (False, False))
        self.assertEqual(extras['external'], {'status': 'no_access', 'can_edit': False, 'items': [], 'count': 0})
        self.assertFalse(self.Tender.with_user(self.mgr).search([]), '受限帳號讀外部標案：預設拒絕')
        with self.assertRaises(AccessError):
            self.Project.with_user(self.mgr).action_dash_geocode('project')
        # 地圖上點位置走的是 ORM write：唯讀帳號寫不進去
        with self.assertRaises(AccessError):
            self.pa.with_user(self.mgr).write({'latitude': 25.05, 'longitude': 121.53, 'dash_geo_source': 'manual'})
        self.assertFalse(self.pa.latitude)

    def test_plain_internal_user_reads_external_but_cannot_locate(self):
        self._tender('一般後台人員看得到', latitude=25.05, longitude=121.53)
        extras = self.Project.with_user(self.plain).get_dash_map_extras()
        self.assertEqual((extras['external']['status'], extras['external']['can_edit']), ('ok', False))
        self.assertTrue([item for item in extras['external']['items'] if item['name'] == 'MAPX 一般後台人員看得到'])
        with self.assertRaises(AccessError):
            self.Tender.with_user(self.plain).create({'name': 'MAPX 不能建'})

    def test_map_click_write_by_supervisor(self):
        """地圖上點位置＝對工程寫入緯度、經度與來源；監造管理員寫得進去（施工中的工程也可以）。"""
        self.assertEqual(self.pa.state, 'construction')
        self.pa.with_user(self.sup).write({'latitude': 25.0612345, 'longitude': 121.5412345, 'dash_geo_source': 'manual'})
        self.assertEqual((self.pa.latitude, self.pa.longitude, self.pa.dash_geo_source),
                         (25.0612345, 121.5412345, 'manual'))
        action = self.pa.with_user(self.sup).action_dash_locate_on_map()
        self.assertEqual((action['type'], action['tag'], action['params']),
                         ('ir.actions.client', MAP_PAGE_TAG, {'locate_project_id': self.pa.id}))

    # ── 自動定位 ────────────────────────────────────────────────────────
    def test_geocode_tenders_sends_only_location_text(self):
        found = self._tender('查得到', location='MAPX 臺北市某路', tender_no='SECRET-NO-1')
        missing = self._tender('查不到', location='MAPX 不存在的地方')
        abroad = self._tender('同名在國外', location='MAPX 東京')
        offline = self._tender('服務不通', location='MAPX 斷線')
        garbled = self._tender('回傳看不懂', location='MAPX 亂碼')
        no_text = self._tender('沒有地點文字')
        already = self._tender('已經有座標', location='MAPX 已有', latitude=24.0, longitude=121.0)
        result, calls, sleeps = self._geocode(self.sup, 'tender', {
            'MAPX 臺北市某路': [TAIPEI], 'MAPX 不存在的地方': [], 'MAPX 東京': [TOKYO],
            'MAPX 斷線': requests.ConnectionError('boom'), 'MAPX 亂碼': [{'nope': 1}]})
        self.assertEqual([item['id'] for item in result['located']], [found.id])
        self.assertEqual((found.latitude, found.longitude, found.geo_source), (25.0478, 121.5319, 'geocoded'))
        reasons = {item['id']: item['reason'] for item in result['failed']}
        self.assertEqual(reasons, {missing.id: '查不到這個地點', abroad.id: '查到的位置不在臺灣範圍內',
                                   offline.id: '定位服務沒有回應', garbled.id: '定位服務回傳的資料看不懂'})
        for tender in (missing, abroad, offline, garbled, no_text):
            self.assertFalse(tender.latitude or tender.longitude or tender.geo_source, tender.name)
        self.assertEqual((already.latitude, already.geo_source), (24.0, False), '已經有座標的不碰')
        self.assertEqual((result['remaining'], result['no_location']), (0, 1))
        # 只送地點文字：沒有標案名稱、案號；有帶可辨識但不含個資的 User-Agent；一秒只查一個
        self.assertEqual(sorted(call['params']['q'] for call in calls),
                         sorted(['MAPX 臺北市某路', 'MAPX 不存在的地方', 'MAPX 東京', 'MAPX 斷線', 'MAPX 亂碼']))
        for call in calls:
            self.assertEqual(set(call['params']), {'q', 'format', 'limit', 'countrycodes', 'accept-language'})
            self.assertEqual(call['headers'], {'User-Agent': GEOCODE_USER_AGENT})
            self.assertNotIn('SECRET-NO-1', str(call))
            self.assertNotIn('查得到', str(call))
            self.assertTrue(call['timeout'])
        # 每個請求之前都等（含第一個：上一次自動定位的最後一個請求可能才剛送出，見 test_geocode_spacing_holds_across_calls）
        self.assertEqual(len(sleeps), len(calls))
        self.assertTrue(all(seconds >= 1 for seconds in sleeps))

    def test_geocode_falls_back_to_street_then_district(self):
        """外部服務查不到臺灣的門牌（2026-11-13 實測）：整段查不到就退一級——只到路段，再不行只到行政區。
        退一級查到的標 approx；每個請求之間都要隔開。"""
        self.assertEqual(geocode_candidates('臺北市信義區市府路1號'),
                         ['臺北市信義區市府路1號', '臺北市信義區市府路', '臺北市信義區'])
        self.assertEqual(geocode_candidates(' 新北市板橋區文化路一段  100號3樓 '),
                         ['新北市板橋區文化路一段 100號3樓', '新北市板橋區文化路一段', '新北市板橋區'])
        self.assertEqual(geocode_candidates('士林區雙溪橡皮壩'), ['士林區雙溪橡皮壩', '士林區'])
        self.assertEqual(geocode_candidates('臺北市信義區'), ['臺北市信義區'], '重複的不列')
        self.assertEqual(geocode_candidates('某某工地旁'), ['某某工地旁'])
        by_street = self._tender('門牌查不到、路段查得到', location='臺北市信義區市府路1號')
        by_district = self._tender('只有行政區查得到', location='臺北市大安區某某巷弄 5號')
        nowhere = self._tender('退到行政區也查不到', location='新北市板橋區文化路一段100號')
        result, calls, sleeps = self._geocode(self.sup, 'tender', {
            '臺北市信義區市府路': [TAIPEI], '臺北市大安區': [TAIPEI]})
        located = {item['id']: item['approx'] for item in result['located']}
        self.assertEqual(located, {by_street.id: True, by_district.id: True})
        self.assertEqual([item['id'] for item in result['failed']], [nowhere.id])
        self.assertEqual(result['failed'][0]['reason'], '查不到這個地點')
        self.assertEqual([call['params']['q'] for call in calls], [
            '臺北市信義區市府路1號', '臺北市信義區市府路',
            '臺北市大安區某某巷弄 5號', '臺北市大安區',
            '新北市板橋區文化路一段100號', '新北市板橋區文化路一段', '新北市板橋區'])
        self.assertEqual(len(sleeps), len(calls), '每個請求之前都要等（含第一個）')
        self.assertEqual(by_street.geo_source, 'geocoded')
        # 整段就查得到的不算「大概」
        exact = self._tender('整段查得到', location='MAPX 整段查得到')
        result, _calls, _sleeps = self._geocode(self.sup, 'tender', {'MAPX 整段查得到': [TAIPEI]})
        self.assertEqual({item['id']: item['approx'] for item in result['located']}, {exact.id: False})

    def test_geocode_batch_limit_leaves_the_rest_for_next_time(self):
        tenders = [self._tender('批次 %s' % index, location='MAPX 批次 %s' % index) for index in range(3)]
        answers = {'MAPX 批次 %s' % index: [TAIPEI] for index in range(3)}
        with patch.object(project_geo, 'GEOCODE_BATCH_LIMIT', 2):
            first, calls, _sleeps = self._geocode(self.sup, 'tender', answers)
            self.assertEqual((len(first['located']), first['remaining'], len(calls)), (2, 1, 2))
            second, calls, _sleeps = self._geocode(self.sup, 'tender', answers)
        self.assertEqual((len(second['located']), second['remaining'], len(calls)), (1, 0, 1))
        self.assertTrue(all(tender.geo_source == 'geocoded' for tender in tenders))

    def test_geocode_projects_marks_source(self):
        """工程：用「工程地點」查；庫裡其他沒座標的工程假服務一律回查不到，不會被寫入。"""
        self.pa.write({'location': 'MAPX 工程 PA 的地點'})
        with patch.object(project_geo, 'GEOCODE_BATCH_LIMIT', 100000):
            result, calls, _sleeps = self._geocode(self.sup, 'project', {'MAPX 工程 PA 的地點': [TAIPEI]})
        self.assertIn(self.pa.id, [item['id'] for item in result['located']])
        self.assertEqual(len(result['located']), 1)
        self.assertEqual((self.pa.latitude, self.pa.longitude, self.pa.dash_geo_source), (25.0478, 121.5319, 'geocoded'))
        self.assertNotIn(self.pa.name, str(calls), '工程名稱不能送出去')
        self.assertNotIn(self.pa.code, str(calls))

    def test_geocode_can_be_switched_off(self):
        self.env['ir.config_parameter'].sudo().set_param(GEOCODE_PARAM, 'OFF')
        self.assertFalse(self.Project.with_user(self.sup).get_dash_map_extras()['geocode_enabled'])
        with self.assertRaises(UserError):
            self._geocode(self.sup, 'tender', {})
        self.env['ir.config_parameter'].sudo().set_param(GEOCODE_PARAM, 'https://geocoder.example.invalid/search')
        self._tender('自架服務', location='MAPX 自架')
        _result, calls, _sleeps = self._geocode(self.sup, 'tender', {'MAPX 自架': [TAIPEI]})
        self.assertEqual(calls[0]['url'], 'https://geocoder.example.invalid/search')
        with self.assertRaises(UserError):
            self.Project.with_user(self.sup).action_dash_geocode('nope')

    def test_geocode_spacing_holds_across_calls(self):
        """「一秒一個請求」要跨呼叫成立（淞源權限審查 low #7）：連按兩次（或兩個人前後按），
        第二次的第一個請求也要和上一次的最後一個隔開。用假的時鐘量：sleep 推進時鐘、送請求時記下時鐘。"""
        clock, sent_at = [0.0], []

        def fake_sleep(seconds):
            clock[0] += seconds

        def fake_get(url, params=None, headers=None, timeout=None):
            sent_at.append(clock[0])
            response = MagicMock()
            response.json.return_value = [TAIPEI]
            response.raise_for_status.return_value = None
            return response

        for index in range(2):
            self._tender('連按 %s' % index, location='MAPX 連按 %s' % index)
            with patch.object(project_geo.requests, 'get', side_effect=fake_get), \
                    patch.object(project_geo.time, 'sleep', side_effect=fake_sleep):
                result = self.Project.with_user(self.sup).action_dash_geocode('tender')
            self.assertEqual(len(result['located']), 1, '夾具：每次剛好查一筆')
        self.assertEqual(len(sent_at), 2)
        self.assertGreaterEqual(sent_at[1] - sent_at[0], 1, '兩次呼叫之間的請求也要隔一秒以上')

    def test_geocode_refuses_while_another_call_is_running(self):
        """同一時間只讓一個自動定位在跑（不同請求、不同 worker 也一樣；淞源權限審查 low #7）：
        別人正在查（另一條資料庫連線拿著鎖）時回「請稍候」，一個請求都不送；別人查完就可以了。"""
        lock_key = getattr(project_geo, 'GEOCODE_LOCK_KEY', None)
        self.assertIsNotNone(lock_key, '要有跨請求的鎖')
        tender = self._tender('同時按', location='MAPX 同時按')
        other = db_connect(self.env.cr.dbname).cursor()
        try:
            other.execute('SELECT pg_try_advisory_xact_lock(%s)', [lock_key])
            self.assertTrue(other.fetchone()[0], '前提：另一條連線拿得到鎖')
            calls = []
            with patch.object(project_geo.requests, 'get', side_effect=fake_service({}, calls)), \
                    patch.object(project_geo.time, 'sleep'):
                with self.assertRaises(UserError) as caught:
                    self.Project.with_user(self.sup).action_dash_geocode('tender')
            self.assertIn('請稍候', str(caught.exception))
            self.assertEqual(calls, [], '別人正在查：一個請求都不送')
            other.rollback()            # 別人查完（交易結束，鎖放開）
        finally:
            other.close()
        result, calls, _sleeps = self._geocode(self.sup, 'tender', {'MAPX 同時按': [TAIPEI]})
        self.assertEqual([item['id'] for item in result['located']], [tender.id])

    # ── 外部標案的所屬公司（S4 寫後檢查）─────────────────────────────────
    def test_tender_cannot_be_moved_outside_allowed_companies(self):
        """有編輯權的帳號不能把外部標案的所屬公司改成自己允許公司以外的（淞源權限審查 low #6）：
        核心只在寫入「前」用舊值檢查規則，改完那一筆就落到別家公司。允許公司內換公司照常。"""
        tender = self._tender('改公司')
        with self.assertRaises(AccessError), self.cr.savepoint():
            tender.with_user(self.sup).write({'company_id': self.co_a.id})
        self.env.invalidate_all()
        self.assertEqual(tender.company_id, self.co_s, '被拒之後資料沒變')
        both = self._user('dashb_sup_sb', ['base.group_user', SUPERVISOR_ADMIN], self.co_s, self.co_s | self.co_b)
        tender.with_user(both).write({'company_id': self.co_b.id})
        self.assertEqual(tender.company_id, self.co_b)

    def test_tender_write_guard_fields_match_its_rules(self):
        """寫後檢查要盯的欄位＝外部標案的全域規則用得到、寫得進去的欄位（從資料庫的規則推，不抄實作）。"""
        context = dict(self.env['ir.rule']._eval_context(), company_ids=[])
        rules = self.env['ir.rule'].sudo().search([('model_id.model', '=', TENDER_MODEL), ('global', '=', True)])
        self.assertTrue(rules, '前提：外部標案有全域規則')
        derived = {leaf[0].split('.', 1)[0] for rule in rules for leaf in safe_eval(rule.domain_force, context)
                   if expression.is_leaf(leaf)} - set(LOG_ACCESS_COLUMNS)
        watched = getattr(company_rule_write_guard, 'COMPANY_OWNED_RULE_FIELDS', {}).get(TENDER_MODEL, frozenset())
        self.assertEqual(set(watched), derived)

    # ── 其他 ────────────────────────────────────────────────────────────
    def test_tender_coordinates_are_validated(self):
        for vals in ({'latitude': 121.5, 'longitude': 25.0}, {'latitude': 25.0, 'longitude': 250.0}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._tender('座標填反', **vals)
        self._tender('沒填座標')        # 0 視為沒填

    def test_methods_are_on_the_gate_allowlist(self):
        for method in MAP_METHODS:
            self.assertIn(('project.project', method), DASHBOARD_METHODS)
            self.assertEqual(gate_verdict(self.env(user=self.mgr), 'project.project', method), [])

    def test_import_template_matches_field_labels(self):
        from openpyxl import load_workbook
        templates = self.Tender.get_import_templates()
        self.assertEqual(len(templates), 1)
        relative = templates[0]['template'].split('/construction_company_dashboard/', 1)[1]
        workbook = load_workbook('%s/%s' % (get_module_path('construction_company_dashboard'), relative))
        headers = [cell.value for cell in workbook.worksheets[0][1]]
        labels = {field.string for field in self.Tender._fields.values()}
        self.assertTrue(headers)
        self.assertEqual([header for header in headers if header not in labels], [], '範本的欄名要等於欄位的中文標籤')
        self.assertIn('標案名稱', headers)
