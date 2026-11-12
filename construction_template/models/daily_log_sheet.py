# -*- coding: utf-8 -*-
"""施工日誌 → 日報表／施工日誌樣板的一鍵套印匯出。"""

import logging

from odoo import api, fields, models

from ..utils import progress

_logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_TYPE = 'daily_log_1'


class DailyLogSheet(models.Model):
    _name = 'daily.log.sheet'
    _inherit = ['daily.log.sheet', 'document.template.export.mixin']

    # 當天已完成的自主檢查（淞源 C1，2026-11-12）。不儲存：每次讀都現查，已鎖定的日誌也看得到，
    # 也不會動到手填的「施工取樣試驗紀錄」。清單怎麼組只有一份，在 construction_quality。
    same_day_inspection_text = fields.Text(
        string='本日自主檢查',
        compute='_compute_same_day_inspection_text',
        help='同工程、同一天已完成（非草稿）的自主檢查，自動帶入。'
             '匯出施工日誌第一聯時，會接在「施工取樣試驗紀錄」手填內容的後面。')

    @api.depends('supervision_project_id', 'log_date')
    def _compute_same_day_inspection_text(self):
        Summary = self.env['self.inspection.daily.summary']
        for sheet in self:
            sheet.same_day_inspection_text = Summary._block_text(
                sheet.supervision_project_id, sheet.log_date) or False

    def print_actual_cumulative(self):
        """列印用的累計實際進度 %（與日誌第一聯、第二聯同一條規則，utils/progress.py）；沒有資料回 0。
        給 construction_daily_log 的後台 PDF 報表用（report/daily_log_report_progress.xml），
        它原本印 actual_progress——那欄只有舊匯入會寫，換版後的新日誌印 0%（r1 審查 F1）"""
        self.ensure_one()
        return progress.rounded(progress.actual_cumulative_on(
            self.supervision_project_id, self.log_date, sheet=self)) or 0.0

    def action_export_daily_log_template(self):
        """把本張日誌的資料填進樣板並下載。

        要匯出哪一種由 context 的 template_type 決定（按鈕上指定）：
          daily_log_1   監造版 公共工程監造日報表 第一聯
          daily_log_c1  營造版 公共工程施工日誌 第一聯
          daily_log_c2  營造版 公共工程施工日誌 第二聯
        """
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', DEFAULT_TEMPLATE_TYPE))
