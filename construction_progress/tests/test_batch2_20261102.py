# -*- coding: utf-8 -*-
"""第 2 批修正（2026-11-02）：進度表圖表、啟用精靈重複日誌、新版本帶實際進度。

B9  圖表不得畫草稿版本；今天之後的實際進度不畫（None），否則曲線掉到 0。
B10 啟用精靈的「已存在日誌」要看同工程同日、不分填表人，換填表人不得建出同日重複日誌。
B26 有實際進度的進度表建新版本不可被 create 守衛擋下；新版本實際進度從 0 開始。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

LINE_DAYS = 10          # 每個區間的天數
PLANNED_V1 = (10.0, 20.0)
PLANNED_V2 = (40.0, 80.0)
ACTUAL_FIRST = 5.0


@tagged('post_install', '-at_install', 'construction_progress')
class TestBatch2Progress(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        # 今天落在第二個區間的第一天：第一區間已過、第二區間（含今天之後）還沒過完
        cls.d0 = fields.Date.today() - timedelta(days=LINE_DAYS)
        cls.d_end = cls.d0 + timedelta(days=2 * LINE_DAYS - 1)
        cls.project = cls.env['project.project'].create({
            'name': '第2批進度測試', 'code': 'PRG-B2', 'project_type': 'general',
            'state': 'construction', 'company_id': company.id,
            'contract_start_date': cls.d0, 'contract_end_date': cls.d_end})
        cls.employee_a = cls.env['hr.employee'].create({'name': '填表人甲', 'company_id': company.id})
        cls.employee_b = cls.env['hr.employee'].create({'name': '填表人乙', 'company_id': company.id})

    def _schedule(self, planned, state='draft', actual_first=0.0, change_date=None):
        sch = self.env['progress.schedule'].create({
            'project_id': self.project.id,
            'change_date': change_date or (self.d0 - timedelta(days=1)),
            'original_end_date': self.d_end,
        })
        Line = self.env['progress.schedule.line'].with_context(allow_sync_progress=True)
        for idx, plan in enumerate(planned):
            start = self.d0 + timedelta(days=idx * LINE_DAYS)
            Line.create({
                'schedule_id': sch.id, 'sequence': (idx + 1) * 10,
                'date_start': start, 'date_end': start + timedelta(days=LINE_DAYS - 1),
                'planned_progress': plan,
                'actual_progress': actual_first if idx == 0 else 0.0})
        if state != 'draft':
            sch.write({'state': state})
        return sch

    # ---- B9 ----
    def test_chart_excludes_draft_version(self):
        v1 = self._schedule(PLANNED_V1, state='active', actual_first=ACTUAL_FIRST)
        self._schedule(PLANNED_V2, change_date=fields.Date.today() - timedelta(days=3))   # v2 草稿
        data = self.project.get_progress_chart_data()
        self.assertEqual(data['version_changes'], [], '草稿版本不該出現在版本變更點')
        self.assertEqual(max(data['dates']), self.d_end.isoformat(), 'v1 應畫到自己的完工日，不被草稿截斷')
        self.assertEqual(max(data['planned']), v1.line_ids.sorted('sequence')[-1].cumulative_planned,
                         '預定進度不得出現草稿版本的值')

    def test_chart_keeps_archived_version(self):
        self._schedule(PLANNED_V1, state='archived', actual_first=ACTUAL_FIRST)
        self._schedule(PLANNED_V2, state='active', change_date=fields.Date.today() - timedelta(days=3))
        data = self.project.get_progress_chart_data()
        self.assertEqual([c['version'] for c in data['version_changes']], [2], '已歸檔的 v1 照舊參與圖表')

    def test_future_actual_is_none(self):
        self._schedule(PLANNED_V1, state='active', actual_first=ACTUAL_FIRST)
        data = self.project.get_progress_chart_data()
        today = fields.Date.today().isoformat()
        past = [a for d, a in zip(data['dates'], data['actual']) if d <= today]
        future = [a for d, a in zip(data['dates'], data['actual']) if d > today]
        self.assertTrue(future, '測試資料要有今天之後的日期')
        self.assertTrue(all(a is None for a in future), '今天之後的實際進度要是 None，而不是 0 或內插值')
        self.assertTrue(all(isinstance(a, float) for a in past), '今天以前（含）仍要有數值')
        self.assertTrue(all(isinstance(p, float) for p in data['planned']), '預定進度整條都要有值')

    # ---- B10 ----
    def _wizard(self, schedule, employee):
        return self.env['progress.activate.wizard'].create({
            'schedule_id': schedule.id, 'employee_id': employee.id})

    def test_second_employee_does_not_duplicate_logs(self):
        sch = self._schedule(PLANNED_V1, state='active')
        total_days = (self.d_end - self.d0).days + 1
        first = self._wizard(sch, self.employee_a)
        self.assertEqual(first._create_daily_logs(), total_days)
        second = self._wizard(sch, self.employee_b)
        self.assertEqual(second.existing_log_count, total_days, '預覽應看到別人名下已建好的日誌')
        self.assertEqual(second._create_daily_logs(), 0, '換填表人不得再建同日日誌')
        sheets = self.env['daily.log.sheet'].search([('supervision_project_id', '=', self.project.id)])
        self.assertEqual(len(sheets), total_days)
        self.assertEqual(len(set(sheets.mapped('log_date'))), total_days, '同工程同日只能有一張日誌')

    # ---- B26 ----
    def test_new_version_of_schedule_with_actual_progress(self):
        v1 = self._schedule(PLANNED_V1, state='active', actual_first=ACTUAL_FIRST)
        self.assertEqual(v1.line_ids.sorted('sequence')[0].actual_progress, ACTUAL_FIRST)
        action = v1.action_create_new_version()
        v2 = self.env['progress.schedule'].browse(action['res_id'])
        self.assertEqual((v2.version, v2.state), (2, 'draft'))
        self.assertEqual(len(v2.line_ids), len(v1.line_ids), '新版本要帶預定進度明細')
        self.assertEqual(v2.line_ids.mapped('actual_progress'), [0.0] * len(v2.line_ids),
                         '新版本實際進度從 0 開始')
        self.assertEqual(v1.line_ids.sorted('sequence')[0].actual_progress, ACTUAL_FIRST, '舊版不受影響')
