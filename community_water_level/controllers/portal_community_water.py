# -*- coding: utf-8 -*-
"""社區蓄水池的前台水情頁。

與工程端的水位頁刻意分開兩支路由，因為兩者的主角不同：
* 工程／河川看的是「水位幾公尺、離警戒線多遠」
* 社區看的是「這個池還剩幾 %、要不要叫水車」

存取控制**不自己判斷**，交給 record rule：以非 sudo 的 browse 讀場域，
不是成員就讀不到，直接 redirect。自己寫一套 partner 比對等於在這個 codebase
引入一種只有這裡有的機制，日後沒人記得它存在。

2026-10 從 construction_portal 搬出來（社區模組可以不裝工程前台單獨上線）。
刻意寫成獨立的 http.Controller，不 mix 進 CustomerPortal：construction_portal 的
CustomerPortal 子類別曾因同名異簽章的方法污染整個 portal（memory
feedback_customer_portal_method_collision），這裡的方法名一律加 _community 前綴。
"""

from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.community_water_level.controllers.common import community_tabs
from odoo.addons.community_water_level.utils import LOCAL_TZ_NAME, SECONDS_PER_HOUR, local_stamp, to_local

RANGE_HOURS_DEFAULT = 24
RANGE_HOURS_MAX = 24 * 30
RAW_HOURS_LIMIT = 24
HOUR_BUCKET_LIMIT = 24 * 7
BUCKET_HOUR = 'hour'
BUCKET_DAY = 'day'


class CommunityWaterPortal(http.Controller):

    # ==================== 入口 ====================

    @http.route(['/community'], type='http', auth='user', website=True)
    def portal_community_index(self, **kw):
        """/my 首頁卡片連到這裡。只有一個社區就直接進去（管委會帳號幾乎都只有一個）。"""
        sites = request.env['water.level.site'].search(
            [('site_type', '=', 'community')], order='name')
        if len(sites) == 1:
            return request.redirect('/community/%s/water' % sites.id)
        return request.render('community_water_level.portal_community_index', {
            'sites': sites,
            'page_name': 'community_water',
        })

    # ==================== 頁面 ====================

    @http.route(['/community/<int:site_id>/water'],
                type='http', auth='user', website=True)
    def portal_community_water(self, site_id, **kw):
        site = self._community_site_or_none(site_id)
        if not site:
            return request.redirect('/community')

        tanks = request.env['water.level.tank'].sudo().search(
            [('site_id', '=', site.id)], order='sequence, id')
        values = {
            'site': site,
            'tanks': tanks,
            'tank_states': {t.id: self._community_tank_payload(t) for t in tanks},
            'page_name': 'community_water',
            'metered_count': len(tanks.filtered(lambda t: t.device_ids)),
            'default_hours': RANGE_HOURS_DEFAULT,
            'tabs': community_tabs(site, 'water'),
        }
        # 返回要去哪裡：只有一個社區的人，/community 會直接導回這一頁——返回連結若寫死 /community
        # 就原地不動、整頁回不到 /my（2026-10-21 使用者在 8071 踩到）。條件與 portal_community_index
        # 相同、一樣不 sudo，看得到幾個社區照樣交給 record rule。
        community_count = request.env['water.level.site'].search_count(
            [('site_type', '=', 'community')])
        values['back_url'] = '/community' if community_count > 1 else '/my'
        return request.render(
            'community_water_level.portal_community_water', values)

    # ==================== 資料端點 ====================

    @http.route(['/community/<int:site_id>/water/data'],
                type='json', auth='user', methods=['POST'])
    def portal_community_water_data(self, site_id, tank_id=None, hours=None, **post):
        site = self._community_site_or_none(site_id)
        if not site:
            return {'error': 'Access denied'}

        hours = self._community_clean_hours(hours)
        tanks = request.env['water.level.tank'].sudo().search(
            [('site_id', '=', site.id)], order='sequence, id')
        if not tanks:
            return {'tanks': [], 'series': None, 'hours': hours}

        # 指定的池不屬於這個社區就退回第一個有裝表的池，
        # 別讓 tank_id 變成跨社區讀取的縫隙
        try:
            wanted = int(tank_id or 0)
        except (TypeError, ValueError):
            wanted = 0
        selected = tanks.filtered(lambda t: t.id == wanted)
        if not selected:
            selected = tanks.filtered(lambda t: t.device_ids)[:1] or tanks[:1]

        device = selected.primary_device_id or selected.device_ids[:1]
        return {
            'site_name': site.name,
            'tanks': [self._community_tank_payload(t) for t in tanks],
            'selected_id': selected.id,
            'hours': hours,
            'series': self._community_series(device, hours) if device else None,
        }

    # ==================== 內部工具 ====================

    @staticmethod
    def _community_site_or_none(site_id):
        """用 record rule 當門。讀得到就是成員，讀不到就不是——不自己判斷。"""
        try:
            site = request.env['water.level.site'].browse(site_id).exists()
            if not site or site.site_type != 'community':
                return None
            site.check_access('read')
            return site.sudo()
        except (AccessError, MissingError):
            return None

    @staticmethod
    def _community_clean_hours(hours):
        try:
            hours = int(hours or RANGE_HOURS_DEFAULT)
        except (TypeError, ValueError):
            return RANGE_HOURS_DEFAULT
        return max(1, min(hours, RANGE_HOURS_MAX))

    def _community_tank_payload(self, tank):
        """一個池的摘要。物管看的是百分比，公尺是次要資訊。"""
        device = tank.primary_device_id or tank.device_ids[:1]
        offline = bool(device and device.is_offline)
        status = 'none'
        if device:
            if offline:
                status = 'offline'
            elif tank.low_fill_alert_pct and tank.fill_rate < tank.low_fill_alert_pct:
                status = 'low'
            elif tank.high_fill_alert_pct and tank.fill_rate > tank.high_fill_alert_pct:
                status = 'high'
            else:
                status = 'ok'
        return {
            'id': tank.id,
            'name': tank.name,
            'usage': dict(tank._fields['usage'].selection).get(tank.usage, ''),
            'has_device': bool(device),
            'status': status,
            # 斷線就不要給一個看起來很正常的數字
            'fill_rate': tank.fill_rate if (device and not offline) else None,
            'volume': tank.current_volume_m3 if (device and not offline) else None,
            'capacity': tank.effective_volume_m3,
            'level': tank.current_level if (device and not offline) else None,
            'low_pct': tank.low_fill_alert_pct or None,
            'high_pct': tank.high_fill_alert_pct or None,
            'last_seen': self._community_last_seen(device),
            # 圖表空白時 core 的 JS 用這兩個寫「最後一筆是什麼時候」並建議改看幾天（renderEmptyState）；
            # 相對時間（「57 天前」）不足以讓人決定要改看哪一段
            'last_ts': local_stamp(device.last_seen) if device and device.last_seen else None,
            'last_ts_age_h': (int((fields.Datetime.now() - device.last_seen).total_seconds() // SECONDS_PER_HOUR)
                              if device and device.last_seen else None),
            'latitude': device.latitude if device else 0.0,
            'longitude': device.longitude if device else 0.0,
        }

    @staticmethod
    def _community_last_seen(device):
        if not device:
            return '尚未裝表'
        if not device.last_seen:
            return '從未上報'
        minutes = int((fields.Datetime.now() - device.last_seen).total_seconds() // 60)
        if minutes < 1:
            return '剛剛更新'
        if minutes < 60:
            return '%s 分鐘前' % minutes
        if minutes < 60 * 24:
            return '%s 小時前' % (minutes // 60)
        return '%s 天前' % (minutes // (60 * 24))

    def _community_series(self, device, hours):
        """時序圖。與工程頁同一套做法：category 軸 + 後端格式化好的 label，
        超過 24 小時就分桶取每桶最高——池子看的是「最低到過哪」與「有沒有溢流」，
        平均會把兩端都抹掉，但最大值至少保住溢流那一側，與工程端保持一致。"""
        since = fields.Datetime.now() - timedelta(hours=hours)
        # 台灣時區，不跟著帳號（管委會帳號常沒設時區，會印成 UTC；見 utils.py 檔頭）
        tz_name = LOCAL_TZ_NAME

        if hours <= RAW_HOURS_LIMIT:
            readings = request.env['water.level.reading'].sudo().search(
                [('device_id', '=', device.id), ('ts', '>=', since)], order='ts asc')
            return {
                'labels': [to_local(r.ts).strftime('%H:%M') for r in readings],
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
            'labels': [row[0].strftime(label_format) for row in rows],
            'values': [float(row[1]) for row in rows],
            'granularity': bucket,
        }
