# -*- coding: utf-8 -*-
"""告警外送通道 —— 讓「異常即時告警推播」這句話成立的那一段。

**這個測試在防什麼**
DM 旗艦等級（定價 17 萬）白紙黑字寫「異常即時告警推播」，但在 2.4.0 之前，
`water.level.monitor._notify()` 只做 `message_post`——訊息落在 Odoo 的 chatter，
使用者不登入就看不到。文宣與實況不符。

所以第一個測試（test_alert_reaches_outside_world）就是這句承諾的可執行版本：
**告警發生時，系統必須把它送到 Odoo 之外**。拿掉 `_notify()` 裡的 `_dispatch`
那一行，這個測試就會紅。

**為什麼不打真的 HTTP**
`_send_webhook` 用 requests 打外網，測試環境不該依賴外部端點。
這裡改寫 `_send`（型別分派的那一層）而不是 `_send_webhook`，
因為要驗的是「派送層有沒有把正確的東西交給傳輸層」，
傳輸層本身（HMAC 簽章怎麼算、requests 怎麼呼叫）是另一回事。

**為什麼用 flagship 服務等級而不是直接設 feature_realtime_alert**
那是 compute 欄位（依 service_level 推導），直接寫不進去。
測試要走跟正式環境同一條路：設等級，讓系統自己推出旗艦功能。
"""

import json
from unittest.mock import patch

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestWaterLevelAlertChannel(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 社區型場域有 constrains 要求填擁有者（管委會／物業），不是可省的欄位
        cls.owner = cls.env['res.partner'].create({'name': '測試管委會'})
        cls.site = cls.env['water.level.site'].create({
            'name': '測試社區',
            'site_type': 'community',
            'owner_partner_id': cls.owner.id,
        })
        cls.device = cls.env['water.level.device'].create({
            'name': '地下蓄水池',
            'site_id': cls.site.id,
            'device_uid': 'TEST-ALERT-001',
            'service_level': 'flagship',
        })
        cls.channel = cls.env['water.level.alert.channel'].create({
            'name': '測試通道',
            'channel_type': 'webhook',
            'endpoint': 'https://example.invalid/hook',
            'min_severity': 'warning',
        })

    def _make_event(self, severity='critical', event_type='offline'):
        return self.env['water.level.event'].create({
            'device_id': self.device.id,
            'event_type': event_type,
            'severity': severity,
            'start_ts': '2026-08-31 00:00:00',
            'note': '測試用事件',
        })

    def _patch_send(self, sink=None, raises=None):
        """把傳輸層換掉，攔下要送出去的內容。

        用 mock.patch.object 而不是直接 setattr：`_send` 定義在基底類別，
        setattr 會在 registry class 上新增一個屬性，還原時也刪不掉，
        Odoo 的 TransactionCase 會以「Found unexpected attributes」擋下來。
        mock 知道屬性原本是不是本地定義的，該 delattr 就 delattr。
        """
        def fake_send(channel_self, payload_text):
            if raises:
                raise raises
            if sink is not None:
                sink.append(payload_text)
            return True

        patcher = patch.object(
            type(self.env['water.level.alert.channel']), '_send', fake_send)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ==================== 核心承諾 ====================

    def test_alert_reaches_outside_world(self):
        """告警必須離開 Odoo。這是 DM 那句「即時告警推播」的可執行定義。"""
        sink = []
        self._patch_send(sink=sink)
        event = self._make_event()

        self.env['water.level.monitor']._notify(self.device, event)

        self.assertEqual(len(sink), 1, '告警沒有被送出系統外——站內 chatter 不算推播')
        payload = json.loads(sink[0])
        self.assertEqual(payload['event_id'], event.id)
        self.assertEqual(payload['severity'], 'critical')
        self.assertEqual(payload['site']['name'], '測試社區')
        self.assertEqual(payload['device']['name'], '地下蓄水池')

        delivery = self.env['water.level.alert.delivery'].search(
            [('event_id', '=', event.id)])
        self.assertEqual(delivery.state, 'sent')
        self.assertTrue(delivery.sent_at, '送達時間沒寫進去，事後無法舉證')

    def test_station_notice_still_posted(self):
        """加了外送之後，站內通知不能不見——那是舉證用的憑據。"""
        self._patch_send(sink=[])
        event = self._make_event()
        before = len(event.message_ids)

        self.env['water.level.monitor']._notify(self.device, event)

        self.assertGreater(len(event.message_ids), before, '站內 chatter 訊息消失了')

    # ==================== 壞掉的端點不能拖垮系統 ====================

    def test_dead_endpoint_does_not_break_alerting(self):
        """外部端點掛掉時，事件與站內通知照常，只有送達紀錄記為待送。

        這是最重要的一條防線：一個死掉的 webhook 不可以害整批告警掃不完。
        """
        self._patch_send(raises=RuntimeError('connection refused'))
        event = self._make_event()

        self.env['water.level.monitor']._notify(self.device, event)  # 不得拋例外

        delivery = self.env['water.level.alert.delivery'].search(
            [('event_id', '=', event.id)])
        self.assertEqual(delivery.state, 'pending', '失敗應留待重送，不是直接丟掉')
        self.assertEqual(delivery.attempts, 1)
        self.assertIn('connection refused', delivery.last_error)

    def test_retry_cron_picks_up_pending(self):
        """端點修好之後，重送 cron 要把積著的告警送出去。"""
        self._patch_send(raises=RuntimeError('boom'))
        event = self._make_event()
        self.env['water.level.monitor']._notify(self.device, event)
        delivery = self.env['water.level.alert.delivery'].search(
            [('event_id', '=', event.id)])
        self.assertEqual(delivery.state, 'pending')

        sink = []
        self._patch_send(sink=sink)          # 端點修好了
        self.env['water.level.alert.delivery']._cron_retry()

        self.assertEqual(delivery.state, 'sent')
        self.assertEqual(delivery.attempts, 2, '重送次數要累加，才看得出試了幾次')
        self.assertEqual(len(sink), 1)

    # ==================== 過濾與節流 ====================

    def test_below_min_severity_not_sent(self):
        """低於門檻的事件不外送，避免資訊級事件洗版管委會的手機。"""
        sink = []
        self._patch_send(sink=sink)
        event = self._make_event(severity='info')

        self.env['water.level.monitor']._notify(self.device, event)

        self.assertEqual(sink, [], '資訊級事件不該外送')
        self.assertFalse(self.env['water.level.alert.delivery'].search(
            [('event_id', '=', event.id)]))

    def test_other_site_not_sent(self):
        """通道指定了場域時，別的場域的告警不該送過去（多客戶共用同一站台的隔離）。"""
        other_site = self.env['water.level.site'].create({
            'name': '別的社區', 'site_type': 'community',
            'owner_partner_id': self.owner.id})
        self.channel.site_ids = [(6, 0, [other_site.id])]
        sink = []
        self._patch_send(sink=sink)

        self.env['water.level.monitor']._notify(self.device, self._make_event())

        self.assertEqual(sink, [], '送到了不該送的場域，等於把 A 客戶的告警送給 B 客戶')

    def test_hourly_cap_skips_without_losing_event(self):
        """告警風暴時停止外送，但事件本身必須完整留在系統裡。"""
        self.channel.max_per_hour = 1
        sink = []
        self._patch_send(sink=sink)

        first = self._make_event()
        self.env['water.level.monitor']._notify(self.device, first)
        second = self._make_event(event_type='power_loss')
        self.env['water.level.monitor']._notify(self.device, second)

        self.assertEqual(len(sink), 1, '超過上限還繼續送')
        skipped = self.env['water.level.alert.delivery'].search(
            [('event_id', '=', second.id)])
        self.assertEqual(skipped.state, 'skipped')
        self.assertTrue(second.exists(), '事件不可以因為送不出去就消失')
