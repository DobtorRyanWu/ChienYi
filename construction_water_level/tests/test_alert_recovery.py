# -*- coding: utf-8 -*-
"""狀態型告警恢復後要自己收掉。

**這個測試在防什麼**

2026-09-08 生產站（jt.qytech）出的事：撈取排程漏跑兩輪，設備 31 分鐘沒上報，
掃描正確地開了一筆 critical 斷線事件。兩小時後資料恢復、`is_offline` 變回 False，
**但事件掛了 21 小時沒關**——因為當時的 `_cron_alert_scan` 只有開事件的路徑，
整個檔案裡沒有任何 close / end_ts 的處理。畫面上就一直掛著「斷線」。

所以第一個測試就是那句話的可執行版本：**異常條件消失後，狀態型事件必須自己結束**。
把 `_cron_alert_scan` 裡的 `_close_recovered` 那一行拿掉，這個測試就會紅。

**為什麼水位越線要有反例測試**

「恢復就自動關」不能一路套到底。水位退下去不代表那場淹水沒發生過——
災情事件要有人複核過才算結束，那是 `action_close` 人工按的意義。
第二個測試把這條界線釘住，避免日後有人「順手」把 level_high 也加進
RECOVERABLE_TYPES，讓災情紀錄在無人看過的情況下自己消失。
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestWaterLevelAlertRecovery(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 社區型場域有 constrains 要求填擁有者，不是可省的欄位
        cls.owner = cls.env['res.partner'].create({'name': '測試管委會（恢復）'})
        cls.site = cls.env['water.level.site'].create({
            'name': '測試社區（恢復）',
            'site_type': 'community',
            'owner_partner_id': cls.owner.id,
        })
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

    def _set_last_seen(self, minutes_ago):
        self.device.write({
            'last_seen': fields.Datetime.now() - timedelta(minutes=minutes_ago),
        })

    def test_offline_event_closes_when_data_returns(self):
        """斷線 → 開事件；資料回來 → 同一筆事件自己關掉。"""
        # ① 超過門檻沒上報：掃描應該開一筆 critical 斷線事件
        self._set_last_seen(minutes_ago=45)
        self.assertTrue(self.device.is_offline, '前提不成立：45 分鐘沒上報應該算斷線')
        self.monitor._cron_alert_scan()

        events = self._events('offline')
        self.assertEqual(len(events), 1, '斷線後應該恰好開一筆事件')
        self.assertEqual(events.state, 'open')
        self.assertFalse(events.end_ts, '剛開的事件不該有結束時間')

        # ② 再掃一次不該重複開（_open_event 的既有行為，一併釘住）
        self.monitor._cron_alert_scan()
        self.assertEqual(len(self._events('offline')), 1, '同一個異常不該開第二筆')

        # ③ 資料回來了：同一筆事件應該被關掉，而不是留著讓人以為還在斷線
        self._set_last_seen(minutes_ago=1)
        self.assertFalse(self.device.is_offline, '前提不成立：1 分鐘前上報不該算斷線')
        self.monitor._cron_alert_scan()

        events = self._events('offline')
        self.assertEqual(len(events), 1, '關閉不該產生新事件')
        self.assertEqual(events.state, 'closed', '斷線恢復後事件必須自己結束')
        self.assertTrue(events.end_ts, '關閉的事件要有結束時間')

    def test_level_breach_event_stays_open(self):
        """水位越線的事件不自動關——災情要有人複核過才算結束。"""
        # 去抖動要連續 3 筆都超標，所以照實建 3 筆讀值
        base = fields.Datetime.now() - timedelta(minutes=30)
        for index in range(3):
            self.env['water.level.reading'].create({
                'device_id': self.device.id,
                'ts': base + timedelta(minutes=index * 10),
                'value': 12.0,                      # 高於 level_1 = 10.0
            })
        self.device.write({'last_value': 12.0, 'last_seen': fields.Datetime.now()})
        self.assertEqual(self.device.level_state, 'lv1', '前提不成立：12.0 應該是一級警戒')

        self.monitor._cron_alert_scan()
        events = self._events('level_high')
        self.assertEqual(len(events), 1, '連續三筆超標應該開一筆越線事件')
        self.assertEqual(events.state, 'open')

        # 水位退回正常後再掃：事件應該**仍然開著**，等人複核
        self.device.write({'last_value': 3.0, 'last_seen': fields.Datetime.now()})
        self.assertEqual(self.device.level_state, 'normal', '前提不成立：3.0 應該回到正常')
        self.monitor._cron_alert_scan()

        events = self._events('level_high')
        self.assertEqual(events.state, 'open',
                         '水位越線是災情事件，退水了也不該自動結案')
