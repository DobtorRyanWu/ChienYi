# -*- coding: utf-8 -*-
"""累計進度統一成一套算法（2026-11-24，models/progress_calc.py）：同一天，首頁、進度表、進度報告、
進度曲線同一個數字。

交叉核對打出來的（odoo shell 實測，舊程式）：
- 今天在第 2 段中間：首頁預定 30（那一段結束值）、印的 22；首頁實際 11（不算草稿）、印的 15；
  進度報告（期間到第 13 天）30／11，應 16／6；曲線 21.11／7.44。
- 兩段中間空 10 天：空檔那天的日誌進度表不算（6，應 9）。
- 交界日：印的預定多算後一段一天（12，應 10）；曲線在日誌之前就畫出實際進度。
- 契約變更當天：印的預定用舊版、實際用校正後。
使用者定：草稿日誌也算、首頁預定到今天、一段的預定當天算進去、變更當天用變更後（曲線畫變更前、變更後兩個點）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_supervision_base.utils.local_date import local_today


@tagged('post_install', '-at_install', 'construction_progress')
class TestProgressUnified(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.employee = cls.env['hr.employee'].create({'name': '統一算法測試員工', 'company_id': cls.co.id})

    def _project(self, code, d0, segments, end):
        project = self.env['project.project'].create({
            'name': '統一算法 ' + code, 'code': code, 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': d0, 'contract_end_date': d0 + timedelta(days=end)})
        sched = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': d0})
        for seq, (start, stop, planned) in enumerate(segments, 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': sched.id, 'sequence': seq * 10, 'planned_progress': planned,
                'date_start': d0 + timedelta(days=start), 'date_end': d0 + timedelta(days=stop)})
        sched._do_activate()
        project.write({'state': 'construction'})
        return project, sched

    def _log(self, project, day, pct, state='filled'):
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': self.co.id,
            'employee_id': self.employee.id, 'log_date': day, 'daily_actual_progress': pct})
        if state != 'draft':
            sheet.write({'state': state})
        return sheet

    def _fresh(self):
        self.env.flush_all()
        self.env.invalidate_all()

    def _chart_on(self, project, day):
        """曲線上這一天的點 [(預定, 實際), …]（變更那一天兩個點）"""
        data = project.get_progress_chart_data()
        return [(p, a) for d, p, a in zip(data['dates'], data['planned'], data['actual']) if d == day.isoformat()]

    def test_mid_segment_today_everywhere_same(self):
        """今天在第 2 段中間：首頁、進度表目前累計、曲線、進度報告都是到今天（含）的值，草稿也算。"""
        today = local_today()
        d0 = today - timedelta(days=15)
        p, s = self._project('TU-MID', d0, [(0, 9, 10.0), (10, 19, 20.0)], 19)
        for n, v in ((2, 1.0), (4, 2.0), (12, 3.0), (14, 5.0)):
            self._log(p, d0 + timedelta(days=n), v)
        self._log(p, today, 4.0, state='draft')
        self._fresh()
        # 到今天（第 16 天）：預定 10 + 20 × 6/10 = 22；實際 1+2+3+5+4 = 15
        self.assertAlmostEqual(p.schedule_cumulative_planned, 22.0)
        self.assertAlmostEqual(p.schedule_cumulative_actual, 15.0)
        self.assertAlmostEqual(s.current_cumulative_planned, 22.0)
        self.assertAlmostEqual(s.current_cumulative_actual, 15.0)
        self.assertEqual(self._chart_on(p, today), [(22.0, 15.0)])
        # 第 13 天：預定 10 + 20 × 3/10 = 16；實際 1+2+3 = 6（第 15 天的 5 不能算進來）
        day13 = d0 + timedelta(days=12)
        self.assertEqual(self._chart_on(p, day13), [(16.0, 6.0)])
        self.assertEqual(p._progress_cumulative_on(day13), (16.0, 6.0))
        if 'general.progress.report' in self.env:
            report = self.env['general.progress.report'].create({
                'project_id': p.id, 'company_id': self.co.id, 'report_type': 'weekly',
                'report_date': day13, 'period_start': d0 + timedelta(days=6), 'period_end': day13})
            report._sync_cumulative_progress()
            self.assertEqual((report.planned_progress, report.actual_progress), (16.0, 6.0))
        # 進度表各段：到每一段結束日的累計
        seg1, seg2 = s.line_ids.sorted('date_start')
        self.assertEqual((seg1.actual_progress, seg1.cumulative_actual), (3.0, 3.0))
        self.assertEqual((seg2.actual_progress, seg2.cumulative_actual), (12.0, 15.0))

    def test_gap_days_counted(self):
        """兩段中間空 10 天：空檔那天的日誌也算（算進下一段），預定在空檔停在前一段的值。"""
        d0 = local_today() - timedelta(days=60)
        p, s = self._project('TU-GAP', d0, [(0, 9, 10.0), (20, 29, 20.0)], 29)
        for n, v in ((5, 2.0), (15, 3.0), (25, 4.0)):
            self._log(p, d0 + timedelta(days=n), v)
        self._fresh()
        self.assertAlmostEqual(p.schedule_cumulative_actual, 9.0)
        seg1, seg2 = s.line_ids.sorted('date_start')
        self.assertEqual((seg2.actual_progress, seg2.cumulative_actual), (7.0, 9.0))
        self.assertEqual(self._chart_on(p, d0 + timedelta(days=15)), [(10.0, 5.0)])

    def test_shared_boundary_planned(self):
        """第 11 天兩段共用：那一天算在第 1 段；第 2 段的 20% 分到它自己剩下的 9 天。"""
        d0 = local_today() - timedelta(days=60)
        p, s = self._project('TU-SHARE', d0, [(0, 10, 10.0), (10, 19, 20.0)], 19)
        boundary = self._log(p, d0 + timedelta(days=10), 1.0)
        after = self._log(p, d0 + timedelta(days=11), 1.0)
        self._fresh()
        self.assertEqual(self._chart_on(p, d0 + timedelta(days=9)), [(round(10.0 * 10 / 11, 2), 0.0)],
                         '日誌在第 11 天，第 10 天的實際進度不能先畫出來')
        self.assertEqual(self._chart_on(p, d0 + timedelta(days=10)), [(10.0, 1.0)])
        self.assertEqual(self._chart_on(p, d0 + timedelta(days=11)), [(round(10 + 20 / 9, 2), 2.0)])
        self.assertEqual(boundary.progress_line_id.date_end, d0 + timedelta(days=10))
        self.assertAlmostEqual(boundary.daily_planned_progress, 10.0 / 11, places=2)   # 欄位存到小數兩位
        self.assertAlmostEqual(after.daily_planned_progress, 20.0 / 9, places=2)
        self.assertAlmostEqual(s.line_ids.sorted('date_start')[-1].cumulative_planned, 30.0)

    def test_same_sequence_not_double_counted(self):
        """兩段序號一樣：累計照日期排，不互相多算（以前照序號「小於等於」）。"""
        d0 = local_today() - timedelta(days=60)
        p, s = self._project('TU-SEQ', d0, [(0, 9, 10.0), (10, 19, 20.0)], 19)
        s.write({'state': 'draft'})
        s.line_ids.write({'sequence': 10})
        self._fresh()
        first, second = s.line_ids.sorted('date_start')
        self.assertEqual((first.cumulative_planned, second.cumulative_planned), (10.0, 30.0))

    def test_change_day_before_and_after(self):
        """契約變更當天（使用者的例子 1/16）：單一數字用變更後（31／20），曲線那一天畫變更前、變更後兩個點。"""
        d0 = local_today() - timedelta(days=120)
        p, v1 = self._project('TU-CHG', d0, [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)], 29)
        for n in range(16):
            self._log(p, d0 + timedelta(days=n), 2.5)
        cd = d0 + timedelta(days=15)
        v2 = v1._create_new_version(cd)
        v2.write({'correction_target_cumulative': 31.0, 'correction_target_actual': 20.0})
        v2._do_activate()
        self._fresh()
        self.assertEqual(p._progress_cumulative_on(cd), (31.0, 20.0))
        self.assertEqual(p._progress_cumulative_on(cd, before=True), (32.0, 40.0))
        self.assertEqual(self._chart_on(p, cd), [(32.0, 40.0), (31.0, 20.0)])
        self.assertEqual(self._chart_on(p, cd - timedelta(days=1)), [(30.0, 37.5)])
        part2 = v2.line_ids.filtered(lambda l: l.date_start == l.date_end == cd)
        self.assertEqual((part2.cumulative_planned, part2.cumulative_actual), (31.0, 20.0))
