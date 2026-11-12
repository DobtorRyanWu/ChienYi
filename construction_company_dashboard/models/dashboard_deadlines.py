# -*- coding: utf-8 -*-
"""公司儀表板總覽頁的三個區塊：期限待辦、近期行事曆、每月估驗（淞源 2026-11-10 會議 C5、C7）。

會議記錄第七節 C5：主管儀表板缺「契約期限待辦清單」和「每月請款追蹤」。
老闆：待辦要依期限排序，先試試看感覺；快到期還沒安排就在主管的控台亮燈。

* get_dash_deadline_items()：期限待辦清單與各燈號件數。清單本身由 construction_portal 的
  project.project._cy_deadline_data() 產生（手機首頁與每日提醒讀同一份），這裡只加上
  「帳號整個被預設拒絕」的處理；燈號的兩個天數讀目前公司的設定（res.company._cy_deadline_days）。
* get_dash_monthly_estimates()：最近幾個月每月的估驗期數與金額（不含草稿，與卡片「本月估驗」同一個定義）。
  資料來源用估驗（payment.estimate）：dev 上請款單（payment.claim）是 0 筆、估驗 107 筆，現場實際在用的是估驗。
* get_dash_week_calendar()：今天起 7 天內的行事曆待辦事項（含還沒完成的過期事項）。行事曆在選裝模組
  construction_office；沒裝就回 installed=False，前端整塊不顯示。清單由那邊的 _office_upcoming() 產生
  （手機行事曆頁的「7 天內」是同一個條件）。
* 都以看的人自己的權限算（不 sudo）；讀不到 → status=no_access，不補算、不顯示 0（合約 §1-8）。
* 三支方法要列在 models/method_gate.py 的 DASHBOARD_METHODS。
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .project_dashboard import (
    BLOCKED_MESSAGES, ESTIMATE_AMOUNT_FIELD, ESTIMATE_EXCLUDED_STATES, STATUS_ERROR, STATUS_MESSAGES,
    STATUS_NO_ACCESS, STATUS_OK, _month_bounds,
)

_logger = logging.getLogger(__name__)

ESTIMATE_MODEL = 'payment.estimate'
CALENDAR_MODEL = 'construction.calendar.event'      # construction_office（選裝）
DEADLINE_LIST_LIMIT = 30            # 總覽頁的期限待辦最多列幾筆（件數另外給全部）
MONTHLY_ESTIMATE_MONTHS = 12        # 每月估驗看最近幾個月（含本月）
MONTH_KEY_FORMAT = '%Y-%m'


class ProjectProjectDashDeadlines(models.Model):
    _inherit = 'project.project'

    @api.model
    def get_dash_deadline_items(self):
        """期限待辦（看得到的全部工程）。

        回傳 {'status', 'message', 'today', 'items', 'counts', 'denied', 'site_days', 'manager_days'}；
        items／counts 的格式見 construction_portal 的 _cy_deadline_data。
        """
        result = {'status': STATUS_OK, 'message': False, 'today': local_today().isoformat(), 'items': [],
                  'counts': None, 'denied': [], 'site_days': None, 'manager_days': None}
        blocked = self._dash_blocked_reason()
        if blocked:
            result.update(status=STATUS_NO_ACCESS, message=BLOCKED_MESSAGES[blocked])
            return result
        try:
            # 燈號的兩個天數讀目前公司的設定（公司表單「工程監造」頁；淞源 C8）
            site_days, manager_days = self.env.company._cy_deadline_days()
            result.update(self._cy_deadline_data(limit=DEADLINE_LIST_LIMIT, site_days=site_days,
                                                 manager_days=manager_days))
        except AccessError:
            result.update(status=STATUS_NO_ACCESS, message=STATUS_MESSAGES[STATUS_NO_ACCESS])
        except Exception:
            _logger.exception('公司儀表板期限待辦計算失敗')
            result.update(status=STATUS_ERROR, message=STATUS_MESSAGES[STATUS_ERROR])
        return result

    @api.model
    def get_dash_week_calendar(self):
        """近期行事曆（看得到的事項）。

        回傳 {'status', 'message', 'installed', 'today', 'days', 'count', 'items'}；
        items 的格式見 construction_office 的 construction.calendar.event._office_upcoming。
        """
        result = {'status': STATUS_OK, 'message': False, 'installed': CALENDAR_MODEL in self.env,
                  'today': local_today().isoformat(), 'days': None, 'count': None, 'items': []}
        if not result['installed']:
            return result
        blocked = self._dash_blocked_reason()
        if blocked:
            result.update(status=STATUS_NO_ACCESS, message=BLOCKED_MESSAGES[blocked])
            return result
        try:
            Event = self.env[CALENDAR_MODEL]
            Event.check_access('read')
            result.update(Event._office_upcoming())
        except AccessError:
            result.update(status=STATUS_NO_ACCESS, message=STATUS_MESSAGES[STATUS_NO_ACCESS])
        except Exception:
            _logger.exception('公司儀表板近期行事曆讀取失敗')
            result.update(status=STATUS_ERROR, message=STATUS_MESSAGES[STATUS_ERROR])
        return result

    @api.model
    def _dash_recent_months(self, today, count):
        """最近 count 個月的 1 日（由舊到新，最後一個是本月）。"""
        months = [today.replace(day=1)]
        while len(months) < count:
            months.append((months[-1] - timedelta(days=1)).replace(day=1))
        return list(reversed(months))

    @api.model
    def get_dash_monthly_estimates(self):
        """最近 MONTHLY_ESTIMATE_MONTHS 個月每月的估驗（不含草稿）：期數與金額。

        回傳 {'status', 'message', 'months': [{'month': 'YYYY-MM', 'count', 'amount'}], 'total_count',
              'total_amount', 'max_amount'（畫橫條用）, 'date_from', 'date_to'}
        """
        today = local_today()
        months = self._dash_recent_months(today, MONTHLY_ESTIMATE_MONTHS)
        # 本月算到月底（估驗日期可以先填這個月稍後的日子）：這樣最後一列和卡片「本月估驗」是同一個數字
        _month_start, month_end = _month_bounds(today)
        result = {'status': STATUS_OK, 'message': False, 'months': [], 'total_count': None, 'total_amount': None,
                  'max_amount': None, 'date_from': fields.Date.to_string(months[0]),
                  'date_to': fields.Date.to_string(month_end)}
        blocked = self._dash_blocked_reason()
        if blocked:
            result.update(status=STATUS_NO_ACCESS, message=BLOCKED_MESSAGES[blocked])
            return result
        try:
            if not self._dash_group_readable('estimate'):
                raise AccessError(STATUS_MESSAGES[STATUS_NO_ACCESS])
            Estimate = self.env[ESTIMATE_MODEL].with_context(active_test=False)
            Estimate.check_access('read')
            domain = self.browse()._dash_scope(ESTIMATE_MODEL) + [
                ('estimate_date', '>=', months[0]), ('estimate_date', '<=', month_end),
                ('state', 'not in', ESTIMATE_EXCLUDED_STATES)]
            groups = Estimate._read_group(domain, ['estimate_date:month'], ['__count', f'{ESTIMATE_AMOUNT_FIELD}:sum'])
            by_month = {fields.Date.to_date(month): (count, amount or 0.0) for month, count, amount in groups if month}
            rows = [{'month': month.strftime(MONTH_KEY_FORMAT),
                     'count': by_month.get(month, (0, 0.0))[0],
                     'amount': by_month.get(month, (0, 0.0))[1]} for month in months]
            result.update(months=rows,
                          total_count=sum(row['count'] for row in rows),
                          total_amount=sum(row['amount'] for row in rows),
                          max_amount=max(row['amount'] for row in rows))
        except AccessError:
            result.update(status=STATUS_NO_ACCESS, message=STATUS_MESSAGES[STATUS_NO_ACCESS])
        except Exception:
            _logger.exception('公司儀表板每月估驗計算失敗')
            result.update(status=STATUS_ERROR, message=STATUS_MESSAGES[STATUS_ERROR])
        return result
