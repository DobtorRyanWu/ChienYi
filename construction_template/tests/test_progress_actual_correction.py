# -*- coding: utf-8 -*-
"""日誌與估驗附件印的累計實際進度：計畫倒退校正填了「校正後累計實際進度」時照它（2026-11-24）。

使用者的例子：1/1～1/16 每天實際 2.5%（到 1/16 累計 40%），1/16 契約變更，已完成的占比重新換算成 20%。
進度表照它算（construction_progress 18.0.1.13.0），印出來的也要照它，不然兩邊數字不一樣。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.utils import progress


@tagged('post_install', '-at_install', 'construction_template')
class TestProgressActualCorrection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.d0 = fields.Date.today() - timedelta(days=120)
        cls.employee = cls.env['hr.employee'].create({'name': '校正實際進度員工', 'company_id': cls.co.id})

    def D(self, n):
        return self.d0 + timedelta(days=n)

    def setUp(self):
        super().setUp()
        if not hasattr(self.env['progress.schedule'], '_create_new_version'):
            self.skipTest('construction_progress 沒有「變更日進度」（18.0.1.15.0 以前）')
        self.project = self.env['project.project'].create({
            'name': '校正實際進度', 'code': 'TPL-ACTCORR', 'project_type': 'general', 'state': 'draft',
            'company_id': self.co.id, 'contract_start_date': self.D(0), 'contract_end_date': self.D(29)})
        v1 = self.env['progress.schedule'].create({'project_id': self.project.id, 'change_date': self.D(0)})
        for seq, (start, end) in enumerate(((0, 9), (10, 19), (20, 29)), 1):
            self.env['progress.schedule.line'].create({
                'schedule_id': v1.id, 'sequence': seq * 10, 'planned_progress': 20.0,
                'date_start': self.D(start), 'date_end': self.D(end)})
        v1._do_activate()
        self.project.write({'state': 'construction'})
        for n in range(16):
            self._log(n, 2.5)
        # construction_progress 1.15.0 起：建立新版本先給變更日期，兩格填了馬上算（沒有「套用校正」）
        self.v2 = v1._create_new_version(self.D(15))
        self.v2.write({'correction_target_cumulative': 31.0, 'correction_target_actual': 20.0})
        self.v2._do_activate()

    def _log(self, n, pct, **vals):
        sheet = self.env['daily.log.sheet'].create(dict({
            'supervision_project_id': self.project.id, 'company_id': self.co.id,
            'employee_id': self.employee.id, 'log_date': self.D(n), 'daily_actual_progress': pct}, **vals))
        sheet.write({'state': 'filled'})
        return sheet

    def on(self, n):
        return progress.actual_cumulative_on(self.project, self.D(n))

    def test_printed_actual_follows_correction(self):
        self.assertAlmostEqual(self.on(14), 37.5, msg='基準日以前照日誌加總')
        self.assertAlmostEqual(self.on(15), 20.0, msg='基準日當天＝填的數字（含當天那篇日誌）')
        self._log(16, 2.5)
        self.assertAlmostEqual(self.on(16), 22.5)
        # 跟進度表同一個數字
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertAlmostEqual(self.project.schedule_cumulative_actual, 22.5)

    def test_later_imported_cumulative_wins(self):
        """舊系統匯入的累計值在基準日之後：照它（日期晚的那一個是基準）。"""
        self._log(18, 0.0, actual_progress=30.0)
        self._log(19, 1.0)
        self.assertAlmostEqual(self.on(19), 31.0)

    def test_printed_equals_everywhere_else(self):
        """印出來的累計預定／實際跟進度模組的共用算法同一個數字（2026-11-24 統一）；變更當天用變更後。"""
        for n in (9, 14, 15, 16, 25):
            day = self.D(n)
            self.assertEqual(
                (progress.planned_cumulative_on(self.project, day), progress.actual_cumulative_on(self.project, day)),
                self.project._progress_cumulative_on(day), '第 %d 天' % (n + 1))
        self.assertAlmostEqual(progress.planned_cumulative_on(self.project, self.D(15)), 31.0,
                               msg='變更當天用新版（以前印舊版的 32）')

    def test_cleared_correction_back_to_logs(self):
        self.v2.write({'correction_target_actual': 0.0})
        self.assertAlmostEqual(self.on(15), 40.0)
