# -*- coding: utf-8 -*-
"""公司儀表板指標（合約 §5、§10 B 列）。

自己造資料（時間凍結在台灣 2026-11-05 週四 12:00）：營造廠 A、B、監造公司 S（新公司，看的人只看得到這些測試資料，
所以期望值是確切數字）。
工程：PA（只有 A）、PS（A＋B 共用）、PB（只有 B）、PR（預約式、只有 A）、PN（未開始、只有 A）、PE（2015 開工、只有 A）。
帳號：監造方、A 的營造廠主管（已啟用兩步驟驗證）、A 的營造廠主管（未啟用）、只有內部使用者群組的後台帳號。

期望值由測試依資料寫死（不是拿實作再算一次）；斷言打在看的人看得到的數字與狀態，筆數兩個方向都比。
"""
import base64
import importlib.util
import os
import re
from datetime import date, datetime

from freezegun import freeze_time
from lxml import etree

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

from odoo.addons.construction_supervision_base.utils.local_date import local_today, to_local_date

from .test_scope_rules import require_totp

MANAGER_GROUP = 'construction_company_dashboard.group_contractor_manager'
SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'
TOTP_FIXTURE_SECRET = 'JBSWY3DPEHPK3PXP'
PNG_B64 = base64.b64encode(
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
    b'\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
FROZEN_NOW = '2026-11-05 04:00:00'      # UTC；台灣 2026-11-05 12:00（週四，工作天）
TODAY = date(2026, 11, 5)
FOUND_DATE = date(2026, 10, 1)       # 缺失發現日（期限不得早於它）
# 會出現在使用者輸入欄位裡的記號：SVG 裡一個都不能有
USER_MARK = 'DASHMARK'
EVIL_NAME = f'<script>alert(1)</script>{USER_MARK}"\'&'
# SVG 允許的元素、屬性與非數字屬性值（測試獨立寫一份）
SVG_NS = 'http://www.w3.org/2000/svg'
SVG_TAGS = {'svg', 'rect', 'polyline', 'line'}
SVG_ATTRS = {'class', 'viewBox', 'width', 'height', 'preserveAspectRatio', 'role', 'aria-label', 'x', 'y',
             'fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'points', 'x1', 'y1', 'x2', 'y2'}
SVG_FIXED_VALUES = {'o_dash_scurve', 'o_dash_scurve_frame', 'o_dash_scurve_planned', 'o_dash_scurve_actual',
                    'o_dash_scurve_today', 'none', 'img', '進度 S 曲線', '#e2e8f0', '#94a3b8', '#2563eb',
                    '#f97316'}
NUMERIC_VALUE = re.compile(r'^[0-9. ,]+$')
PHOTO_MIGRATION = ('migrations', '18.0.3.8.0', 'post-migrate.py')


def utc(*args):
    return datetime(*args)


class DashIndicatorCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_a = Company.create({'name': 'DASHB 營造 A', 'company_type': 'contractor'})
        cls.co_b = Company.create({'name': 'DASHB 營造 B', 'company_type': 'contractor'})
        cls.co_s = Company.create({'name': 'DASHB 監造 S', 'company_type': 'supervision'})
        a, b, ab = [(6, 0, cls.co_a.ids)], [(6, 0, cls.co_b.ids)], [(6, 0, (cls.co_a | cls.co_b).ids)]
        cls.pa = cls._project(EVIL_NAME, 'DASHB-PA', a, date(2026, 11, 2), date(2026, 11, 30))
        cls.ps = cls._project('DASHB 共用', 'DASHB-PS', ab, date(2026, 11, 2), date(2026, 11, 30))
        cls.pb = cls._project('DASHB 只有 B', 'DASHB-PB', b, date(2026, 11, 2), date(2026, 11, 30))
        cls.pr = cls._project('DASHB 預約式', 'DASHB-PR', a, date(2026, 11, 2), date(2026, 11, 30),
                              ptype='reservation')
        cls.pn = cls._project('DASHB 未開始', 'DASHB-PN', a, date(2026, 12, 1), date(2026, 12, 31), state='draft')
        cls.pe = cls._project('DASHB 2015 開工', 'DASHB-PE', a, date(2015, 4, 2), date(2027, 6, 30))
        cls.employee = env['hr.employee'].create({'name': 'DASHB 填表人', 'company_id': cls.co_s.id})
        cls.task = env['project.task'].create({
            'name': 'DASHB 工項', 'project_id': cls.pa.id, 'item_no': '1', 'unit': '式',
            'planned_qty': 10.0, 'unit_price': 100.0})

        # 帳號
        cls.sup = cls._user('dashb_sup', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s)
        cls.mgr = cls._user('dashb_mgr', [MANAGER_GROUP], cls.co_s, cls.co_s | cls.co_a, scope=cls.co_a)
        cls.mgr.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
        cls.mgr_nototp = cls._user('dashb_mgr_nototp', [MANAGER_GROUP], cls.co_s, cls.co_s | cls.co_a,
                                   scope=cls.co_a)
        cls.plain = cls._user('dashb_plain', ['base.group_user'], cls.co_s)

        # 進度表：PA 兩個區間，今天是第二區間第一天 → 今天的累計預定 10、實際 5（內插比例 0）；日誌要先有進度表
        cls.pa_schedule = cls._schedule(cls.pa, [(date(2026, 11, 2), date(2026, 11, 4), 10.0, 5.0),
                                                 (date(2026, 11, 5), date(2026, 11, 14), 20.0, 0.0)],
                                        reason=EVIL_NAME)
        # 日誌：PA 今天一張（編輯中）、昨天一張
        Log = env['daily.log.sheet']
        cls.log_today = Log.create({'supervision_project_id': cls.pa.id, 'employee_id': cls.employee.id,
                                    'log_date': TODAY})
        Log.create({'supervision_project_id': cls.pa.id, 'employee_id': cls.employee.id,
                    'log_date': date(2026, 11, 4)})

        # 照片：PA 今天 8 張（含台灣 00:00、07:59、08:00 三個邊界）＋台灣昨天 23:59 一張＋今天封存一張
        cls.pa_today_photos = env['supervision.photo']
        for shot_at in (utc(2026, 11, 4, 16, 0), utc(2026, 11, 4, 23, 59), utc(2026, 11, 5, 0, 0),
                        utc(2026, 11, 5, 1, 0), utc(2026, 11, 5, 2, 0), utc(2026, 11, 5, 3, 0),
                        utc(2026, 11, 5, 3, 30), utc(2026, 11, 5, 3, 45)):
            cls.pa_today_photos |= cls._photo(cls.pa, shot_at)
        cls.photo_tw_yesterday = cls._photo(cls.pa, utc(2026, 11, 4, 15, 59))
        cls._photo(cls.pa, utc(2026, 11, 5, 1, 30)).write({'active': False})
        # PS：A、B 各一張、未歸屬一張（共用工程、監造方建立 → 歸屬空白）
        cls._photo(cls.ps, utc(2026, 11, 5, 1, 0), cls.co_a)
        cls._photo(cls.ps, utc(2026, 11, 5, 1, 0), cls.co_b)
        cls.ps_blank_photo = cls._photo(cls.ps, utc(2026, 11, 5, 1, 0))

        # 缺失：PA 待改 4（草稿、已通知×2、已改善）、逾期 1；已驗證、結案不算
        cls._defect(cls.pa, 'draft')
        cls._defect(cls.pa, 'notified', deadline=date(2026, 11, 4))     # 逾期
        cls._defect(cls.pa, 'notified', deadline=TODAY)                  # 今天到期：不算逾期
        cls._defect(cls.pa, 'improved', deadline=date(2026, 11, 1))     # 已改善：待改但不逾期
        cls._defect(cls.pa, 'verified', deadline=date(2026, 11, 1))
        cls._defect(cls.pa, 'closed', deadline=date(2026, 11, 1))
        # PS：A、B、未歸屬各一筆逾期
        cls._defect(cls.ps, 'notified', deadline=date(2026, 11, 1), company=cls.co_a)
        cls._defect(cls.ps, 'notified', deadline=date(2026, 11, 1), company=cls.co_b)
        cls.ps_blank_defect = cls._defect(cls.ps, 'notified', deadline=date(2026, 11, 1))
        # PB：B 一筆待改
        cls._defect(cls.pb, 'notified')
        # PR（預約式）：一筆逾期
        slip = env['reservation.notification.slip'].create({
            'project_id': cls.pr.id, 'location': 'DASHB 地點', 'slip_no': 1})
        slip.sudo().write({'state': 'in_progress'})
        cls._defect(cls.pr, 'notified', deadline=date(2026, 11, 1), model='reservation.defect.improvement',
                    extra={'slip_id': slip.id})

        # 檢試驗：PA 尚未檢驗 2、檢驗完成 1
        Test = env['supervision.test.record']
        standard = env['supervision.test.standard'].create({
            'name': 'DASHB 抗壓', 'material': '預拌混凝土', 'project_id': cls.pa.id})
        for _i in range(2):
            Test.create({'project_id': cls.pa.id, 'standard_id': standard.id})
        cls.test_done = Test.create({'project_id': cls.pa.id, 'standard_id': standard.id, 'result': 'pass'})

        # 估驗：PA 10/15 已核定、11/03 已歸檔、11/04 草稿
        Estimate = env['payment.estimate']
        cls.est = {}
        for key, day, state in (('oct', date(2026, 10, 15), 'approved'), ('nov3', date(2026, 11, 3), 'archived'),
                                ('nov4', date(2026, 11, 4), 'draft')):
            est = Estimate.create({'project_id': cls.pa.id, 'estimate_date': day})
            env['payment.estimate.line'].create({
                'estimate_id': est.id, 'task_id': cls.task.id, 'estimate_qty': 1.0, 'unit_price': 100.0})
            if state != 'draft':
                est.sudo().write({'state': state})
            cls.est[key] = est

        # PS：v1 歸檔、v2 使用中且連了兩張變更單——PS 的（A 讀得到）與 PB 的（A 讀不到）
        cls.co_ps = env['contract.change.order'].create({'project_id': cls.ps.id, 'name': 'DASHB 變更 PS'})
        cls.co_pb = env['contract.change.order'].create({'project_id': cls.pb.id, 'name': f'DASHB 變更 PB {USER_MARK}'})
        cls._schedule(cls.ps, [(date(2026, 11, 2), date(2026, 11, 14), 50.0, 10.0)], state='archived')
        cls.ps_v2 = cls._schedule(cls.ps, [(date(2026, 11, 2), date(2026, 11, 14), 40.0, 10.0)],
                                  change_date=date(2026, 11, 3))
        cls.ps_v2.write({'related_change_order_ids': [(6, 0, (cls.co_ps | cls.co_pb).ids)]})

    # ── 資料工廠 ────────────────────────────────────────────────────────
    @classmethod
    def _project(cls, name, code, contractors, start, end, ptype='general', state='construction'):
        project = cls.env['project.project'].create({
            'name': name, 'code': code, 'project_type': ptype, 'state': state,
            'company_id': cls.co_s.id, 'contractor_company_ids': contractors,
            'contract_start_date': start, 'contract_end_date': end})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': project.id, 'supervision_prefix': code.replace('-', '') + 'S',
            'contractor_prefix': code.replace('-', '') + 'C'})
        return project

    @classmethod
    def _user(cls, login, groups, company, companies=None, scope=None):
        vals = {'name': login, 'login': login, 'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
                'company_id': company.id, 'company_ids': [(6, 0, (companies or company).ids)]}
        if scope:
            vals['dash_scope_company_id'] = scope.id
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    @classmethod
    def _photo(cls, project, shot_at, company=None):
        att = cls.env['ir.attachment'].create({
            'name': 'dashb.png', 'datas': PNG_B64, 'mimetype': 'image/png', 'public': False,
            'res_model': 'supervision.photo'})
        vals = {'project_id': project.id, 'attachment_id': att.id, 'shot_at': shot_at}
        if company:
            vals['contractor_company_id'] = company.id
        return cls.env['supervision.photo'].create(vals)

    @classmethod
    def _defect(cls, project, state, deadline=None, company=None, model='general.defect.improvement', extra=None):
        vals = {'project_id': project.id, 'record_type': 'supervision', 'check_type': 'construction',
                'defect_category': 'workmanship', 'defect_description': 'DASHB 缺失', 'defect_location': 'B1',
                'source_type': 'daily_check', 'state': state, 'deadline': deadline,
                'found_date': FOUND_DATE, 'notification_date': FOUND_DATE}
        if company:
            vals['contractor_company_id'] = company.id
        vals.update(extra or {})
        if model == 'reservation.defect.improvement':
            vals.pop('project_id')
        return cls.env[model].create(vals)

    @classmethod
    def _schedule(cls, project, lines, state='active', change_date=None, reason=False):
        schedule = cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': change_date or date(2026, 11, 1),
            'original_end_date': project.contract_end_date, 'change_reason': reason})
        Line = cls.env['progress.schedule.line'].with_context(allow_sync_progress=True)
        for seq, (start, end, planned, actual) in enumerate(lines, start=1):
            Line.create({'schedule_id': schedule.id, 'sequence': seq * 10, 'date_start': start, 'date_end': end,
                         'planned_progress': planned, 'actual_progress': actual})
        schedule.write({'state': state})
        return schedule

    # ── 量測 ────────────────────────────────────────────────────────────
    def _as(self, user, records):
        return records.with_user(user).with_context(active_test=False)

    def _drill_count(self, user, records, key, model_name=None):
        action = self._as(user, records).action_dash_drilldown(key, model_name)
        Model = self.env[action['res_model']].with_user(user).with_context(active_test=False)
        return Model.search_count(action['domain'])


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestDashboardIndicators(DashIndicatorCase):

    # ── 台灣日期 ────────────────────────────────────────────────────────
    def test_local_today_0759_0800_boundary(self):
        """台灣 07:59 與 08:00 都是同一天（UTC 日期在 08:00 才翻）；23:59／00:00 才換日。"""
        cases = [('2026-11-04 15:59:59', date(2026, 11, 4)), ('2026-11-04 16:00:00', TODAY),
                 ('2026-11-04 23:59:00', TODAY), ('2026-11-05 00:00:00', TODAY)]
        for frozen, expected in cases:
            with freeze_time(frozen):
                self.assertEqual(local_today(), expected, frozen)
        with freeze_time('2026-11-04 23:59:00'):
            self.assertEqual(fields.Date.today(), date(2026, 11, 4), '前提：UTC 日期仍是前一天')
        self.assertEqual(to_local_date(utc(2026, 11, 4, 23, 59)), TODAY)
        self.assertIsNone(to_local_date(False))

    def test_photo_shot_date_is_taiwan_date(self):
        """照片日期＝台灣日期：台灣 07:59、08:00、00:00 上傳的都算 11-05，23:59 的算 11-04。"""
        self.assertEqual(set(self.pa_today_photos.mapped('shot_date')), {TODAY})
        self.assertEqual(self.photo_tw_yesterday.shot_date, date(2026, 11, 4))

    @freeze_time('2026-11-04 23:59:00')
    def test_overdue_uses_taiwan_date_at_0759(self):
        """台灣 11-05 07:59：期限 11-04 的缺失已逾期（UTC 還是 11-04，舊算法要到 08:00 才翻）。"""
        defect = self._defect(self.pa, 'notified', deadline=date(2026, 11, 4))
        self.assertTrue(defect.is_overdue, '儲存的逾期旗標以台灣日期判斷')
        Defect = self.env['general.defect.improvement']
        self.assertIn(defect, Defect.search(Defect._dash_overdue_domain()))
        due_today = self._defect(self.pa, 'notified', deadline=TODAY)
        self.assertFalse(due_today.is_overdue)
        self.assertNotIn(due_today, Defect.search(Defect._dash_overdue_domain()))

    @freeze_time('2026-11-04 23:59:00')
    def test_progress_chart_today_is_taiwan_date_at_0759(self):
        """台灣 11-05 07:59：進度圖表的「今天」是 11-05，當天的實際進度要畫（UTC 還是 11-04）。"""
        data = self._as(self.sup, self.pa).get_progress_chart_data()
        self.assertEqual(data['today'], TODAY.isoformat())
        actual = dict(zip(data['dates'], data['actual']))
        self.assertIsNotNone(actual[TODAY.isoformat()])
        self.assertIsNone(actual[date(2026, 11, 6).isoformat()])

    @freeze_time('2026-11-04 23:59:00')
    def test_portal_project_detail_today_is_taiwan_date_at_0759(self):
        """前台工程首頁台灣 07:59 的今日日誌、今日照片數＝台灣的今天（11-05），不是 UTC 的 11-04。"""
        self.env.flush_all()
        self.env.invalidate_all()
        seen = {}
        with MockRequest(self.env(user=self.sup)) as req:
            req.render = lambda tpl, vals=None, **k: seen.update(vals=vals) or '<render>'
            ConstructionPortal().portal_construction_project_detail(self.pa.id)
        self.assertEqual(seen['vals']['today_log'], self.log_today)
        self.assertEqual(seen['vals']['today_photo_count'], 8)

    # ── 每個指標一案（監造方）─────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_log_today_states(self):
        """今日日誌：PA 已填（編輯中也算）／PS 未填／PN 未開始＝不需填／週六＝不需填。"""
        self.assertEqual(self.log_today.state, 'draft', '前提：編輯中')
        pa, ps, pn = self._as(self.sup, self.pa | self.ps | self.pn)
        self.assertEqual((pa.dash_log_today, ps.dash_log_today, pn.dash_log_today),
                         ('filled', 'missing', 'not_required'))
        with freeze_time('2026-11-07 04:00:00'):     # 台灣週六
            self.env.invalidate_all()                # 不儲存欄位的快取：換一天要重算
            self.assertEqual(self._as(self.sup, self.ps).dash_log_today, 'not_required')

    @freeze_time('2016-06-01 04:00:00')
    def test_log_today_no_calendar(self):
        """今天所在年度缺政府辦公日曆（2016）→ 缺日曆，不是「未填」。"""
        self.assertEqual(self._as(self.sup, self.ps).dash_log_today, 'no_calendar')
        kpis = self._as(self.sup, self.env['project.project']).get_dash_company_kpis()['kpis']
        self.assertEqual(kpis['log_missing']['status'], 'no_calendar')
        self.assertEqual(kpis['log_missing']['message'], '缺 2016 年政府辦公日曆')
        self.assertIsNone(kpis['log_missing']['count'])

    @freeze_time(FROZEN_NOW)
    def test_workday_elapsed_total_and_notes(self):
        """PA：11-02（一）開工到今天 11-05（四）＝4 工作天，到 11-30＝21；PE：2015 開工 → 缺 2015、2016 年。"""
        pa = self._as(self.sup, self.pa)
        self.assertEqual((pa.dash_workday_elapsed, pa.dash_workday_total, pa.dash_workday_state), (4, 21, 'ok'))
        self.assertFalse(pa.dash_workday_note)
        pe = self._as(self.sup, self.pe)
        self.assertEqual(pe.dash_workday_state, 'no_calendar')
        self.assertEqual(pe.dash_workday_note, '缺 2015、2016 年政府辦公日曆')

    @freeze_time(FROZEN_NOW)
    def test_workday_estimated_and_overrun(self):
        """完工日在未公告年度 → 預估；實際開工日優先；已過工期 → 「超過 N 工作天」。"""
        self.pa.write({'contract_end_date': date(2028, 1, 31)})
        pa = self._as(self.sup, self.pa)
        self.assertEqual(pa.dash_workday_state, 'estimated')
        self.assertIn('含未公告年度（2028），為預估', pa.dash_workday_note)
        # 實際開工 10-27（二）優先於契約開工 10-20；完工 10-30（五）＝4 工作天；到今天 11-05＝8 工作天 → 超過 4
        # （10-26 是光復節補假，故意避開；若誤用契約開工日，總工作天會是 8）
        self.pa.write({'contract_start_date': date(2026, 10, 20), 'actual_start_date': date(2026, 10, 27),
                       'contract_end_date': date(2026, 10, 30)})
        self.env.invalidate_all()
        pa = self._as(self.sup, self.pa)
        self.assertEqual((pa.dash_workday_elapsed, pa.dash_workday_total), (8, 4))
        self.assertEqual(pa.dash_workday_note, '超過 4 工作天')
        self.pa.write({'contract_end_date': False})
        self.env.invalidate_all()
        pa = self._as(self.sup, self.pa)
        self.assertEqual((pa.dash_workday_state, pa.dash_workday_note), ('no_dates', '未設契約完工日'))

    @freeze_time(FROZEN_NOW)
    def test_workday_elapsed_stops_at_actual_end(self):
        """有實際完工日：已過工作天算到實際完工日為止，不算到今天（合約 §0b-15）。"""
        pa = self._as(self.sup, self.pa)
        self.assertEqual(pa.dash_workday_elapsed, 4, '前提：沒有完工日時算到今天 11-05')
        self.pa.write({'actual_end_date': date(2026, 11, 3)})
        self.env.invalidate_all()
        pa = self._as(self.sup, self.pa)
        # 11-02（一）、11-03（二）
        self.assertEqual((pa.dash_workday_elapsed, pa.dash_workday_total), (2, 21))

    @freeze_time(FROZEN_NOW)
    def test_today_photos(self):
        """今日照片：PA 8 張（不含台灣昨天 23:59、不含封存），卡片最多 6 張且是最新的。"""
        pa = self._as(self.sup, self.pa)
        self.assertEqual(pa.dash_today_photo_count, 8)
        latest = self.pa_today_photos.sorted(lambda p: (p.shot_at, p.id), reverse=True)[:6]
        self.assertEqual(pa.dash_today_photo_ids.ids, latest.ids)
        self.assertNotIn(self.photo_tw_yesterday, pa.dash_today_photo_ids)

    @freeze_time(FROZEN_NOW)
    def test_defect_counts(self):
        """待改＝不是已驗證、結案（含草稿、已改善）；逾期＝期限早於今天且還沒改善。預約式工程數預約式缺失。"""
        pa, ps, pr = self._as(self.sup, self.pa | self.ps | self.pr)
        self.assertEqual((pa.dash_open_defect_count, pa.dash_overdue_defect_count), (4, 1))
        self.assertEqual((ps.dash_open_defect_count, ps.dash_overdue_defect_count), (3, 3))
        self.assertEqual((pr.dash_open_defect_count, pr.dash_overdue_defect_count), (1, 1))

    @freeze_time(FROZEN_NOW)
    def test_pending_tests(self):
        """檢驗待補＝尚未檢驗（檢驗完成的不算）。"""
        self.assertEqual(self.test_done.processing_status, 'completed', '前提')
        self.assertEqual(self._as(self.sup, self.pa).dash_pending_test_count, 2)

    @freeze_time(FROZEN_NOW)
    def test_estimates(self):
        """最近一期＝草稿以外期數最大（合約 §0b-17）；累計＝草稿以外各期；本月＝估驗日期在 11 月、草稿以外（§0b-14）。"""
        est = self.est
        self.assertTrue(all(e.subtotal > 0 for e in est.values()), '前提：每期都有金額（防恆真）')
        latest = max(est.values(), key=lambda e: e.estimate_no)
        self.assertEqual(latest, est['nov4'], '前提：期數最大的是草稿那期（防恆真）')
        pa = self._as(self.sup, self.pa)
        # 合約 §0b-17（11-05 定案）改成排除草稿：原本斷言含草稿的 11/04，現在是 11/03
        self.assertEqual(pa.dash_latest_estimate_id, est['nov3'])
        self.assertAlmostEqual(pa.dash_estimate_cum_amount, est['oct'].subtotal + est['nov3'].subtotal)
        self.assertAlmostEqual(pa.dash_estimate_month_amount, est['nov3'].subtotal)

    @freeze_time(FROZEN_NOW)
    def test_latest_estimate_excludes_draft_both_ways(self):
        """最近一期排除草稿（合約 §0b-17）：11/04 是草稿 → 11/03；提出（待核定）後 → 11/04。卡片、單一工程頁同一份。"""
        est = self.est
        for state, expected in (('draft', est['nov3']), ('pending_approval', est['nov4'])):
            est['nov4'].sudo().write({'state': state})
            self.env.invalidate_all()
            pa = self._as(self.sup, self.pa)
            self.assertEqual(pa.dash_latest_estimate_id, expected, state)
            self.assertEqual(self._as(self.mgr, self.pa).dash_latest_estimate_id, expected, f'營造廠主管 {state}')

    def _estimate_amounts_with_nov4(self, state):
        """把 11/04 那期改成指定狀態，回傳 (卡片累計, 卡片本月, 公司合計累計, 公司合計本月, 不含 11/04 的累計, 本月)。"""
        est = self.est
        self.assertGreater(est['nov4'].subtotal, 0, '前提：11/04 那期有金額')
        est['nov4'].sudo().write({'state': state})
        self.env.invalidate_all()
        pa = self._as(self.sup, self.pa)
        kpis = self._as(self.mgr, self.env['project.project']).get_dash_company_kpis()['kpis']
        return (pa.dash_estimate_cum_amount, pa.dash_estimate_month_amount,
                kpis['estimate_cum']['amount'], kpis['month_estimate']['amount'],
                est['oct'].subtotal + est['nov3'].subtotal, est['nov3'].subtotal)

    @freeze_time(FROZEN_NOW)
    def test_estimate_draft_not_counted(self):
        """草稿（尚未提出）不算進累計與本月（卡片、公司合計都一樣）。"""
        cum, month, kpi_cum, kpi_month, base_cum, base_month = self._estimate_amounts_with_nov4('draft')
        self.assertAlmostEqual(cum, base_cum)
        self.assertAlmostEqual(month, base_month)
        self.assertAlmostEqual(kpi_cum, base_cum)
        self.assertAlmostEqual(kpi_month, base_month)

    @freeze_time(FROZEN_NOW)
    def test_estimate_pending_counted(self):
        """待核定（已提出）要算：舊系統一提出就算進「總計估驗金額」，不看核定。"""
        cum, month, kpi_cum, kpi_month, base_cum, base_month = self._estimate_amounts_with_nov4('pending_approval')
        nov4 = self.est['nov4'].subtotal
        self.assertAlmostEqual(cum, base_cum + nov4)
        self.assertAlmostEqual(month, base_month + nov4)
        self.assertAlmostEqual(kpi_cum, base_cum + nov4)
        self.assertAlmostEqual(kpi_month, base_month + nov4)

    @freeze_time(FROZEN_NOW)
    def test_estimate_approved_and_archived_counted(self):
        """已核定、已歸檔都算（另外兩期本來就是已核定 10/15、已歸檔 11/03，這裡再把 11/04 依序改成兩種）。"""
        nov4 = self.est['nov4'].subtotal
        for state in ('approved', 'archived'):
            cum, month, kpi_cum, kpi_month, base_cum, base_month = self._estimate_amounts_with_nov4(state)
            self.assertAlmostEqual(cum, base_cum + nov4, state)
            self.assertAlmostEqual(month, base_month + nov4, state)
            self.assertAlmostEqual(kpi_cum, base_cum + nov4, state)
            self.assertAlmostEqual(kpi_month, base_month + nov4, state)

    @freeze_time(FROZEN_NOW)
    def test_progress_values_and_summary_same_numbers(self):
        """進度：今天的累計預定 10、實際 5（手算）；單一工程頁的進度摘要與卡片同一份數字，且不寫入進度表。"""
        pa = self._as(self.sup, self.pa)
        self.assertTrue(pa.dash_has_schedule)
        self.assertEqual((pa.dash_progress_planned, pa.dash_progress_actual, pa.dash_progress_variance),
                         (10.0, 5.0, -5.0))
        # 已存的 current_* 值故意弄成別的：摘要不可讀它，也不可呼叫會寫回的 compute
        self.env.flush_all()
        self.env.cr.execute('UPDATE progress_schedule SET current_cumulative_planned = 77 WHERE id = %s',
                            [self.pa_schedule.id])
        self.pa_schedule.invalidate_recordset(['current_cumulative_planned'])
        summary = self._as(self.sup, self.pa)._dashboard_progress_summary()
        self.assertEqual((summary['cumulative_planned'], summary['cumulative_actual'], summary['variance']),
                         (10.0, 5.0, -5.0))
        self.assertEqual(summary['variance_status'], 'delayed')
        self.env.flush_all()
        self.env.cr.execute('SELECT current_cumulative_planned FROM progress_schedule WHERE id = %s',
                            [self.pa_schedule.id])
        self.assertEqual(self.env.cr.fetchone()[0], 77, '摘要不可寫入進度表')
        pb = self._as(self.sup, self.pb)
        self.assertFalse(pb.dash_has_schedule, '沒建進度表 → 未建，不是 0%')
        self.assertFalse(pb.dash_progress_svg)

    @freeze_time(FROZEN_NOW)
    def test_progress_svg_has_no_user_strings(self):
        """小 S 曲線只含數字與固定標記：工程名稱、版本原因、變更單名稱（含 <script>）一個字都不能出現。"""
        for project in (self.pa, self.ps):
            svg = str(self._as(self.sup, project).dash_progress_svg)
            self.assertTrue(svg.startswith('<svg'), project.code)
            for needle in (USER_MARK, '<script', 'alert', project.code):
                self.assertNotIn(needle, svg)
            root = etree.fromstring(svg.encode())
            for el in root.iter():
                tag = etree.QName(el).localname
                self.assertEqual(etree.QName(el).namespace, SVG_NS)
                self.assertIn(tag, SVG_TAGS)
                self.assertFalse((el.text or '').strip(), f'{tag} 不可有文字')
                self.assertFalse((el.tail or '').strip(), f'{tag} 後面不可有文字')
                for attr, value in el.attrib.items():
                    self.assertIn(attr, SVG_ATTRS, f'{tag}.{attr}')
                    self.assertTrue(NUMERIC_VALUE.match(value) or value in SVG_FIXED_VALUES,
                                    f'{tag}.{attr}={value!r} 不是數字也不是固定標記')
            self.assertEqual(len(root.findall(f'{{{SVG_NS}}}polyline')), 2, '預定與實際兩條線')

    # ── 卡片數＝下鑽筆數 ─────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_card_counts_equal_drilldown(self):
        """每個卡片數字＝下鑽清單筆數（監造方與營造廠主管各算一次）；多來源的指標要指定模型。"""
        fields_by_key = {'today_photo': 'dash_today_photo_count', 'open_defect': 'dash_open_defect_count',
                         'overdue_defect': 'dash_overdue_defect_count', 'pending_test': 'dash_pending_test_count'}
        for user, projects in ((self.sup, self.pa | self.ps | self.pr), (self.mgr, self.pa | self.ps | self.pr)):
            for project in projects:
                for key, field in fields_by_key.items():
                    card = self._as(user, project)[field]
                    self.assertEqual(card, self._drill_count(user, project, key), (user.login, project.code, key))
                log = self._as(user, project).dash_log_today
                self.assertEqual(self._drill_count(user, project, 'log_today'), 1 if log == 'filled' else 0)
                self.assertEqual(self._drill_count(user, project, 'log_filled'), 1 if log == 'filled' else 0)
        with self.assertRaisesRegex(Exception, '請指定'):
            self._as(self.sup, self.env['project.project']).action_dash_drilldown('open_defect')

    def _fixture_share(self, user, key, part_model):
        """某個合計來源裡，屬於測試工程以外的筆數（監造方後台帳號看得到庫裡既有的真實資料）。"""
        fixture = (self.pa | self.ps | self.pb | self.pr | self.pn | self.pe).ids
        action = self._as(user, self.env['project.project']).action_dash_drilldown(key, part_model)
        field = 'id' if part_model == 'project.project' else (
            'supervision_project_id' if part_model == 'daily.log.sheet' else 'project_id')
        Model = self.env[part_model].with_user(user).with_context(active_test=False)
        return Model.search_count(action['domain'] + [(field, 'not in', fixture)])

    @freeze_time(FROZEN_NOW)
    def test_company_kpis_supervision(self):
        """監造方公司合計＝各來源下鑽筆數加總；扣掉庫裡既有資料後，測試資料的部分是確切數字。
        封存工程的未結事項也算、施工中工程只算有效的。"""
        self.pe.write({'active': False})
        Project = self._as(self.sup, self.env['project.project'])
        result = Project.get_dash_company_kpis()
        self.assertFalse(result['blocked_reason'])
        kpis = result['kpis']
        # log_filled＝今日已填日誌的工程數（PA）；log_today 是張數（PA 今天一張）；兩者＋log_missing 見 test_dashboard_page
        expected = {'construction_project': 4, 'log_today': 1, 'log_filled': 1, 'log_missing': 3, 'today_photo': 11,
                    'open_defect': 9, 'overdue_defect': 5, 'pending_test': 2, 'month_estimate': 1,
                    'estimate_cum': 2, 'unattributed': 2}
        self.assertEqual(set(kpis), set(expected))
        outside = {}
        for key, entry in kpis.items():
            self.assertEqual(entry['status'], 'ok', key)
            self.assertEqual(entry['count'], sum(p['count'] for p in entry['parts']), key)
            outside[key] = 0
            for part in entry['parts']:
                self.assertEqual(part['count'], self._drill_count(self.sup, self.env['project.project'], key,
                                                                  part['model']), (key, part['model']))
                outside[key] += self._fixture_share(self.sup, key, part['model'])
        self.assertEqual({k: kpis[k]['count'] - outside[k] for k in kpis}, expected)
        unattributed = {p['model']: p['count'] for p in kpis['unattributed']['parts'] if p['count']}
        self.assertEqual(unattributed, {'general.defect.improvement': 1, 'supervision.photo': 1})
        # 封存工程 PE 的逾期缺失要算進合計；沒有營造廠的工程底下的空白歸屬不算「未歸屬」（那是報表的事）
        before = kpis['overdue_defect']['count']
        self._defect(self.pe, 'notified', deadline=date(2026, 11, 1))
        p0 = self._project('DASHB 沒有營造廠', 'DASHB-P0', [(5, 0, 0)], date(2026, 11, 2), date(2026, 11, 30))
        self._defect(p0, 'notified')
        after = Project.get_dash_company_kpis()['kpis']
        self.assertEqual(after['overdue_defect']['count'], before + 1)
        self.assertEqual(after['unattributed']['count'], kpis['unattributed']['count'])

    # ── 營造廠主管 ─────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_manager_indicators_no_access_error_and_only_own(self):
        """營造廠主管算全部指標不報 AccessError（含進度表連了別家工程變更單、快取先被 sudo 讀過）；只數自家。"""
        # 先以 sudo 讀過變更單（x2many 與名稱的快取不分 sudo）
        self.assertEqual(len(self.ps_v2.sudo().related_change_order_ids.mapped('name')), 2)
        projects = self._as(self.mgr, self.env['project.project']).search([('id', 'in', (
            self.pa | self.ps | self.pb | self.pr | self.pn | self.pe).ids)])
        self.assertEqual(projects, self._as(self.mgr, self.pa | self.ps | self.pr | self.pn | self.pe))
        for project in projects:
            self.assertFalse(project.dash_denied_keys, project.code)
            self.assertFalse(project.dash_error_keys, project.code)
            project.read([name for name in project._fields if name.startswith('dash_')])
        ps = projects.filtered(lambda p: p == self.ps)
        self.assertEqual((ps.dash_open_defect_count, ps.dash_overdue_defect_count, ps.dash_today_photo_count),
                         (1, 1, 1), '共用工程只數 A 的（B 的、未歸屬的看不到）')
        changes = ps.get_progress_chart_data()['version_changes']
        names = [n for c in changes for n in c['change_orders']]
        self.assertEqual(names, [self.co_ps.name], '看不到的變更單不帶名稱')
        kpis = self._as(self.mgr, self.env['project.project']).get_dash_company_kpis()['kpis']
        expected = {'construction_project': 4, 'log_today': 1, 'log_filled': 1, 'log_missing': 3, 'today_photo': 9,
                    'open_defect': 6, 'overdue_defect': 3, 'pending_test': 2, 'month_estimate': 1,
                    'estimate_cum': 2}
        self.assertEqual({k: kpis[k]['count'] for k in expected}, expected)
        self.assertAlmostEqual(kpis['estimate_cum']['amount'], self.est['oct'].subtotal + self.est['nov3'].subtotal)
        self.assertAlmostEqual(kpis['month_estimate']['amount'], self.est['nov3'].subtotal)
        self.assertEqual(kpis['unattributed']['status'], 'not_applicable')
        self.assertTrue(all(kpis[k]['status'] == 'ok' for k in expected))

    @freeze_time(FROZEN_NOW)
    def test_indicator_cache_not_shared_between_users(self):
        """同一個交易裡監造方先讀，營造廠主管再讀同一個工程，數字要是主管自己的（快取鍵含 uid）。"""
        self.assertEqual(self._as(self.sup, self.ps).dash_open_defect_count, 3)
        self.assertEqual(self._as(self.mgr, self.ps).dash_open_defect_count, 1)
        self.assertEqual(self._as(self.sup, self.ps).dash_open_defect_count, 3)

    @freeze_time(FROZEN_NOW)
    @require_totp   # S2 fix2-Z：驗「強制兩步驟驗證時」（DASH_REQUIRE_TOTP 預設 False）
    def test_manager_without_totp_blocked_without_error(self):
        """未啟用兩步驟驗證的營造廠主管：全部「無權限」並附原因，不報錯、不給 0。"""
        result = self._as(self.mgr_nototp, self.env['project.project']).get_dash_company_kpis()
        self.assertEqual(result['blocked_reason'], 'totp_missing')
        for key, entry in result['kpis'].items():
            self.assertEqual(entry['status'], 'no_access', key)
            self.assertIsNone(entry['count'], key)
        pa = self._as(self.mgr_nototp, self.pa)
        pa.dash_open_defect_count  # noqa: B018  讀得到欄位、不丟例外
        self.assertIn('defect', pa.dash_denied_keys.split(','))

    # ── 沒有讀取權 ─────────────────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_no_read_access_marked_not_zero(self):
        """只有內部使用者群組的帳號：讀不到日誌、照片、缺失、檢試驗、進度 → 標「無權限」；估驗讀得到照常算。"""
        pa = self._as(self.plain, self.pa)
        self.assertEqual(set(pa.dash_denied_keys.split(',')), {'log', 'photo', 'defect', 'test', 'progress'})
        self.assertEqual(pa.dash_log_today, 'no_access')
        self.assertFalse(pa.dash_error_keys)
        self.assertAlmostEqual(pa.dash_estimate_month_amount, self.est['nov3'].subtotal)
        kpis = self._as(self.plain, self.env['project.project']).get_dash_company_kpis()['kpis']
        for key in ('log_today', 'log_filled', 'log_missing', 'today_photo', 'open_defect', 'overdue_defect',
                    'pending_test'):
            self.assertEqual(kpis[key]['status'], 'no_access', key)
            self.assertIsNone(kpis[key]['count'], key)
        self.assertEqual(kpis['construction_project']['status'], 'ok')

    # ── 收斂：進度模組的缺失摘要 ─────────────────────────────────────────────
    @freeze_time(FROZEN_NOW)
    def test_defect_summary_uses_open_domain(self):
        """單一工程頁「未改善」＝卡片「待改缺失」（同一個條件方法）。"""
        pa = self._as(self.sup, self.pa)
        self.assertEqual(pa._dashboard_defect_summary()['unimproved_count'], pa.dash_open_defect_count)


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestPhotoShotDateMigration(DashIndicatorCase):
    """照片日期重算（construction_photo 18.0.3.8.0）：只補空值、只改舊公式算錯的，不動人填的與前台上傳的。"""

    def _migration(self):
        path = os.path.join(get_module_path('construction_photo'), *PHOTO_MIGRATION)
        spec = importlib.util.spec_from_file_location('dash_photo_post_migrate', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_recompute_counts_and_values(self):
        migration = self._migration()
        base_fill, base_change, base_skip = migration.classify_shot_dates(self.env.cr)
        night = self.pa_today_photos[1]       # 台灣 07:59（UTC 11-04 23:59）
        blank, old, manual, portal = night, self._photo(self.pa, utc(2026, 11, 4, 22, 0)), \
            self._photo(self.pa, utc(2026, 11, 4, 21, 0)), self._photo(self.pa, utc(2026, 11, 4, 20, 0))
        self.env.flush_all()
        cr = self.env.cr
        cr.execute('UPDATE supervision_photo SET shot_date = NULL WHERE id = %s', [blank.id])
        cr.execute('UPDATE supervision_photo SET shot_date = %s WHERE id IN %s',
                   [date(2026, 11, 4), (old.id, portal.id)])
        cr.execute('UPDATE supervision_photo SET shot_date = %s WHERE id = %s', [date(2026, 10, 1), manual.id])
        cr.execute('UPDATE supervision_photo SET is_portal_uploaded = TRUE WHERE id = %s', [portal.id])
        stats = migration.recompute_shot_dates(cr)
        self.assertEqual(stats, {'filled': len(base_fill) + 1, 'changed': len(base_change) + 1,
                                 'skipped_portal': len(base_skip) + 1})
        (blank | old | manual | portal).invalidate_recordset(['shot_date'])
        self.assertEqual((blank.shot_date, old.shot_date), (TODAY, TODAY))
        self.assertEqual(manual.shot_date, date(2026, 10, 1), '人填的日期不動')
        self.assertEqual(portal.shot_date, date(2026, 11, 4), '前台上傳、分不出是不是人選的：不動')
        again = migration.recompute_shot_dates(cr)
        self.assertEqual((again['filled'], again['changed']), (0, 0), '第二次跑沒有東西要改')

    def test_verification_fails_loudly_when_write_incomplete(self):
        """寫入沒有生效（例：UPDATE 漏了一批）→ 驗算丟例外讓升級失敗，不印「完成」。"""
        migration = self._migration()
        self.env.flush_all()
        self.env.cr.execute('UPDATE supervision_photo SET shot_date = NULL WHERE id = %s', [self.pa_today_photos[0].id])
        migration._write = lambda cr, pairs: None
        with self.assertRaisesRegex(RuntimeError, '驗算不一致'):
            migration.recompute_shot_dates(self.env.cr)
