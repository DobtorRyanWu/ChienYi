# -*- coding: utf-8 -*-
"""LINE 通知：通道設定、收件人與綁定碼、webhook 驗簽、該不該推、怎麼推、用量提醒。

外部 HTTP 一律 mock（不打真的 LINE）。斷言打在使用者看得到的結果上：有沒有綁上、推給誰、
送達紀錄的狀態、管理員有沒有收到提醒、webhook 回什麼狀態碼。
"""

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.community_water_level.models import water_level_line as line
from odoo.addons.water_level_core.models.water_level_alert_channel import PermanentDeliveryError, RateLimitedError
from odoo.addons.water_level_core.models.water_level_device import LEVEL_ADVANCED, LEVEL_BASIC, LEVEL_FLAGSHIP

PASSWORD = 'cw-line-Pass-2026'
SECRET = 'test-channel-secret'
USER_A = 'U' + 'a' * 32
USER_B = 'U' + 'b' * 32
JS_CSRF = re.compile(r'csrf_token["\s]*[:=]\s*"([^"]+)"')


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


class LineCase:
    """兩個 TestCase 共用的資料：旗艦社區、基本社區、LINE 通道。"""

    @classmethod
    def _line_setup(cls):
        cls.member = new_test_user(cls.env, login='cw_line_member', password=PASSWORD, groups='base.group_portal')
        cls.basic_member = new_test_user(cls.env, login='cw_line_basic', password=PASSWORD, groups='base.group_portal')
        cls.manager = new_test_user(cls.env, login='cw_line_mgr', groups='base.group_user,water_level_core.group_water_level_manager')
        owner = cls.env['res.partner'].create({'name': '測試管委會（LINE）'})
        Site = cls.env['water.level.site']
        cls.site = Site.create({'name': 'LINE 旗艦社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                                'service_level': LEVEL_FLAGSHIP, 'member_user_ids': [(6, 0, [cls.member.id])]})
        cls.basic_site = Site.create({'name': 'LINE 基本社區', 'site_type': 'community', 'owner_partner_id': owner.id,
                                      'service_level': LEVEL_BASIC, 'member_user_ids': [(6, 0, [cls.basic_member.id])]})
        cls.device = cls.env['water.level.device'].create({'name': 'LINE-D1', 'device_uid': 'LINE-D1', 'site_id': cls.site.id})
        cls.basic_device = cls.env['water.level.device'].create(
            {'name': 'LINE-D2', 'device_uid': 'LINE-D2', 'site_id': cls.basic_site.id})
        cls.channel = cls.env['water.level.alert.channel'].create({
            'name': '千溢 LINE', 'channel_type': 'line', 'secret': SECRET,
            'line_channel_access_token': 'test-token', 'line_add_friend_url': 'https://lin.ee/test'})
        cls.Recipient = cls.env['water.level.line.recipient']

    def _event(self, device, event_type='level_high'):
        return self.env['water.level.event'].create({'device_id': device.id, 'event_type': event_type,
                                                     'severity': 'critical', 'start_ts': datetime(2026, 10, 21, 1, 0)})

    def _bound(self, site, user_id, name='主委'):
        recipient = self.Recipient._community_new(site, self.channel, name, self.member)
        recipient.sudo().write({'line_user_id': user_id, 'bound_at': datetime(2026, 10, 21), 'bind_code': False})
        return recipient

    def _patch(self, handler):
        patcher = patch.object(line.requests, 'request', side_effect=handler)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock


@tagged('post_install', '-at_install')
class TestLineModel(LineCase, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._line_setup()

    def setUp(self):
        super().setUp()
        # 沒有自己 mock 的測試，一碰外部網路就失敗（2026-10-21 mutation 時有一支沒 mock 的真的連了 api.line.me）
        def no_network(method, url, **kw):
            raise AssertionError('測試不准打外部網路：%s %s' % (method, url))
        self._patch(no_network)

    # ---------- 通道 ----------

    def test_line_channel_defaults_and_constraints(self):
        self.assertEqual(self.channel.max_per_hour, 0, '整個通道一起算的每小時上限會讓 A 社區吃掉 B 社區的告警')
        self.assertEqual(self.channel.audience, 'customer')
        Channel = self.env['water.level.alert.channel']
        base = {'name': 'x', 'channel_type': 'line', 'secret': SECRET, 'line_channel_access_token': 't'}
        for label, vals in {'沒有 secret': {'secret': False}, '沒有 token': {'line_channel_access_token': False},
                            '對象是內部': {'audience': 'internal'},
                            '加好友網址不是 LINE': {'line_add_friend_url': 'javascript:alert(1)'}}.items():
            with self.assertRaises(ValidationError, msg=label):
                Channel.create(dict(base, **vals))

    # ---------- 收件人與綁定碼 ----------

    def test_new_recipient_gets_a_one_time_code(self):
        recipient = self.Recipient._community_new(self.site, self.channel, ' 主委 王先生 ', self.member)
        code = recipient.sudo().bind_code
        self.assertEqual(len(code), line.BIND_CODE_LENGTH)
        self.assertTrue(set(code) <= set(line.BIND_CODE_ALPHABET))
        self.assertAlmostEqual((recipient.bind_code_expires - datetime.now()).total_seconds(),
                               line.BIND_CODE_TTL_HOURS * 3600, delta=120)
        self.assertEqual(recipient.created_by_id, self.member)
        self.assertEqual(recipient.name, '主委 王先生')

    def test_recipient_cap_per_site(self):
        for i in range(line.LINE_MAX_RECIPIENTS_PER_SITE):
            self.Recipient._community_new(self.site, self.channel, '成員 %s' % i, self.member)
        with self.assertRaises(UserError):
            self.Recipient._community_new(self.site, self.channel, '多一位', self.member)

    def test_portal_user_cannot_read_recipients_directly(self):
        self._bound(self.site, USER_A)
        with self.assertRaises(AccessError):
            self.Recipient.with_user(self.member).search([])

    def _say(self, user_id, text):
        return self.channel._line_handle_events([{'type': 'message', 'replyToken': 'rt', 'source': {'userId': user_id},
                                                  'message': {'type': 'text', 'text': text}}])

    def test_bind_with_code_then_code_is_spent(self):
        self._patch(lambda method, url, **kw: FakeResponse(200, {'displayName': '王主委'}))
        recipient = self.Recipient._community_new(self.site, self.channel, '主委', self.member)
        code = recipient.sudo().bind_code
        replies = self._say(USER_A, ' %s-%s ' % (code[:5].lower(), code[5:]))   # 空白、連字號、小寫都容許
        self.assertEqual(replies, [('rt', line.REPLY_BOUND % self.site.name)])
        self.assertEqual(recipient.sudo().line_user_id, USER_A)
        self.assertEqual(recipient.line_display_name, '王主委', '前台要看得出綁上的是誰')
        self.assertFalse(recipient.sudo().bind_code, '綁定碼用過就作廢')
        self.assertEqual(self._say(USER_B, code), [('rt', line.REPLY_BAD_CODE)], '同一組碼不能給第二個人用')
        self.assertEqual(recipient.sudo().line_user_id, USER_A)

    def test_expired_code_is_refused(self):
        self._patch(lambda method, url, **kw: FakeResponse(200, {}))
        recipient = self.Recipient._community_new(self.site, self.channel, '主委', self.member)
        recipient.sudo().bind_code_expires = datetime.now() - timedelta(minutes=1)
        self.assertEqual(self._say(USER_A, recipient.sudo().bind_code), [('rt', line.REPLY_BAD_CODE)])
        self.assertFalse(recipient.sudo().line_user_id)

    def test_too_many_wrong_codes_locks_even_the_right_one(self):
        self._patch(lambda method, url, **kw: FakeResponse(200, {}))
        recipient = self.Recipient._community_new(self.site, self.channel, '主委', self.member)
        for _i in range(line.BIND_MAX_FAILURES):
            self.assertEqual(self._say(USER_A, 'ZZZZZZZZZZ'), [('rt', line.REPLY_BAD_CODE)])
        self.assertEqual(self._say(USER_A, recipient.sudo().bind_code), [('rt', line.REPLY_LOCKED)])
        self.assertFalse(recipient.sudo().line_user_id, '鎖住期間對的碼也不能綁')

    def test_chatting_is_not_a_guess(self):
        for _i in range(line.BIND_MAX_FAILURES + 1):
            self.assertEqual(self._say(USER_A, '請問水塔怎麼了'), [('rt', line.REPLY_HELP)])
        self.assertFalse(self.env['water.level.line.bind.failure'].search_count([('line_user_id', '=', USER_A)]))

    def test_follow_unfollow_and_junk_events(self):
        recipient = self._bound(self.site, USER_A)
        self.assertEqual(self.channel._line_handle_events([{'type': 'follow', 'replyToken': 'rt', 'source': {'userId': USER_A}}]),
                         [('rt', line.REPLY_FOLLOW)])
        self.channel._line_handle_events([{'type': 'unfollow', 'source': {'userId': USER_A}}])
        self.assertFalse(recipient.active, '封鎖或刪好友就停用')
        self.assertEqual(self.channel._line_handle_events([{'type': 'message', 'replyToken': 'rt',
                                                            'source': {'userId': 'not-a-line-id'}}]), [])
        self.assertEqual(self.channel._line_handle_events('junk'), [])

    # ---------- 該不該推 ----------

    def test_push_only_to_flagship_community_with_bound_recipients(self):
        event = self._event(self.device)
        self.assertFalse(self.channel._is_applicable(self.device, event), '沒有已綁定收件人就不建送達紀錄')
        self._bound(self.site, USER_A)
        self.assertTrue(self.channel._is_applicable(self.device, event))
        self._bound(self.basic_site, USER_B)
        basic_event = self._event(self.basic_device)
        self.assertFalse(self.channel._is_applicable(self.basic_device, basic_event), '基本方案的社區有收件人也不推')
        # 上面那條 core 的 audience 判斷（設備沒有即時告警）會先擋下；LINE 自己這一道要直接測才隔離得到
        self.assertFalse(self.channel._line_should_push(self.basic_device, basic_event))

    def _delivered(self, event):
        self.env['water.level.alert.delivery'].create({'channel_id': self.channel.id, 'event_id': event.id,
                                                       'device_id': self.device.id, 'payload': '{}', 'state': 'sent'})

    def test_cooldown_per_device_and_event_type(self):
        """反覆斷線是共用額度被一個社區用光的主因：同一台、同一類一小時內只推一次。"""
        self._bound(self.site, USER_A)
        self._delivered(self._event(self.device, 'offline'))
        self.assertFalse(self.channel._is_applicable(self.device, self._event(self.device, 'offline')),
                         '同一台同一類一小時內只推一次')
        self.assertTrue(self.channel._is_applicable(self.device, self._event(self.device, 'power_loss')), '別類照推')

    def test_level_events_are_left_to_core_so_escalation_gets_through(self):
        """越線由 core 限速（同類 60 分鐘、但警戒升高照送）；LINE 自己再擋一次的話，一小時內的升級（三級→二級）會被吞掉。"""
        self._bound(self.site, USER_A)
        self._delivered(self._event(self.device, 'level_high'))
        self.assertTrue(self.channel._is_applicable(self.device, self._event(self.device, 'level_high')),
                        'core 放行的越線（例如警戒升級），LINE 不能再用冷卻擋掉')

    def test_site_monthly_cap_stops_pushing_and_tells_managers_once(self):
        self._bound(self.site, USER_A)
        usage = self.env['water.level.line.usage']._line_for(self.channel, self.site, line.month_key())
        usage.messages = self.channel.line_site_monthly_cap
        Message = self.env['mail.message']
        before = Message.search_count([('model', '=', self.channel._name), ('res_id', '=', self.channel.id)])
        self.assertFalse(self.channel._is_applicable(self.device, self._event(self.device)))
        self.assertFalse(self.channel._is_applicable(self.device, self._event(self.device, 'offline')))
        after = Message.search_count([('model', '=', self.channel._name), ('res_id', '=', self.channel.id)])
        self.assertEqual(after - before, 1, '達上限只提醒千溢一次')

    def test_quota_exhausted_month_stops_pushing(self):
        self._bound(self.site, USER_A)
        self.channel.line_quota_exhausted_month = line.month_key()
        self.assertFalse(self.channel._is_applicable(self.device, self._event(self.device)))

    def test_other_channel_types_are_untouched(self):
        webhook = self.env['water.level.alert.channel'].create({'name': 'wh', 'channel_type': 'webhook',
                                                                'endpoint': 'https://example.com/hook'})
        self.assertTrue(webhook._is_applicable(self.device, self._event(self.device)), '沒有 LINE 收件人不影響 webhook')

    # ---------- 怎麼推 ----------

    def _payload(self, site):
        return json.dumps({'site': {'id': site.id, 'name': site.name}, 'message': '【測試】水位過高'}, sort_keys=True)

    def test_send_multicasts_to_this_site_only_with_a_stable_retry_key(self):
        self._bound(self.site, USER_A)
        self._bound(self.basic_site, USER_B)
        calls = []
        self._patch(lambda method, url, **kw: calls.append((url, kw)) or FakeResponse(200))
        self.channel._send_line(self._payload(self.site))
        self.channel._send_line(self._payload(self.site))
        self.assertTrue(calls[0][0].endswith('/message/multicast'))
        self.assertEqual(calls[0][1]['json']['to'], [USER_A], '只推本社區已綁定的人')
        self.assertEqual(calls[0][1]['headers']['X-Line-Retry-Key'], calls[1][1]['headers']['X-Line-Retry-Key'],
                         '同一則重送 key 不變，LINE 才擋得住重複推')
        usage = self.env['water.level.line.usage']._line_for(self.channel, self.site, line.month_key())
        self.assertEqual(usage.messages, 2, '推給一個人算一則')

    def test_send_batches_by_multicast_limit(self):
        for user_id in (USER_A, USER_B, 'U' + 'c' * 32):
            self._bound(self.site, user_id)
        calls = []
        self._patch(lambda method, url, **kw: calls.append(kw['json']['to']) or FakeResponse(200))
        with patch.object(line, 'LINE_MULTICAST_MAX', 2):
            self.channel._send_line(self._payload(self.site))
        self.assertEqual([len(batch) for batch in calls], [2, 1])

    def test_send_error_classification(self):
        self._bound(self.site, USER_A)
        cases = [
            (FakeResponse(429, {'message': 'The API rate limit has been exceeded. Try again later.'},
                          {'Retry-After': '30'}), RateLimitedError),
            (FakeResponse(400, {'message': 'Invalid'}), PermanentDeliveryError),
            (FakeResponse(401, {'message': 'Authentication failed'}), PermanentDeliveryError),
        ]
        for response, expected in cases:
            self._patch(lambda method, url, response=response, **kw: response)
            with self.assertRaises(expected, msg=str(response.status_code)) as ctx:
                self.channel._send_line(self._payload(self.site))
            if expected is RateLimitedError:
                self.assertEqual(ctx.exception.retry_after, 30)
        self._patch(lambda method, url, **kw: FakeResponse(500))
        with self.assertRaises(RuntimeError) as ctx:
            self.channel._send_line(self._payload(self.site))
        self.assertNotIsInstance(ctx.exception, PermanentDeliveryError, '5xx 要留給重送')
        self._patch(lambda method, url, **kw: FakeResponse(409))
        self.channel._send_line(self._payload(self.site))   # 409＝同一個 retry key 已收下＝已送達

    def test_monthly_limit_fails_the_delivery_and_stops_the_month(self):
        """走 core 的真實路徑（_dispatch → _attempt）：assertRaises 會開 savepoint、把通道上記的月份一起 rollback，
        測不到正式流程裡 core 接住例外之後留下來的狀態。"""
        self._bound(self.site, USER_A)
        self._patch(lambda method, url, **kw: FakeResponse(429, {'message': line.LINE_MONTHLY_LIMIT_MESSAGE}))
        event = self._event(self.device)
        self.env['water.level.alert.channel']._dispatch(self.device, event, '【LINE 旗艦社區】水位過高')
        delivery = self.env['water.level.alert.delivery'].search([('channel_id', '=', self.channel.id),
                                                                  ('event_id', '=', event.id)])
        self.assertEqual(delivery.state, 'failed', '月額度用完不留給重送（下個月補送一個月前的告警比不送更糟）')
        self.assertEqual(self.channel.line_quota_exhausted_month, line.month_key(), '當月不再推')
        self.assertFalse(self.channel._is_applicable(self.device, self._event(self.device, 'offline')))

    def test_send_refuses_without_site_downgraded_or_no_recipients(self):
        with self.assertRaises(PermanentDeliveryError):
            self.channel._send_line(json.dumps({'message': '測試'}))
        with self.assertRaises(PermanentDeliveryError):
            self.channel._send_line(self._payload(self.site))      # 沒有收件人
        self._bound(self.site, USER_A)
        self.site.service_level = LEVEL_ADVANCED
        with self.assertRaises(PermanentDeliveryError):
            self.channel._send_line(self._payload(self.site))      # 降級後的重送

    def test_dispatch_end_to_end_through_core(self):
        self._bound(self.site, USER_A)
        self._patch(lambda method, url, **kw: FakeResponse(200))
        event = self._event(self.device)
        self.env['water.level.alert.channel']._dispatch(self.device, event, '【LINE 旗艦社區 / LINE-D1】水位過高')
        delivery = self.env['water.level.alert.delivery'].search([('channel_id', '=', self.channel.id),
                                                                  ('event_id', '=', event.id)])
        self.assertEqual(delivery.state, 'sent')

    # ---------- 通道表單的測試鈕：LINE 改成「連線檢查」 ----------

    def _connection_handler(self, info=None, endpoint=None, test=None, calls=None):
        hook = 'https://example.com/water-level/line/webhook/%s' % self.channel.id
        def handler(method, url, **kw):
            if calls is not None:
                calls.append(url)
            if url.endswith('/info'):
                return info or FakeResponse(200, {'displayName': '千溢水位通知', 'basicId': '@123abcd'})
            if url.endswith('/channel/webhook/endpoint'):
                return endpoint or FakeResponse(200, {'endpoint': hook, 'active': True})
            if url.endswith('/channel/webhook/test'):
                return test or FakeResponse(200, {'success': True, 'statusCode': 200, 'reason': 'OK', 'detail': '200'})
            raise AssertionError('連線檢查不該打 %s' % url)
        return handler

    def test_line_connection_check_sends_no_message(self):
        """通道表單上的測試鈕對 LINE 原本必定失敗（測試訊息沒有社區、LINE 不廣播）——2026-10-22 使用者第一次設定就踩到。
        改成檢查 token、Webhook URL、secret（請 LINE 實際打一次 webhook），不推訊息、不扣額度。"""
        calls = []
        self._patch(self._connection_handler(calls=calls))
        result = self.channel.with_user(self.manager).action_test()
        message = result['params']['message']
        self.assertIn('千溢水位通知', message)
        self.assertNotIn('✗', message)
        self.assertFalse([url for url in calls if '/message/' in url], '連線檢查不能推任何訊息')

    def test_line_connection_check_points_at_the_problem(self):
        cases = {
            'token 錯': (dict(info=FakeResponse(401, {'message': 'Authentication failed'})), 'Channel access token'),
            'Webhook 指到別的通道': (dict(endpoint=FakeResponse(200, {'endpoint': 'https://example.com/water-level/line/webhook/999',
                                                                     'active': True})), 'webhook/%s' % self.channel.id),
            'Webhook 沒打開': (dict(endpoint=FakeResponse(200, {'endpoint': 'https://example.com/water-level/line/webhook/%s'
                                                                % self.channel.id, 'active': False})), 'Use webhook'),
            'secret 錯（打到了但簽章不對）': (dict(test=FakeResponse(200, {'success': False, 'statusCode': 401,
                                                                       'reason': 'ERROR_STATUS_CODE', 'detail': '401'})),
                                      'Channel secret'),
            '對外網址不通': (dict(test=FakeResponse(200, {'success': False, 'statusCode': 0, 'reason': 'COULD_NOT_CONNECT',
                                                     'detail': 'Failure to connect'})), '連不到'),
            # 2026-10-22 實際遇到：網址通、是 TLS 協商失敗（LINE ↔ Tailscale Funnel）。只說「連不到」會讓人去查網址，查錯方向
            '加密協商失敗要照實說': (dict(test=FakeResponse(200, {
                'success': False, 'statusCode': 0, 'reason': 'COULD_NOT_CONNECT',
                'detail': 'Session protocol negotiation failure: https://example.com/water-level/line/webhook/1'})),
                'Session protocol negotiation failure'),
        }
        for label, (kwargs, expected) in cases.items():
            self._patch(self._connection_handler(**kwargs))
            with self.assertRaises(UserError, msg=label) as ctx:
                self.channel.with_user(self.manager).action_test()
            self.assertIn(expected, str(ctx.exception), label)

    def test_other_channel_types_keep_the_core_test(self):
        webhook = self.env['water.level.alert.channel'].create({'name': 'wh', 'channel_type': 'webhook',
                                                                'endpoint': 'https://example.com/hook'})
        with patch.object(type(webhook), '_send') as send:
            webhook.with_user(self.manager).action_test()
        self.assertTrue(send.called, 'webhook 通道的測試鈕照舊送測試訊息')

    # ---------- 收件人的「傳測試訊息」（後台，給千溢確認設定） ----------

    def test_recipient_test_message_pushes_to_that_one_person(self):
        recipient = self._bound(self.site, USER_A)
        calls = []
        self._patch(lambda method, url, **kw: calls.append((url, kw['json'])) or FakeResponse(200))
        recipient.with_user(self.manager).action_line_test()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith('/message/push'))
        self.assertEqual(calls[0][1]['to'], USER_A, '只推給這一位，不是整個社區')
        self.assertIn(self.site.name, calls[0][1]['messages'][0]['text'])
        usage = self.env['water.level.line.usage']._line_for(self.channel, self.site, line.month_key())
        self.assertEqual(usage.messages, 1, '測試訊息也扣額度，要算進每社區用量')

    def test_recipient_test_message_refusals(self):
        pending = self.Recipient._community_new(self.site, self.channel, '還沒綁', self.member)
        with self.assertRaises(UserError, msg='沒綁定不能測'):
            pending.with_user(self.manager).action_line_test()
        bound = self._bound(self.site, USER_A)
        self._patch(lambda method, url, **kw: FakeResponse(400, {'message': 'Invalid reply token'}))
        with self.assertRaises(UserError, msg='LINE 拒絕要變成看得懂的訊息，不是 traceback'):
            bound.with_user(self.manager).action_line_test()
        internal = new_test_user(self.env, login='cw_line_internal', groups='base.group_user')
        with self.assertRaises(AccessError, msg='測試訊息會扣共用額度，只有水位管理員能按'):
            bound.with_user(internal).action_line_test()

    # ---------- 用量提醒 ----------

    def test_usage_cron_warns_once_a_month(self):
        def handler(method, url, **kw):
            if url.endswith('/quota'):
                return FakeResponse(200, {'type': 'limited', 'value': 200})
            return FakeResponse(200, {'totalUsage': 170})
        self._patch(handler)
        Message = self.env['mail.message']
        domain = [('model', '=', self.channel._name), ('res_id', '=', self.channel.id)]
        before = Message.search_count(domain)
        self.channel._cron_line_usage_check()
        self.channel._cron_line_usage_check()
        self.assertEqual(Message.search_count(domain) - before, 1)
        self.assertEqual(self.channel.line_usage_warned_month, line.month_key())


@tagged('post_install', '-at_install')
class TestLineHttp(LineCase, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._line_setup()

    def setUp(self):
        super().setUp()
        # Reply 放在 commit 之後；測試裡不能真的打出去
        patcher = patch.object(line.requests, 'post', return_value=FakeResponse(200))
        patcher.start()
        self.addCleanup(patcher.stop)
        self._patch(lambda method, url, **kw: FakeResponse(200, {'displayName': '王主委'}))

    def _webhook(self, channel_id, body, signature):
        headers = {'Content-Type': 'application/json'}
        if signature is not None:
            headers['X-Line-Signature'] = signature
        return self.url_open('/water-level/line/webhook/%s' % channel_id, data=body, headers=headers)

    @staticmethod
    def _sign(body, secret=SECRET):
        return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

    def test_webhook_signature(self):
        body = json.dumps({'destination': 'x', 'events': []}).encode()
        self.assertEqual(self._webhook(self.channel.id, body, self._sign(body)).status_code, 200, 'LINE 後台的驗證要回 200')
        self.assertEqual(self._webhook(self.channel.id, body, self._sign(body, 'wrong')).status_code, 401)
        self.assertEqual(self._webhook(self.channel.id, body, None).status_code, 401, '沒帶簽章')
        self.assertEqual(self._webhook(self.channel.id + 999, body, self._sign(body)).status_code, 401, '通道不存在')
        webhook = self.env['water.level.alert.channel'].create({'name': 'wh', 'channel_type': 'webhook',
                                                                'endpoint': 'https://example.com/hook', 'secret': SECRET})
        self.assertEqual(self._webhook(webhook.id, body, self._sign(body)).status_code, 401, '不是 LINE 通道')
        # secret 空著（繞過 constraint 寫進去）：空金鑰的 HMAC 誰都算得出來
        self.env.cr.execute('UPDATE water_level_alert_channel SET secret = NULL WHERE id = %s', (self.channel.id,))
        self.channel.invalidate_recordset()
        self.assertEqual(self._webhook(self.channel.id, body, self._sign(body, '')).status_code, 401)

    def test_webhook_binds(self):
        recipient = self.Recipient._community_new(self.site, self.channel, '主委', self.member)
        body = json.dumps({'events': [{'type': 'message', 'replyToken': 'rt', 'source': {'userId': USER_A},
                                       'message': {'type': 'text', 'text': recipient.sudo().bind_code}}]}).encode()
        self.assertEqual(self._webhook(self.channel.id, body, self._sign(body)).status_code, 200)
        recipient.invalidate_recordset()
        self.assertEqual(recipient.sudo().line_user_id, USER_A)

    def test_notifications_page_is_flagship_only(self):
        self.authenticate(self.basic_member.login, PASSWORD)
        self.assertEqual(self.url_open('/community/%s/notifications' % self.basic_site.id).status_code, 403)
        self.authenticate(self.member.login, PASSWORD)
        foreign = self.url_open('/community/%s/notifications' % self.basic_site.id)
        self.assertFalse(foreign.url.endswith('/notifications'), '不是那個社區的成員要被導走，實際停在 %s' % foreign.url)
        res = self.url_open('/community/%s/notifications' % self.site.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn('產生綁定碼', res.text)

    def test_member_creates_and_disables_recipients_of_own_site_only(self):
        self.authenticate(self.member.login, PASSWORD)
        token = JS_CSRF.search(self.url_open('/community/%s/notifications' % self.site.id).text).group(1)
        res = self.url_open('/community/%s/notifications/new' % self.site.id, data={'csrf_token': token, 'name': '總幹事'})
        recipient = self.Recipient.search([('site_id', '=', self.site.id), ('name', '=', '總幹事')])
        self.assertTrue(recipient, '新增要建出收件人')
        self.assertIn(recipient.sudo().bind_code, res.text, '新增後頁面要顯示綁定碼')
        other = self._bound(self.basic_site, USER_B)
        res = self.url_open('/community/%s/notifications/%s/disable' % (self.site.id, other.id), data={'csrf_token': token})
        self.assertEqual(res.status_code, 404, '別社區的收件人不能停用')
        self.assertTrue(other.active)
        self.url_open('/community/%s/notifications/%s/disable' % (self.site.id, recipient.id), data={'csrf_token': token})
        recipient.invalidate_recordset()
        self.assertFalse(recipient.active)
        self.assertEqual(recipient.disabled_by_id, self.member)
