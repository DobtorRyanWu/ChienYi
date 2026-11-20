# -*- coding: utf-8 -*-
"""H2 / H3 回歸測試 — 施工日誌 14 天鎖定與累計數量。

H2：is_locked 是 store=True 的 stored compute，depends 無隨時間變動的觸發源，
    建立時 <14 天存成 False 後永不翻 True；write() 的編輯封鎖信任此 stale 值 →
    14 天到期仍可改動（DB 實查：336/1282 aged sheet 仍 is_locked=False）。
    這些數量是估驗/請款金額來源，改得動 = 金額可被竄改。

H3：cumulative_qty 為跨列聚合（同工項、date<=本列）但 @api.depends 只列自身欄位，
    補登較早日期或改量不會重算後續列 → 累計數量/完工率 stale → 請款可估量算錯。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestDailyLogLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Sheet = cls.env['daily.log.sheet']
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': 'H2 鎖定測試工程',
            'code': 'H2-LOCK',
            'project_type': 'general',
            'state': 'construction',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'H2 測試員工',
            'company_id': cls.company.id,
        })
        # 建立日誌前專案須有「使用中」進度表（construction_progress 約束）；
        # 測試直接建並置 active，略過啟用精靈。
        cls.schedule = cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        })
        cls.schedule.write({'state': 'active'})

    def _make_sheet(self, log_date):
        return self.Sheet.create({
            'supervision_project_id': self.project.id,
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'log_date': log_date,
        })

    def test_sheet_older_than_14_days_is_editable(self):
        """2026-11-20 回復原版：過 14 天的日誌照樣能改（舊系統沒有鎖定；這裡原本測的是相反的事）。"""
        sheet = self._make_sheet(fields.Date.today() - timedelta(days=20))
        self.env.cr.execute(                       # 模擬以前就建好的日誌（舊守衛放行本交易剛建立的）
            "UPDATE daily_log_sheet SET create_date = create_date - interval '30 days' WHERE id = %s", (sheet.id,))
        sheet.invalidate_recordset()
        self.assertFalse(sheet.is_locked)
        sheet.write({'notes': '滿 14 天後補記'})
        self.assertEqual(sheet.notes, '滿 14 天後補記')

    def test_young_sheet_editable(self):
        """護欄：未滿 14 天的日誌可正常編輯（修復不得誤鎖）。"""
        sheet = self._make_sheet(fields.Date.today() - timedelta(days=3))
        sheet.write({'notes': '正常編輯'})
        self.assertEqual(sheet.notes, '正常編輯')

    def test_cumulative_qty_ripples_on_backdated_line(self):
        """H3：補登較早日期的列後，較晚列的 cumulative_qty 必須重算納入。

        明細日期必須等於所屬日誌日期，故用兩張不同日期的日誌各掛一列（同工項）。
        """
        today = fields.Date.today()
        task = self.env['project.task'].create({
            'name': 'H3 工項',
            'project_id': self.project.id,
            # 以下為 construction_supervision_base 對 project.task 的 required 欄位
            'item_no': 'H3-001',
            'unit': '式',
            'planned_qty': 100.0,
            'unit_price': 0.0,
        })

        def make_line(sheet, qty):
            return self.env['daily.log.line'].create({
                'sheet_id': sheet.id,
                'work_item_id': task.id,
                'entry_type': 'contract',
                'daily_qty': qty,
                'date': sheet.log_date,
            })

        sheet_later = self._make_sheet(today)
        line_later = make_line(sheet_later, 10.0)
        self.assertEqual(line_later.cumulative_qty, 10.0, "首列累計 = 本日量")

        # 補登較早日期的日誌+列（5）→ 較晚列累計應變 15
        sheet_earlier = self._make_sheet(today - timedelta(days=1))
        make_line(sheet_earlier, 5.0)
        line_later.invalidate_recordset(['cumulative_qty'])
        self.assertEqual(
            line_later.cumulative_qty, 15.0,
            "H3：補登較早列後，較晚列 cumulative_qty 未重算納入較早量",
        )
