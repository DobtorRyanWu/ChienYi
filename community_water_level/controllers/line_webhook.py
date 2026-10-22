# -*- coding: utf-8 -*-
"""LINE 官方帳號的 webhook：綁定碼、加好友、封鎖。

骨架照 core 的 /water-level/ingest：auth='none'（LINE 平台沒有 session）、**readonly=False**
（Odoo 18 對 auth='none' 預設唯讀，寫不進去）、csrf=False、save_session=False。
沒有 session 的請求要靠 dbfilter 只對到一個庫才選得到資料庫——8071 是單庫，學長那邊部署也必須單庫（與 ingest 同一個前提）。

驗證：通道不存在、不是 LINE、secret 空著、簽章空著或對不上，一律回同一個 401（不讓人用回應差異探通道 id）。
body 不寫進 log：裡面有綁定碼與 userId。
"""

import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import Response, request

from odoo.addons.community_water_level.models.water_level_line import CHANNEL_LINE

_logger = logging.getLogger(__name__)

# LINE 的 webhook body 很小（一次幾個事件）；驗簽前要整個讀進來，所以上限要設小
LINE_WEBHOOK_MAX_BYTES = 256 * 1024
HTTP_UNAUTHORIZED = 401
HTTP_BAD_REQUEST = 400


class CommunityLineWebhook(http.Controller):

    @http.route('/water-level/line/webhook/<int:channel_id>', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False, readonly=False, max_content_length=LINE_WEBHOOK_MAX_BYTES)
    def line_webhook(self, channel_id, **kw):
        env = request.env(user=SUPERUSER_ID)
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('X-Line-Signature', '')
        channel = env['water.level.alert.channel'].browse(channel_id).exists()
        if not channel or channel.channel_type != CHANNEL_LINE or not channel._line_signature_ok(body, signature):
            return Response(status=HTTP_UNAUTHORIZED)
        try:
            data = json.loads(body)
        except ValueError:
            return Response(status=HTTP_BAD_REQUEST)
        # LINE 後台按「驗證」時送 events: []，要回 200
        replies = channel._line_handle_events(data.get('events') if isinstance(data, dict) else [])
        if replies:
            token = channel.sudo().line_channel_access_token
            env.cr.postcommit.add(lambda: channel._line_send_replies(token, replies))
        return Response('OK', status=200)
