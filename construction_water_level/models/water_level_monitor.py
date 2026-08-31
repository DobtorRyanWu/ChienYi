# -*- coding: utf-8 -*-
"""定期監控與稽核：告警、保存期間、日摘要、封存提醒。

放在獨立的 AbstractModel 而不是塞進 device：這些是排程作業不是設備的行為，
混在一起之後沒人分得清哪些方法是 cron 在用的。

DM 對應：
* 旗艦「異常即時告警推播」→ _cron_alert_scan
* 基本「每分鐘一筆、保存兩年」→ _cron_retention_audit（產出可對客戶舉證的稽核紀錄）
* 效能（不是清理）→ _cron_daily_rollup
* 保存到期 → _cron_archive_notice（只通知，不刪）
"""

import logging
from datetime import timedelta

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


class WaterLevelMonitor(models.AbstractModel):
    _name = 'water.level.monitor'
    _description = '水位監控排程作業'

    # ==================== 告警 ====================

    @api.model
    def _cron_alert_scan(self):
        """掃描異常並開事件；旗艦等級才推播。

        四種異常：水位越線、斷線、失電、時鐘偏移。
        水位越線要去抖動——連續 ALERT_DEBOUNCE_COUNT 筆都超標才算，
        單筆突波是感測器雜訊不是災情。
        """
        Event = self.env['water.level.event']
        devices = self.env['water.level.device'].search([('active', '=', True)])
        opened = 0
        for device in devices:
            for event_type, severity, note in self._detect(device):
                event = self._open_event(device, event_type, severity, note)
                if event:
                    opened += 1
                    if device.feature_realtime_alert:
                        self._notify(device, event)
        _logger.info('水位告警掃描：開了 %s 個事件', opened)
        return opened

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

        if device.level_state in ALERT_STATES and self._debounced(device):
            is_low = device.level_state.startswith('low')
            found.append((
                'level_low' if is_low else 'level_high',
                'critical' if device.level_state in ('lv1', 'low1') else 'warning',
                _('連續 %(n)s 筆處於「%(state)s」，最新水位 %(value).3f m。',
                  n=ALERT_DEBOUNCE_COUNT,
                  state=dict(device._fields['level_state'].selection)[device.level_state],
                  value=device.last_value)))
        return found

    def _debounced(self, device):
        """最近 N 筆是不是都超標。只看讀值本身，不看 level_state——
        level_state 只有最新一筆的狀態，看它等於沒有去抖動。"""
        readings = self.env['water.level.reading'].search(
            [('device_id', '=', device.id)], order='ts desc',
            limit=ALERT_DEBOUNCE_COUNT)
        if len(readings) < ALERT_DEBOUNCE_COUNT:
            return False
        for reading in readings:
            if not self._value_breaches(device, reading.value):
                return False
        return True

    @staticmethod
    def _value_breaches(device, value):
        if device.alert_direction in ('high', 'both'):
            for threshold in (device.level_1, device.level_2, device.level_3):
                if threshold and value >= threshold:
                    return True
        if device.alert_direction in ('low', 'both'):
            for threshold in (device.low_level_1, device.low_level_2, device.low_level_3):
                if threshold and value <= threshold:
                    return True
        return False

    def _open_event(self, device, event_type, severity, note):
        """同一台設備的同一種異常，已經有進行中的事件就不重複開。"""
        Event = self.env['water.level.event']
        existing = Event.search([
            ('device_id', '=', device.id),
            ('event_type', '=', event_type),
            ('state', '=', 'open'),
        ], limit=1)
        if existing:
            return False
        return Event.create({
            'device_id': device.id,
            'tank_id': device.tank_id.id or False,
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

        站外：交給 water.level.alert.channel 外送（Webhook，日後可加 LINE／簡訊）。
        站內這條是憑據、站外那條才是「即時」——使用者不登入也收得到。
        外送整段包在 _dispatch 裡，壞掉的外部端點不會影響站內通知與告警掃描。
        """
        body = _('【%(site)s / %(device)s】%(type)s：%(note)s',
                 site=device.site_id.name, device=device.name,
                 type=dict(event._fields['event_type'].selection)[event.event_type],
                 note=event.note or '')
        event.message_post(body=body, subtype_xmlid='mail.mt_comment')
        device.message_post(body=body, subtype_xmlid='mail.mt_comment')
        self.env['water.level.alert.channel']._dispatch(device, event, body)

    # ==================== 保存稽核 ====================

    @api.model
    def _cron_retention_audit(self):
        """每台設備產一筆保存稽核：最舊資料多久、昨天實收幾筆 vs 期望幾筆。

        期望筆數依**每台自己的**取樣間隔換算：社區設備每分鐘一筆 → 1440，
        河川測站每 10 分鐘一筆 → 144。這支的產出就是對客戶舉證
        「我們有守住約定的取樣密度、保存兩年」的憑據。
        """
        Integrity = self.env['water.level.integrity.check']
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        start = fields.Datetime.to_datetime('%s 00:00:00' % yesterday)
        end = start + timedelta(days=1)
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
    def _cron_daily_rollup(self):
        """產昨天的日摘要。**只新增，原始 reading 永不因此被刪。**"""
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        self.env.cr.execute("""
            INSERT INTO water_level_reading_daily
                (device_id, day, min_value, max_value, avg_value, reading_count)
            SELECT device_id, %s, min(value), max(value), avg(value), count(*)
              FROM water_level_reading
             WHERE ts >= %s AND ts < %s
             GROUP BY device_id
            ON CONFLICT (device_id, day) DO UPDATE
               SET min_value = EXCLUDED.min_value,
                   max_value = EXCLUDED.max_value,
                   avg_value = EXCLUDED.avg_value,
                   reading_count = EXCLUDED.reading_count
        """, (yesterday, '%s 00:00:00' % yesterday, '%s 00:00:00' % (yesterday + timedelta(days=1))))
        _logger.info('水位日摘要：%s 完成', yesterday)

    # ==================== 封存提醒（只提醒，不刪）====================

    @api.model
    def _cron_archive_notice(self):
        """超過保存期只發通知，實際封存要人按按鈕。

        自動刪掉超過兩年的資料聽起來很合理，但那是把「合約到期」與「可以刪」
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
