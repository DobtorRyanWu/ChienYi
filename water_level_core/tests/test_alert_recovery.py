# -*- coding: utf-8 -*-
"""狀態型告警恢復後要自己收掉。

**這個測試在防什麼**

2026-09-08 生產站（jt.qytech）出的事：撈取排程漏跑兩輪，設備 31 分鐘沒上報，
掃描正確地開了一筆 critical 斷線事件。兩小時後資料恢復、`is_offline` 變回 False，
**但事件掛了 21 小時沒關**——因為當時的 `_cron_alert_scan` 只有開事件的路徑，
整個檔案裡沒有任何 close / end_ts 的處理。畫面上就一直掛著「斷線」。

所以第一個測試就是那句話的可執行版本：**異常條件消失後，狀態型事件必須自己結束**。
把 `_cron_alert_scan` 裡的 `_close_recovered` 那一行拿掉，這個測試就會紅。

**水位越線：2026-10-21 起也會自動結束（使用者定案，社區與工程都套用）**

規則與理由的完整版在 models/water_level_monitor.py 的 LEVEL_TYPES、_level_recovered_at、_open_event，
外送限速在 LEVEL_NOTIFY_COOLDOWN_MINUTES 與 _level_notify_cooling。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .common import site_vals


@tagged('post_install', '-at_install')
class TestWaterLevelAlertRecovery(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['water.level.site'].create(site_vals(cls.env, '測試社區（恢復）'))
        cls.device = cls.env['water.level.device'].create({
            'name': '測試蓄水池',
            'site_id': cls.site.id,
            'device_uid': 'TEST-RECOVER-001',
            'offline_after_min': 30,
            'alert_direction': 'high',
            'level_1': 10.0,
            'level_2': 8.0,
            'level_3': 6.0,
        })
        cls.monitor = cls.env['water.level.monitor']

    def _events(self, event_type):
        return self.env['water.level.event'].search([
            ('device_id', '=', self.device.id),
            ('event_type', '=', event_type),
        ])

    def _scan(self):
        """跑一輪告警掃描，而且這台測試設備不能在掃描裡出錯：掃描會把單台的錯誤吞成 log，
        不擋的話，「某件事沒發生」的斷言會因為掃描半途出錯而假綠。"""
        with self.assertNoLogs('odoo.addons.water_level_core.models.water_level_monitor', level='ERROR'):
            self.monitor._cron_alert_scan()

    def _set_last_seen(self, minutes_ago):
        self.device.write({
            'last_seen': fields.Datetime.now() - timedelta(minutes=minutes_ago),
        })

    def test_offline_event_closes_when_data_returns(self):
        """斷線 → 開事件；資料回來 → 同一筆事件自己關掉。"""
        # ① 超過門檻沒上報：掃描應該開一筆 critical 斷線事件
        self._set_last_seen(minutes_ago=45)
        self.assertTrue(self.device.is_offline, '前提不成立：45 分鐘沒上報應該算斷線')
        self._scan()

        events = self._events('offline')
        self.assertEqual(len(events), 1, '斷線後應該恰好開一筆事件')
        self.assertEqual(events.state, 'open')
        self.assertFalse(events.end_ts, '剛開的事件不該有結束時間')

        # ② 再掃一次不該重複開（_open_event 的既有行為，一併釘住）
        self._scan()
        self.assertEqual(len(self._events('offline')), 1, '同一個異常不該開第二筆')

        # ③ 資料回來了：同一筆事件應該被關掉，而不是留著讓人以為還在斷線
        self._set_last_seen(minutes_ago=1)
        self.assertFalse(self.device.is_offline, '前提不成立：1 分鐘前上報不該算斷線')
        self._scan()

        events = self._events('offline')
        self.assertEqual(len(events), 1, '關閉不該產生新事件')
        self.assertEqual(events.state, 'closed', '斷線恢復後事件必須自己結束')
        self.assertTrue(events.end_ts, '關閉的事件要有結束時間')

    # ==================== 水位越線 ====================

    def _readings(self, start, values, step_min=10, update_last=True):
        """從 start 起每 step_min 分鐘一筆，依序寫入 values。
        `update_last=False`：設備的最新水位不跟著變（模擬時間比現有讀值早的補送）。"""
        Reading = self.env['water.level.reading']
        ts = start
        for value in values:
            Reading.create({'device_id': self.device.id, 'ts': ts, 'value': value})
            ts += timedelta(minutes=step_min)
        if update_last:
            self.device.write({'last_value': values[-1], 'last_seen': fields.Datetime.now()})

    def _open_breach(self, start, event_type='level_high', values=(12.0, 12.0, 12.0)):
        """連續 3 筆超標 → 掃描開一筆越線事件。

        start_ts 是開事件當下的伺服器時間，讀值要晚於它才採計；這裡把它撥到第三筆超標之後一分鐘
        （掃描剛好在那時跑），跟正式環境的時間軸一樣。讀值晚到的情況另有一支測試。"""
        self._readings(start, list(values))
        self.assertIn(self.device.level_state, ('lv1', 'lv3', 'low1'), '前提不成立：應該在警戒內')
        self._scan()
        event = self._events(event_type).filtered(lambda e: e.state == 'open')
        self.assertEqual(len(event), 1, '連續三筆超標應該開一筆越線事件')
        # 保全起點是建事件時依 start_ts 算的，撥時間要一起撥
        scan_ts = start + timedelta(minutes=21)
        event.write({'start_ts': scan_ts, 'protected_from_ts': event._buffer_start(scan_ts)})
        return event

    def test_level_breach_closes_after_sustained_recovery(self):
        """水位連續 3 筆回到正常 → 事件自己結束，結束時間是第一筆正常的讀值。"""
        from odoo.addons.water_level_core.models.water_level_event import POST_EVENT_BUFFER_MINUTES
        base = fields.Datetime.now() - timedelta(minutes=120)
        event = self._open_breach(base)

        first_normal = base + timedelta(minutes=30)
        self._readings(first_normal, [3.0, 3.0, 3.0])
        self.assertEqual(self.device.level_state, 'normal', '前提不成立：3.0 應該回到正常')
        self._scan()

        self.assertEqual(event.state, 'closed', '水位恢復正常後越線事件應該自己結束')
        self.assertEqual(event.end_ts, first_normal, '結束時間應該是第一筆回到正常的讀值')
        self.assertEqual(event.protected_to_ts,
                         first_normal + timedelta(minutes=POST_EVENT_BUFFER_MINUTES),
                         '保全區段要照既有規則延到結束後')

    def test_level_breach_stays_open_while_recovery_is_short(self):
        """只有 2 筆正常就不結束——去抖動，避免水位在警戒線上下抖時一直開開關關。"""
        base = fields.Datetime.now() - timedelta(minutes=120)
        event = self._open_breach(base)

        self._readings(base + timedelta(minutes=30), [3.0, 3.0])
        self._scan()

        self.assertEqual(event.state, 'open', '才 2 筆正常就結束了')

    def test_level_breach_in_between_restarts_recovery(self):
        """正常、正常、又超標、正常——最後一次超標之後還不到 3 筆正常，不結束。"""
        base = fields.Datetime.now() - timedelta(minutes=120)
        event = self._open_breach(base)

        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 7.0, 3.0])   # 7.0 高於三級 6.0
        self._scan()

        self.assertEqual(event.state, 'open', '中間又超標過，恢復要重新計算')

    def test_late_readings_never_invert_protection(self):
        """恢復的讀值時間早於事件開始（晚到、補送）：不採計，保全區段不能前後顛倒。"""
        base = fields.Datetime.now() - timedelta(minutes=120)
        self._readings(base, [12.0, 12.0, 12.0])
        self._scan()
        event = self._events('level_high')                 # start_ts＝現在，比讀值晚約 100 分鐘
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()
        self.assertEqual(event.state, 'open', '用事件開始之前的讀值結束了事件')

        self._readings(fields.Datetime.now() + timedelta(minutes=1), [3.0, 3.0, 3.0], step_min=1)
        self._scan()
        self.assertEqual(event.state, 'closed')
        self.assertGreater(event.end_ts, event.start_ts)
        self.assertLess(event.protected_from_ts, event.protected_to_ts, '保全區段前後顛倒')

    def test_low_level_event_closes_on_recovery(self):
        """低水位方向（社區蓄水池主要用這個）同樣會自動結束。"""
        self.device.write({'alert_direction': 'low', 'low_level_1': 2.0,
                           'low_level_2': 3.0, 'low_level_3': 4.0})
        base = fields.Datetime.now() - timedelta(minutes=120)
        event = self._open_breach(base, 'level_low', values=(1.0, 1.0, 1.0))

        self._readings(base + timedelta(minutes=30), [3.5, 5.0, 5.0, 5.0])   # 3.5 仍低於三級 4.0
        self._scan()

        self.assertEqual(event.state, 'closed')
        self.assertEqual(event.end_ts, base + timedelta(minutes=40), '3.5 還在低水位，不算恢復')

    def test_device_reported_event_not_auto_closed(self):
        """設備自己回報的事件（有 event_uid）由設備送結束時間，掃描不替它關。"""
        event = self.env['water.level.event'].create({
            'device_id': self.device.id, 'event_uid': 'DEV-EVT-1', 'event_type': 'level_low',
            'severity': 'warning', 'start_ts': fields.Datetime.now() - timedelta(minutes=60)})
        self._readings(fields.Datetime.now() - timedelta(minutes=40), [5.0, 5.0, 5.0])

        self._scan()

        self.assertEqual(event.state, 'open', '掃描關掉了設備端回報的事件')

    def _capture_dispatch(self, delivered=1):
        """換掉外送（_dispatch），只收這台測試設備送出去的事件；庫裡別的真設備不算進來。
        `delivered` 是假裝當場送達了幾個通道（0＝都沒送到）。"""
        dispatched = []

        def fake_dispatch(channels, dev, event, body):
            if dev == self.device:
                dispatched.append(event.id)
            return delivered

        self.patch(type(self.env['water.level.alert.channel']), '_dispatch', fake_dispatch)
        return dispatched

    def test_rebreach_within_cooldown_opens_event_without_dispatch(self):
        """結束後一小時內又越線：照開新事件（留紀錄、能簽收），但不外送——擺盪不洗版、不吃 LINE 額度。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()
        self.assertEqual(first.state, 'closed')

        self._readings(base + timedelta(minutes=55), [12.0, 12.0, 12.0], step_min=5)
        self._scan()

        second = self._events('level_high') - first
        self.assertEqual(len(second), 1, '再越線應該開新事件')
        self.assertEqual(dispatched, [first.id], '限速期間又外送了一次')
        self.assertFalse(second.alert_notified_at, '沒外送的事件不該有外送時間')

    def test_cooldown_does_not_slide_with_suppressed_events(self):
        """限速看「上次真的外送」：被壓掉的事件不能把限速往後延，擺盪再久每小時也要推一次。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)
        first.alert_notified_at = fields.Datetime.now() - timedelta(minutes=61)
        self.env['water.level.event'].create({     # 中間一筆被壓掉、剛結束的事件
            'device_id': self.device.id, 'event_type': 'level_high', 'severity': 'critical',
            'trigger_state': 'lv1', 'state': 'closed',
            'start_ts': fields.Datetime.now() - timedelta(minutes=30),
            'end_ts': fields.Datetime.now() - timedelta(minutes=10)})
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [12.0, 12.0, 12.0], step_min=5)
        self._scan()

        third = self._events('level_high').filtered(lambda e: e.state == 'open')
        self.assertEqual(dispatched, [first.id, third.id], '被壓掉的事件把限速往後延了')

    def test_escalation_within_cooldown_still_dispatches(self):
        """一小時內從三級升到二級（嚴重度欄位都是「警告」）：警戒等級升高照推，不能被限速吞掉。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base, values=(7.0, 7.0, 7.0))           # 三級
        self.assertEqual((first.trigger_state, first.severity), ('lv3', 'warning'), '前提不成立')
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [9.0, 9.0, 9.0], step_min=5)   # 二級
        self._scan()

        second = self._events('level_high') - first
        self.assertEqual((second.trigger_state, second.severity), ('lv2', 'warning'), '前提不成立')
        self.assertEqual(dispatched, [first.id, second.id], '警戒等級升高卻被限速壓住了')

    def test_deescalation_within_cooldown_is_suppressed(self):
        """一級推過之後，一小時內又越線但只到三級：等級沒升高，不再外送。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)                                     # 一級
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [7.0, 7.0, 7.0], step_min=5)   # 三級
        self._scan()

        self.assertEqual(dispatched, [first.id], '等級降低還外送了一次')

    def test_undelivered_dispatch_does_not_start_cooldown(self):
        """外送沒有任何通道送達（被上限略過、沒通道、送失敗）就不算送過，下一次越線照送。"""
        dispatched = self._capture_dispatch(delivered=0)
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)
        self.assertFalse(first.alert_notified_at, '沒送達卻記了外送時間')
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [12.0, 12.0, 12.0], step_min=5)
        self._scan()

        self.assertEqual(len(dispatched), 2, '上一則沒送達，這次卻被限速壓住了')

    def test_future_notified_at_does_not_suppress(self):
        """外送時間被填成未來（人工亂填）不能讓這台設備永久靜音。"""
        dispatched = self._capture_dispatch()
        self.env['water.level.event'].create({
            'device_id': self.device.id, 'event_type': 'level_high', 'severity': 'critical',
            'trigger_state': 'lv1', 'state': 'closed', 'start_ts': fields.Datetime.now(),
            'alert_notified_at': fields.Datetime.now() + timedelta(days=365)})

        event = self._open_breach(fields.Datetime.now() - timedelta(minutes=40))

        self.assertEqual(dispatched, [event.id], '一筆未來的外送時間讓設備靜音了')

    def test_pending_delivery_counts_as_sent(self):
        """排進重送（通道暫時斷線）也算外送過：不然斷線期間每一波都排一則，恢復後一次補送。"""
        channel = self.env['water.level.alert.channel'].create({
            'name': '測試通道', 'channel_type': 'webhook', 'audience': 'internal',
            'endpoint': 'https://example.invalid/pending'})
        dispatched = []

        def fake_dispatch(channels, dev, event, body):
            if dev == self.device:
                dispatched.append(event.id)
                self.env['water.level.alert.delivery'].create({
                    'channel_id': channel.id, 'event_id': event.id, 'device_id': dev.id,
                    'state': 'pending'})
            return 0                                                       # 當場沒送到

        self.patch(type(self.env['water.level.alert.channel']), '_dispatch', fake_dispatch)
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [12.0, 12.0, 12.0], step_min=5)
        self._scan()

        self.assertEqual(dispatched, [first.id], '待重送沒算外送過，又排了一則')

    def test_unsent_events_do_not_suppress(self):
        """沒外送過的事件（人工建立、設備回報）不能拿來壓住告警。"""
        dispatched = self._capture_dispatch()
        self.env['water.level.event'].create({
            'device_id': self.device.id, 'event_type': 'level_high', 'severity': 'critical',
            'trigger_state': 'lv1', 'state': 'closed',
            'start_ts': fields.Datetime.now() - timedelta(minutes=30),
            'end_ts': fields.Datetime.now() - timedelta(minutes=5)})

        event = self._open_breach(fields.Datetime.now() - timedelta(minutes=40))

        self.assertEqual(dispatched, [event.id], '一筆沒外送過的舊事件壓住了推播')

    def test_other_type_does_not_suppress(self):
        """低水位剛推過，不能壓住高水位（限速是每一類各自算）。"""
        dispatched = self._capture_dispatch()
        self.device.write({'alert_direction': 'both', 'low_level_1': 2.0})
        self.env['water.level.event'].create({
            'device_id': self.device.id, 'event_type': 'level_low', 'severity': 'critical',
            'trigger_state': 'low1', 'state': 'closed', 'start_ts': fields.Datetime.now(),
            'alert_notified_at': fields.Datetime.now()})

        event = self._open_breach(fields.Datetime.now() - timedelta(minutes=40))

        self.assertEqual(dispatched, [event.id], '別類事件的外送壓住了這一類')

    def test_other_device_does_not_suppress(self):
        """別台設備剛推過，不能壓住這一台（限速是每台設備各自算）。"""
        dispatched = self._capture_dispatch()
        other = self.env['water.level.device'].create({
            'name': '別台', 'site_id': self.site.id, 'device_uid': 'TEST-RECOVER-002'})
        self.env['water.level.event'].create({
            'device_id': other.id, 'event_type': 'level_high', 'severity': 'critical',
            'trigger_state': 'lv1', 'state': 'closed', 'start_ts': fields.Datetime.now(),
            'alert_notified_at': fields.Datetime.now()})

        event = self._open_breach(fields.Datetime.now() - timedelta(minutes=40))

        self.assertEqual(dispatched, [event.id], '別台設備的外送壓住了這一台')

    def test_cooldown_only_for_level_events(self):
        """斷線之類的狀態型告警不限速：一小時內第二次斷線照樣外送。"""
        dispatched = self._capture_dispatch()
        # 水位同時在一級：斷線事件的 trigger_state 也會是 lv1，「只管越線」這條才測得到
        self.device.last_value = 12.0
        self._set_last_seen(minutes_ago=45)
        self._scan()
        self._set_last_seen(minutes_ago=1)
        self._scan()
        self._set_last_seen(minutes_ago=45)
        self._scan()

        self.assertEqual(len(dispatched), 2, '第二次斷線被限速壓掉了')

    def test_station_notice_posted_even_when_suppressed(self):
        """限速只壓外送：旗艦方案的站內通知是憑據，照發。"""
        self._capture_dispatch()
        if 'service_level' in self.site._fields:
            self.site.service_level = 'flagship'      # 社區模組：設備等級跟著場域、且必須相等
        else:
            self.device.service_level = 'flagship'
        base = fields.Datetime.now() - timedelta(minutes=70)
        first = self._open_breach(base)
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()

        self._readings(base + timedelta(minutes=55), [12.0, 12.0, 12.0], step_min=5)
        self._scan()

        second = self._events('level_high') - first
        self.assertFalse(second.alert_notified_at, '前提不成立：這筆應該被限速壓掉')
        comment = self.env.ref('mail.mt_comment')
        self.assertTrue(second.message_ids.filtered(lambda m: m.subtype_id == comment),
                        '限速把站內通知也壓掉了')

    def test_new_breach_after_cooldown_dispatches_again(self):
        """這次修改的目的：恢復超過一小時後再淹一次，要開新事件、再推播一次。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=300)
        first = self._open_breach(base)
        first.alert_notified_at = fields.Datetime.now() - timedelta(minutes=290)
        self._readings(base + timedelta(minutes=30), [3.0, 3.0, 3.0])
        self._scan()
        self.assertEqual(first.state, 'closed')

        second = self._open_breach(base + timedelta(minutes=200))

        self.assertNotEqual(second, first)
        self.assertEqual(dispatched, [first.id, second.id], '恢復很久之後再越線沒有推播')

    def test_device_event_without_uid_gets_one(self):
        """設備回報的事件沒帶 uid 也要補一個：event_uid 空白是「掃描開的事件」的記號。"""
        event = self.env['water.level.event'].record_from_device(self.device, {
            'type': 'level_high', 'severity': 'critical',
            'start_ts': fields.Datetime.now() - timedelta(minutes=10)})

        self.assertTrue(event.event_uid, '沒帶 uid 的設備事件會被當成掃描事件')

    def test_clock_skewed_device_still_alerts_immediately(self):
        """設備把台灣時間當 UTC 送（每筆快 8 小時）：越線告警照樣當場發，不能延後。"""
        dispatched = self._capture_dispatch()
        self._readings(fields.Datetime.now() + timedelta(hours=8), [12.0, 12.0, 12.0])

        self._scan()

        event = self._events('level_high')
        self.assertEqual(len(event), 1, '時鐘快的設備沒有開越線事件')
        self.assertEqual(dispatched, event.ids)

    def test_future_breach_batch_does_not_loop(self):
        """時鐘亂跳送進一串未來時間的超標讀值：事件可以卡著，但不能每輪開了又關、反覆外送。"""
        dispatched = self._capture_dispatch()
        base = fields.Datetime.now() - timedelta(minutes=120)
        self._open_breach(base)
        self._readings(fields.Datetime.now() + timedelta(days=2), [12.0, 12.0, 12.0], step_min=1)
        # 之後真正的讀值時間都比那串未來讀值早，算補送：設備的最新水位卡在那筆未來的超標值。
        # 恢復判斷若跟開事件看的讀值不一致，會先關掉、下一輪又開新的
        for _round in range(5):
            self._readings(fields.Datetime.now() - timedelta(minutes=15 - _round * 3), [3.0],
                           step_min=1, update_last=False)
            self._scan()

        self.assertEqual(len(self._events('level_high')), 1, '開了又關、又開新事件')

    def test_far_future_reading_closes_without_error(self):
        """時鐘錯成 9999 年的讀值：保全區段的終點會超出日期上限，不能因此出錯（事件照樣結束）。"""
        base = fields.Datetime.now() - timedelta(minutes=120)
        event = self._open_breach(base)
        far = fields.Datetime.to_datetime('9999-12-31 23:50:00')
        self._readings(far, [3.0, 3.0, 3.0], step_min=1)

        self._scan()

        self.assertEqual(event.state, 'closed', '9999 年的讀值讓結束事件出錯了')

    def test_one_device_failure_does_not_stop_others(self):
        """一台監測站處理時出錯，只略過它；其他監測站照樣告警。"""
        other = self.env['water.level.device'].create({
            'name': '別台', 'site_id': self.site.id, 'device_uid': 'TEST-RECOVER-003',
            'offline_after_min': 30})
        other.last_seen = fields.Datetime.now() - timedelta(minutes=45)
        monitor_class = type(self.monitor)
        original = monitor_class._detect

        def broken_detect(monitor, device):
            if device == self.device:
                # 資料庫層的錯誤：沒有 savepoint 的話整個交易進入 aborted，後面的設備一起失敗
                monitor.env.cr.execute('SELECT 1/0')
            return original(monitor, device)

        self.patch(monitor_class, '_detect', broken_detect)
        with mute_logger('odoo.addons.water_level_core.models.water_level_monitor', 'odoo.sql_db'):
            self.monitor._cron_alert_scan()

        self.assertTrue(self.env['water.level.event'].search(
            [('device_id', '=', other.id), ('event_type', '=', 'offline')]),
            '一台出錯讓整支掃描停了')

    def test_level_event_direction_matches_readings(self):
        """level_state 說「高」（例如被一筆舊值或未來值卡住）但讀值其實是低水位：不能開高水位事件。"""
        self.device.write({'alert_direction': 'both', 'low_level_1': 2.0})
        self._readings(fields.Datetime.now() - timedelta(minutes=30), [1.0, 1.0, 1.0])
        self.device.write({'last_value': 12.0})                 # level_state 變成 lv1
        self.assertEqual(self.device.level_state, 'lv1', '前提不成立')

        self._scan()

        self.assertFalse(self._events('level_high'), '低水位讀值撐開了高水位事件')

    def test_open_device_event_does_not_block_scan(self):
        """設備端回報的越線事件一直開著，掃描照樣要開自己的事件（才會推播）。"""
        self.env['water.level.event'].create({
            'device_id': self.device.id, 'event_uid': 'DEV-EVT-2', 'event_type': 'level_high',
            'severity': 'warning', 'start_ts': fields.Datetime.now() - timedelta(minutes=300)})

        self._readings(fields.Datetime.now() - timedelta(minutes=30), [12.0, 12.0, 12.0])
        self._scan()

        scan_events = self._events('level_high').filtered(lambda e: not e.event_uid)
        self.assertEqual(len(scan_events), 1, '設備端的事件擋住了掃描告警')
