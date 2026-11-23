# -*- coding: utf-8 -*-
"""18.0.1.15.0「變更日進度」（原「計畫倒退校正」，2026-11-24 使用者定案，照舊系統的概念）。

- 建立新版本先問變更日期；變更日在明細裡獨立成一列（不跟前後段共用那一天：段中間、兩段交界、空檔都一樣）；
  變更日以後各段預定歸零、日期分段留著。
- 兩格「變更後累計預定／實際進度」都可以不填：預定空白＝當天照變更前的值；實際空白＝照日誌加總。
  填了、改了、清空了，或改了變更日以前的段 → 變更日那一列馬上重算（沒有「套用校正」）。
- 改變更日期 → 照新日期從原本那一版重切、再歸零；匯入、手動建的版本不會被自動切分、歸零。
- 啟用時變更日以後全部是 0 → 提醒，不擋。
例子：1/1～1/10、1/11～1/20、1/21～1/30 各 20%；1/1～1/16 每天實際 2.5%（1/16 累計 40%）；變更日 1/16（第 15 天）。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

SEGS = [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)]


@tagged('post_install', '-at_install', 'construction_progress')
class TestChangeDay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=120)
        cls.employee = cls.env['hr.employee'].create({'name': '變更日測試員工', 'company_id': cls.co.id})

    def D(self, n):
        return self.d0 + timedelta(days=n)

    def _project(self, code, segments=SEGS, logs=True):
        project = self.env['project.project'].create({
            'name': '變更日 ' + code, 'code': code, 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': self.D(0), 'contract_end_date': self.D(29)})
        v1 = self.env['progress.schedule'].create({'project_id': project.id, 'change_date': self.D(0)})
        self._lines_create(v1, segments)
        v1._do_activate()
        project.write({'state': 'construction'})
        if logs:
            for n in range(16):
                sheet = self.env['daily.log.sheet'].create({
                    'supervision_project_id': project.id, 'company_id': self.co.id,
                    'employee_id': self.employee.id, 'log_date': self.D(n), 'daily_actual_progress': 2.5})
                sheet.write({'state': 'filled'})
        return project, v1

    def _lines_create(self, sched, segments):
        for seq, (start, end, planned) in enumerate(segments, 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': sched.id, 'sequence': seq * 10,
                'date_start': self.D(start), 'date_end': self.D(end), 'planned_progress': planned})

    def _rows(self, sched):
        self.env.flush_all()
        self.env.invalidate_all()
        return [((l.date_start - self.d0).days, (l.date_end - self.d0).days, round(l.planned_progress, 2))
                for l in sched.line_ids.sorted(lambda l: (l.date_start, l.date_end, l.id))]

    def _row(self, sched, n):
        self.env.flush_all()
        self.env.invalidate_all()
        return sched.line_ids.filtered(lambda l: l.date_start == l.date_end == self.D(n))

    def _no_line_shares(self, sched, n):
        others = sched.line_ids.filtered(
            lambda l: l.date_start <= self.D(n) <= l.date_end and not (l.date_start == l.date_end == self.D(n)))
        self.assertFalse(others, '變更日那一天不能跟別的段共用')

    # ── 建立新版本 ────────────────────────────────────────────────────────────
    def test_button_opens_wizard_and_wizard_needs_date(self):
        p, v1 = self._project('CD-WIZ', logs=False)
        act = v1.action_create_new_version()
        self.assertEqual(act['res_model'], 'progress.new.version.wizard')
        self.assertTrue(self.env['progress.new.version.wizard']._fields['change_date'].required)
        self.assertFalse(self.env['progress.new.version.wizard'].default_get(['change_date']).get('change_date'),
                         '變更日期不預設今天')
        wiz = self.env['progress.new.version.wizard'].create({
            'schedule_id': v1.id, 'change_date': self.D(15), 'change_reason': '第 1 次契約變更'})
        res = wiz.action_confirm()
        v2 = self.env['progress.schedule'].browse(res['res_id'])
        self.assertEqual((v2.version, v2.state, v2.change_date, v2.copied_from_id), (2, 'draft', self.D(15), v1))
        self.assertEqual(v2.change_reason, '第 1 次契約變更')
        self.assertEqual(v2.effective_change_date, self.D(15))

    def test_new_version_splits_and_zeroes(self):
        """段中間：1/11～1/15 照舊（10%）、1/16 獨立一列、1/17 以後歸零；預定空白＝變更前的值（32）。"""
        p, v1 = self._project('CD-SPLIT')
        v2 = v1._create_new_version(self.D(15))
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 14, 10.0), (15, 15, 2.0), (16, 19, 0.0), (20, 29, 0.0)])
        self._no_line_shares(v2, 15)
        row = self._row(v2, 15)
        self.assertTrue(row.is_change_day_row)
        self.assertAlmostEqual(row.cumulative_planned, 32.0, msg='預定空白＝當天照變更前的值')
        self.assertAlmostEqual(v2.correction_pre_cumulative, 32.0)
        self.assertAlmostEqual(v2.change_pre_actual, 40.0)
        self.assertEqual(self._rows(v1), [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)], '舊版不動')

    def test_shared_boundary_both_cut(self):
        """變更日剛好是兩段交界（第 11 天）：前一段切到前一天、後一段從隔天開始，那一天獨立一列。"""
        p, v1 = self._project('CD-SHARE', segments=[(0, 10, 10.0), (10, 19, 20.0)], logs=False)
        v2 = v1._create_new_version(self.D(10))
        self.assertEqual(self._rows(v2), [(0, 9, 9.09), (10, 10, 0.91), (11, 19, 0.0)])
        self._no_line_shares(v2, 10)
        self.assertAlmostEqual(self._row(v2, 10).cumulative_planned, 10.0)

    def test_gap_gets_a_row(self):
        """變更日落在兩段中間的空檔：照樣放一列（以前會報「找不到包含校正基準日的區間」）。"""
        p, v1 = self._project('CD-GAP', segments=[(0, 9, 10.0), (20, 29, 20.0)], logs=False)
        v2 = v1._create_new_version(self.D(15))
        self.assertEqual(self._rows(v2), [(0, 9, 10.0), (15, 15, 0.0), (20, 29, 0.0)])
        v2.write({'correction_target_cumulative': 8.0})
        self.assertEqual(self._rows(v2)[1], (15, 15, -2.0))

    def test_change_on_first_day_not_split(self):
        """變更日不晚於第一段開始日（還沒開工就改版、整張重排）：不切分、不歸零、兩格不適用。"""
        p, v1 = self._project('CD-FIRST', logs=False)
        v2 = v1._create_new_version(self.D(0))
        self.assertFalse(v2.change_day_applicable)
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 20.0)])

    # ── 兩格 ──────────────────────────────────────────────────────────────────
    def test_planned_target_live(self):
        """填了馬上算、改了變更日以前的段照樣等於填的、清空回到變更前的值。"""
        p, v1 = self._project('CD-PLAN')
        v2 = v1._create_new_version(self.D(15))
        v2.write({'correction_target_cumulative': 31.0})
        row = self._row(v2, 15)
        self.assertAlmostEqual(row.planned_progress, 1.0)
        self.assertAlmostEqual(row.cumulative_planned, 31.0)
        v2.line_ids.filtered(lambda l: l.date_start == self.D(10)).write({'planned_progress': 12.0})
        row = self._row(v2, 15)
        self.assertAlmostEqual(row.planned_progress, -1.0)
        self.assertAlmostEqual(row.cumulative_planned, 31.0, msg='變更日以前的段改了，變更日照樣是填的數字')
        v2.write({'correction_target_cumulative': 0.0})
        self.assertAlmostEqual(self._row(v2, 15).cumulative_planned, 32.0, msg='清空＝照變更前的值')

    def test_blank_targets_no_drop(self):
        """兩格都不填（跟舊系統一樣可以不填）：變更日當天不往下掉，實際照日誌加總。"""
        p, v1 = self._project('CD-BLANK')
        v2 = v1._create_new_version(self.D(15))
        v2._do_activate()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(p._progress_cumulative_on(self.D(15)), (32.0, 40.0))
        self.assertEqual(p._progress_cumulative_on(self.D(15), before=True), (32.0, 40.0))
        self.assertFalse(self._row(v2, 15).actual_correction_target)

    def test_actual_target_and_clear(self):
        p, v1 = self._project('CD-ACT')
        v2 = v1._create_new_version(self.D(15))
        v2.write({'correction_target_cumulative': 31.0, 'correction_target_actual': 20.0})
        self.assertAlmostEqual(self._row(v2, 15).actual_correction_target, 20.0)
        v2._do_activate()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(p._progress_cumulative_on(self.D(15)), (31.0, 20.0))
        self.assertEqual(p._progress_cumulative_on(self.D(15), before=True), (32.0, 40.0))
        v2.write({'correction_target_actual': 0.0})   # 使用中也能改實際（以前就可以）
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(p._progress_cumulative_on(self.D(15)), (31.0, 40.0))

    # ── 改變更日期 ────────────────────────────────────────────────────────────
    def test_change_date_edit_resplits(self):
        p, v1 = self._project('CD-EDIT')
        v2 = v1._create_new_version(self.D(15))
        v2.line_ids.filtered(lambda l: l.date_start == self.D(16)).write({'planned_progress': 4.0})
        v2.write({'change_date': self.D(12)})
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 11, 4.0), (12, 12, 2.0), (13, 19, 0.0), (20, 29, 0.0)])
        self.assertFalse(self._row(v2, 15), '舊的變更日那一列不留')
        self.assertEqual(v2.effective_change_date, self.D(12))
        warning = v2.new({'copied_from_id': v1.id, 'state': 'draft', 'change_date': self.D(13)},
                         origin=v2)._onchange_change_date_resplit()
        self.assertIn('重新切分', warning['warning']['message'])

    # ── 匯入、手動建的版本 ────────────────────────────────────────────────────
    def test_plain_version_date_change_splits_now(self):
        """沒有 copied_from_id（匯入、手動建、1.15.0 以前建的）：改變更日期馬上切出獨立的一天、不歸零（1.15.1；
        以前要等填了兩格才切）；預定空白＝這一版自己那一天的份額；清空後回到份額（以前留著填過的調整）。"""
        p, v1 = self._project('CD-PLAIN', logs=False)
        v2 = self.env['progress.schedule'].create({'project_id': p.id, 'change_date': self.D(15)})
        self._lines_create(v2, [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 30.0)])
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 30.0)], '只建立、沒改日期 → 不動')
        v2.write({'change_date': self.D(14)})
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 13, 8.0), (14, 14, 2.0), (15, 19, 10.0), (20, 29, 30.0)])
        self._no_line_shares(v2, 14)
        self.assertTrue(self._row(v2, 14).is_change_day_row)
        v2.write({'correction_target_cumulative': 25.0})
        self.assertEqual(self._rows(v2)[2], (14, 14, -3.0))
        self.assertAlmostEqual(self._row(v2, 14).cumulative_planned, 25.0)
        v2.write({'correction_target_cumulative': 0.0})
        self.assertEqual(self._rows(v2)[2], (14, 14, 2.0), '清空 → 回到這一天本來的份額，不留 −3')
        v2.write({'change_date': self.D(16)})
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 14, 10.0), (15, 15, 2.0), (16, 16, 2.0),
                                          (17, 19, 6.0), (20, 29, 30.0)],
                         '舊日期那一列併回原本那一段、新日期切一列，其他明細不動')
        self.assertAlmostEqual(self._row(v2, 16).cumulative_planned, 34.0, msg='到變更日的累計跟沒切以前一樣')

    def test_rebaselined_plain_version_keeps_its_own_value(self):
        """整張重排的修正表（從開工日起重新分配百分比，匯入或手動建）：改變更日期切出那一天，
        預定空白照這一版自己的值（15），不替它補平回舊版的值（30）——那個往下掉本來就是修正表要表達的。"""
        p, v1 = self._project('CD-REBASE', logs=False)
        v2 = self.env['progress.schedule'].create({'project_id': p.id, 'change_date': self.D(15)})
        self._lines_create(v2, [(0, 9, 10.0), (10, 19, 10.0), (20, 29, 80.0)])
        v2.write({'change_date': self.D(14)})
        row = self._row(v2, 14)
        self.assertAlmostEqual(row.planned_progress, 1.0)
        self.assertAlmostEqual(row.cumulative_planned, 15.0)
        v2._do_activate()
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(p._progress_cumulative_on(self.D(14))[0], 15.0)
        self.assertEqual(p._progress_cumulative_on(self.D(14), before=True)[0], 30.0)

    def test_plain_version_change_date_twice_with_targets(self):
        """你回報的情形：1.15.0 以前建的版本，填了兩格之後改第二次變更日期 → 以前被擋下，現在照樣切、數字照填的。"""
        p, v1 = self._project('CD-LEGACY')
        v2 = self.env['progress.schedule'].create({'project_id': p.id, 'change_date': self.D(15)})
        self._lines_create(v2, SEGS)
        v2.write({'correction_target_cumulative': 25.0, 'correction_target_actual': 20.0})
        self.assertAlmostEqual(self._row(v2, 15).cumulative_planned, 25.0)
        v2.write({'change_date': self.D(14)})
        v2.write({'change_date': self.D(13)})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertFalse(v2._change_day_line(self.D(15)) or v2._change_day_line(self.D(14)), '舊日期切出來的那一列不留')
        row = v2._change_day_line()
        self.assertEqual(row.date_start, self.D(13))
        self.assertAlmostEqual(row.cumulative_planned, 25.0)
        self.assertAlmostEqual(row.actual_correction_target, 20.0)
        self.assertAlmostEqual(sum((v2.line_ids - row).mapped('planned_progress')) + row.split_share, 60.0, places=2,
                               msg='除了變更日那一天的調整，整張的預定一點都沒少')
        self._no_line_shares(v2, 13)

    def test_copied_change_date_twice_with_targets(self):
        p, v1 = self._project('CD-TWICE')
        v2 = v1._create_new_version(self.D(15))
        v2.write({'correction_target_cumulative': 31.0, 'correction_target_actual': 20.0})
        v2.write({'change_date': self.D(12)})
        v2.write({'change_date': self.D(13)})
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 12, 6.0), (13, 13, 5.0), (14, 19, 0.0), (20, 29, 0.0)])
        self.assertAlmostEqual(self._row(v2, 13).cumulative_planned, 31.0)
        self.assertAlmostEqual(self._row(v2, 13).actual_correction_target, 20.0)

    def test_actual_synced_right_after_split(self):
        """建立新版本、改變更日期之後，表上各段的實際進度馬上照日誌算（以前要等啟用或有日誌存檔）。"""
        p, v1 = self._project('CD-SYNC')
        v2 = v1._create_new_version(self.D(15))
        self.assertEqual([(r[0], r[1], round(l.actual_progress, 2)) for r, l in zip(
            self._rows(v2), v2.line_ids.sorted(lambda l: (l.date_start, l.date_end, l.id)))],
            [(0, 9, 25.0), (10, 14, 12.5), (15, 15, 2.5), (16, 19, 0.0), (20, 29, 0.0)])
        v2.write({'change_date': self.D(12)})
        self.env.flush_all()
        self.env.invalidate_all()
        row = self._row(v2, 12)
        self.assertAlmostEqual(row.actual_progress, 2.5)
        self.assertAlmostEqual(row.cumulative_actual, 32.5)

    def test_plain_version_activate_untouched(self):
        p, v1 = self._project('CD-PLAIN2', logs=False)
        v2 = self.env['progress.schedule'].create({'project_id': p.id, 'change_date': self.D(15)})
        self._lines_create(v2, [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 30.0)])
        v2._do_activate()
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 19, 20.0), (20, 29, 30.0)])

    def test_copy_from_previous_same_as_new_version(self):
        p, v1 = self._project('CD-COPY', logs=False)
        v2 = self.env['progress.schedule'].create({'project_id': p.id, 'change_date': self.D(15)})
        v2.action_copy_from_previous_version()
        self.assertEqual(v2.copied_from_id, v1)
        self.assertEqual(self._rows(v2), [(0, 9, 20.0), (10, 14, 10.0), (15, 15, 2.0), (16, 19, 0.0), (20, 29, 0.0)])

    # ── 啟用提醒 ──────────────────────────────────────────────────────────────
    def test_activate_reminder_zero_after(self):
        p, v1 = self._project('CD-WARN', logs=False)
        v2 = v1._create_new_version(self.D(15))
        Wizard = self.env['progress.activate.wizard']
        wiz = Wizard.create({'schedule_id': v2.id, 'employee_id': self.employee.id})
        self.assertTrue(wiz.zero_after_change, '變更日以後全部是 0 → 提醒')
        v2.line_ids.filtered(lambda l: l.date_start == self.D(16)).write({'planned_progress': 4.0})
        wiz = Wizard.create({'schedule_id': v2.id, 'employee_id': self.employee.id})
        self.assertFalse(wiz.zero_after_change)
        wiz.action_confirm()   # 只提醒、不擋
        self.assertEqual(v2.state, 'active')
