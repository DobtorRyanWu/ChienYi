# -*- coding: utf-8 -*-
"""社區前台：報表頁、讀值 CSV、週期報表 PDF（基本方案就有）。

門與其他社區頁同一支 `_community_site_or_none`；池參數一律驗屬於這個社區。
參數不合（期間超過上限、起訖顛倒、日期格式錯、結束日在未來）一律回報表頁顯示原因，**不默默截斷**——
匯出檔是拿去給主管機關看的，少一段而沒有人知道比拿不到更糟。
"""

import csv
import io
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import http
from odoo.http import content_disposition, request

from odoo.addons.community_water_level.controllers.common import community_tabs
from odoo.addons.community_water_level.controllers.portal_community_water import CommunityWaterPortal
from odoo.addons.community_water_level.models.water_level_site_report import PERIOD_LABELS, PERIOD_WEEK
from odoo.addons.community_water_level.utils import local_today, to_local, to_utc_naive

KIND_RAW = 'raw'
KIND_DAILY = 'daily'
# 一次匯出的期間上限（天）：逐筆一個月（每分鐘一筆＝4 萬多列／台）；日彙總 3 年＝保存年限
RAW_MAX_DAYS = 31
DAILY_MAX_DAYS = 3 * 366
CSV_STAMP_FORMAT = '%Y-%m-%d %H:%M:%S'
CSV_DAY_FORMAT = '%Y-%m-%d'
BOM = '﻿'                      # Excel 要有 BOM 才把 UTF-8 的中文讀對
PERCENT_FULL = 100.0
BAD_REQUEST = 400
PERIOD_REPORT = 'community_water_level.action_report_community_period'
# 「上一期」捷徑：從今天往回多少天一定落在上一期
PREVIOUS_PERIOD_OFFSETS = [('week', '上週', {'days': 7}), ('month', '上月', {'months': 1}),
                           ('quarter', '上一季', {'months': 3}), ('half', '上一個半年', {'months': 6}),
                           ('year', '去年', {'years': 1})]


class CommunityReportError(ValueError):
    """前台參數不合，訊息直接給使用者看。"""


class CommunityWaterReports(http.Controller):

    # ==================== 報表頁 ====================

    @http.route(['/community/<int:site_id>/reports'], type='http', auth='user', website=True)
    def community_reports(self, site_id, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        if not site:
            return request.redirect('/community')
        return self._community_render_reports(site)

    def _community_render_reports(self, site, error=None, form=None, status=200):
        today = local_today()
        return request.render('community_water_level.portal_community_reports', {
            'site': site,
            'tanks': site.tank_ids.sorted(lambda t: (t.sequence, t.id)),
            'periods': PERIOD_LABELS,
            'today': today.isoformat(),
            'previous': [(period, label, (today - relativedelta(**offset)).isoformat())
                         for period, label, offset in PREVIOUS_PERIOD_OFFSETS],
            'raw_max_days': RAW_MAX_DAYS,
            'daily_max_days': DAILY_MAX_DAYS,
            'error': error,
            'form': form or {'from': (today - timedelta(days=6)).isoformat(), 'to': today.isoformat(),
                             'kind': KIND_DAILY, 'tank': ''},
            'tabs': community_tabs(site, 'reports'),
            'header_title': site.name,
            'back_url': '/community/%s/water' % site.id,
            'page_name': 'community_water',
        }, status=status)

    # ==================== 讀值 CSV ====================

    @http.route(['/community/<int:site_id>/reports/readings.csv'], type='http', auth='user', website=True)
    def community_readings_csv(self, site_id, kind=KIND_DAILY, tank='', **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        if not site:
            return request.redirect('/community')
        form = {'from': kw.get('from', ''), 'to': kw.get('to', ''), 'kind': kind, 'tank': tank}
        try:
            start, end = self._community_parse_range(kw.get('from'), kw.get('to'),
                                                    RAW_MAX_DAYS if kind == KIND_RAW else DAILY_MAX_DAYS)
            if kind not in (KIND_RAW, KIND_DAILY):
                raise CommunityReportError('不認得的匯出格式。')
            devices = self._community_devices_for(site, tank)
        except CommunityReportError as exc:
            return self._community_render_reports(site, error=str(exc), form=form, status=BAD_REQUEST)

        start_utc = to_utc_naive(datetime.combine(start, time.min))
        end_utc = to_utc_naive(datetime.combine(end + timedelta(days=1), time.min))
        if kind == KIND_RAW:
            header, rows = self._community_raw_rows(devices, start_utc, end_utc)
        else:
            header, rows = self._community_daily_csv_rows(site, devices, start_utc, end_utc)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        content = (BOM + buffer.getvalue()).encode('utf-8')
        filename = '%s_水位%s_%s_%s.csv' % (site.name, '逐筆' if kind == KIND_RAW else '日彙總',
                                           start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))
        return request.make_response(content, headers=[
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition(filename)),
            ('Cache-Control', 'no-store'),
        ])

    @staticmethod
    def _community_parse_range(raw_from, raw_to, max_days):
        try:
            start = date.fromisoformat(raw_from or '')
            end = date.fromisoformat(raw_to or '')
        except ValueError:
            raise CommunityReportError('日期格式不對，請用日曆選日期。')
        if start > end:
            raise CommunityReportError('起日不能晚於迄日。')
        if end > local_today():
            raise CommunityReportError('迄日不能晚於今天。')
        if (end - start).days + 1 > max_days:
            raise CommunityReportError('一次最多匯出 %s 天，請把期間縮短或分次匯出。' % max_days)
        return start, end

    @staticmethod
    def _community_devices_for(site, tank):
        """要匯出的設備（含停用的）。指定的池必須屬於這個社區。"""
        devices = site._community_report_devices()
        if not tank:
            return devices
        try:
            tank_id = int(tank)
        except (TypeError, ValueError):
            raise CommunityReportError('找不到這個蓄水池。')
        if tank_id not in site.tank_ids.ids:
            raise CommunityReportError('找不到這個蓄水池。')
        return devices.filtered(lambda d: d.tank_id.id == tank_id)

    @staticmethod
    def _community_device_label(device):
        return '%s（已停用）' % device.name if not device.active else device.name

    def _community_raw_rows(self, devices, start_utc, end_utc):
        header = ['時間（台灣）', '蓄水池', '監測站', '水位(m)', '原始值(m)', '序號']
        if not devices:
            return header, []
        by_id = {d.id: d for d in devices}
        request.env.cr.execute(
            """SELECT device_id, ts, value, raw_value, seq_no FROM water_level_reading
                WHERE device_id IN %s AND ts >= %s AND ts < %s ORDER BY ts, device_id""",
            (tuple(devices.ids), start_utc, end_utc))
        rows = []
        for device_id, ts, value, raw_value, seq_no in request.env.cr.fetchall():
            device = by_id[device_id]
            rows.append([to_local(ts).strftime(CSV_STAMP_FORMAT), device.tank_id.name or '',
                         self._community_device_label(device),
                         '%.3f' % value if value is not None else '',
                         '%.3f' % raw_value if raw_value is not None else '',
                         seq_no if seq_no is not None else ''])
        return header, rows

    def _community_daily_csv_rows(self, site, devices, start_utc, end_utc):
        header = ['日期（台灣）', '蓄水池', '監測站', '筆數', '最高水位(m)', '最低水位(m)', '平均水位(m)',
                  '最高水位時儲水率(%)', '最低水位時儲水率(%)']
        by_id = {d.id: d for d in devices}
        rows = []
        for row in site._community_daily_rows(devices, start_utc, end_utc):
            device = by_id[row['device_id']]
            tank = device.tank_id
            capacity = tank._capacity() if tank else 0.0

            def fill(level):
                return '%.1f' % (tank._volume_at(level) / capacity * PERCENT_FULL) if capacity else ''

            rows.append([row['day'].strftime(CSV_DAY_FORMAT), tank.name or '', self._community_device_label(device),
                         row['count'], '%.3f' % row['max'], '%.3f' % row['min'], '%.3f' % row['avg'],
                         fill(row['max']), fill(row['min'])])
        return header, rows

    # ==================== 週期報表 PDF ====================

    @http.route(['/community/<int:site_id>/reports/period.pdf'], type='http', auth='user', website=True)
    def community_period_pdf(self, site_id, period=PERIOD_WEEK, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        if not site:
            return request.not_found()
        form = {'period': period, 'date': kw.get('date', '')}
        try:
            if period not in PERIOD_LABELS:
                raise CommunityReportError('不認得的報表期間。')
            try:
                anchor = date.fromisoformat(kw.get('date') or local_today().isoformat())
            except ValueError:
                raise CommunityReportError('日期格式不對，請用日曆選日期。')
            if anchor > local_today():
                raise CommunityReportError('日期不能晚於今天。')
        except CommunityReportError as exc:
            return self._community_render_reports(site, error=str(exc), form=form, status=BAD_REQUEST)
        stats = site._community_period_stats(period, anchor)
        pdf, _report_type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            PERIOD_REPORT, site.ids, data=stats)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition('%s_%s.pdf' % (site.name, stats['title']))),
            ('Cache-Control', 'no-store'),
        ])
