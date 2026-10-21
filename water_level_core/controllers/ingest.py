# -*- coding: utf-8 -*-
"""設備上報端點（契約 v2）。

⚠️ 這是本系統唯一一支 auth='none' 的路由，也就是對外唯一開著的門。改這個檔案前先讀完：

1. **readonly=False 不能拿掉**。Odoo 18 對 auth='none' 的路由預設 readonly=True
   （odoo/http.py:889 `default_mode = ... (default_auth == 'none')`），跑在唯讀游標上
   寫不進資料庫。這個預設值不明寫就會踩到。
2. **錯誤訊息不分「站不存在」與「金鑰錯」**，都回同一句 unauthorized，
   否則這支端點會變成設備碼的探測器。
3. 金鑰比對走 `hmac.compare_digest`（見 water.level.device._verify_api_key），不要改成 ==。
4. 回應只帶「收了幾筆、要補送哪些、想要哪個版本」，不帶任何業務資料。
5. **補送清單放在回應裡**，不另開查詢端點：設備在 4G/NAT 後面沒有公網入口，
   Odoo 反向連不進去；而設備本來每分鐘就會打這支，掛在回應上零額外攻擊面。

契約全文（含 golden vector 與範例 curl）：docs/PAYLOAD_CONTRACT.md
"""

import base64
import hashlib
import logging
from datetime import datetime, timezone

from odoo import SUPERUSER_ID, http
from odoo.http import request

_logger = logging.getLogger(__name__)

# 單次上報的上限。設備正常是幾分鐘一筆，補傳最多也就幾百筆；
# 超過就是打錯或被亂打，直接擋掉不要進 ORM。
MAX_READINGS_PER_REQUEST = 2000
MAX_BODY_BYTES = 1024 * 1024  # 1 MB
# 單張關鍵幀上限。影像走自己的端點，不吃 ingest 的額度。
MAX_FRAME_BYTES = 8 * 1024 * 1024  # 8 MB

# 選填的來源 IP 白名單（逗號分隔），沒設就不檢查
IP_ALLOWLIST_PARAM = 'water_level.allowed_ips'

CONTRACT_VERSION = 2


class WaterLevelIngest(http.Controller):

    @http.route('/water-level/ingest', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def ingest(self, **kw):
        env = request.env(user=SUPERUSER_ID)

        # --- 0. 來源 IP 白名單（沒設定就跳過）---
        allowlist = (env['ir.config_parameter'].sudo()
                     .get_param(IP_ALLOWLIST_PARAM) or '').strip()
        if allowlist:
            allowed = {ip.strip() for ip in allowlist.split(',') if ip.strip()}
            if request.httprequest.remote_addr not in allowed:
                _logger.warning('水位上報被 IP 白名單擋下：%s',
                                request.httprequest.remote_addr)
                return self._json(403, {'error': 'forbidden'})

        # --- 1. 大小 ---
        content_length = request.httprequest.content_length or 0
        if content_length > MAX_BODY_BYTES:
            return self._json(413, {'error': 'payload too large'})

        # --- 2. 解析 body ---
        try:
            payload = request.get_json_data()
        except Exception:
            return self._json(400, {'error': 'bad payload'})
        if not isinstance(payload, dict):
            return self._json(400, {'error': 'bad payload'})

        raw_readings = payload.get('readings')
        if not isinstance(raw_readings, list) or not raw_readings:
            return self._json(400, {'error': 'bad payload'})
        if len(raw_readings) > MAX_READINGS_PER_REQUEST:
            return self._json(400, {'error': 'too many readings'})

        # --- 3. 認證（先查站再驗金鑰，兩種失敗回同一句話）---
        headers = request.httprequest.headers
        device_uid = headers.get('X-Device-Uid')
        api_key = headers.get('X-Api-Key')
        device = env['water.level.device'].sudo().search(
            [('device_uid', '=', device_uid)], limit=1) if device_uid else None
        if not device or not device.active or not device._verify_api_key(api_key):
            _logger.warning('水位上報認證失敗：uid=%s ip=%s',
                            device_uid, request.httprequest.remote_addr)
            return self._json(401, {'error': 'unauthorized'})

        # --- 4. 逐筆轉型，任何一筆壞掉就整批退回（不要吃掉一半）---
        try:
            rows = [self._parse_reading(item) for item in raw_readings]
        except (KeyError, TypeError, ValueError):
            return self._json(400, {'error': 'bad reading format'})

        # --- 5. 韌性狀態與設備端事件（選填）---
        device.update_health(payload.get('device') or {})
        for event_payload in (payload.get('events') or []):
            try:
                env['water.level.event'].record_from_device(device, event_payload)
            except Exception as exc:      # 事件壞掉不該讓整批讀值退回
                _logger.warning('水位事件寫入失敗 %s：%s', device.device_uid, exc)

        result = device.ingest_readings(rows)
        _logger.info('水位上報 %s：收 %s 筆、重複 %s 筆、補送 %s 段%s',
                     device.device_uid, result['accepted'], result['duplicated'],
                     len(result['resend']), '（補送批次）' if result['backfill'] else '')

        return self._json(200, {
            'ok': True,
            'v': CONTRACT_VERSION,
            'accepted': result['accepted'],
            'duplicated': result['duplicated'],
            'ack_seq': result['ack_seq'],
            'resend': result['resend'],
            'desired': device.desired_versions(),
            'server_time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        })

    # ==================== 影像關鍵幀 ====================

    @http.route('/water-level/frame', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False,
                readonly=False)
    def frame(self, **post):
        """事件影像關鍵幀上傳（multipart/form-data）。

        為什麼另開一支而不是塞進 ingest 的 JSON：base64 會膨脹 33%，
        而且一張關鍵幀就可能吃掉 ingest 那支 1 MB 的上限，讓水位資料連帶進不來。
        影像掉了可以補，水位掉了就是缺號——兩者不能共用同一個瓶頸。

        表單欄位：event_uid（設備端事件碼）、ts、kind（pre/peak/post）、
        sequence（選填）、file（檔案本體）。
        """
        env = request.env(user=SUPERUSER_ID)
        headers = request.httprequest.headers
        device_uid = headers.get('X-Device-Uid')
        api_key = headers.get('X-Api-Key')
        device = env['water.level.device'].sudo().search(
            [('device_uid', '=', device_uid)], limit=1) if device_uid else None
        if not device or not device.active or not device._verify_api_key(api_key):
            _logger.warning('關鍵幀上傳認證失敗：uid=%s ip=%s',
                            device_uid, request.httprequest.remote_addr)
            return self._json(401, {'error': 'unauthorized'})

        if not device.feature_event_capture:
            # 商業等級不含事件保全就不收。這是合約範圍，不是安全邊界。
            return self._json(402, {'error': 'event capture not included in service level'})

        upload = request.httprequest.files.get('file')
        event_uid = post.get('event_uid')
        if not upload or not event_uid:
            return self._json(400, {'error': 'file and event_uid are required'})

        event = env['water.level.event'].sudo().search([
            ('device_id', '=', device.id), ('event_uid', '=', event_uid)], limit=1)
        if not event:
            return self._json(404, {'error': 'unknown event'})

        try:
            ts = self._parse_ts(post.get('ts')) if post.get('ts') else event.start_ts
        except (TypeError, ValueError):
            return self._json(400, {'error': 'bad ts'})

        content = upload.read()
        if len(content) > MAX_FRAME_BYTES:
            return self._json(413, {'error': 'frame too large'})

        attachment = env['ir.attachment'].sudo().create({
            'name': upload.filename or ('%s-%s.jpg' % (event.name, post.get('kind', 'peak'))),
            'datas': base64.b64encode(content),
            'res_model': 'water.level.event.frame',
            'mimetype': upload.mimetype or 'image/jpeg',
        })
        frame = env['water.level.event.frame'].sudo().create({
            'event_id': event.id,
            'ts': ts,
            'kind': post.get('kind') or 'peak',
            'sequence': int(post.get('sequence') or 10),
            'attachment_id': attachment.id,
            'frame_hash': hashlib.sha256(content).hexdigest(),
            'byte_size': len(content),
        })
        attachment.sudo().write({'res_id': frame.id})
        _logger.info('關鍵幀入庫 %s 事件 %s：%s bytes', device.device_uid, event.name, len(content))
        return self._json(200, {'ok': True, 'frame_id': frame.id,
                                'hash': frame.frame_hash})

    # ==================== 內部工具 ====================

    @classmethod
    def _parse_reading(cls, item):
        """一筆讀值：ts 與 value 必填，seq_no 與 hash 是 v2 選填。"""
        row = {
            'ts': cls._parse_ts(item['ts']),
            'value': float(item['value']),
        }
        if item.get('seq_no') is not None:
            row['seq_no'] = int(item['seq_no'])
        if item.get('hash'):
            row['hash'] = str(item['hash'])
        return row

    @staticmethod
    def _parse_ts(value):
        """把上報時間轉成 naive UTC（Odoo Datetime 欄位存的就是這個）。

        接受三種寫法：
        * Unix timestamp（int/float）—— 依定義就是 UTC
        * 帶時區的 ISO 8601，例如 2026-08-19T14:22:00Z 或 +08:00
        * 不帶時區的 ISO 8601 —— 依契約視為 UTC

        時區換算只在這裡做一次。誰都不准在別的地方 + timedelta(hours=8)。
        """
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        parsed = datetime.fromisoformat(str(value).strip())
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _json(status, data):
        return request.make_json_response(data, status=status)
