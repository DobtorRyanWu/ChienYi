# -*- coding: utf-8 -*-
"""告警對象分流（千溢內部／客戶）與 Discord 通道。

**這個測試在防什麼**
2026-10-21 使用者定案：告警要同時送兩種人——
* 千溢內部（Discord 頻道）：**所有方案的社區都要收**，千溢要維護每一台設備
* 客戶（管委會）：照 DM，只有旗艦方案才有「即時告警推播」
在這之前「是不是旗艦」是在告警掃描裡判斷的（不是旗艦就整個不外送），
千溢自己的監看頻道因此看不到基本、進階方案的設備斷線。

**為什麼 Discord 要擋 @everyone、要藏網址**
事件說明、場域名稱是使用者打的字，Discord 預設會把內文的 @everyone／@here 變成真的提及。
Discord 推送網址本身就是發文憑證：讀得到就能對頻道發任何訊息、自己帶 @everyone、甚至刪掉 webhook。

**為什麼不打真的 HTTP**
換掉 `requests.post`，攔下送出去的內容、控制對方回什麼——要驗的是「格式對不對、
對方回什麼錯時我們怎麼處理」，不是 Discord 本身。

**為什麼 setUpClass 先封存既有通道**
這組測試也會在正式資料的拷貝庫上跑（pull 後影響檢查）。庫裡若已有真的通道（例如千溢的 Discord），
它們也會收到測試事件，「送了幾則」就不準；封存只在測試交易裡，結束會還原。
"""

import json
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import common, new_test_user, tagged
from odoo.tools import mute_logger

from .common import site_vals

DISCORD_TOKEN = 'SECRETTOKEN42xyz'
DISCORD_HOOK = 'https://discord.com/api/webhooks/123/%s' % DISCORD_TOKEN
ROLE_ID = '987654321'


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        # webhook 傳輸用的；與 requests.Response 一樣，4xx／5xx 才拋
        if self.status_code >= 400:
            raise RuntimeError('HTTP %s' % self.status_code)


@tagged('post_install', '-at_install')
class TestAlertAudienceAndDiscord(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Channel = cls.env['water.level.alert.channel']
        Channel.search([]).write({'active': False})
        # 不同等級的設備放在不同場域：社區模組要求社區場域的設備等級等於場域等級
        Site = cls.env['water.level.site']
        cls.site = Site.create(site_vals(cls.env, '青田路社區', service_level='basic'))
        cls.flagship_site = Site.create(site_vals(cls.env, '頂樓社區', service_level='flagship'))
        Device = cls.env['water.level.device']
        cls.basic = Device.create({
            'name': 'B1 蓄水池', 'site_id': cls.site.id,
            'device_uid': 'TEST-AUD-BASIC', 'service_level': 'basic',
        })
        cls.flagship = Device.create({
            'name': '頂樓水塔', 'site_id': cls.flagship_site.id,
            'device_uid': 'TEST-AUD-FLAG', 'service_level': 'flagship',
        })
        cls.internal = Channel.create({
            'name': '千溢監看', 'channel_type': 'webhook', 'audience': 'internal',
            'endpoint': 'https://example.invalid/internal', 'max_per_hour': 0,
        })
        cls.customer = Channel.create({
            'name': '管委會', 'channel_type': 'webhook', 'audience': 'customer',
            'endpoint': 'https://example.invalid/customer',
        })

    def _event(self, device, event_type='offline', note='測試用事件'):
        return self.env['water.level.event'].create({
            'device_id': device.id, 'event_type': event_type, 'severity': 'critical',
            'start_ts': '2026-10-21 00:00:00', 'note': note,
        })

    def _deliveries(self, channel, device):
        return self.env['water.level.alert.delivery'].search(
            [('channel_id', '=', channel.id), ('device_id', '=', device.id)])

    def _patch_post(self, response, sink=None):
        """換掉 requests.post：一律回 response（或拋它，如果它是例外），送出去的 (url, json) 收進 sink。"""
        def fake_post(url, json=None, data=None, headers=None, timeout=None, allow_redirects=True):
            if sink is not None:
                sink.append({'url': url, 'json': json})
            if isinstance(response, Exception):
                raise response
            return response

        patcher = patch('requests.post', fake_post)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _notify(self, device, note='測試用事件'):
        event = self._event(device, note=note)
        self.env['water.level.monitor']._notify(device, event)
        return event

    # ==================== 對象分流 ====================

    def test_new_channel_defaults_to_customer(self):
        """沒指定對象的通道要當成客戶通道——既有的客戶 webhook 升級後行為不能變。"""
        channel = self.env['water.level.alert.channel'].create({
            'name': '舊的 webhook', 'channel_type': 'webhook',
            'endpoint': 'https://example.invalid/old',
        })
        self.assertEqual(channel.audience, 'customer')

    def test_scan_sends_basic_plan_alert_to_internal_only(self):
        """基本方案的設備斷線：千溢監看頻道收得到，管委會的通道收不到。

        走告警掃描（不是直接呼叫 _notify），因為「不是旗艦就不外送」原本就擋在掃描裡。
        """
        self._patch_post(FakeResponse(204))
        self.basic.write({'last_seen': '2020-01-01 00:00:00', 'offline_after_min': 30})

        self.env['water.level.monitor']._cron_alert_scan()

        internal = self._deliveries(self.internal, self.basic)
        self.assertEqual(len(internal), 1, '千溢監看頻道沒收到基本方案設備的斷線告警')
        self.assertEqual(internal.state, 'sent')
        self.assertFalse(self._deliveries(self.customer, self.basic),
                         '基本方案不該推給客戶——那是旗艦方案才有的功能')

    def test_flagship_alert_goes_to_both(self):
        self._patch_post(FakeResponse(204))
        self._notify(self.flagship)

        self.assertEqual(self._deliveries(self.internal, self.flagship).state, 'sent')
        self.assertEqual(self._deliveries(self.customer, self.flagship).state, 'sent')

    def test_basic_plan_gets_no_station_notice(self):
        """站內通知（chatter）維持只有旗艦才發，這次只改外送的分流。"""
        self._patch_post(FakeResponse(204))
        event = self._event(self.basic)
        before = len(event.message_ids)

        self.env['water.level.monitor']._notify(self.basic, event)

        self.assertEqual(len(event.message_ids), before)

    def test_archived_site_still_restricts_channel(self):
        """通道只綁 A 社區，A 封存後不可以變成「所有場域」——那會把全部客戶的告警送給 A。"""
        other = self.env['water.level.site'].create(site_vals(self.env, '已解約社區'))
        self.customer.site_ids = [(6, 0, [other.id])]
        other.active = False
        self._patch_post(FakeResponse(204))

        self._notify(self.flagship)

        self.assertFalse(self._deliveries(self.customer, self.flagship),
                         '綁定的場域封存後，通道收到了別的社區的告警')

    def test_one_broken_channel_does_not_abort_others(self):
        """一個通道在資料庫層出錯，只退回它自己；排在後面的通道照送，交易也還能用。"""
        broken = self.env['water.level.alert.channel'].create({
            'name': '壞通道', 'sequence': 1, 'channel_type': 'webhook', 'audience': 'internal',
            'endpoint': 'https://example.invalid/broken',
        })
        original = type(broken)._send

        def send(channel, payload_text):
            if channel.id == broken.id:
                channel.env.cr.execute('SELECT 1/0')
            return original(channel, payload_text)

        self._patch_post(FakeResponse(204))
        with patch.object(type(broken), '_send', send), \
                mute_logger('odoo.sql_db', 'odoo.addons.water_level_core.models.water_level_alert_channel'):
            self._notify(self.basic)

        self.assertEqual(self._deliveries(self.internal, self.basic).state, 'sent',
                         '前一個通道的資料庫錯誤拖垮了後面的通道')

    # ==================== Discord：設定 ====================

    def _discord(self, **vals):
        return self.env['water.level.alert.channel'].create(dict({
            'name': '千溢 Discord', 'channel_type': 'discord', 'audience': 'internal',
            'discord_webhook_url': DISCORD_HOOK, 'max_per_hour': 0,
        }, **vals))

    def test_discord_requires_https_discord_url(self):
        Channel = self.env['water.level.alert.channel']
        for url in (False, 'http://discord.com/api/webhooks/1/x', 'https://example.com/hook'):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                Channel.create({'name': '錯網址', 'channel_type': 'discord',
                                'discord_webhook_url': url})

    def test_discord_role_id_must_be_digits(self):
        for role in ('<@&123>', '@告警', '12 34'):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                self._discord(discord_role_id=role)

    def test_internal_user_cannot_read_discord_url(self):
        """推送網址就是發文憑證：一般內部使用者讀不到。"""
        channel = self._discord()
        user = new_test_user(self.env, login='wl_internal_reader', groups='base.group_user')
        with self.assertRaises(AccessError):
            channel.with_user(user).read(['discord_webhook_url'])

    def test_readonly_user_cannot_send_test_message(self):
        """唯讀使用者按「送出測試訊息」要先被擋，不能等 HTTP 送出去之後才在寫入時失敗。"""
        channel = self._discord()
        user = new_test_user(self.env, login='wl_internal_tester', groups='base.group_user')
        sink = []
        self._patch_post(FakeResponse(204), sink)

        with self.assertRaises(AccessError):
            channel.with_user(user).action_test()
        self.assertEqual(sink, [], '沒有權限的人已經把訊息送出去了')

    # ==================== Discord：訊息 ====================

    def test_discord_message_mentions_only_the_alert_role(self):
        """@ 告警身分組（設成「僅限提及」的人也會跳通知），而且只允許提及這一個。"""
        channel = self._discord(discord_role_id=ROLE_ID)
        sink = []
        self._patch_post(FakeResponse(204), sink)

        self._notify(self.basic, note='水位 @everyone 過低')

        sent = [s for s in sink if s['url'] == DISCORD_HOOK]
        self.assertEqual(len(sent), 1)
        message = sent[0]['json']
        self.assertTrue(message['content'].startswith('<@&%s>' % ROLE_ID))
        self.assertEqual(message['allowed_mentions'], {'parse': [], 'roles': [ROLE_ID]},
                         '使用者打的 @everyone 會變成真的全體提及')
        for text in ('青田路社區', 'B1 蓄水池', '斷線'):
            self.assertIn(text, message['content'])
        self.assertEqual(self._deliveries(channel, self.basic).state, 'sent')

    def test_discord_without_role_mentions_nobody(self):
        self._discord()
        sink = []
        self._patch_post(FakeResponse(204), sink)

        self._notify(self.basic, note='@here 測試')

        message = [s for s in sink if s['url'] == DISCORD_HOOK][0]['json']
        self.assertEqual(message['allowed_mentions'], {'parse': [], 'roles': []})
        self.assertNotIn('<@&', message['content'])

    def test_discord_content_fits_limit(self):
        from ..models.water_level_alert_channel import DISCORD_CONTENT_MAX
        self._discord(discord_role_id=ROLE_ID)
        sink = []
        self._patch_post(FakeResponse(204), sink)

        self._notify(self.basic, note='長' * 5000)

        message = [s for s in sink if s['url'] == DISCORD_HOOK][0]['json']
        self.assertLessEqual(len(message['content']), DISCORD_CONTENT_MAX)

    # ==================== Discord：對方出錯 ====================

    def test_discord_404_fails_without_retry(self):
        """推送網址被刪掉（404）：不要再重送，通道標出錯誤。重送只會累積無效請求。"""
        channel = self._discord()
        self._patch_post(FakeResponse(404, {'message': 'Unknown Webhook', 'code': 10015}))

        self._notify(self.basic)

        delivery = self._deliveries(channel, self.basic)
        self.assertEqual(delivery.state, 'failed', '404 還留在待送，重送 cron 會一直打')
        self.assertEqual(delivery.attempts, 1)
        self.assertIn('404', channel.last_error)

        sink = []
        self._patch_post(FakeResponse(204), sink)
        self.env['water.level.alert.delivery']._cron_retry()
        self.assertFalse([s for s in sink if s['url'] == DISCORD_HOOK])

    def test_discord_429_pauses_channel_without_counting(self):
        """被限流（429）：不算一次嘗試，通道暫停到對方要求的秒數之後，期間重送 cron 不打它。"""
        channel = self._discord()
        self._patch_post(FakeResponse(429, {'retry_after': 30, 'global': False}))

        self._notify(self.basic)

        delivery = self._deliveries(channel, self.basic)
        self.assertEqual(delivery.state, 'pending')
        self.assertEqual(delivery.attempts, 0, '限流不該吃掉重送次數——吃完就永久失敗，告警就漏了')
        self.assertTrue(channel.rate_limited_until)

        sink = []
        self._patch_post(FakeResponse(204), sink)
        self.env['water.level.alert.delivery']._cron_retry()
        self.assertFalse([s for s in sink if s['url'] == DISCORD_HOOK], '限流期間還在打')
        self.assertEqual(delivery.state, 'pending')

        channel.rate_limited_until = '2020-01-01 00:00:00'   # 暫停結束
        self.env['water.level.alert.delivery']._cron_retry()
        self.assertEqual(delivery.state, 'sent')

    def test_discord_connection_error_hides_token(self):
        """連線錯誤的訊息帶完整網址（含 token），不能原文寫進 last_error。"""
        channel = self._discord()
        self._patch_post(requests.ConnectionError(
            'Max retries exceeded with url: /api/webhooks/123/%s' % DISCORD_TOKEN))

        self._notify(self.basic)

        delivery = self._deliveries(channel, self.basic)
        self.assertEqual(delivery.state, 'pending')
        self.assertNotIn(DISCORD_TOKEN, delivery.last_error)
        self.assertNotIn(DISCORD_TOKEN, channel.last_error)
