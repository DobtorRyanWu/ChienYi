# -*- coding: utf-8 -*-
"""LINE 通知（旗艦方案）：告警推到管委會成員的 LINE。

接在 core 的告警外送層上（water.level.alert.channel）：這裡只 `selection_add` 一個 'line' 類型、
實作 `_send_line()`，派送、送達紀錄、失敗重送都是 core 的。金鑰存在**通道上**（core 的 `secret`＝
LINE 的 Channel secret），日後某個社區要用自己的官方帳號＝新增一個通道，程式不改（那個社區的人要重綁：
LINE 的 userId 依 provider 不同）。

**額度是所有社區共用的**（2026-10-21 先用千溢一個官方帳號，輕用量每月 200 則、推幾個人算幾則）。
一個社區反覆斷線就可能把整個月用光、讓所有社區都收不到，所以使用者定了三道保護：
* 冷卻：同一台設備、同一類事件 `LINE_COOLDOWN_MIN` 分鐘內只推一次——**越線（core 的 LEVEL_TYPES）除外**：
  core 3.2.0 起越線自己限速（同類 60 分鐘、但警戒升高照送），LINE 再擋一次會把一小時內的升級吞掉
* 每社區每月上限（通道上的 `line_site_monthly_cap`）：超過的社區當月只剩站內通知，並提醒千溢一次
* 整個月額度用完：通道當月停推（不用 core 的 RateLimitedError——那會在下個月把一個月前的告警補送出去），提醒千溢

綁定：前台成員產生一次性綁定碼 → 加官方帳號好友、把碼傳給它 → webhook 收到就綁上那個人的 userId。
綁定碼是持有即可用的憑證（被轉傳的話，拿到的人就會收到那個社區的告警），所以：一次性、24 小時過期、
≥40 bit、同一個 LINE 帳號猜錯太多次就鎖住；前台清單顯示 LINE 上的顯示名稱，管委會看得出綁上的是誰。
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import uuid
from datetime import timedelta
from http import HTTPStatus

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.community_water_level.utils import local_today
from odoo.addons.water_level_core.models.water_level_alert_channel import (
    HTTP_TIMEOUT_SEC, RATE_LIMIT_DEFAULT_SEC, RATE_LIMIT_MAX_SEC, PermanentDeliveryError, RateLimitedError)
from odoo.addons.water_level_core.models.water_level_device import LEVEL_FLAGSHIP
from odoo.addons.water_level_core.models.water_level_monitor import LEVEL_TYPES
from odoo.addons.water_level_core.models.water_level_site import SITE_TYPE_COMMUNITY

_logger = logging.getLogger(__name__)

CHANNEL_LINE = 'line'
AUDIENCE_CUSTOMER = 'customer'
LINE_API = 'https://api.line.me/v2/bot'
LINE_MULTICAST_MAX = 500             # LINE 的 multicast 一次最多 500 個 userId
LINE_TEXT_MAX = 5000                 # LINE 文字訊息上限（字元）
LINE_SITE_MONTHLY_CAP_DEFAULT = 50   # 每社區每月上限（則＝推給一個人一次），千溢可在通道上改
LINE_COOLDOWN_MIN = 60
LINE_QUOTA_WARN_RATIO = 0.8          # 整個官方帳號用到八成時提醒千溢
LINE_MONTHLY_LIMIT_MESSAGE = 'You have reached your monthly limit.'   # LINE 文件上月額度用完的 429 訊息
# 409＝同一個 X-Line-Retry-Key 已經被收下＝已送達，不是失敗
MONTH_FORMAT = '%Y-%m'

BIND_CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'   # 去掉 0/O、1/I/L，手機上不會抄錯
BIND_CODE_LENGTH = 10                # 31^10 ≈ 2^49.5
BIND_CODE_TTL_HOURS = 24
BIND_MAX_FAILURES = 5                # 同一個 LINE 帳號在下面這段時間內猜錯幾次就鎖住
BIND_FAILURE_WINDOW_HOURS = 24
LINE_MAX_RECIPIENTS_PER_SITE = 20
LINE_USER_ID = re.compile(r'^U[0-9a-f]{32}$')
LINE_FRIEND_URL = re.compile(r'^https://(line\.me|lin\.ee)/')
CODE_LIKE = re.compile(r'^[%s]{%d}$' % (BIND_CODE_ALPHABET, BIND_CODE_LENGTH))

REPLY_FOLLOW = '感謝加入！請把管委會給您的 10 碼綁定碼傳到這裡，綁定後就會收到社區蓄水池的異常通知。'
REPLY_HELP = '這個帳號只負責傳送蓄水池異常通知。要綁定請直接傳 10 碼綁定碼。'
REPLY_BAD_CODE = '綁定碼不正確或已過期，請向管委會索取新的綁定碼。'
REPLY_LOCKED = '嘗試次數太多，請 24 小時後再試，或聯絡管委會。'
REPLY_BOUND = '綁定成功：之後「%s」的蓄水池異常會傳到這裡。'
REPLY_ALREADY = '您已經綁定「%s」，不必重複綁定。'
TEST_MESSAGE = '【測試】這是「%s」蓄水池異常通知的測試訊息，收到代表 LINE 設定正確。'


def month_key():
    """台灣的這個月（hypothesis：LINE 的月額度以哪個時區換月沒查到，差的是月初那幾小時）。"""
    return local_today().strftime(MONTH_FORMAT)


def normalize_code(text):
    return re.sub(r'[\s\-]', '', text or '').upper()


class WaterLevelAlertChannel(models.Model):
    _inherit = 'water.level.alert.channel'

    channel_type = fields.Selection(selection_add=[(CHANNEL_LINE, 'LINE')], ondelete={CHANNEL_LINE: 'cascade'})
    # Channel secret 沿用 core 的 `secret`（同樣限系統管理員、同樣是簽章金鑰），表單上標籤寫清楚
    line_channel_access_token = fields.Char(string='LINE Channel access token', groups='base.group_system')
    line_add_friend_url = fields.Char(
        string='加好友網址', help='LINE 官方帳號的加好友連結（https://line.me/… 或 https://lin.ee/…），前台綁定說明會用到。')
    line_site_monthly_cap = fields.Integer(
        string='每社區每月上限（則）', default=LINE_SITE_MONTHLY_CAP_DEFAULT,
        help='一則＝推給一個人一次。超過的社區當月只剩站內通知，並提醒千溢。0＝不限。')
    line_quota_exhausted_month = fields.Char(string='LINE 額度用完的月份', readonly=True, copy=False)
    line_usage_warned_month = fields.Char(string='已提醒用量的月份', readonly=True, copy=False)
    line_recipient_ids = fields.One2many('water.level.line.recipient', 'channel_id', string='LINE 收件人')

    @api.model_create_multi
    def create(self, vals_list):
        # 每小時上限是整個通道一起算、超過記 skipped 不重送：A 社區洗版會吃掉 B 社區的告警。LINE 改由每社區上限控制
        for vals in vals_list:
            if vals.get('channel_type') == CHANNEL_LINE:
                vals.setdefault('max_per_hour', 0)
                vals.setdefault('audience', AUDIENCE_CUSTOMER)
        return super().create(vals_list)

    @api.constrains('channel_type', 'audience', 'secret', 'line_channel_access_token', 'line_add_friend_url')
    def _check_line_channel(self):
        for channel in self.sudo().filtered(lambda c: c.channel_type == CHANNEL_LINE):
            # secret 空著＝簽章金鑰是空字串，誰都算得出來，webhook 就能被偽造
            if not channel.secret or not channel.line_channel_access_token:
                raise ValidationError(_('LINE 通道要填 Channel secret 與 Channel access token。'))
            if channel.audience != AUDIENCE_CUSTOMER:
                raise ValidationError(_('LINE 通道是給管委會的（旗艦方案），對象請選「客戶」。'))
            if channel.line_add_friend_url and not LINE_FRIEND_URL.match(channel.line_add_friend_url):
                raise ValidationError(_('加好友網址要是 https://line.me/ 或 https://lin.ee/ 開頭。'))

    # ==================== 該不該推 ====================

    def _is_applicable(self, device, event):
        if not super()._is_applicable(device, event):
            return False
        if self.channel_type != CHANNEL_LINE:
            return True
        return self._line_should_push(device, event)

    def _line_should_push(self, device, event):
        """不推就不建送達紀錄——沒有收件人的社區每個事件記一筆失敗，會把通道上真正的錯誤蓋掉。"""
        site = device.site_id
        if site.site_type != SITE_TYPE_COMMUNITY or not site._community_level_at_least(LEVEL_FLAGSHIP):
            return False
        month = month_key()
        if self.line_quota_exhausted_month == month:
            return False
        recipients = self._line_recipients(site)
        if not recipients:
            return False
        since = fields.Datetime.now() - timedelta(minutes=LINE_COOLDOWN_MIN)
        recent = event.event_type not in LEVEL_TYPES and self.env['water.level.alert.delivery'].sudo().search_count([
            ('channel_id', '=', self.id), ('device_id', '=', device.id),
            ('event_id.event_type', '=', event.event_type), ('create_date', '>=', since),
            ('state', 'in', ('pending', 'sent'))])
        if recent:
            return False
        usage = self.env['water.level.line.usage']._line_for(self, site, month)
        if self.line_site_monthly_cap and usage.messages + len(recipients) > self.line_site_monthly_cap:
            usage._line_notify_cap_once()
            return False
        return True

    def _line_recipients(self, site):
        return self.env['water.level.line.recipient'].sudo().search([
            ('channel_id', '=', self.id), ('site_id', '=', site.id), ('line_user_id', '!=', False)])

    # ==================== 送 ====================

    def _send_line(self, payload_text):
        """core 的 `_send` 依類型分派到這裡。例外的意思照 core：PermanentDeliveryError＝記失敗不重送、
        RateLimitedError＝通道暫停、其他＝pending 給重送 cron。"""
        self.ensure_one()
        payload = json.loads(payload_text)
        site_id = (payload.get('site') or {}).get('id')
        if not site_id:
            # core 的「傳測試訊息」沒有指定社區；LINE 不能因此廣播給所有社區的人
            raise PermanentDeliveryError(_('LINE 通道不送沒有指定社區的訊息（測試請到收件人上用「傳測試訊息」）。'))
        site = self.env['water.level.site'].sudo().browse(site_id).exists()
        # 降級之後重送排隊中的告警：再驗一次
        if not site or site.site_type != SITE_TYPE_COMMUNITY or not site._community_level_at_least(LEVEL_FLAGSHIP):
            raise PermanentDeliveryError(_('這個社區的方案不含 LINE 通知。'))
        recipients = self._line_recipients(site)
        if not recipients:
            raise PermanentDeliveryError(_('這個社區沒有已綁定的 LINE 收件人。'))
        text = (payload.get('message') or '')[:LINE_TEXT_MAX]
        user_ids = recipients.mapped('line_user_id')
        digest = hashlib.sha256(payload_text.encode()).hexdigest()
        for start in range(0, len(user_ids), LINE_MULTICAST_MAX):
            # 同一則送達紀錄重送時 key 不變：LINE 收過的會回 409，不會重複推、不會重複扣額度
            retry_key = str(uuid.uuid5(uuid.NAMESPACE_URL, 'water-level-line:%s:%s:%s' % (self.id, start, digest)))
            response = self._line_request('post', '/message/multicast', {
                'to': user_ids[start:start + LINE_MULTICAST_MAX],
                'messages': [{'type': 'text', 'text': text}],
            }, retry_key=retry_key)
            self._line_raise_for_status(response)
        self.env['water.level.line.usage']._line_for(self, site, month_key())._line_add(len(user_ids))

    def _line_request(self, method, path, body=None, retry_key=None):
        headers = {'Authorization': 'Bearer %s' % self.sudo().line_channel_access_token}
        if retry_key:
            headers['X-Line-Retry-Key'] = retry_key
        try:
            return requests.request(method, LINE_API + path, json=body, headers=headers, timeout=HTTP_TIMEOUT_SEC)
        except requests.RequestException as exc:
            # 只寫例外型別：requests 的訊息會帶完整網址（core 同一個做法）
            raise RuntimeError(_('連不到 LINE（%s）') % type(exc).__name__) from None

    def _line_raise_for_status(self, response):
        status = response.status_code
        if status < HTTPStatus.MULTIPLE_CHOICES or status == HTTPStatus.CONFLICT:
            return
        try:
            message = str((response.json() or {}).get('message') or '')
        except ValueError:
            message = ''
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            if LINE_MONTHLY_LIMIT_MESSAGE in message:
                self.sudo().write({'line_quota_exhausted_month': month_key()})
                self._line_notify_managers(
                    _('LINE 本月額度已用完'),
                    _('LINE 通道「%s」本月的推播額度已用完，這個月剩下的告警只有站內通知。') % self.name)
                raise PermanentDeliveryError(_('LINE 本月額度已用完，這個月不再推播。'))
            retry_after = response.headers.get('Retry-After')
            seconds = int(retry_after) if (retry_after or '').isdigit() else RATE_LIMIT_DEFAULT_SEC
            raise RateLimitedError(min(seconds, RATE_LIMIT_MAX_SEC))
        if HTTPStatus.BAD_REQUEST <= status < HTTPStatus.INTERNAL_SERVER_ERROR:
            raise PermanentDeliveryError(_('LINE 拒絕（%(status)s）：%(message)s', status=status, message=message[:200]))
        raise RuntimeError(_('LINE 暫時無法處理（%s）') % status)

    def action_test(self):
        """通道表單的測試鈕。LINE 改成「連線檢查」：core 的測試訊息沒有指定社區，LINE 那條路必定拒絕
        （不能廣播給所有社區的人）——2026-10-22 使用者第一次設定就按到、看到一句看不懂的錯。
        檢查 token、Webhook URL、secret（請 LINE 實際打一次 webhook），都不推訊息、不扣額度。"""
        if self.channel_type != CHANNEL_LINE:
            return super().action_test()
        self.ensure_one()
        self.check_access('write')
        results = self._line_check_connection()
        report = '\n'.join(('✓ ' if ok else '✗ ') + text for ok, text in results)
        if not all(ok for ok, _text in results):
            self.write({'last_error': report[:500]})
            raise UserError(_('LINE 連線檢查沒過：\n%s') % report)
        self.write({'last_error': False})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('LINE 連線正常'), 'message': report, 'type': 'success', 'sticky': True}}

    def _line_check_connection(self):
        """[(通過與否, 一句話)]。前一關沒過、後面依賴它的就不檢查（token 錯時後面全部都會 401）。"""
        expected_path = '/water-level/line/webhook/%s' % self.id
        try:
            info = self._line_request('get', '/info')
        except RuntimeError as exc:
            return [(False, str(exc))]
        if info.status_code != HTTPStatus.OK:
            return [(False, _('Channel access token 不正確（LINE 回 %s）：請到 LINE Developers 的 Messaging API 分頁'
                              '重新複製「Channel access token (long-lived)」。') % info.status_code)]
        bot = info.json() or {}
        results = [(True, _('Channel access token 正確：官方帳號「%(name)s」（%(id)s）',
                            name=bot.get('displayName', ''), id=bot.get('basicId', '')))]
        endpoint = self._line_request('get', '/channel/webhook/endpoint')
        hook = (endpoint.json() or {}) if endpoint.status_code == HTTPStatus.OK else {}
        url = hook.get('endpoint') or ''
        if not url:
            results.append((False, _('LINE 後台還沒有填 Webhook URL（網址結尾應該是 %s）。') % expected_path))
            return results
        if not url.rstrip('/').endswith(expected_path):
            results.append((False, _('LINE 後台的 Webhook URL 是 %(url)s，沒有指到這個通道（結尾應該是 %(path)s）。',
                                     url=url, path=expected_path)))
            return results
        results.append((True, _('Webhook URL：%s') % url))
        if not hook.get('active'):
            results.append((False, _('LINE 後台的「Use webhook」還沒打開。')))
        test = self._line_request('post', '/channel/webhook/test', {})
        outcome = (test.json() or {}) if test.status_code == HTTPStatus.OK else {}
        status, reason = outcome.get('statusCode'), outcome.get('reason') or ''
        if outcome.get('success') and status == HTTPStatus.OK:
            results.append((True, _('LINE 實際打了一次 webhook，簽章驗證通過（Channel secret 正確）。')))
        elif status == HTTPStatus.UNAUTHORIZED:
            results.append((False, _('LINE 打到這台了，但簽章不對：Channel secret 跟 LINE 後台「Basic settings」的不一樣。')))
        elif reason in ('COULD_NOT_CONNECT', 'REQUEST_TIMEOUT'):
            # detail 照抄 LINE 的原文：同一個 reason 底下有「連不上」也有「連上了但 TLS 協商失敗」，修法完全不同
            # （2026-10-22 實例：Tailscale Funnel 的網址通，LINE 回 Session protocol negotiation failure）
            results.append((False, _('LINE 連不到 Webhook URL（%(reason)s：%(detail)s）。',
                                     reason=reason, detail=outcome.get('detail') or '')))
        else:
            results.append((False, _('Webhook 測試沒過：%(reason)s %(detail)s',
                                     reason=reason or test.status_code, detail=outcome.get('detail') or '')))
        return results

    def _line_notify_managers(self, subject, body):
        """站內通知水位管理員（千溢）。通道沒有 chatter，用 message_notify 指向通道這一筆。"""
        managers = self.env.ref('water_level_core.group_water_level_manager').sudo().users
        if managers:
            self.env['mail.thread'].sudo().message_notify(
                model=self._name, res_id=self.id, partner_ids=managers.partner_id.ids, subject=subject, body=body)

    @api.model
    def _cron_line_usage_check(self):
        """每天看一次整個官方帳號的用量，到八成時每月提醒千溢一次。查不到就記 log，不擋別的通道。"""
        month = month_key()
        for channel in self.sudo().search([('channel_type', '=', CHANNEL_LINE)]):
            if channel.line_usage_warned_month == month:
                continue
            try:
                quota = channel._line_request('get', '/message/quota').json()
                used = channel._line_request('get', '/message/quota/consumption').json()
            except (RuntimeError, ValueError) as exc:
                _logger.warning('LINE 通道 %s 查用量失敗：%s', channel.name, exc)
                continue
            limit = quota.get('value') if quota.get('type') == 'limited' else None
            total = used.get('totalUsage') or 0
            if limit and total >= limit * LINE_QUOTA_WARN_RATIO:
                channel.write({'line_usage_warned_month': month})
                channel._line_notify_managers(
                    _('LINE 推播額度快用完'),
                    _('LINE 通道「%(name)s」本月已用 %(used)s／%(limit)s 則。', name=channel.name, used=total, limit=limit))

    # ==================== 綁定（webhook） ====================

    def _line_signature_ok(self, body, signature):
        """X-Line-Signature＝base64(HMAC-SHA256(Channel secret, 原始 body))。secret 或簽章空著一律不通過。"""
        self.ensure_one()
        secret = self.sudo().secret
        if not secret or not signature:
            return False
        expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(expected, signature)

    def _line_handle_events(self, events):
        """處理 webhook 事件，回傳要 Reply 的 [(replyToken, 文字)]——實際送出由呼叫端放在 commit 之後
        （先回「綁定成功」、交易卻因衝突重跑，使用者會被告知成功而實際沒綁上）。"""
        self.ensure_one()
        replies = []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            user_id = (event.get('source') or {}).get('userId') or ''
            if not LINE_USER_ID.match(user_id):
                continue
            kind = event.get('type')
            if kind == 'unfollow':
                self._line_unbind_user(user_id)
                continue
            token = event.get('replyToken')
            if kind == 'follow':
                replies.append((token, REPLY_FOLLOW))
            elif kind == 'message' and (event.get('message') or {}).get('type') == 'text':
                replies.append((token, self._line_try_bind(user_id, event['message'].get('text'))))
        return [(token, text) for token, text in replies if token]

    def _line_try_bind(self, user_id, text):
        Failure = self.env['water.level.line.bind.failure'].sudo()
        since = fields.Datetime.now() - timedelta(hours=BIND_FAILURE_WINDOW_HOURS)
        if Failure.search_count([('channel_id', '=', self.id), ('line_user_id', '=', user_id),
                                 ('create_date', '>=', since)]) >= BIND_MAX_FAILURES:
            return REPLY_LOCKED
        code = normalize_code(text)
        if not CODE_LIKE.match(code):
            return REPLY_HELP      # 一般聊天不算猜錯
        recipient = self.env['water.level.line.recipient'].sudo().search([
            ('channel_id', '=', self.id), ('bind_code', '=', code),
            ('bind_code_expires', '>', fields.Datetime.now())], limit=1)
        if not recipient:
            Failure.create({'channel_id': self.id, 'line_user_id': user_id})
            return REPLY_BAD_CODE  # 不說是錯還是過期
        return recipient._line_bind(user_id, self._line_display_name(user_id))

    def _line_display_name(self, user_id):
        """LINE 上的顯示名稱，給管委會看出綁上的是誰。查不到就空著，不擋綁定。"""
        try:
            response = self._line_request('get', '/profile/%s' % user_id)
            if response.status_code >= HTTPStatus.MULTIPLE_CHOICES:
                return ''
            return (response.json() or {}).get('displayName') or ''
        except (RuntimeError, ValueError):
            return ''

    def _line_unbind_user(self, user_id):
        """對方封鎖或刪除好友：這個通道上他綁的收件人全部停用（留紀錄，不刪）。"""
        recipients = self.env['water.level.line.recipient'].sudo().search([
            ('channel_id', '=', self.id), ('line_user_id', '=', user_id)])
        for recipient in recipients:
            recipient._line_disable(None, _('LINE 上封鎖或刪除了好友'))

    @staticmethod
    def _line_send_replies(token, replies):
        """commit 之後才呼叫（postcommit）：Reply API 免費、不扣額度。失敗只記 log。"""
        for reply_token, text in replies:
            try:
                requests.post(LINE_API + '/message/reply', json={
                    'replyToken': reply_token, 'messages': [{'type': 'text', 'text': text}]},
                    headers={'Authorization': 'Bearer %s' % token}, timeout=HTTP_TIMEOUT_SEC)
            except requests.RequestException as exc:
                _logger.warning('LINE Reply 失敗：%s', type(exc).__name__)


class WaterLevelLineRecipient(models.Model):
    _name = 'water.level.line.recipient'
    _description = 'LINE 通知收件人'
    _order = 'site_id, create_date desc, id desc'

    site_id = fields.Many2one('water.level.site', string='社區', required=True, ondelete='cascade', index=True)
    channel_id = fields.Many2one('water.level.alert.channel', string='LINE 通道', required=True, ondelete='cascade',
                                 domain=[('channel_type', '=', CHANNEL_LINE)], index=True)
    name = fields.Char(string='名稱', required=True, help='管委會自己填的，例如「主委 王先生」。')
    line_user_id = fields.Char(string='LINE userId', groups='base.group_system', index=True, copy=False)
    line_display_name = fields.Char(string='LINE 顯示名稱', copy=False)
    bind_code = fields.Char(string='綁定碼', groups='base.group_system', copy=False, index=True)
    bind_code_expires = fields.Datetime(string='綁定碼到期', copy=False)
    bound_at = fields.Datetime(string='綁定時間', copy=False)
    created_by_id = fields.Many2one('res.users', string='建立人', readonly=True)
    disabled_by_id = fields.Many2one('res.users', string='停用人', readonly=True)
    disabled_at = fields.Datetime(string='停用時間', readonly=True)
    disabled_reason = fields.Char(string='停用原因', readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [('bind_code_unique', 'unique(bind_code)', '綁定碼重複。')]

    @api.constrains('line_user_id')
    def _check_line_user_id(self):
        for recipient in self.sudo():
            if recipient.line_user_id and not LINE_USER_ID.match(recipient.line_user_id):
                raise ValidationError(_('LINE userId 格式不對。'))

    @api.model
    def _community_new(self, site, channel, name, user):
        """前台新增收件人：產生一次性綁定碼。呼叫端（controller）負責先確認 user 是旗艦社區的成員。"""
        name = (name or '').strip()
        if not name:
            raise UserError(_('請填名稱。'))
        if self.sudo().search_count([('site_id', '=', site.id)]) >= LINE_MAX_RECIPIENTS_PER_SITE:
            raise UserError(_('一個社區最多 %s 位 LINE 收件人，請先停用不用的。') % LINE_MAX_RECIPIENTS_PER_SITE)
        recipient = self.sudo().create({
            'site_id': site.id, 'channel_id': channel.id, 'name': name[:64], 'created_by_id': user.id,
            'bind_code': self._line_new_code(),
            'bind_code_expires': fields.Datetime.now() + timedelta(hours=BIND_CODE_TTL_HOURS),
        })
        site.sudo().message_post(body=_('%(user)s 新增了 LINE 收件人「%(name)s」（等待綁定）。', user=user.name, name=recipient.name))
        return recipient

    @api.model
    def _line_new_code(self):
        while True:
            code = ''.join(secrets.choice(BIND_CODE_ALPHABET) for _i in range(BIND_CODE_LENGTH))
            if not self.sudo().with_context(active_test=False).search_count([('bind_code', '=', code)]):
                return code

    def _line_bind(self, user_id, display_name):
        """綁定碼對了：綁上、碼作廢。同一個人已經綁過這個社區就不重複建，這筆作廢。"""
        self.ensure_one()
        recipient = self.sudo()
        duplicate = recipient.search([('id', '!=', recipient.id), ('channel_id', '=', recipient.channel_id.id),
                                      ('site_id', '=', recipient.site_id.id), ('line_user_id', '=', user_id)], limit=1)
        if duplicate:
            recipient.write({'bind_code': False, 'bind_code_expires': False, 'active': False,
                             'disabled_at': fields.Datetime.now(), 'disabled_reason': _('同一個 LINE 帳號已經綁定')})
            return REPLY_ALREADY % recipient.site_id.name
        recipient.write({'line_user_id': user_id, 'line_display_name': display_name, 'bound_at': fields.Datetime.now(),
                         'bind_code': False, 'bind_code_expires': False})
        recipient.site_id.message_post(body=_('LINE 收件人「%(name)s」已綁定（LINE 顯示名稱：%(display)s）。',
                                              name=recipient.name, display=display_name or _('未取得')))
        return REPLY_BOUND % recipient.site_id.name

    def action_line_test(self):
        """後台「傳測試訊息」：只推給這一位（Push API），給千溢確認通道設定。會扣共用額度，所以只有水位管理員能按。

        core 的通道「傳測試訊息」沒有指定社區，LINE 那條路會拒絕（不能廣播給所有社區的人）——要測就從這裡。
        """
        self.ensure_one()
        if not self.env.user.has_group('water_level_core.group_water_level_manager'):
            raise AccessError(_('只有水位管理員可以傳 LINE 測試訊息（會扣共用額度）。'))
        recipient = self.sudo()
        if not recipient.active or not recipient.line_user_id:
            raise UserError(_('「%s」還沒有綁定 LINE（或已停用），無法傳測試訊息。') % recipient.name)
        channel = recipient.channel_id
        try:
            response = channel._line_request('post', '/message/push', {
                'to': recipient.line_user_id,
                'messages': [{'type': 'text', 'text': TEST_MESSAGE % recipient.site_id.name}]})
            channel._line_raise_for_status(response)
        except (PermanentDeliveryError, RateLimitedError, RuntimeError) as exc:
            raise UserError(_('LINE 沒有收下測試訊息：%s') % (exc if not isinstance(exc, RateLimitedError)
                                                            else _('對方限流，請稍後再試'))) from None
        self.env['water.level.line.usage']._line_for(channel, recipient.site_id, month_key())._line_add(1)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _('已送出測試訊息給「%s」。') % recipient.name, 'type': 'success'}}

    def _line_disable(self, actor, reason):
        """停用（不刪，留紀錄）。actor 為 None＝LINE 那邊封鎖或刪除好友。

        參數刻意不叫 `user`：Odoo 18 的 `_()` 會從呼叫端的區域變數 `user` 取 uid（int(user)），None 會讓 `_()` 直接 TypeError。
        """
        for recipient in self.sudo().filtered('active'):
            recipient.write({'active': False, 'disabled_by_id': actor.id if actor else False,
                             'disabled_at': fields.Datetime.now(), 'disabled_reason': reason,
                             'bind_code': False, 'bind_code_expires': False})
            recipient.site_id.message_post(body=_('LINE 收件人「%(name)s」已停用：%(reason)s',
                                                  name=recipient.name, reason=reason))


class WaterLevelLineBindFailure(models.Model):
    """綁定碼猜錯的紀錄，給「同一個 LINE 帳號猜錯太多次就鎖住」用。"""
    _name = 'water.level.line.bind.failure'
    _description = 'LINE 綁定失敗紀錄'

    channel_id = fields.Many2one('water.level.alert.channel', required=True, ondelete='cascade', index=True)
    line_user_id = fields.Char(required=True, index=True)


class WaterLevelLineUsage(models.Model):
    """每個社區每月推了幾則（＝推給幾個人次），給每社區上限用。"""
    _name = 'water.level.line.usage'
    _description = 'LINE 每社區每月用量'

    channel_id = fields.Many2one('water.level.alert.channel', required=True, ondelete='cascade', index=True)
    site_id = fields.Many2one('water.level.site', required=True, ondelete='cascade', index=True)
    month = fields.Char(required=True, help='台灣的年月，YYYY-MM')
    messages = fields.Integer(default=0)
    cap_notified = fields.Boolean(default=False)

    _sql_constraints = [('channel_site_month_unique', 'unique(channel_id, site_id, month)', '同一個月只有一筆。')]

    @api.model
    def _line_for(self, channel, site, month):
        usage = self.sudo().search([('channel_id', '=', channel.id), ('site_id', '=', site.id), ('month', '=', month)])
        return usage or self.sudo().create({'channel_id': channel.id, 'site_id': site.id, 'month': month})

    def _line_add(self, count):
        self.ensure_one()
        self.sudo().write({'messages': self.messages + count})

    def _line_notify_cap_once(self):
        self.ensure_one()
        if self.cap_notified:
            return
        self.sudo().write({'cap_notified': True})
        self.channel_id._line_notify_managers(
            _('社區 LINE 推播已達本月上限'),
            _('「%(site)s」本月 LINE 推播已達上限 %(cap)s 則，這個月剩下的告警只有站內通知。',
              site=self.site_id.name, cap=self.channel_id.line_site_monthly_cap))
