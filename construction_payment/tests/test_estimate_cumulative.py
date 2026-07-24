# -*- coding: utf-8 -*-
"""M3.0 #2 回歸測試 — 估驗累計數量須反映「較晚才核定的較早期估驗」。

原始 bug（稽核 M3.0 #2）：cumulative_estimate_* 若為 stored compute，且 @api.depends
只看本估驗自身欄位，則當一張「日期較早」的估驗事後才被核定時，較晚估驗的累計
不會重算 → 請款累計金額 stale。

現行設計（系統改版後）：previous_approved_qty 與 cumulative_estimate_qty/amount 皆為
**非儲存** compute（help 明載「非儲存以反映他單核定」）→ 每次讀取即以日期查詢重算。
本測試鎖定此正確行為，防止未來有人誤加 store=True 而讓 bug 復發。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEstimateCumulative(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '估驗累計測試工程',
            'code': 'EST-CUM',
            'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.task = cls.env['project.task'].create({
            'name': '估驗工項X',
            'project_id': cls.project.id,
            'item_no': 'X-1',
            'unit': '式',
            'planned_qty': 100.0,
            'unit_price': 10.0,
        })

    def _make_estimate(self, est_date, qty):
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': est_date,
        })
        self.env['payment.estimate.line'].create({
            'estimate_id': est.id,
            'task_id': self.task.id,
            'estimate_qty': qty,
            'unit_price': 10.0,
        })
        return est

    def _line(self, est):
        return est.line_ids.filtered(lambda l: l.task_id == self.task)

    def test_cumulative_reflects_later_approved_earlier_estimate(self):
        today = fields.Date.today()
        est_early = self._make_estimate(today - timedelta(days=10), 5.0)
        est_late = self._make_estimate(today, 3.0)
        line_late = self._line(est_late)

        # 較早估驗尚未核定 → 較晚估驗前期累計 = 0、累計 = 本次 3
        self.assertEqual(line_late.previous_approved_qty, 0.0)
        self.assertEqual(line_late.cumulative_estimate_qty, 3.0)

        # 事後才核定「日期較早」的估驗（M3.0 #2 關鍵場景）
        est_early.action_approve()
        line_late.invalidate_recordset()

        # 非儲存 compute → 重讀即反映：前期累計 = 5、本次累計 = 5 + 3 = 8
        self.assertEqual(
            line_late.previous_approved_qty, 5.0,
            "M3.0#2：較早估驗事後核定，較晚估驗前期累計未反映（stale）",
        )
        self.assertEqual(
            line_late.cumulative_estimate_qty, 8.0,
            "M3.0#2：較晚估驗累計數量未納入事後核定的較早估驗",
        )
        self.assertEqual(
            line_late.cumulative_estimate_amount, 80.0,
            "累計金額 = 單價10 × 累計8",
        )
