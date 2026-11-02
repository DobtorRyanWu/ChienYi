# -*- coding: utf-8 -*-
"""一般式進度報告同步累計進度（B8，2026-11-02）。

原本同時要求 is_latest_version 與 state='active'：進度表有新草稿時，最新版是草稿，
使用中的舊版不是最新版，兩個條件交集為空，報告的預定／實際累計進度靜默留 0。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

PLANNED = (10.0, 20.0)
ACTUAL_FIRST = 4.0
LINE_DAYS = 10


@tagged('post_install', '-at_install', 'construction_general')
class TestProgressReportSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.d0 = fields.Date.today() - timedelta(days=30)
        cls.project = cls.env['project.project'].create({
            'name': '進度報告同步測試', 'code': 'GEN-SYNC', 'project_type': 'general',
            'company_id': cls.env.company.id})

    def _schedule(self, state, plans, actual_first=0.0):
        sch = self.env['progress.schedule'].create({
            'project_id': self.project.id, 'change_date': self.d0})
        Line = self.env['progress.schedule.line'].with_context(allow_sync_progress=True)
        for idx, plan in enumerate(plans):
            start = self.d0 + timedelta(days=idx * LINE_DAYS)
            Line.create({
                'schedule_id': sch.id, 'sequence': (idx + 1) * 10,
                'date_start': start, 'date_end': start + timedelta(days=LINE_DAYS - 1),
                'planned_progress': plan, 'actual_progress': actual_first if idx == 0 else 0.0})
        if state != 'draft':
            sch.write({'state': state})
        return sch

    def _report(self):
        return self.env['general.progress.report'].create({
            'project_id': self.project.id,
            'period_start': self.d0, 'period_end': self.d0 + timedelta(days=LINE_DAYS - 1)})

    def test_sync_uses_active_when_newer_draft_exists(self):
        v1 = self._schedule('active', PLANNED, actual_first=ACTUAL_FIRST)
        self._schedule('draft', (50.0, 90.0))          # v2 草稿 → v2 才是 is_latest_version
        self.assertFalse(v1.is_latest_version, '測試前提：使用中的 v1 不是最新版')
        report = self._report()
        report._sync_cumulative_progress()
        self.assertEqual(report.planned_progress, PLANNED[0])
        self.assertEqual(report.actual_progress, ACTUAL_FIRST)

    def test_sync_takes_highest_active_version(self):
        self._schedule('archived', (30.0, 60.0), actual_first=1.0)
        self._schedule('active', PLANNED, actual_first=ACTUAL_FIRST)
        report = self._report()
        report._sync_cumulative_progress()
        self.assertEqual((report.planned_progress, report.actual_progress), (PLANNED[0], ACTUAL_FIRST))
