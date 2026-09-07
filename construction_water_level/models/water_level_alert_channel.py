# -*- coding: utf-8 -*-
"""告警外送通道 —— 把水位異常推到系統外面去。

**為什麼需要這個模組**
`water.level.monitor._notify()` 原本只做 message_post，訊息落在 Odoo 的
chatter（內部收件匣／前台通知中心）。使用者不登入就看不到，
撐不起 DM 旗艦等級白紙黑字的「異常即時告警推播」。

**傳輸方式刻意留白**
最終要走 LINE 官方帳號、簡訊還是別的，尚未決定。所以這裡切成兩層：
* 與管道無關的部分（挑通道、節流、送達紀錄、失敗重送）——本檔完整實作
* 真正的傳輸——`_send_<channel_type>` 一個方法一種管道

目前只實作 `webhook`，因為它是唯一不需要先辦任何外部帳號的傳輸方式，
可以立刻端到端驗證。日後加 LINE 就是補一個 `_send_line()` 與一組欄位，
派送層不必動。**不要預先把未實作的管道放進 Selection**——選得到卻送不出去
比沒有這個選項更糟。

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

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 出站逾時要比入站短——這是在 cron 交易裡同步呼叫，不能讓對方拖著我們
HTTP_TIMEOUT_SEC = 5
# 重送上限。超過就不再自動試，留給人看 last_error
MAX_ATTEMPTS = 5
# 嚴重度排序，用來比對通道設定的最低門檻
SEVERITY_ORDER = {'info': 0, 'warning': 1, 'critical': 2}


class WaterLevelAlertChannel(models.Model):
    _name = 'water.level.alert.channel'
    _description = '水位告警外送通道'
    _order = 'sequence, id'

    name = fields.Char(string='通道名稱', required=True)
    sequence = fields.Integer(string='順序', default=10)
    active = fields.Boolean(string='啟用', default=True)

    channel_type = fields.Selection(
        [('webhook', 'Webhook')],
        string='通道類型', required=True, default='webhook',
        help='目前僅支援 Webhook。日後新增 LINE 或簡訊時於此擴充。')

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

    max_per_hour = fields.Integer(
        string='每小時上限', default=60,
        help='告警風暴時的保險絲。0 表示不限。超過上限的告警記為「已略過」，'
             '事件本身仍完整保留在系統裡。')

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

    @api.constrains('channel_type', 'endpoint')
    def _check_endpoint(self):
        """webhook 沒有網址就是設定不完整，存檔當下就要擋，
        不要等到半夜告警時才發現送不出去。"""
        for channel in self:
            if channel.channel_type == 'webhook' and not channel.endpoint:
                raise UserError(_('Webhook 通道必須填推送網址。'))

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
                if channel._is_applicable(device, event):
                    sent += 1 if channel._deliver(device, event, body) else 0
            except Exception:
                # 單一通道爆掉只影響它自己
                _logger.exception('告警通道 %s 派送失敗', channel.name)
        return sent

    def _is_applicable(self, device, event):
        """這則事件該不該走這個通道。"""
        self.ensure_one()
        if self.site_ids and device.site_id not in self.site_ids:
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
        """依通道類型分派。新增管道時在這裡加一行。"""
        self.ensure_one()
        return {
            'webhook': self._send_webhook,
        }[self.channel_type](payload_text)

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

    # ==================== 人工操作 ====================

    def action_test(self):
        """送一則測試訊息。客戶設定完通道要能自己確認通不通，
        不必等真的出事才知道設錯。"""
        self.ensure_one()
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
        """
        self.ensure_one()
        self.attempts += 1
        try:
            self.channel_id._send(self.payload)
        except Exception as exc:
            message = str(exc)[:500]
            self.write({
                'state': 'failed' if self.attempts >= MAX_ATTEMPTS else 'pending',
                'last_error': message,
            })
            self.channel_id.write({'last_error': message})
            _logger.warning('告警外送失敗（第 %s 次）：%s', self.attempts, message)
            return False
        now = fields.Datetime.now()
        self.write({'state': 'sent', 'sent_at': now, 'last_error': False})
        self.channel_id.write({'last_sent_at': now, 'last_error': False})
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
