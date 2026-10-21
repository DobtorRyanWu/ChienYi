# -*- coding: utf-8 -*-
"""定期監控與稽核：告警、保存期間、日摘要、封存提醒。

放在獨立的 AbstractModel 而不是塞進 device：這些是排程作業不是設備的行為，
混在一起之後沒人分得清哪些方法是 cron 在用的。

DM 對應：
* 旗艦「異常即時告警推播」→ _cron_alert_scan
* 基本「每分鐘一筆、保存三年」→ _cron_retention_audit（產出可對客戶舉證的稽核紀錄）
* 效能（不是清理）→ _cron_daily_rollup（台灣日；每天重算最近幾天，接住晚到的讀值）
* 保存到期 → _cron_archive_notice（只通知，不刪）
"""

import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# 連續幾筆超標才告警。不做去抖動，感測器雜訊會讓手機在半夜變鬧鐘。
ALERT_DEBOUNCE_COUNT = 3
# 一天有幾分鐘。除以設備的「期望取樣間隔」才是這台一天應該有幾筆——
# 寫死 1440 等於假設全世界的設備都是每分鐘一筆，10 分鐘取樣的河川測站
# 會被判成只收到一成資料，稽核清單天天紅一片。
MINUTES_PER_DAY = 1440
# 實收低於期望的幾成就算不合格
RETENTION_OK_RATIO = 0.95
# 保存期到期前幾天開始提醒
ARCHIVE_NOTICE_LEAD_DAYS = 30

ALERT_STATES = ('lv1', 'lv2', 'lv3', 'low1', 'low2', 'low3')
# 狀態型告警：異常條件消失就該自己收掉，因為它們描述的是「當下的狀態」。
RECOVERABLE_TYPES = ('offline', 'power_loss', 'comm_switch')
# 水位越線：2026-10-21 起也自動結束（使用者定案，社區與工程都套用），但要連續
# ALERT_DEBOUNCE_COUNT 筆回到正常才算——與開事件同一個去抖動門檻。
# 原本刻意不自動結束（「災情要有人複核」），結果第一次越線後事件一直開著，
# 之後再淹幾次都不會開新事件、也不會推播。「結束」不等於「複核」：複核仍是人按「已複核」。
LEVEL_TYPES = ('level_high', 'level_low')
# 越線告警的外送限速：同一台設備同一類越線，這麼久之內已經外送過、而且警戒等級沒有更高，
# 新事件就不外送（事件照開、照樣能簽收，站內通知照發）。少了它，水位在警戒線附近擺盪
# （蓄水池抽水循環、感潮河段）每幾分鐘就推一次，吃光通道的每小時上限——千溢內部通道收所有
# 客戶的告警，別台真正的告警會被略過——也吃光 LINE 每月額度。
# 只壓外送、不把新事件併回舊事件：併回去要處理簽收、保全區段一路延長、結束時間的可信度
LEVEL_NOTIFY_COOLDOWN_MINUTES = 60
# 警戒等級高低（一級最嚴重）。限速期間等級升高照推：三級→二級在嚴重度欄位上都是「警告」，分不出來
LEVEL_RANK = {'lv3': 1, 'lv2': 2, 'lv1': 3, 'low3': 1, 'low2': 2, 'low1': 3}
# 未來時間的讀值（設備時鐘錯）開事件與判斷恢復都照算，兩邊一致：刻意不排除。
# 排除的話，把台灣時間當 UTC 送的設備（每筆快 8 小時）越線告警會延後 8 小時——淹水告警絕不能延後。
# 代價是時鐘亂跳到未來的那台，事件可能卡著不結束（跟 3.2.0 之前一樣，不會更差）。

# 日摘要用哪個時區切「一天」：系統只在台灣使用，場域上沒有時區欄位
ROLLUP_TZ = 'Asia/Taipei'
# 每天重算最近幾天：斷網續存、缺號補送的讀值可能晚好幾天才進來
ROLLUP_RECOMPUTE_DAYS = 7


class WaterLevelMonitor(models.AbstractModel):
    _name = 'water.level.monitor'
    _description = '水位監控排程作業'

    # ==================== 告警 ====================

    @api.model
    def _cron_alert_scan(self):
        """掃描異常並開事件，每個新事件都交給 _notify（推不推、推給誰由通道決定）。

        四種異常：水位越線、斷線、失電、時鐘偏移。
        水位越線要去抖動——連續 ALERT_DEBOUNCE_COUNT 筆都超標才算，
        單筆突波是感測器雜訊不是災情。
        """
        devices = self.env['water.level.device'].search([('active', '=', True)])
        opened = closed = 0
        for device in devices:
            # 每台各自一個 savepoint：一台的資料壞掉（例如時鐘錯成 9999 年）只退回它自己。
            # 少了它整支排程回滾——排在後面的設備從此不告警，排在前面的事件被回滾、外送卻已送出，
            # 每 5 分鐘重送一次
            # 先收已恢復的、最後才開新事件並外送：外送之後就沒有會出錯的步驟，
            # 不會發生「訊息已送出、這台的交易卻被退回、下一輪再送一次」
            try:
                with self.env.cr.savepoint():
                    detected = self._detect(device)
                    device_closed = self._close_recovered(device, {t for t, _sev, _n in detected})
                    device_opened = 0
                    for event_type, severity, note in detected:
                        event = self._open_event(device, event_type, severity, note)
                        if event:
                            device_opened += 1
                            self._notify(device, event)
                opened += device_opened
                closed += device_closed
            except Exception:
                _logger.exception('水位告警掃描：監測站 %s 處理失敗，已略過（其他監測站照常）',
                                  device.device_uid)
        _logger.info('水位告警掃描：開了 %s 個事件、關了 %s 個已恢復的', opened, closed)
        return opened

    def _level_notify_cooling(self, device, event):
        """這筆越線事件要不要先不外送：同一台設備同一類越線，LEVEL_NOTIFY_COOLDOWN_MINUTES 內
        已經外送過（有通道送達或排進重送；看 alert_notified_at，伺服器時間），而且當時的警戒等級不比這次低。

        看的是「外送過」，不是「上一筆什麼時候結束」：被限速壓掉、所有通道都略過、沒有通道收的
        事件都不算，所以擺盪再久每小時還是會送一次；設備端回報、人工建立的事件沒送過，壓不住告警。
        限速以事件為單位、不分通道：一個通道送到、另一個被上限略過，這一小時內兩個都不再送。
        送達時間在未來的（人工亂填）不算；等級不明的事件照送——拿不準就送。"""
        rank = LEVEL_RANK.get(event.trigger_state)
        if event.event_type not in LEVEL_TYPES or rank is None:
            return False
        now = fields.Datetime.now()
        sent = self.env['water.level.event'].search([
            ('device_id', '=', device.id),
            ('event_type', '=', event.event_type),
            ('alert_notified_at', '>=', now - timedelta(minutes=LEVEL_NOTIFY_COOLDOWN_MINUTES)),
            ('alert_notified_at', '<=', now),
        ])
        return any(LEVEL_RANK.get(sent_event.trigger_state, 0) >= rank for sent_event in sent)

    def _close_recovered(self, device, active_types):
        """異常消失後把事件收掉，回傳關掉幾個。

        留一筆 critical 掛在畫面上，看的人會以為現在還在斷線——實際案例：
        2026-09-08 生產站的撈取排程漏跑兩輪觸發斷線事件，資料兩小時後就恢復了，
        事件卻掛了 21 小時沒關，因為當時的掃描只開不關。

        `active_types` 是這一輪掃描仍然偵測到的異常種類，由呼叫端傳進來——
        不在裡面就代表條件已經消失。水位越線另外看讀值（見 _level_recovered_at）：
        「這一輪沒偵測到」只代表最近 3 筆不全超標，不代表已經連續 3 筆正常。
        """
        Event = self.env['water.level.event']
        stale = Event.search([
            ('device_id', '=', device.id),
            ('state', '=', 'open'),
            ('event_type', 'in', RECOVERABLE_TYPES),
        ]).filtered(lambda event: event.event_type not in active_types)
        if stale:
            stale.action_close()
        closed = len(stale)

        # 只收掃描自己開的事件：設備端回報的事件（有 event_uid）不替它決定結束時間
        for event in Event.search([
            ('device_id', '=', device.id),
            ('state', '=', 'open'),
            ('event_type', 'in', LEVEL_TYPES),
            ('event_uid', '=', False),
        ]):
            recovered_at = self._level_recovered_at(device, event)
            if recovered_at:
                # end_ts 先寫成「第一筆回到正常的讀值」，action_close 再依它延伸保全區段
                event.end_ts = recovered_at
                event.action_close()
                closed += 1
        return closed

    def _level_recovered_at(self, device, event):
        """越線事件已恢復就回傳「第一筆回到正常的讀值時間」，否則 False。

        恢復＝事件開始之後、最後一次超標之後，已經有連續 ALERT_DEBOUNCE_COUNT 筆讀值。
        「超標」與開事件的去抖動用同一條線（_breach_line），只看事件那個方向。

        **只採計事件開始之後的讀值**：start_ts 是開事件當下的伺服器時間，讀值時間來自設備。
        讀值晚到（補送、撈取延遲）或開事件後調高了門檻（「最後一次超標」退回去年的洪水），
        結束時間都會早於開始時間，保全區段跟著前後顛倒、事件報表的讀值是空的。
        """
        low = event.event_type == 'level_low'
        line = self._breach_line(device, low)
        # None 進 SQL 是 NULL，比較結果不成立＝這個方向沒有超標可言
        above = None if low else line
        below = line if low else None
        self.env.cr.execute("""
            SELECT ts FROM water_level_reading
             WHERE device_id = %(device)s
               AND ts > GREATEST(%(start)s, COALESCE((
                       SELECT max(ts) FROM water_level_reading
                        WHERE device_id = %(device)s
                          AND (value >= %(above)s OR value <= %(below)s)), %(start)s))
             ORDER BY ts LIMIT %(count)s
        """, {'device': device.id, 'start': event.start_ts,
              'above': above, 'below': below, 'count': ALERT_DEBOUNCE_COUNT})
        rows = self.env.cr.fetchall()
        if len(rows) < ALERT_DEBOUNCE_COUNT:
            return False
        return rows[0][0]

    def _detect(self, device):
        """回傳這台設備當下的異常清單 [(event_type, severity, note), ...]。"""
        found = []

        if device.is_offline and device.last_seen:
            found.append((
                'offline', 'critical',
                _('最後上報 %s，已超過斷線判定 %s 分鐘。')
                % (device.last_seen, device.offline_after_min)))

        if device.on_backup_power:
            found.append((
                'power_loss', 'critical',
                _('設備改用備援電力（電量 %.1f%%）。') % (device.battery_percent or 0.0)))

        if device.comm_path == 'backup':
            found.append((
                'comm_switch', 'warning', _('主線路不通，已切換備援線路。')))

        from .water_level_device import CLOCK_DRIFT_ALERT_SEC
        if abs(device.clock_drift_sec or 0.0) > CLOCK_DRIFT_ALERT_SEC:
            found.append((
                'clock_drift', 'warning',
                _('設備時鐘與伺服器差 %.1f 秒，斷網期間的時間戳可能不可靠。')
                % device.clock_drift_sec))

        is_low = (device.level_state or '').startswith('low')
        if device.level_state in ALERT_STATES and self._debounced(device, low=is_low):
            found.append((
                'level_low' if is_low else 'level_high',
                'critical' if device.level_state in ('lv1', 'low1') else 'warning',
                _('連續 %(n)s 筆處於「%(state)s」，最新水位 %(value).3f m。',
                  n=ALERT_DEBOUNCE_COUNT,
                  state=dict(device._fields['level_state'].selection)[device.level_state],
                  value=device.last_value)))
        return found

    def _debounced(self, device, low):
        """最近 N 筆是不是都在 `low` 那個方向超標。只看讀值本身，不看 level_state——
        level_state 只有最新一筆的狀態，看它等於沒有去抖動。

        方向與讀值範圍都跟判斷恢復（_level_recovered_at）一致：不一致的話，偵測說「還在超標」、
        恢復說「已經正常」，事件就每輪開了又關。"""
        line = self._breach_line(device, low)
        if line is None:
            return False
        readings = self.env['water.level.reading'].search(
            [('device_id', '=', device.id)], order='ts desc', limit=ALERT_DEBOUNCE_COUNT)
        if len(readings) < ALERT_DEBOUNCE_COUNT:
            return False
        return all((r.value <= line) if low else (r.value >= line) for r in readings)

    @staticmethod
    def _breach_line(device, low):
        """這個方向「超標」的那條線：有設定的門檻裡最寬的一條（高水位取最小、低水位取最大），
        任何一級被越過就一定越過它。這個方向沒在看、或一條門檻都沒設，回 None。"""
        if low:
            levels = (device.low_level_1, device.low_level_2, device.low_level_3)
            watching = device.alert_direction in ('low', 'both')
        else:
            levels = (device.level_1, device.level_2, device.level_3)
            watching = device.alert_direction in ('high', 'both')
        levels = [level for level in levels if level]       # 0 視為沒設，與 level_state 一致
        if not (watching and levels):
            return None
        return max(levels) if low else min(levels)

    def _open_event(self, device, event_type, severity, note):
        """同一台設備的同一種異常，已經有進行中的事件就不重複開。"""
        Event = self.env['water.level.event']
        domain = [
            ('device_id', '=', device.id),
            ('event_type', '=', event_type),
            ('state', '=', 'open'),
        ]
        if event_type in LEVEL_TYPES:
            # 設備端回報的越線事件（有 event_uid）就算一直開著，也不能擋住掃描告警
            domain.append(('event_uid', '=', False))
        if Event.search(domain, limit=1):
            return False
        return Event.create({
            'device_id': device.id,
            'event_type': event_type,
            'severity': severity,
            'start_ts': fields.Datetime.now(),
            'peak_value': device.last_value,
            'trigger_state': device.level_state,
            'note': note,
        })

    def _notify(self, device, event):
        """告警通知，兩條路一起走。

        站內：既有的 mail.thread —— 內部使用者進 inbox，
        前台使用者由既有的通知中心（鈴鐺）撈同一批訊息，不另造一套。

        站外：交給 water.level.alert.channel 外送（Webhook、Discord，社區模組加 LINE）。
        站內這條是憑據、站外那條才是「即時」——使用者不登入也收得到。
        外送整段包在 _dispatch 裡，壞掉的外部端點不會影響站內通知與告警掃描。

        站內通知只有旗艦方案才發（維持 2026-10-21 之前的行為）；外送一律進 _dispatch，
        由每個通道依「送給誰」判斷——千溢內部通道所有方案都收，客戶通道要旗艦。
        """
        body = _('【%(site)s / %(device)s】%(type)s：%(note)s',
                 site=device.site_id.name, device=device.name,
                 type=dict(event._fields['event_type'].selection)[event.event_type],
                 note=event.note or '')
        if device.feature_realtime_alert:
            event.message_post(body=body, subtype_xmlid='mail.mt_comment')
            device.message_post(body=body, subtype_xmlid='mail.mt_comment')
        # 限速只壓外送；站內通知是憑據，上面照發
        if self._level_notify_cooling(device, event):
            return
        # 有通道已送達或排進重送才記：被每小時上限略過、沒有通道、確定送不出去的不算，不啟動限速。
        # 待重送也要算——不算的話通道斷線期間每一波都排一則，恢復後一次補送
        delivered = self.env['water.level.alert.channel']._dispatch(device, event, body)
        if delivered or self.env['water.level.alert.delivery'].search_count(
                [('event_id', '=', event.id), ('state', 'in', ('sent', 'pending'))]):
            event.alert_notified_at = fields.Datetime.now()

    # ==================== 保存稽核 ====================

    @api.model
    def _cron_retention_audit(self, today=None):
        """每台設備產一筆保存稽核：最舊資料多久、昨天實收幾筆 vs 期望幾筆。

        期望筆數依**每台自己的**取樣間隔換算：社區設備每分鐘一筆 → 1440，
        河川測站每 10 分鐘一筆 → 144。這支的產出就是對客戶舉證
        「我們有守住約定的取樣密度、保存三年」的憑據。
        """
        Integrity = self.env['water.level.integrity.check']
        # 「昨天」是台灣的昨天，與日摘要同一套日界（`today` 給測試用）。舊寫法用 cron 使用者的時區
        # 取日期、再拿日期字串去比 UTC 的 ts，量到的其實是 UTC 那一天，標的卻是本地日期
        today = today or self._local_today()
        yesterday = today - timedelta(days=1)
        start = self._local_midnight_utc(yesterday)
        end = self._local_midnight_utc(today)
        for device in self.env['water.level.device'].search([('active', '=', True)]):
            self.env.cr.execute("""
                SELECT count(*), min(ts) FROM water_level_reading
                 WHERE device_id = %s AND ts >= %s AND ts < %s
            """, (device.id, start, end))
            day_count, _first = self.env.cr.fetchone()
            self.env.cr.execute(
                "SELECT min(ts) FROM water_level_reading WHERE device_id = %s", (device.id,))
            oldest = self.env.cr.fetchone()[0]

            expected = MINUTES_PER_DAY / (device.expected_interval_min or 1)
            ratio = day_count / expected
            result = 'ok' if ratio >= RETENTION_OK_RATIO else 'gap'
            Integrity.create({
                'check_type': 'retention',
                'device_id': device.id,
                'range_from_ts': start,
                'range_to_ts': end,
                'checked_count': day_count,
                'result': result,
                'note': _('%(day)s 實收 %(got)s 筆／期望 %(want)s 筆（%(pct).1f%%）；'
                          '最舊資料 %(oldest)s。',
                          day=yesterday, got=day_count, want=int(expected),
                          pct=ratio * 100, oldest=oldest or '無'),
            })

    # ==================== 日摘要（效能，不是清理）====================

    @api.model
    def _cron_daily_rollup(self, today=None):
        """重算最近 ROLLUP_RECOMPUTE_DAYS 天（台灣日，不含今天）的日摘要。

        **只重寫摘要，原始 reading 永不因此被刪。**
        `today` 給測試用；排程不帶，用台灣的今天。
        """
        today = today or self._local_today()
        first_day = today - timedelta(days=ROLLUP_RECOMPUTE_DAYS)
        # 先清這段再寫（同一個交易，別人看不到中間狀態）：某天的讀值若在維護視窗被刪光，摘要也要跟著消失
        self.env.cr.execute(
            "DELETE FROM water_level_reading_daily WHERE day >= %s AND day < %s", (first_day, today))
        rows = self._rollup_insert(self._local_midnight_utc(first_day), self._local_midnight_utc(today))
        _logger.info('水位日摘要：重算 %s 起到昨天（台灣日），寫入 %s 列', first_day, rows)

    @api.model
    def _rollup_all(self):
        """整個重算（台灣日）。2026-10-21 之前的日摘要是 UTC 日，日期標籤與內容都不對。
        升級（migrations/18.0.3.2.0）與接手舊資料的新裝（hooks.post_init_hook）用。

        每台設備只清「它現存最早一筆讀值的 UTC 日期」以後的摘要：舊摘要的日期標籤就是讀值的
        UTC 日期，所以這樣剛好涵蓋所有舊列；更早的摘要對應的讀值已依保存期清除，是僅存的歷史
        （換場域鎖靠它），不能跟著消失。未來時間的讀值（設備時鐘錯）不算，摘要只寫到今天。
        """
        self.env.cr.execute("""
            DELETE FROM water_level_reading_daily d
             USING (SELECT device_id, min(ts)::date AS first_day
                      FROM water_level_reading GROUP BY device_id) f
             WHERE d.device_id = f.device_id AND d.day >= f.first_day
        """)
        rows = self._rollup_insert(
            datetime.min, self._local_midnight_utc(self._local_today() + timedelta(days=1)))
        _logger.info('水位日摘要：全部重算（台灣日），寫入 %s 列', rows)

    def _rollup_insert(self, start, end):
        """把 [start, end)（UTC）的讀值依（設備, 台灣日）彙總寫進日摘要，回傳寫了幾列。"""
        self.env.cr.execute("""
            INSERT INTO water_level_reading_daily
                (device_id, day, min_value, max_value, avg_value, reading_count)
            SELECT device_id, (ts AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date AS local_day,
                   min(value), max(value), avg(value), count(*)
              FROM water_level_reading
             WHERE ts >= %(start)s AND ts < %(end)s
             GROUP BY device_id, local_day
            ON CONFLICT (device_id, day) DO UPDATE
               SET min_value = EXCLUDED.min_value,
                   max_value = EXCLUDED.max_value,
                   avg_value = EXCLUDED.avg_value,
                   reading_count = EXCLUDED.reading_count
        """, {'tz': ROLLUP_TZ, 'start': start, 'end': end})
        rows = self.env.cr.rowcount
        # raw SQL 改了表，ORM 快取裡的舊值要丟掉
        self.env['water.level.reading.daily'].invalidate_model()
        return rows

    def _local_today(self):
        return fields.Date.context_today(self.with_context(tz=ROLLUP_TZ))

    @staticmethod
    def _local_midnight_utc(day):
        """台灣某一天的 00:00，換成 UTC（不帶時區，與 ts 欄位同格式）。三支排程共用這一個日界。"""
        local = pytz.timezone(ROLLUP_TZ).localize(datetime.combine(day, time.min))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ==================== 封存提醒（只提醒，不刪）====================

    @api.model
    def _cron_archive_notice(self):
        """超過保存期只發通知，實際封存要人按按鈕。

        自動刪掉超過保存期的資料聽起來很合理，但那是把「合約到期」與「可以刪」
        劃上等號——客戶可能還在打官司。這支只講「可以評估封存了」。
        """
        for site in self.env['water.level.site'].search([('active', '=', True)]):
            cutoff = fields.Datetime.now() - timedelta(
                days=site.retention_days - ARCHIVE_NOTICE_LEAD_DAYS)
            self.env.cr.execute("""
                SELECT count(*) FROM water_level_reading r
                  JOIN water_level_device d ON d.id = r.device_id
                 WHERE d.site_id = %s AND r.ts < %s
            """, (site.id, cutoff))
            count = self.env.cr.fetchone()[0]
            if count:
                site.message_post(body=_(
                    '有 %(count)s 筆水位紀錄已接近或超過保存期（%(days)s 天）。'
                    '請依合約決定是否封存——系統不會自動刪除任何資料。',
                    count=count, days=site.retention_days))


class WaterLevelReadingDaily(models.Model):
    _name = 'water.level.reading.daily'
    _description = '水位日摘要'
    _order = 'day desc, device_id'
    _log_access = False

    device_id = fields.Many2one(
        'water.level.device', string='監測站',
        required=True, ondelete='cascade', index=True)
    day = fields.Date(string='日期', required=True, index=True)
    min_value = fields.Float(string='最低水位(m)', digits=(10, 3))
    max_value = fields.Float(string='最高水位(m)', digits=(10, 3), aggregator='max')
    avg_value = fields.Float(string='平均水位(m)', digits=(10, 3))
    reading_count = fields.Integer(string='筆數')

    _sql_constraints = [
        ('device_day_uniq', 'unique(device_id, day)', '同一天只會有一筆摘要。'),
    ]
