# -*- coding: utf-8 -*-
"""政府辦公日曆（合約 §4）：國定假日、補行上班日，與「哪些年度有資料」。

資料來源：人事行政總處「中華民國政府行政機關辦公日曆表」（政府資料開放平台資料集 14718），
由 odoo18-docker/tools/dashboard/convert_dgpa_calendar.py 轉成本模組 data/ 底下的 CSV（每筆有 xmlid，升級即覆蓋）。

* construction.official.calendar：例外日（國定假日／補行上班日）。一般的週六日不收——例假日由每個工程自己設定。
* construction.official.calendar.year：這一年有官方資料，並記下來源檔與兩種例外日筆數。
  「缺年度」靠這張表明確判斷（不是「這一年剛好沒有例外日」）；筆數與實際列數不符的年度也當缺。

全系統共用的參照資料（不含業務資料）：工作天計算一律以 sudo 讀，看的人有沒有這兩個模型的讀取權都不影響，
指標本身仍以看的人自己的權限算（合約 §1-5）。
"""
import logging
from collections import Counter

from odoo import api, fields, models

from odoo.addons.construction_supervision_base.utils.local_date import local_today

_logger = logging.getLogger(__name__)

DAY_TYPE_HOLIDAY = 'holiday'
DAY_TYPE_MAKEUP = 'makeup_workday'
# 年度狀態
YEAR_OFFICIAL = 'official'      # 有完整的官方資料
YEAR_ESTIMATED = 'estimated'    # 尚未公告的未來年度：只依例假日推算（畫面標「預估」）
YEAR_MISSING = 'missing'        # 該有資料卻沒有（例：2015、2016 平台上沒有）→ 大聲顯示「缺 YYYY 年」


class OfficialCalendarIndex:
    """一次讀進來的日曆（例外日＋有資料的年度），給一批工作天計算共用。"""

    def __init__(self, special, official_years, today):
        self.special = special                    # {date: day_type}
        self.official_years = frozenset(official_years)
        self.max_year = max(self.official_years) if self.official_years else None
        self.this_year = today.year

    def year_status(self, year):
        if year in self.official_years:
            return YEAR_OFFICIAL
        # 未公告＝比已有資料的最後一年還晚、且不早於今年；早於今年卻沒有資料＝缺（不是「還沒公告」）
        if self.max_year is not None and year > self.max_year and year >= self.this_year:
            return YEAR_ESTIMATED
        return YEAR_MISSING


class ConstructionOfficialCalendar(models.Model):
    _name = 'construction.official.calendar'
    _description = '政府辦公日曆例外日'
    _order = 'date'

    date = fields.Date(string='日期', required=True, index=True)
    day_type = fields.Selection([
        (DAY_TYPE_HOLIDAY, '國定假日'),
        (DAY_TYPE_MAKEUP, '補行上班日'),
    ], string='類型', required=True)
    name = fields.Char(string='名稱', required=True, help='政府辦公日曆的備註（例：春節、補假、補行上班）')

    _sql_constraints = [
        ('date_uniq', 'UNIQUE (date)', '同一天只能有一筆政府辦公日曆例外日。'),
    ]

    @api.model
    def _dash_calendar_index(self):
        """讀整份日曆（sudo，參照資料）。年度的例外日筆數與宣告不符 → 該年度當缺，並記錯誤 log。"""
        today = local_today()
        days = self.sudo().search_read([], ['date', 'day_type'])
        years = self.env['construction.official.calendar.year'].sudo().search_read(
            [], ['year', 'holiday_count', 'makeup_count'])
        special = {row['date']: row['day_type'] for row in days}
        counted = Counter((d.year, t) for d, t in special.items())
        official = set()
        for row in years:
            year = row['year']
            actual = (counted[(year, DAY_TYPE_HOLIDAY)], counted[(year, DAY_TYPE_MAKEUP)])
            declared = (row['holiday_count'], row['makeup_count'])
            if actual != declared:
                _logger.error('政府辦公日曆 %s 年不完整：國定假日／補行上班日 實際 %s、宣告 %s，該年度當作缺資料',
                              year, actual, declared)
                continue
            official.add(year)
        return OfficialCalendarIndex(special, official, today)


class ConstructionOfficialCalendarYear(models.Model):
    _name = 'construction.official.calendar.year'
    _description = '政府辦公日曆年度'
    _order = 'year'
    _rec_name = 'year'

    year = fields.Integer(string='西元年', required=True)
    source_name = fields.Char(string='來源檔名稱')
    source_url = fields.Char(string='來源網址')
    source_sha256 = fields.Char(string='來源檔 SHA-256')
    holiday_count = fields.Integer(string='國定假日筆數', help='轉檔時算出的筆數；與實際筆數不符的年度當作缺資料')
    makeup_count = fields.Integer(string='補行上班日筆數', help='轉檔時算出的筆數；與實際筆數不符的年度當作缺資料')

    _sql_constraints = [
        ('year_uniq', 'UNIQUE (year)', '同一年度只能有一筆。'),
    ]
