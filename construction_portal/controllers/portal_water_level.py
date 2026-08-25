# -*- coding: utf-8 -*-
"""WaterLevelRoutesMixin —— 前台水位監測頁（v11）。

路由兩條：頁面 + 資料端點。前台沒有 orm service，資料一律由 controller 吐 JSON，
JS 端 30 秒重打一次（水位這種資料 30 秒跟即時沒有實質差別，但省掉一整套 websocket 維護）。

聚合策略：24 小時以內給原始點（5 分鐘一筆共 288 點，畫得動）；再長就分桶，
而且**取每桶最大值不是平均值**——防汛看的是峰值，平均會把一波洪峰抹平。
分桶用使用者時區切，不然「一天」會從早上八點切到隔天早上八點。
"""

from datetime import timedelta

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

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 60 * 24


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

        values = {
            'project': project,
            'page_name': 'construction_water_level',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'devices': devices,
            'device_states': {d.id: self._water_level_device_payload(d) for d in devices},
            'default_hours': RANGE_HOURS_DEFAULT,
        }
        return request.render(
            'construction_portal.portal_construction_water_level', values)

    # ==================== 資料端點 ====================

    @http.route(['/construction/<int:project_id>/water-level/data'],
                type='json', auth='user', methods=['POST'])
    def portal_water_level_data(self, project_id, device_id=None, hours=None, **post):
        try:
            self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'error': 'Access denied'}

        hours = self._water_level_clean_hours(hours)
        devices = request.env['water.level.device'].sudo().search(
            [('project_id', '=', project_id)], order='seq, id')
        if not devices:
            return {'devices': [], 'series': None, 'hours': hours}

        # 指定的站不屬於這個專案就退回第一站，別讓 device_id 變成跨專案讀取的縫隙
        selected = devices.filtered(lambda d: d.id == int(device_id or 0)) or devices[0]

        return {
            'devices': [self._water_level_device_payload(d) for d in devices],
            'selected_id': selected.id,
            'hours': hours,
            'series': self._water_level_series(selected, hours),
        }

    # ==================== 內部工具 ====================

    @staticmethod
    def _water_level_clean_hours(hours):
        try:
            hours = int(hours or RANGE_HOURS_DEFAULT)
        except (TypeError, ValueError):
            return RANGE_HOURS_DEFAULT
        return max(1, min(hours, RANGE_HOURS_MAX))

    def _water_level_device_payload(self, device):
        """站台摘要。狀態把「斷線」疊在水位等級之上——設備死掉比水位超標更常發生，
        也更容易被忽略，所以它要蓋過一切。"""
        offline = device.is_offline
        return {
            'id': device.id,
            'name': device.name,
            'seq': device.seq,
            'latitude': device.latitude,
            'longitude': device.longitude,
            'value': device.last_value if not offline else None,
            'state': 'offline' if offline else device.level_state,
            'last_seen': self._water_level_last_seen_text(device),
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

    def _water_level_series(self, device, hours):
        """回傳 {'labels': [...], 'values': [...], 'granularity': ...}。

        x 軸給格式化好的字串（category 軸），不給時間戳——Chart.js v4 的 time 軸
        要另外載 date adapter，前台為了一條折線去背一個外部相依不划算。
        """
        since = fields.Datetime.now() - timedelta(hours=hours)
        tz_name = request.env.user.tz or 'UTC'

        if hours <= RAW_HOURS_LIMIT:
            readings = request.env['water.level.reading'].sudo().search(
                [('device_id', '=', device.id), ('ts', '>=', since)], order='ts asc')
            labels = [
                fields.Datetime.context_timestamp(device, r.ts).strftime('%H:%M')
                for r in readings
            ]
            return {
                'labels': labels,
                'values': [r.value for r in readings],
                'granularity': 'raw',
            }

        bucket = BUCKET_HOUR if hours <= HOUR_BUCKET_LIMIT else BUCKET_DAY
        label_format = '%m/%d %H:%M' if bucket == BUCKET_HOUR else '%m/%d'
        request.env.cr.execute(
            """
            SELECT date_trunc(%s, (ts AT TIME ZONE 'UTC') AT TIME ZONE %s) AS bucket,
                   max(value) AS peak
              FROM water_level_reading
             WHERE device_id = %s AND ts >= %s
             GROUP BY bucket
             ORDER BY bucket
            """,
            (bucket, tz_name, device.id, since),
        )
        rows = request.env.cr.fetchall()
        return {
            # bucket 已經是當地時間，這裡不要再做一次時區換算
            'labels': [row[0].strftime(label_format) for row in rows],
            'values': [float(row[1]) for row in rows],
            'granularity': bucket,
        }
