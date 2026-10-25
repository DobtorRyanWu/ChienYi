# -*- coding: utf-8 -*-
"""日誌與進度報告表的「預定進度(%)」「實際進度(%)」要印累計值。

2026-10-24 以前營造版（daily_log_c1）與監造版（daily_log_1）日誌的預定進度印的是
daily_planned_progress——那是「當日份額」（區間預定進度 ÷ 區間天數，dev 最大值 0.23），
契約附表9-1 註 4 要的是累計。實際進度印的是當張日誌的 actual_progress，而這個欄位
只有 xlsm 匯入會寫，沒填的日子印空白。

使用者裁示（2026-10-25）：
  預定進度＝依進度表內插到當天的累計值（換版當天沿用舊版，與日誌自己的
            base_progress_schedule_id 規則相同）。
  實際進度＝當天或之前最後一次有填的累計值。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import daily_log_1, daily_log_c1
from odoo.addons.construction_template.utils import progress
from odoo.addons.construction_template.utils.template_render import build_values


@tagged('post_install', '-at_install', 'construction_template')
class TestProgressCumulative(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        today = fields.Date.today()
        cls.d0 = today - timedelta(days=12)          # 第一個區間的第一天
        cls.project = cls.env['project.project'].create({
            'name': '累計進度測試', 'code': 'TPL-PROGCUM',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
        })
        cls.v1 = cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': cls.d0 - timedelta(days=1),
        })
        Line = cls.env['progress.schedule.line']
        # 區間一 10 天預定 10%、區間二 10 天預定 20%
        Line.create({'schedule_id': cls.v1.id, 'sequence': 10,
                     'date_start': cls.d0, 'date_end': cls.d0 + timedelta(days=9),
                     'planned_progress': 10.0})
        Line.create({'schedule_id': cls.v1.id, 'sequence': 20,
                     'date_start': cls.d0 + timedelta(days=10), 'date_end': cls.d0 + timedelta(days=19),
                     'planned_progress': 20.0})
        cls.v1.write({'state': 'active'})
        cls.employee = cls.env['hr.employee'].create(
            {'name': '累計進度測試員工', 'company_id': company.id})

    def _sheet(self, day, **vals):
        return self.env['daily.log.sheet'].create(dict({
            'supervision_project_id': self.project.id,
            'company_id': self.env.company.id,
            'employee_id': self.employee.id,
            'log_date': day,
        }, **vals))

    def test_planned_interpolates_cumulative(self):
        on = lambda n: progress.planned_cumulative_on(self.project, self.d0 + timedelta(days=n))
        self.assertEqual(progress.planned_cumulative_on(self.project, self.d0 - timedelta(days=3)), 0.0)
        self.assertAlmostEqual(on(0), 1.0)      # 第 1 天：10 × 1/10
        self.assertAlmostEqual(on(4), 5.0)      # 第 5 天
        self.assertAlmostEqual(on(9), 10.0)     # 區間一最後一天
        self.assertAlmostEqual(on(14), 20.0)    # 10 + 20 × 5/10
        self.assertAlmostEqual(on(25), 30.0)    # 超過最後一個區間：最後的累計
        # 對照：舊算法（當日份額）在同一天只有 2%
        self.assertNotAlmostEqual(on(14), 20.0 / 10)

    def test_no_schedule_returns_none(self):
        other = self.env['project.project'].create({
            'name': '沒有進度表', 'code': 'TPL-PROGNONE', 'project_type': 'general',
            'company_id': self.env.company.id})
        self.assertIsNone(progress.planned_cumulative_on(other, fields.Date.today()))
        self.assertIsNone(progress.actual_cumulative_on(other, fields.Date.today()))

    def test_actual_takes_last_filled(self):
        self._sheet(self.d0 + timedelta(days=2), actual_progress=4.0)
        self._sheet(self.d0 + timedelta(days=5))                     # 沒填
        self._sheet(self.d0 + timedelta(days=8), actual_progress=9.5)
        on = lambda n: progress.actual_cumulative_on(self.project, self.d0 + timedelta(days=n))
        self.assertIsNone(on(1))
        self.assertEqual(on(2), 4.0)
        self.assertEqual(on(6), 4.0)            # 沒填的日子沿用前一次
        self.assertEqual(on(8), 9.5)

    def test_daily_logs_print_cumulative(self):
        self._sheet(self.d0 + timedelta(days=2), actual_progress=4.0)
        sheet = self._sheet(self.d0 + timedelta(days=14))            # 當天沒填實際進度
        ctx = daily_log_c1.build_context(sheet)
        self.assertEqual(ctx['expectProgress'], '20')
        self.assertEqual(ctx['exportProgress'], '4')
        values = build_values(sheet, daily_log_1)
        self.assertEqual(values['C10'], '20.00')
        self.assertEqual(values['G10'], '4.00')
