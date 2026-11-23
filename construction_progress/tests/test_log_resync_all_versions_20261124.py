# -*- coding: utf-8 -*-
"""18.0.1.15.2：施工日誌改了、刪了，這個工程每一版進度表的明細實際進度都跟著重算（2026-11-24 使用者定）。

以前存檔只重算「這一天所屬那一版」＋使用中那一版 → 三版以上時夾在中間的舊版、變更日之後的日子對舊版、
還沒啟用的草稿，明細都停在舊數字；刪日誌則哪一版都不重算。（兩版時改變更日之前的日誌，本來就會重算兩版。）
例子（同 test_change_day_20261124）：1/1～1/10、1/11～1/20、1/21～1/30 各 20%；1/1～1/16 每天實際 2.5%；
第 2 版變更日 1/16。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

SEGS = [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)]


@tagged('post_install', '-at_install', 'construction_progress')
class TestLogResyncAllVersions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=120)
        cls.employee = cls.env['hr.employee'].create({'name': '日誌重算測試員工', 'company_id': cls.co.id})

    def D(self, n):
        return self.d0 + timedelta(days=n)

    def _project(self, code):
        project = self.env['project.project'].create({
            'name': '日誌重算 ' + code, 'code': code, 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': self.D(0), 'contract_end_date': self.D(29)})
        v1 = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': self.D(0)})
        for seq, (start, end, planned) in enumerate(SEGS, 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': v1.id, 'sequence': seq * 10,
                'date_start': self.D(start), 'date_end': self.D(end), 'planned_progress': planned})
        v1._do_activate()
        project.write({'state': 'construction'})
        logs = {}
        for n in range(16):
            sheet = self.env['daily.log.sheet'].create({
                'supervision_project_id': project.id, 'company_id': self.co.id,
                'employee_id': self.employee.id, 'log_date': self.D(n), 'daily_actual_progress': 2.5})
            sheet.write({'state': 'filled'})
            logs[n] = sheet
        return project, v1, logs

    def _actual(self, sched):
        """[(開始第幾天, 結束第幾天, 實際進度, 累計實際進度)]"""
        self.env.flush_all()
        self.env.invalidate_all()
        return [((l.date_start - self.d0).days, (l.date_end - self.d0).days,
                 round(l.actual_progress or 0.0, 2), round(l.cumulative_actual or 0.0, 2))
                for l in sched.line_ids.sorted(lambda l: (l.date_start, l.date_end, l.id))]

    def _v2_active(self, code):
        p, v1, logs = self._project(code)
        v2 = v1._create_new_version(self.D(15))
        v2._do_activate()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual((v1.state, v2.state), ('archived', 'active'))
        self.assertEqual(self._actual(v1), [(0, 9, 25.0, 25.0), (10, 19, 15.0, 40.0), (20, 29, 0.0, 40.0)])
        return p, v1, v2, logs

    def test_middle_archived_follows_pre_change_edit(self):
        """三版：第 2 版（變更日 1/16）已歸檔、第 3 版（變更日 1/21）使用中。改 1/5 的日誌（2.5 → 10）：
        夾在中間的第 2 版也跟著變（以前只重算 1/5 所屬的第 1 版＋使用中的第 3 版，第 2 版停在 25）。"""
        p, v1, v2, logs = self._v2_active('LR-MID')
        v3 = v2._create_new_version(self.D(20))
        v3._do_activate()
        self.assertEqual((v1.state, v2.state, v3.state), ('archived', 'archived', 'active'))
        self.assertEqual(self._actual(v2)[0], (0, 9, 25.0, 25.0))
        logs[4].write({'daily_actual_progress': 10.0})
        self.assertEqual(self._actual(v2)[0], (0, 9, 32.5, 32.5))
        self.assertEqual(self._actual(v2)[-1][3], 47.5)
        self.assertEqual(self._actual(v1)[0], (0, 9, 32.5, 32.5))
        self.assertEqual(self._actual(v3)[0], (0, 9, 32.5, 32.5))

    def test_archived_follows_log_after_change(self):
        """變更日之後的日子補一篇日誌（1/21 4%）：已歸檔的第 1 版自己的明細也跟著變
        （那一天屬於第 2 版，以前第 1 版停在 40）。再刪掉它也一樣。"""
        p, v1, v2, logs = self._v2_active('LR-AFTER')
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': p.id, 'company_id': self.co.id, 'employee_id': self.employee.id,
            'log_date': self.D(20), 'daily_actual_progress': 4.0})
        self.assertEqual(self._actual(v1), [(0, 9, 25.0, 25.0), (10, 19, 15.0, 40.0), (20, 29, 4.0, 44.0)])
        sheet.write({'daily_actual_progress': 6.0})
        self.assertEqual(self._actual(v1)[-1], (20, 29, 6.0, 46.0))
        sheet.unlink()
        self.assertEqual(self._actual(v1)[-1], (20, 29, 0.0, 40.0))

    def test_pre_change_edit_two_versions(self):
        """兩版、改變更日之前的日誌：第 1 版、第 2 版都跟著變（以前就會，防退化）。"""
        p, v1, v2, logs = self._v2_active('LR-EDIT')
        logs[4].write({'daily_actual_progress': 10.0})
        self.assertEqual(self._actual(v1), [(0, 9, 32.5, 32.5), (10, 19, 15.0, 47.5), (20, 29, 0.0, 47.5)])
        self.assertEqual(self._actual(v2)[0], (0, 9, 32.5, 32.5))

    def test_log_delete_resyncs_every_version(self):
        """刪掉一篇日誌：使用中、已歸檔兩版的明細都跟著變（以前刪日誌哪一版都不重算）。"""
        p, v1, v2, logs = self._v2_active('LR-DEL')
        logs[4].unlink()
        self.assertEqual(self._actual(v1), [(0, 9, 22.5, 22.5), (10, 19, 15.0, 37.5), (20, 29, 0.0, 37.5)])
        self.assertEqual(self._actual(v2)[0], (0, 9, 22.5, 22.5))

    def test_draft_follows_log_edit(self):
        """還沒啟用的草稿新版本：明細的實際進度也跟著日誌變（以前要等啟用）。"""
        p, v1, logs = self._project('LR-DRAFT')
        v2 = v1._create_new_version(self.D(15))
        self.assertEqual(self._actual(v2)[0], (0, 9, 25.0, 25.0))
        logs[4].write({'daily_actual_progress': 10.0})
        self.assertEqual(self._actual(v2)[0], (0, 9, 32.5, 32.5))
        self.assertEqual(self._actual(v1)[0], (0, 9, 32.5, 32.5))

    def test_other_project_untouched(self):
        """別的工程的進度表不受影響（防退化）。"""
        p, v1, v2, logs = self._v2_active('LR-OWN')
        q, w1, qlogs = self._project('LR-OTHER')
        before = self._actual(w1)
        logs[4].write({'daily_actual_progress': 10.0})
        logs[5].unlink()
        self.assertEqual(self._actual(w1), before)
