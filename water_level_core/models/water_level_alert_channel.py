# -*- coding: utf-8 -*-
"""告警外送通道 —— 把水位異常推到系統外面去。

**為什麼需要這個模組**
`water.level.monitor._notify()` 原本只做 message_post，訊息落在 Odoo 的
chatter（內部收件匣／前台通知中心）。使用者不登入就看不到，
撐不起 DM 旗艦等級白紙黑字的「異常即時告警推播」。

**兩層**
* 與管道無關的部分（挑通道、節流、送達紀錄、失敗重送）——本檔完整實作
* 真正的傳輸——`_send_<channel_type>` 一個方法一種管道

核心實作 `webhook` 與 `discord`（2026-10-21，千溢內部監看用）。其他管道由別的模組
`selection_add` 一個類型、實作 `_send_<類型>()` 就接得上（社區模組要用這個方式加 LINE），
派送層不必動。**不要預先把未實作的管道放進 Selection**——選得到卻送不出去
比沒有這個選項更糟。

**送給誰：對象分流（audience）**
告警同時要送兩種人（2026-10-21 使用者定案）：
* 千溢內部（`internal`）：**所有方案都送**——千溢要維護每一台設備，基本方案的斷線也要知道
* 客戶（`customer`）：照 DM，只有旗艦方案才有「即時告警推播」
所以「是不是旗艦」由通道判斷，不再擋在告警掃描裡。

**為什麼 inline 送、失敗才交給 cron 重送**
告警要即時，所以在開事件的當下就送；但 HTTP 呼叫在 cron 交易裡，
對方沒回應會把交易吊著。折衷是短逾時（5 秒）先試一次，
失敗就落成 pending 由重送 cron 接手。即時性與交易安全兩邊都顧到。
"""

import hashlib
import hmac
import json
import logging
from datetime import timedelta
from http import HTTPStatus

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# 出站逾時要比入站短——這是在 cron 交易裡同步呼叫，不能讓對方拖著我們
HTTP_TIMEOUT_SEC = 5
# 重送上限。超過就不再自動試，留給人看 last_error
MAX_ATTEMPTS = 5
# Discord 單則訊息內文上限（字元）
DISCORD_CONTENT_MAX = 2000
# 只接受 https 的 Discord webhook 網址：http 會被 301 轉址，requests 把 POST 改成 GET，
# 對方回 200 卻什麼都沒送出——會被記成「已送達」
DISCORD_URL_PREFIXES = ('https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/')
# 被限流（429）時暫停送這個通道多久：對方沒給秒數用預設，給太大就封頂
RATE_LIMIT_DEFAULT_SEC = 60
RATE_LIMIT_MAX_SEC = 3600

# 嚴重度排序，用來比對通道設定的最低門檻
SEVERITY_ORDER = {'info': 0, 'warning': 1, 'critical': 2}


class PermanentDeliveryError(Exception):
    """重送也不會好的失敗（推送網址被刪或失效）。送達紀錄直接記失敗，不留給重送 cron——
    一直重打只會累積無效請求（Discord 對大量 4xx 會封 IP）。"""


class RateLimitedError(Exception):
    """對方要求等一下（429）。不算一次嘗試，通道暫停到 retry_after 秒後，期間誰都不送。"""

    def __init__(self, retry_after):
        super().__init__(retry_after)
        self.retry_after = retry_after


class WaterLevelAlertChannel(models.Model):
    _name = 'water.level.alert.channel'
    _description = '水位告警外送通道'
    _order = 'sequence, id'

    name = fields.Char(string='通道名稱', required=True)
    sequence = fields.Integer(string='順序', default=10)
    active = fields.Boolean(string='啟用', default=True)

    channel_type = fields.Selection(
        [('webhook', 'Webhook'), ('discord', 'Discord')],
        string='通道類型', required=True, default='webhook',
        help='Webhook：推 JSON 給客戶自己的系統。Discord：推到 Discord 頻道（千溢內部監看）。')

    # 預設 customer：升級前建立的通道都是給客戶的，行為不能因為加了這個欄位而改變
    audience = fields.Selection(
        [('internal', '千溢內部（所有方案都送）'),
         ('customer', '客戶（旗艦方案才送）')],
        string='送給誰', required=True, default='customer',
        help='千溢內部：所有方案的告警都送，用來維護設備。'
             '客戶：只有旗艦方案（即時告警推播）的設備才送。')

    # 空 = 不限場域。留空是常見設定（單一客戶只有一個場域），
    # 所以預設就要能運作，不要強迫填。
    site_ids = fields.Many2many(
        'water.level.site', string='適用場域',
        help='留空表示所有場域的告警都送這個通道。')

    min_severity = fields.Selection(
        [('info', '資訊'), ('warning', '警告'), ('critical', '嚴重')],
        string='最低嚴重度', default='warning', required=True,
        help='低於此嚴重度的事件不送，避免資訊級事件洗版。')

    # === webhook 專用 ===
    endpoint = fields.Char(string='推送網址', help='接收告警的 HTTPS 網址。')
    secret = fields.Char(
        string='簽章金鑰', groups='base.group_system',
        help='填了就在 X-EAGLE-Signature 標頭附上 HMAC-SHA256，收端可驗證來源。')

    # === discord 專用 ===
    # 網址本身就是發文憑證（拿到就能對頻道發任何訊息、甚至刪掉 webhook），
    # 所以跟 secret 一樣只有系統管理員讀得到，不放在所有內部使用者都讀得到的 endpoint
    discord_webhook_url = fields.Char(
        string='Discord 推送網址', groups='base.group_system',
        help='Discord 頻道設定 → 整合 → Webhook → 複製網址。只有系統管理員看得到。')
    discord_role_id = fields.Char(
        string='提及的身分組 ID',
        help='填了就在訊息開頭 @ 這個身分組：成員把伺服器設成「僅限提及」也會收到手機通知。'
             '在 Discord 開發者模式下對身分組按右鍵「複製身分組 ID」（一串數字）。')
    rate_limited_until = fields.Datetime(
        string='限流暫停到', readonly=True,
        help='對方回「太快了」（429）時暫停送這個通道，到這個時間之後重送排程才會再送。')

    max_per_hour = fields.Integer(
        string='每小時上限', default=60,
        help='告警風暴時的保險絲。0 表示不限。超過上限的告警記為「已略過」，'
             '事件本身仍完整保留在系統裡。千溢內部通道收所有方案、所有場域的告警，'
             '共用這一個額度——一台設備反覆斷線就可能吃掉別台的額度，內部通道建議設 0 或調高。')

    # === 狀態 ===
    last_sent_at = fields.Datetime(string='最後送出時間', readonly=True)
    last_error = fields.Char(string='最後錯誤', readonly=True)
    delivery_ids = fields.One2many(
        'water.level.alert.delivery', 'channel_id', string='送達紀錄')
    delivery_count = fields.Integer(
        string='送達筆數', compute='_compute_delivery_count')

    @api.depends('delivery_ids')
    def _compute_delivery_count(self):
        # 通道數量是個位數，直接 search_count 就好；
        # 不用 read_group 是因為它在 Odoo 版本之間的回傳格式會變。
        Delivery = self.env['water.level.alert.delivery']
        for channel in self:
            channel.delivery_count = Delivery.search_count(
                [('channel_id', '=', channel.id)])

    @api.constrains('channel_type', 'endpoint', 'discord_webhook_url', 'discord_role_id')
    def _check_endpoint(self):
        """設定不完整，存檔當下就要擋，不要等到半夜告警時才發現送不出去。"""
        for channel in self:
            if channel.channel_type == 'webhook' and not channel.endpoint:
                raise ValidationError(_('Webhook 通道必須填推送網址。'))
            if channel.channel_type != 'discord':
                continue
            url = (channel.sudo().discord_webhook_url or '').strip()
            if not url.startswith(DISCORD_URL_PREFIXES):
                raise ValidationError(_(
                    'Discord 推送網址要以 %s 開頭（在 Discord 頻道設定 → 整合 → Webhook 複製）。')
                    % DISCORD_URL_PREFIXES[0])
            if channel.discord_role_id and not channel.discord_role_id.isdigit():
                raise ValidationError(_(
                    '身分組 ID 只能是數字（例如 1234567890），不是 @名稱 也不是 <@&…>。'))

    # ==================== 派送 ====================

    @api.model
    def _dispatch(self, device, event, body):
        """把一則告警送到所有符合條件的通道。

        **這個方法絕對不能往外拋例外**——呼叫端是告警掃描 cron，
        一個壞掉的外部端點不可以害其他設備的告警整批掃不完。
        """
        try:
            channels = self.search([])
        except Exception:  # pragma: no cover - 查通道都失敗代表 DB 有更大的問題
            _logger.exception('讀取告警通道失敗，本次不外送')
            return 0

        sent = 0
        for channel in channels:
            try:
                # savepoint：一個通道的資料庫錯誤（例如兩支 cron 同時寫同一個通道）
                # 只退回它自己；少了它整個交易進入 aborted，這一輪掃描開的事件全部跟著消失
                with self.env.cr.savepoint():
                    if channel._is_applicable(device, event):
                        sent += 1 if channel._deliver(device, event, body) else 0
            except Exception:
                # 單一通道爆掉只影響它自己
                _logger.exception('告警通道 %s 派送失敗', channel.name)
        return sent

    def _is_applicable(self, device, event):
        """這則事件該不該走這個通道。"""
        self.ensure_one()
        if self.audience == 'customer' and not device.feature_realtime_alert:
            return False
        # active_test=False：x2many 讀取會濾掉已封存的場域。通道只綁 A、A 封存之後
        # site_ids 讀出來是空的＝「所有場域」，客戶通道就收到全部客戶的告警
        sites = self.with_context(active_test=False).site_ids
        if sites and device.site_id not in sites:
            return False
        if SEVERITY_ORDER.get(event.severity, 0) < SEVERITY_ORDER.get(self.min_severity, 0):
            return False
        return True

    def _is_throttled(self):
        """近一小時已送出的筆數是否已達上限。"""
        self.ensure_one()
        if not self.max_per_hour:
            return False
        since = fields.Datetime.now() - timedelta(hours=1)
        recent = self.env['water.level.alert.delivery'].search_count([
            ('channel_id', '=', self.id),
            ('state', '=', 'sent'),
            ('sent_at', '>=', since),
        ])
        return recent >= self.max_per_hour

    def _deliver(self, device, event, body):
        """建立送達紀錄並立刻試送一次。回傳是否送成功。"""
        self.ensure_one()
        payload = self._build_payload(device, event, body)
        delivery = self.env['water.level.alert.delivery'].create({
            'channel_id': self.id,
            'event_id': event.id,
            'device_id': device.id,
            'payload': json.dumps(payload, ensure_ascii=False, sort_keys=True),
        })
        if self._is_throttled():
            delivery.write({
                'state': 'skipped',
                'last_error': _('已達每小時上限 %s 則') % self.max_per_hour,
            })
            return False
        return delivery._attempt()

    def _build_payload(self, device, event, body):
        """對外的 JSON 契約。欄位一旦發布就不要改名——收端會綁死。"""
        event_labels = dict(event._fields['event_type'].selection)
        severity_labels = dict(event._fields['severity'].selection)
        return {
            'event_id': event.id,
            # 示範站的告警照樣送出去（要能展示外送這件事），但收端必須看得出來
            # 這不是真的水位事件。少了這個欄位，假告警在對方系統裡與真告警長得一模一樣。
            'is_demo': device.is_demo,
            'event_type': event.event_type,
            'event_type_label': event_labels.get(event.event_type, event.event_type),
            'severity': event.severity,
            'severity_label': severity_labels.get(event.severity, event.severity),
            'site': {'id': device.site_id.id, 'name': device.site_id.name or ''},
            'device': {'id': device.id, 'name': device.name or ''},
            'note': event.note or '',
            'start_ts': fields.Datetime.to_string(event.start_ts) if event.start_ts else '',
            'peak_value': event.peak_value,
            'message': body,
        }

    # ==================== 傳輸 ====================

    def _send(self, payload_text):
        """依通道類型分派到 `_send_<類型>`。別的模組加管道只要實作那個方法。

        可能拋 PermanentDeliveryError（不重送）、RateLimitedError（暫停這個通道）、
        其他例外（留給重送 cron）。"""
        self.ensure_one()
        sender = getattr(self, '_send_%s' % self.channel_type, None)
        if sender is None:
            raise PermanentDeliveryError(
                _('通道類型「%s」沒有對應的傳輸方法') % self.channel_type)
        return sender(payload_text)

    def _send_webhook(self, payload_text):
        import requests

        headers = {'Content-Type': 'application/json; charset=utf-8'}
        secret = self.sudo().secret
        if secret:
            digest = hmac.new(
                secret.encode('utf-8'),
                payload_text.encode('utf-8'),
                hashlib.sha256).hexdigest()
            headers['X-EAGLE-Signature'] = 'sha256=%s' % digest
        response = requests.post(
            self.endpoint, data=payload_text.encode('utf-8'),
            headers=headers, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        return True

    def _send_discord(self, payload_text):
        import requests

        try:
            response = requests.post(
                self.sudo().discord_webhook_url,
                json=self._discord_message(json.loads(payload_text)),
                timeout=HTTP_TIMEOUT_SEC, allow_redirects=False)
        except requests.RequestException as exc:
            # requests／urllib3 的例外訊息帶完整網址，而網址裡就是 token——
            # 原文寫進 last_error 或 log 等於把發文憑證公開給所有讀得到的人
            raise RuntimeError(_('連不上 Discord（%s）') % type(exc).__name__) from None
        status = response.status_code
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            raise RateLimitedError(self._discord_retry_after(response))
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise RuntimeError(_('Discord 伺服器錯誤（%s）') % status)
        if status >= HTTPStatus.MULTIPLE_CHOICES:
            # 3xx（不跟轉址）與 4xx：網址錯了或 webhook 被刪掉，重送也不會好
            raise PermanentDeliveryError(_(
                'Discord 拒收（%(status)s）：推送網址可能已被刪除或失效，'
                '請到 Discord 重新產生後更新通道。%(detail)s',
                status=status, detail=response.text[:200]))
        return True

    @staticmethod
    def _discord_retry_after(response):
        """429 要求等幾秒。拿不到就用預設，太大就封頂。"""
        try:
            seconds = float((response.json() or {}).get('retry_after'))
        except (TypeError, ValueError):
            seconds = RATE_LIMIT_DEFAULT_SEC
        return min(max(seconds, 1), RATE_LIMIT_MAX_SEC)

    def _discord_message(self, payload):
        """把通用告警 payload 轉成 Discord 訊息。`message` 已含場域、設備、類型、說明。

        **只允許提及設定好的身分組**：內文裡的場域名稱、事件說明是使用者打的字，
        不鎖 allowed_mentions 的話，有人把名稱取成 @everyone 就能對整個伺服器發通知。
        """
        prefix = '<@&%s> ' % self.discord_role_id if self.discord_role_id else ''
        if payload.get('is_demo'):
            prefix += _('【示範資料】')
        if payload.get('severity_label'):
            prefix += '【%s】' % payload['severity_label']
        content = prefix + (payload.get('message') or payload.get('event_type_label') or '')
        if len(content) > DISCORD_CONTENT_MAX:
            content = content[:DISCORD_CONTENT_MAX - 1] + '…'
        roles = [self.discord_role_id] if self.discord_role_id else []
        return {'content': content, 'allowed_mentions': {'parse': [], 'roles': roles}}

    # ==================== 人工操作 ====================

    def action_test(self):
        """送一則測試訊息。客戶設定完通道要能自己確認通不通，
        不必等真的出事才知道設錯。"""
        self.ensure_one()
        # 唯讀的內部使用者也按得到這顆鈕；不先擋的話 HTTP 已經送出去，之後寫 last_error 才失敗
        self.check_access('write')
        payload = json.dumps({
            'event_type': 'test',
            'event_type_label': _('連線測試'),
            'severity': 'info',
            'message': _('這是一則來自 EAGLE 的測試訊息，收到表示通道設定正確。'),
        }, ensure_ascii=False, sort_keys=True)
        try:
            self._send(payload)
        except Exception as exc:
            self.write({'last_error': str(exc)[:500]})
            raise UserError(_('測試失敗：%s') % exc)
        self.write({'last_sent_at': fields.Datetime.now(), 'last_error': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('成功'), 'message': _('測試訊息已送出。'),
                       'type': 'success', 'sticky': False},
        }


class WaterLevelAlertDelivery(models.Model):
    _name = 'water.level.alert.delivery'
    _description = '水位告警送達紀錄'
    _order = 'create_date desc, id desc'

    channel_id = fields.Many2one(
        'water.level.alert.channel', string='通道',
        required=True, ondelete='cascade', index=True)
    event_id = fields.Many2one(
        'water.level.event', string='水位事件',
        required=True, ondelete='cascade', index=True)
    device_id = fields.Many2one(
        'water.level.device', string='監測站', ondelete='cascade')

    # 送出去的原文留著。這是「我們確實通知過」的憑據，
    # 與整個產品「每件事都留得下痕跡」的立場一致。
    payload = fields.Text(string='送出內容', readonly=True)

    state = fields.Selection(
        [('pending', '待送'), ('sent', '已送達'),
         ('failed', '失敗'), ('skipped', '已略過')],
        string='狀態', default='pending', required=True, index=True)
    attempts = fields.Integer(string='嘗試次數', default=0, readonly=True)
    last_error = fields.Char(string='最後錯誤', readonly=True)
    sent_at = fields.Datetime(string='送達時間', readonly=True)

    def _attempt(self):
        """試送一次。成功回傳 True。

        **不往外拋**：失敗就記下來留給重送 cron，告警掃描不受影響。
        通道被限流期間不送、也不算嘗試次數，留給重送 cron 在暫停結束後送。
        """
        self.ensure_one()
        channel = self.channel_id
        now = fields.Datetime.now()
        if channel.rate_limited_until and channel.rate_limited_until > now:
            return False
        try:
            channel._send(self.payload)
        except RateLimitedError as exc:
            message = _('對方限流（429），暫停 %s 秒後再送') % exc.retry_after
            self.write({'state': 'pending', 'last_error': message})
            channel.write({
                'rate_limited_until': now + timedelta(seconds=exc.retry_after),
                'last_error': message,
            })
            return False
        except Exception as exc:
            self.attempts += 1
            permanent = isinstance(exc, PermanentDeliveryError)
            message = str(exc)[:500]
            self.write({
                'state': 'failed' if permanent or self.attempts >= MAX_ATTEMPTS else 'pending',
                'last_error': message,
            })
            channel.write({'last_error': message})
            _logger.warning('告警外送失敗（第 %s 次%s）：%s', self.attempts,
                            '，不會重送' if permanent else '', message)
            return False
        self.attempts += 1
        self.write({'state': 'sent', 'sent_at': now, 'last_error': False})
        channel.write({'last_sent_at': now, 'last_error': False})
        return True

    @api.model
    def _cron_retry(self):
        """重送 pending 的告警。inline 那一次失敗後由這支接手。"""
        pending = self.search([
            ('state', '=', 'pending'),
            ('attempts', '<', MAX_ATTEMPTS),
        ], limit=200)
        done = sum(1 for delivery in pending if delivery._attempt())
        if pending:
            _logger.info('告警重送：%s 筆待送，%s 筆成功', len(pending), done)
        return done

    def action_retry(self):
        """人工重送（修好端點之後用）。"""
        for delivery in self:
            delivery.write({'state': 'pending'})
            delivery._attempt()
        return True
