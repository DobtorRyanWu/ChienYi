# -*- coding: utf-8 -*-
"""2026-11-24：交界日只算一次、計畫倒退校正碰到共用交界日、啟用時重算、校正後累計實際進度。

起因：區間不重疊放寬後（PG-06，上一段結束日＝下一段開始日不算重疊），
- 交界日那篇日誌的本日實際進度被前後兩段各加一次（實測 60% 算成 70%）；
- 計畫倒退校正碰到共用交界日：校正前累計預定少算前一段、新切的子區間排到第一段前面
  （實測累計預定 45% 算成 95%、首頁工程進度 65% 算成 25%）；
另外啟用新版時前面幾段的實際進度沒有重算（首頁 60% 掉到 25%），
以及契約變更後已完成的占比要重新換算時（使用者的例子：1/16 累計實際 40% 要變成 20%），系統沒有地方填。
1.15.0 起「計畫倒退校正」改成「變更日進度」：建立新版本時就切出變更日那一列（沒有開關、沒有校正基準日、
沒有「套用校正」按鈕），兩格填了馬上算 → 這裡的測試照新的做法建版本，要驗的事不變。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestBoundaryAndActualCorrection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=120)
        cls.employee = cls.env['hr.employee'].create({'name': '交界日測試員工', 'company_id': cls.co.id})

    # ── 工具 ────────────────────────────────────────────────────────────────
    def D(self, n):
        return self.d0 + timedelta(days=n)

    def _project(self, code, end=60):
        return self.env['project.project'].create({
            'name': '交界日 ' + code, 'code': code, 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': self.D(0), 'contract_end_date': self.D(end)})

    def _schedule(self, project, segments):
        sched = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': self.D(0)})
        for seq, (start, end, planned) in enumerate(segments, 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': sched.id, 'sequence': seq * 10,
                'date_start': self.D(start), 'date_end': self.D(end), 'planned_progress': planned})
        sched._do_activate()
        project.write({'state': 'construction'})
        return sched

    def _log(self, project, n, pct):
        sheet = self.env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': self.co.id,
            'employee_id': self.employee.id, 'log_date': self.D(n), 'daily_actual_progress': pct})
        sheet.write({'state': 'filled'})
        return sheet

    def _lines(self, sched):
        self.env.flush_all()
        self.env.invalidate_all()
        return sched.line_ids.sorted(lambda l: (l.sequence, l.date_start, l.id))

    def _line_on(self, sched, n, single_day=False):
        lines = self._lines(sched).filtered(
            lambda l: l.date_start <= self.D(n) <= l.date_end and (not single_day or l.date_start == l.date_end))
        self.assertEqual(len(lines), 1, '第 %d 天應該剛好找到一段' % n)
        return lines

    def _home(self, project):
        self.env.flush_all()
        self.env.invalidate_all()
        return project.schedule_cumulative_actual

    def _new_version(self, sched, change_day, correction=None):
        """correction＝(變更後累計預定, 變更後累計實際)；None＝兩格都不填"""
        v2 = sched._create_new_version(self.D(change_day))
        if correction:
            v2.write({'correction_target_cumulative': correction[0],
                      'correction_target_actual': correction[1]})
        return v2

    # ── ① 交界日只算一次 ──────────────────────────────────────────────────────
    def test_shared_boundary_day_counted_once(self):
        """第 30 天兩段共用：那一天的 10% 只算在第 1 段，累計 60 不是 70。"""
        p = self._project('TB-SHARED')
        s = self._schedule(p, [(0, 30, 50.0), (30, 60, 50.0)])
        for n, pct in ((10, 20.0), (20, 20.0), (30, 10.0), (40, 10.0)):
            self._log(p, n, pct)
        seg1, seg2 = self._lines(s)
        self.assertAlmostEqual(seg1.actual_progress, 50.0)
        self.assertAlmostEqual(seg2.actual_progress, 10.0, msg='第 30 天的 10% 已經算在第 1 段')
        self.assertAlmostEqual(seg2.cumulative_actual, 60.0)
        self.assertAlmostEqual(self._home(p), 60.0)
        # 「從日誌同步進度」按鈕同一套算法
        s.action_sync_all_lines_from_daily_log()
        seg1, seg2 = self._lines(s)
        self.assertAlmostEqual(seg2.cumulative_actual, 60.0)

    def test_three_segments_share_one_day(self):
        """交界日上還有一條單日列（三段共用同一天）：那一天也只算一次。"""
        p = self._project('TB-THREE')
        s = self._schedule(p, [(0, 30, 40.0), (30, 30, 0.0), (30, 60, 60.0)])
        self._log(p, 30, 10.0)
        self._log(p, 40, 5.0)
        lines = self._lines(s)
        self.assertEqual([round(l.actual_progress, 2) for l in lines], [10.0, 0.0, 5.0])
        self.assertAlmostEqual(lines[-1].cumulative_actual, 15.0)

    # ── ② 啟用新版時重算 ──────────────────────────────────────────────────────
    def test_activation_syncs_all_lines(self):
        """新版從舊版複製、實際進度從 0 開始；啟用時要重算，首頁不能掉到只算部分段。"""
        p = self._project('TB-ACT')
        s = self._schedule(p, [(0, 29, 50.0), (30, 60, 50.0)])
        for n, pct in ((10, 20.0), (20, 20.0), (30, 10.0), (40, 10.0)):
            self._log(p, n, pct)
        self.assertAlmostEqual(self._home(p), 60.0)
        v2 = self._new_version(s, 35)
        v2._do_activate()
        self.assertAlmostEqual(self._home(p), 60.0, msg='啟用新版當下就要是 60，不用按同步')
        self._log(p, 45, 5.0)
        self.assertAlmostEqual(self._home(p), 65.0)

    # ── ③ 變更日進度碰到共用交界日 ────────────────────────────────────────────
    def test_correction_with_shared_boundary(self):
        p = self._project('TB-CORR')
        s = self._schedule(p, [(0, 30, 50.0), (30, 60, 50.0)])
        for n, pct in ((10, 20.0), (20, 20.0), (30, 10.0), (40, 10.0)):
            self._log(p, n, pct)
        v2 = self._new_version(s, 35, correction=(45.0, 0.0))
        self.env.flush_all()
        # 變更前＝舊版到第 36 天：第 1 段 50（含共用交界日）＋ 第 2 段 50 × 5/30
        self.assertAlmostEqual(v2.correction_pre_cumulative, 50.0 + 50.0 * 5 / 30, places=2)
        lines = self._lines(v2)
        self.assertEqual(lines[0].date_start, self.D(0), '新切的子區間要排在第 1 段後面')
        part2 = self._line_on(v2, 35, single_day=True)
        self.assertAlmostEqual(part2.cumulative_planned, 45.0)
        v2._do_activate()
        self._log(p, 45, 5.0)
        lines = self._lines(v2)
        self.assertAlmostEqual(lines[-1].cumulative_planned, 45.0)
        self.assertAlmostEqual(lines[-1].cumulative_actual, 65.0)
        self.assertAlmostEqual(self._home(p), 65.0)

    # ── ④ 校正後累計實際進度（使用者的例子） ─────────────────────────────────
    def _user_example(self, code, actual_target=20.0):
        """1/1～1/10 預定 20%、1/11～1/20 20%、1/21～1/30 20%；1/1～1/16 每天實際 2.5%（到 1/16 累計 40%）。
        1/16 契約變更：1/11～1/15 照舊版（10%），1/16～1/20 改 5%、1/21～1/30 維持 20%
        → 累計預定 1/10 20、1/15 30、1/20 35、1/30 55；累計實際 1/16 從 40% 下修成 actual_target。"""
        p = self._project(code, end=29)
        v1 = self._schedule(p, [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)])
        logs = {n: self._log(p, n, 2.5) for n in range(16)}
        self.assertAlmostEqual(self._lines(v1)[1].cumulative_actual, 40.0)
        v2 = self._new_version(v1, 15, correction=(31.0, actual_target))
        # 建立新版本時變更日以後已經歸零，照新的計畫填：1/17～1/20 4%（1/16 那一天 1%）、1/21～1/30 20%
        self._line_on(v2, 17).write({'planned_progress': 4.0})
        self._line_on(v2, 25).write({'planned_progress': 20.0})
        v2._do_activate()
        return p, v1, v2, logs

    def test_actual_correction_user_example(self):
        p, v1, v2, logs = self._user_example('TB-USER')
        part1, part2, part3, seg3 = (self._line_on(v2, 12), self._line_on(v2, 15, single_day=True),
                                     self._line_on(v2, 17), self._line_on(v2, 25))
        # 預定：1/10 20、1/15 30、1/16 31、1/20 35、1/30 55
        self.assertEqual([round(l.cumulative_planned, 2) for l in (part1, part2, part3, seg3)],
                         [30.0, 31.0, 35.0, 55.0])
        # 實際：1/16 從 40 變 20；那一小段放 20 − 37.5 ＝ −17.5 的調整
        self.assertAlmostEqual(part2.actual_correction_target, 20.0)
        self.assertAlmostEqual(part2.cumulative_actual, 20.0)
        self.assertAlmostEqual(part2.actual_progress, -17.5)
        self.assertAlmostEqual(self._home(p), 20.0)
        # 之後照日誌往上加
        self._log(p, 16, 2.5)
        self.assertAlmostEqual(self._line_on(v2, 17).cumulative_actual, 22.5)
        self.assertAlmostEqual(self._home(p), 22.5)
        # 舊版不套用第 2 版的調整（不會變成 22.5），照樣加上之後的日誌：40 ＋ 2.5
        # （1.15.2 以前寫 40：那一天屬於第 2 版，舊版不會重算，停在舊數字）
        self.assertAlmostEqual(self._line_on(v1, 12).cumulative_actual, 42.5)
        # 變更前的日誌事後被改了（1/6 從 2.5 改成 5）：1/16 照樣等於填的 20
        logs[5].write({'daily_actual_progress': 5.0})
        self.assertAlmostEqual(self._line_on(v2, 15, single_day=True).cumulative_actual, 20.0)
        self.assertAlmostEqual(self._home(p), 22.5)

    def test_actual_correction_cleared_falls_back_to_logs(self):
        """0＝不調整：照施工日誌加總（跟以前一樣）。"""
        p, v1, v2, logs = self._user_example('TB-CLEAR')
        v2.write({'correction_target_actual': 0.0})
        part2 = self._line_on(v2, 15, single_day=True)
        self.assertAlmostEqual(part2.actual_correction_target, 0.0)
        self.assertAlmostEqual(part2.cumulative_actual, 40.0)

    def test_actual_correction_filled_after_apply(self):
        """啟用之後才填「變更後累計實際進度」（使用中的版本）：照樣帶到變更日那一列。"""
        p, v1, v2, logs = self._user_example('TB-LATE', actual_target=0.0)
        self.assertAlmostEqual(self._home(p), 40.0)
        v2.write({'correction_target_actual': 20.0})
        self.assertAlmostEqual(self._line_on(v2, 15, single_day=True).cumulative_actual, 20.0)
        self.assertAlmostEqual(self._home(p), 20.0)

    def test_actual_correction_carried_to_next_version(self):
        """再一次變更（不校正）：前一次的調整跟著新版本複製，累計照樣從 20 往上加。"""
        p, v1, v2, logs = self._user_example('TB-NEXT')
        self._log(p, 16, 2.5)
        v3 = self._new_version(v2, 20)
        v3._do_activate()
        self.assertAlmostEqual(self._line_on(v3, 15, single_day=True).cumulative_actual, 20.0)
        self.assertAlmostEqual(self._home(p), 22.5)

    def test_no_correction_unchanged(self):
        """只填預定、不填實際：變更日那一列照日誌算（跟以前一樣），累計不下修。"""
        p, v1, v2, logs = self._user_example('TB-PLAIN', actual_target=0.0)
        part2 = self._line_on(v2, 15, single_day=True)
        self.assertAlmostEqual(part2.actual_progress, 2.5)
        self.assertAlmostEqual(part2.cumulative_actual, 40.0)
