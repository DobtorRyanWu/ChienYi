# -*- coding: utf-8 -*-
"""WaterLevelRoutesMixin —— 前台水位監測頁（v11）。

路由兩條：頁面 + 資料端點。前台沒有 orm service，資料一律由 controller 吐 JSON，
JS 端 30 秒重打一次（水位這種資料 30 秒跟即時沒有實質差別，但省掉一整套 websocket 維護）。

聚合策略：24 小時以內給原始點（5 分鐘一筆共 288 點，畫得動）；再長就分桶，
而且**取每桶最大值不是平均值**——防汛看的是峰值，平均會把一波洪峰抹平。
分桶用使用者時區切，不然「一天」會從早上八點切到隔天早上八點。
"""

import csv
import io
from datetime import datetime, timedelta
from urllib.parse import quote

import pytz

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

# 前台時間範圍按鈕
RANGE_HOURS_DEFAULT = 24
RANGE_HOURS_MAX = 24 * 30
# 這個範圍以內直接給原始點，超過就分桶
RAW_HOURS_LIMIT = 24
HOUR_BUCKET_LIMIT = 24 * 7

# 允許的分桶粒度（會進 SQL，必須是白名單，不能吃使用者輸入）
BUCKET_HOUR = 'hour'
BUCKET_DAY = 'day'
BUCKET_RAW = 'raw'

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 60 * 24

# 原始點超過這個數就降級成每小時——每分鐘上報的設備 24 小時是 1440 點，
# 手機畫得動但滑起來會頓，而且逐筆表也塞不下。
RAW_POINT_LIMIT = 2000
# 逐筆表一次回傳的上限。要完整資料請走 CSV 匯出，不要把它塞進輪詢的 payload。
TABLE_ROW_LIMIT = 500
# CSV 匯出的硬上限與取數批次（避免一次 fetchall 幾十萬列）
EXPORT_ROW_LIMIT = 200000
EXPORT_CHUNK = 5000

HOURS_IN_DAY = 24
SECONDS_PER_HOUR = 3600

# 自訂區間的時間格式：前端送 'YYYY-MM-DD' + 小時（0-23）兩個欄位，
# 不用 datetime-local——行動瀏覽器對它的分鐘粒度與 UI 差異太大。
DATE_INPUT_FORMAT = '%Y-%m-%d'
STAMP_FORMAT = '%m/%d %H:%M'      # 逐筆表用（手機兩欄，不放年）
CSV_STAMP_FORMAT = '%Y-%m-%d %H:%M:%S'   # 匯出檔用（完整，給 Excel）
FILENAME_STAMP_FORMAT = '%Y%m%d%H%M'


class WaterLevelRoutesMixin:

    # ==================== 頁面 ====================

    @http.route(['/construction/<int:project_id>/water-level'],
                type='http', auth='user', website=True)
    def portal_construction_water_level(self, project_id, **kw):
        """水位監測頁。第一次進來就把站台清單 server render 出來，
        圖表資料才走 JSON（首屏不要等 XHR）。"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        devices = request.env['water.level.device'].sudo().search(
            [('project_id', '=', project_id)], order='seq, id')

        # 自訂區間的預設值：迄=今天、起=昨天，使用者一展開就是可以直接按查詢的狀態
        today_local = fields.Datetime.context_timestamp(
            request.env.user, fields.Datetime.now()).date()
        values = {
            'project': project,
            'primary_device': self._water_level_primary(devices) or devices[:1],
            'page_name': 'construction_water_level',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'devices': devices,
            'device_states': {d.id: self._water_level_device_payload(d) for d in devices},
            'default_hours': RANGE_HOURS_DEFAULT,
            'range_max_days': RANGE_HOURS_MAX // HOURS_IN_DAY,
            'custom_date_from': (today_local - timedelta(days=1)).strftime(DATE_INPUT_FORMAT),
            'custom_date_to': today_local.strftime(DATE_INPUT_FORMAT),
            'hour_choices': list(range(HOURS_IN_DAY)),
        }
        return request.render(
            'construction_portal.portal_construction_water_level', values)

    # ==================== 資料端點 ====================

    @http.route(['/construction/<int:project_id>/water-level/data'],
                type='json', auth='user', methods=['POST'])
    def portal_water_level_data(self, project_id, device_id=None, hours=None,
                                date_from=None, hour_from=None,
                                date_to=None, hour_to=None, **post):
        try:
            self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'error': 'Access denied'}

        window = self._water_level_window(hours, date_from, hour_from, date_to, hour_to)
        devices = request.env['water.level.device'].sudo().search(
            [('project_id', '=', project_id)], order='seq, id')
        if not devices:
            return {'devices': [], 'series': None, 'hours': window['hours']}

        # 指定的站不屬於這個專案就退回第一站，別讓 device_id 變成跨專案讀取的縫隙
        selected = (devices.filtered(lambda d: d.id == int(device_id or 0))
                    or self._water_level_primary(devices)
                    or devices[0])

        return {
            'devices': [self._water_level_device_payload(d) for d in devices],
            'selected_id': selected.id,
            'hours': window['hours'],
            'series': self._water_level_series(selected, window),
        }

    # ==================== CSV 匯出 ====================

    @http.route(['/construction/<int:project_id>/water-level/export.csv'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_water_level_export_csv(self, project_id, device_id=None, hours=None,
                                      date_from=None, hour_from=None,
                                      date_to=None, hour_to=None, **kw):
        """把畫面上那段區間的**原始逐筆**資料吐成 CSV。

        走 type='http' 的 GET 而不是 json＋Blob：手機（尤其 iOS）對 blob: 下載的支援
        不一致，但對「連結指向一個會回 attachment 的網址」是穩的。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        devices = request.env['water.level.device'].sudo().search(
            [('project_id', '=', project_id)], order='seq, id')
        if not devices:
            return request.redirect('/construction/%s/water-level' % project_id)
        # 同 data 端點：device_id 只拿來在本專案的站裡挑，不直接 browse
        device = (devices.filtered(lambda d: d.id == int(device_id or 0))
                  or self._water_level_primary(devices)
                  or devices[0])

        window = self._water_level_window(hours, date_from, hour_from, date_to, hour_to)
        rows, truncated = self._water_level_export_rows(device, window)

        tz = pytz.timezone(self._water_level_tz())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['# 工程', project.name])
        writer.writerow(['# 監測站', device.name])
        writer.writerow(['# 區間', '%s ~ %s（%s）' % (
            self._water_level_to_local(window['start']).strftime(CSV_STAMP_FORMAT),
            self._water_level_to_local(window['end']).strftime(CSV_STAMP_FORMAT),
            tz.zone)])
        if device.is_demo:
            # 匯出檔會離開這個頁面單獨流傳，示範資料的警語必須跟著檔案走
            writer.writerow(['# 示範資料：系統模擬值，不是現場量測值'])
        writer.writerow(['時間', '水位(m)', '設備原始值'])
        for ts, value, raw_value in rows:
            writer.writerow([
                self._water_level_to_local(ts).strftime(CSV_STAMP_FORMAT),
                '' if value is None else '%.3f' % value,
                '' if raw_value is None else '%.3f' % raw_value,
            ])
        if truncated:
            writer.writerow(['# 已達單次匯出上限 %s 列，請縮小查詢區間取得其餘資料'
                             % EXPORT_ROW_LIMIT])

        # BOM：沒有它 Excel 開中文欄位一定亂碼
        content = ('﻿' + buf.getvalue()).encode('utf-8')
        filename = self._water_level_export_filename(device, window)
        return request.make_response(content, headers=[
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Length', len(content)),
            # 兩種形式都給：Safari 讀 filename=，其餘讀 filename*=
            ('Content-Disposition',
             'attachment; filename="water-level-%s.csv"; filename*=UTF-8\'\'%s'
             % (device.id, quote(filename))),
            ('Cache-Control', 'no-store'),
        ])

    # ==================== 內部工具 ====================

    @staticmethod
    def _water_level_clean_hours(hours):
        try:
            hours = int(hours or RANGE_HOURS_DEFAULT)
        except (TypeError, ValueError):
            return RANGE_HOURS_DEFAULT
        return max(1, min(hours, RANGE_HOURS_MAX))

    @staticmethod
    def _water_level_tz():
        return request.env.user.tz or 'UTC'

    @classmethod
    def _water_level_to_local(cls, dt):
        """naive UTC → 使用者時區的 aware datetime。

        reading.ts 存的是 naive UTC，畫面與匯出一律換成當地時間；
        少換一次就會出現「凌晨的洪峰標成下午」這種對不起現場的事。
        """
        return pytz.utc.localize(dt).astimezone(pytz.timezone(cls._water_level_tz()))

    @classmethod
    def _water_level_parse_local(cls, date_str, hour_str):
        """把 'YYYY-MM-DD' + 小時（0-23）當作使用者時區的時刻，轉成 naive UTC。

        解析失敗一律回 None（呼叫端會退回快捷區間）——查詢條件壞掉不該丟例外給業主看，
        也不該把壞字串往 SQL 送。
        """
        if not date_str:
            return None
        try:
            day = datetime.strptime(str(date_str).strip(), DATE_INPUT_FORMAT)
            hour = int(hour_str or 0)
        except (TypeError, ValueError):
            return None
        if not 0 <= hour < HOURS_IN_DAY:
            return None
        local = pytz.timezone(cls._water_level_tz()).localize(
            day.replace(hour=hour, minute=0, second=0, microsecond=0))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _water_level_window(self, hours=None, date_from=None, hour_from=None,
                            date_to=None, hour_to=None):
        """算出這次要查的區間。回 dict：start/end（naive UTC）、hours、mode、notice。

        優先序：起訖都解析得出來 → 自訂區間；否則退回 24/168/720 那組快捷。
        起訖顛倒自動對調、迄夾到現在（不給未來）、跨度夾到 30 天並回一句 notice——
        默默截斷比報錯更糟，使用者會以為自己看到的是完整區間。
        """
        now = fields.Datetime.now()
        start = self._water_level_parse_local(date_from, hour_from)
        end = self._water_level_parse_local(date_to, hour_to)
        if not (start and end):
            hours = self._water_level_clean_hours(hours)
            return {
                'start': now - timedelta(hours=hours),
                'end': now,
                'hours': hours,
                'mode': 'quick',
                'notice': '',
            }

        notice = ''
        if start > end:
            start, end = end, start
            notice = '起訖時間對調了'
        if end > now:
            end = now
            notice = '迄止時間已調整到現在'
        span_hours = max(1, int((end - start).total_seconds() // SECONDS_PER_HOUR))
        if span_hours > RANGE_HOURS_MAX:
            start = end - timedelta(hours=RANGE_HOURS_MAX)
            span_hours = RANGE_HOURS_MAX
            notice = '一次最多查 %s 天，已自動縮短' % (RANGE_HOURS_MAX // HOURS_IN_DAY)
        return {
            'start': start,
            'end': end,
            'hours': span_hours,
            'mode': 'custom',
            'notice': notice,
        }

    def _water_level_granularity(self, device, window):
        """決定這個區間要給原始點還是分桶。

        回傳值只可能是三個模組常數之一——它會進 `date_trunc()`，
        絕對不能有任何一條路徑讓使用者輸入流到這裡。
        """
        if window['hours'] > HOUR_BUCKET_LIMIT:
            return BUCKET_DAY
        if window['hours'] > RAW_HOURS_LIMIT:
            return BUCKET_HOUR
        count = request.env['water.level.reading'].sudo().search_count([
            ('device_id', '=', device.id),
            ('ts', '>=', window['start']),
            ('ts', '<=', window['end']),
        ])
        # 每分鐘上報的設備 24 小時就 1440 點，降一級才畫得順
        return BUCKET_RAW if count <= RAW_POINT_LIMIT else BUCKET_HOUR

    def _water_level_stats(self, device, window):
        """區間統計。用原始值算，不受分桶影響——分桶取的是每桶最大值，
        拿分桶結果算平均會比真實平均高。"""
        request.env.cr.execute(
            """
            SELECT min(value), max(value), avg(value), count(*)
              FROM water_level_reading
             WHERE device_id = %s AND ts >= %s AND ts <= %s
            """,
            (device.id, window['start'], window['end']),
        )
        low, high, avg, count = request.env.cr.fetchone()
        return {
            'min': float(low) if low is not None else None,
            'max': float(high) if high is not None else None,
            'avg': float(avg) if avg is not None else None,
            'count': count or 0,
        }

    def _water_level_export_rows(self, device, window):
        """匯出用的原始逐筆資料。分批 fetch，不用 ORM——
        43,200 筆的 recordset 光 prefetch 就吃掉幾百 MB。"""
        request.env.cr.execute(
            """
            SELECT ts, value, raw_value
              FROM water_level_reading
             WHERE device_id = %s AND ts >= %s AND ts <= %s
             ORDER BY ts
             LIMIT %s
            """,
            (device.id, window['start'], window['end'], EXPORT_ROW_LIMIT + 1),
        )
        rows = []
        while True:
            chunk = request.env.cr.fetchmany(EXPORT_CHUNK)
            if not chunk:
                break
            rows.extend(chunk)
        truncated = len(rows) > EXPORT_ROW_LIMIT
        return rows[:EXPORT_ROW_LIMIT], truncated

    def _water_level_export_filename(self, device, window):
        prefix = '示範資料_' if device.is_demo else ''
        name = '%s水位_%s_%s-%s.csv' % (
            prefix,
            device.name,
            self._water_level_to_local(window['start']).strftime(FILENAME_STAMP_FORMAT),
            self._water_level_to_local(window['end']).strftime(FILENAME_STAMP_FORMAT),
        )
        # 檔名裡的路徑字元會讓某些瀏覽器把檔案存到奇怪的地方，全部換掉
        for bad in '/\\:*?"<>|\r\n\t':
            name = name.replace(bad, '_')
        return name

    @staticmethod
    def _water_level_primary(devices):
        """場域指定的代表站——一個工程有好幾站時，預設要先看哪一台。

        工地自己的設備比流域上游的參考站更該擺在第一眼（上游站是拿來對照的）。
        場域沒指定就回空，呼叫端自己退回上下游序最前面那台。
        """
        return devices.filtered(lambda d: d == d.site_id.primary_device_id)[:1]

    def _water_level_device_payload(self, device):
        """站台摘要。狀態把「斷線」疊在水位等級之上——設備死掉比水位超標更常發生，
        也更容易被忽略，所以它要蓋過一切。"""
        offline = device.is_offline
        return {
            'id': device.id,
            'name': device.name,
            'is_demo': device.is_demo,
            'seq': device.seq,
            'map_label': device.map_label or '',
            'latitude': device.latitude,
            'longitude': device.longitude,
            'value': device.last_value if not offline else None,
            'state': 'offline' if offline else device.level_state,
            'last_seen': self._water_level_last_seen_text(device),
            # 絕對時間：相對時間（「1 天前」）不足以讓人決定要改看幾天
            'last_ts': (self._water_level_to_local(device.last_seen).strftime(STAMP_FORMAT)
                        if device.last_seen else None),
            'last_ts_age_h': (int((fields.Datetime.now() - device.last_seen).total_seconds()
                                  // SECONDS_PER_HOUR)
                              if device.last_seen else None),
            'levels': {
                'lv3': device.level_3 or None,
                'lv2': device.level_2 or None,
                'lv1': device.level_1 or None,
            },
        }

    @staticmethod
    def _water_level_last_seen_text(device):
        if not device.last_seen:
            return '從未上報'
        elapsed_min = int(
            (fields.Datetime.now() - device.last_seen).total_seconds() // 60)
        if elapsed_min < 1:
            return '剛剛更新'
        if elapsed_min < MINUTES_PER_HOUR:
            return '%s 分鐘前' % elapsed_min
        if elapsed_min < MINUTES_PER_DAY:
            return '%s 小時前' % (elapsed_min // MINUTES_PER_HOUR)
        return '%s 天前' % (elapsed_min // MINUTES_PER_DAY)

    def _water_level_series(self, device, window):
        """回傳圖表與逐筆表共用的一組資料。

        x 軸給格式化好的字串（category 軸），不給時間戳——Chart.js v4 的 time 軸
        要另外載 date adapter，前台為了一條折線去背一個外部相依不划算。

        `rows` 是**圖上那些點**的逐筆版本（最新在前），不是永遠的原始逐筆：
        表格與圖必須是同一組數字，否則 30 天的分桶圖配逐筆原始表，
        會讓人以為圖漏畫了。要完整原始資料請走 CSV 匯出。
        """
        granularity = self._water_level_granularity(device, window)
        tz_name = self._water_level_tz()
        # 跨日的區間，x 軸只給 HH:MM 會出現一堆重複刻度，要帶上日期
        cross_day = window['hours'] > HOURS_IN_DAY

        if granularity == BUCKET_RAW:
            readings = request.env['water.level.reading'].sudo().search(
                [('device_id', '=', device.id),
                 ('ts', '>=', window['start']),
                 ('ts', '<=', window['end'])], order='ts asc')
            locals_ = [self._water_level_to_local(r.ts) for r in readings]
            labels = [t.strftime(STAMP_FORMAT if cross_day else '%H:%M') for t in locals_]
            stamps = [t.strftime(STAMP_FORMAT) for t in locals_]
            values = [r.value for r in readings]
        else:
            label_format = STAMP_FORMAT if granularity == BUCKET_HOUR else '%m/%d'
            request.env.cr.execute(
                """
                SELECT date_trunc(%s, (ts AT TIME ZONE 'UTC') AT TIME ZONE %s) AS bucket,
                       max(value) AS peak
                  FROM water_level_reading
                 WHERE device_id = %s AND ts >= %s AND ts <= %s
                 GROUP BY bucket
                 ORDER BY bucket
                """,
                (granularity, tz_name, device.id, window['start'], window['end']),
            )
            buckets = request.env.cr.fetchall()
            # bucket 已經是當地時間，這裡不要再做一次時區換算
            labels = [row[0].strftime(label_format) for row in buckets]
            stamps = labels
            values = [float(row[1]) for row in buckets]

        stats = self._water_level_stats(device, window)
        # 表格最新在最上面：現場的人先看到的應該是「現在多高」
        rows = list(zip(stamps, values))[::-1]
        return {
            'labels': labels,
            'values': values,
            'granularity': granularity,
            'rows': rows[:TABLE_ROW_LIMIT],
            'row_total': len(rows),
            'row_truncated': len(rows) > TABLE_ROW_LIMIT,
            'raw_total': stats['count'],
            'stats': stats,
            'window': {
                'from': self._water_level_to_local(window['start']).strftime(STAMP_FORMAT),
                'to': self._water_level_to_local(window['end']).strftime(STAMP_FORMAT),
                'hours': window['hours'],
                'mode': window['mode'],
                'notice': window['notice'],
            },
        }
