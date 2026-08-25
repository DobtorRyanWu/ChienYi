# -*- coding: utf-8 -*-
"""水位資料來源（pull）。

2026-08-25 確認資料流向是「對方寫資料庫、我們去撈」，不是設備打進來。
但**介面型態還沒定**（可能打網址、可能直連資料庫），而且對方明說
「你依據那些關鍵字處理就好」——所以這個模型的重點只有兩件事：

1. **來源型態可換**：http_json / postgres / file_json 三種走同一個介面，
   之後換 TimescaleDB 也只是換一筆設定，不用改程式。
2. **欄位對應可設定**：對方的欄位叫什麼名字都行，在這裡對過去就好。

三種 adapter 最後都回傳同一種格式，丟進既有的 `water.level.device.ingest_readings()`：
寫入、去重、基準高程換算、狀態機、缺口關閉全部沿用，不重寫。

時區只在 `_parse_ts()` 轉一次。誰都不准在別的地方 + timedelta(hours=8)。
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# 每次往回多撈多久（分鐘）。對方補寫舊資料、我們自己漏掉一輪，都靠這個接住。
DEFAULT_OVERLAP_MINUTES = 60
# 單次撈取的筆數上限，防呆
DEFAULT_MAX_ROWS = 5000
# HTTP 逾時。**不能省**：來源一 hang，cron worker 就被卡住，
# Odoo 的 worker 數量有限，卡兩個就開始有人反映系統很慢。
HTTP_TIMEOUT_SEC = 20
# 沒有水位線時，第一次往回撈多久
FIRST_PULL_DAYS = 7

# 資料庫識別字只允許這種形狀。識別字不能用參數綁定，只能自己驗——
# 讓人在欄位裡填任意字串再拼進 SQL，就是開一個注入孔。
IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
CM_PER_M = 100.0


class WaterLevelSource(models.Model):
    _name = 'water.level.source'
    _description = '水位資料來源'
    _order = 'name'

    name = fields.Char(string='來源名稱', required=True)
    active = fields.Boolean(string='啟用', default=True)
    source_type = fields.Selection(
        [('http_json', '打網址取 JSON'),
         ('postgres', '直連 PostgreSQL'),
         ('file_json', '讀本機 JSON 檔')],
        string='來源型態', required=True, default='http_json',
        help='介面型態未定，所以做成可換。換 TimescaleDB 時改這裡就好，不用改程式。')

    # === http_json ===
    endpoint = fields.Char(
        string='網址／檔案路徑',
        help='http_json 填網址；file_json 填本機路徑。')
    auth_type = fields.Selection(
        [('none', '不需認證'), ('bearer', 'Bearer Token'), ('basic', '帳號密碼')],
        string='認證方式', default='none')
    auth_token = fields.Char(string='Token', groups='base.group_system')
    auth_user = fields.Char(string='帳號')
    auth_password = fields.Char(string='密碼', groups='base.group_system')
    param_device = fields.Char(string='查詢參數：設備', default='device')
    param_since = fields.Char(string='查詢參數：起', default='since')
    param_until = fields.Char(string='查詢參數：迄', default='until')
    param_time_format = fields.Selection(
        [('iso', 'ISO 8601'), ('epoch', 'Unix 秒數')],
        string='查詢時間格式', default='iso')
    extra_params = fields.Char(
        string='額外查詢參數', help='形如 a=1&b=2，原樣附加在網址後。')

    # === postgres ===
    db_host = fields.Char(string='資料庫主機')
    db_port = fields.Integer(string='連接埠', default=5432)
    db_name = fields.Char(string='資料庫名')
    db_user = fields.Char(string='資料庫帳號')
    db_password = fields.Char(string='資料庫密碼', groups='base.group_system')
    db_table = fields.Char(string='資料表名')

    # === 欄位對應（對方說「依據那些關鍵字處理」，這裡就是那些關鍵字）===
    records_path = fields.Char(
        string='資料陣列位置',
        help='JSON 裡陣列的路徑，例如 data.readings。留空代表最外層就是陣列。')
    key_timestamp = fields.Char(string='關鍵字：時間', required=True, default='timestamp')
    key_value = fields.Char(string='關鍵字：水位值', required=True, default='value')
    key_device = fields.Char(string='關鍵字：設備', default='device_id')
    key_seq = fields.Char(
        string='關鍵字：流水號',
        help='留空代表來源沒有流水號——缺號偵測會自動退回「時間模式」。')
    key_hash = fields.Char(
        string='關鍵字：雜湊',
        help='留空代表來源不簽章——鏈只能由我們入庫時補算，'
             '報表會標示成「伺服器代算」。')

    # === 數值與時間的解讀 ===
    value_unit = fields.Selection(
        [('m', '公尺'), ('cm', '公分')], string='數值單位',
        default='m', required=True)
    ts_timezone = fields.Char(
        string='來源時區', default='UTC',
        help='來源時間戳沒有帶時區標記時，用這個解讀。'
             '填錯的後果是整批資料位移，而且寫入不會報錯。')

    # === 撈取行為 ===
    overlap_minutes = fields.Integer(
        string='回頭重撈(分鐘)', default=DEFAULT_OVERLAP_MINUTES)
    max_rows_per_pull = fields.Integer(
        string='單次筆數上限', default=DEFAULT_MAX_ROWS)

    # === 狀態 ===
    last_sync_ts = fields.Datetime(string='已同步到', readonly=True)
    last_pull_at = fields.Datetime(string='最後執行時間', readonly=True)
    sync_state = fields.Selection(
        [('ok', '正常'), ('error', '失敗'), ('never', '尚未執行')],
        string='同步狀態', default='never', readonly=True)
    last_error = fields.Char(string='最後錯誤', readonly=True)

    device_ids = fields.One2many(
        'water.level.device', 'source_id', string='供應的監測站')
    device_count = fields.Integer(string='設備數', compute='_compute_device_count')

    def _compute_device_count(self):
        for source in self:
            source.device_count = len(source.device_ids)

    @api.constrains('source_type', 'endpoint', 'db_host', 'db_table')
    def _check_connection_fields(self):
        for source in self:
            if source.source_type in ('http_json', 'file_json') and not source.endpoint:
                raise ValidationError(_('「%s」需要填網址或檔案路徑。', source.name))
            if source.source_type == 'postgres' and not (source.db_host and source.db_table):
                raise ValidationError(_('「%s」需要填資料庫主機與資料表名。', source.name))

    @api.constrains('db_table', 'key_timestamp', 'key_value', 'key_device', 'key_seq')
    def _check_identifiers(self):
        """postgres 模式下這些名字會被拼進 SQL，形狀必須乾淨。"""
        for source in self:
            if source.source_type != 'postgres':
                continue
            for label, value in [('資料表', source.db_table),
                                 ('時間欄位', source.key_timestamp),
                                 ('水位欄位', source.key_value),
                                 ('設備欄位', source.key_device),
                                 ('流水號欄位', source.key_seq)]:
                if value and not IDENT_RE.match(value):
                    raise ValidationError(_(
                        '%(label)s「%(value)s」不是合法的資料庫識別字'
                        '（只允許英數與底線，且不以數字開頭）。',
                        label=label, value=value))

    # ==================== 取得資料 ====================

    def fetch_rows(self, device, since, until):
        """回傳統一格式：[{'ts': naive UTC, 'value': float(公尺), 'seq_no': int|None, 'hash': str|None}]"""
        self.ensure_one()
        raw_rows = {
            'http_json': self._fetch_http_json,
            'file_json': self._fetch_file_json,
            'postgres': self._fetch_postgres,
        }[self.source_type](device, since, until)
        return [row for row in (self._normalize(raw) for raw in raw_rows) if row]

    def _fetch_http_json(self, device, since, until):
        import requests

        params = {}
        if self.param_device and device.remote_key:
            params[self.param_device] = device.remote_key
        if self.param_since:
            params[self.param_since] = self._format_query_time(since)
        if self.param_until:
            params[self.param_until] = self._format_query_time(until)
        for pair in (self.extra_params or '').split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key.strip()] = value.strip()

        headers = {}
        auth = None
        if self.auth_type == 'bearer' and self.sudo().auth_token:
            headers['Authorization'] = 'Bearer %s' % self.sudo().auth_token
        elif self.auth_type == 'basic':
            auth = (self.auth_user or '', self.sudo().auth_password or '')

        response = requests.get(self.endpoint, params=params, headers=headers,
                                auth=auth, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        return self._extract_records(response.json())

    def _fetch_file_json(self, device, since, until):
        """讀本機檔案。最便宜的一種，也是測試用的假來源。

        檔案裡通常是整包資料，時間範圍在這裡自己過濾——
        不能假設對方會幫我們切好。
        """
        with open(self.endpoint, encoding='utf-8') as handle:
            payload = json.load(handle)
        return self._extract_records(payload)

    def _fetch_postgres(self, device, since, until):
        """直連對方的 PostgreSQL。

        SQL 由我們用欄位對應表組，不讓人在欄位裡填整段 SQL——
        識別字已由 constrains 驗過形狀，值一律走參數綁定。
        """
        import psycopg2

        columns = [self.key_timestamp, self.key_value]
        if self.key_seq:
            columns.append(self.key_seq)
        if self.key_hash and IDENT_RE.match(self.key_hash):
            columns.append(self.key_hash)

        where = ['%s >= %%s' % self.key_timestamp, '%s < %%s' % self.key_timestamp]
        args = [since, until]
        if self.key_device and device.remote_key:
            where.insert(0, '%s = %%s' % self.key_device)
            args.insert(0, device.remote_key)

        sql = 'SELECT %s FROM %s WHERE %s ORDER BY %s LIMIT %%s' % (
            ', '.join(columns), self.db_table, ' AND '.join(where), self.key_timestamp)
        args.append(self.max_rows_per_pull or DEFAULT_MAX_ROWS)

        conn = psycopg2.connect(
            host=self.db_host, port=self.db_port or 5432, dbname=self.db_name,
            user=self.db_user, password=self.sudo().db_password,
            connect_timeout=HTTP_TIMEOUT_SEC)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, args)
                rows = cursor.fetchall()
        finally:
            conn.close()

        return [dict(zip(columns, row)) for row in rows]

    # ==================== 正規化 ====================

    def _extract_records(self, payload):
        """把 JSON 裡的資料陣列挖出來。records_path 例如 data.readings。"""
        node = payload
        for part in (self.records_path or '').split('.'):
            if not part:
                continue
            if not isinstance(node, dict) or part not in node:
                raise UserError(_(
                    '在來源資料裡找不到路徑「%(path)s」的「%(part)s」。'
                    '請確認「資料陣列位置」設定與實際回傳結構一致。',
                    path=self.records_path, part=part))
            node = node[part]
        if not isinstance(node, list):
            raise UserError(_('來源資料不是陣列，請檢查「資料陣列位置」設定。'))
        return node

    def _normalize(self, raw):
        """一筆來源資料 → 我們的格式。缺必要欄位就跳過該筆並記 log，不要整批炸掉。"""
        if not isinstance(raw, dict):
            return None
        if self.key_timestamp not in raw or self.key_value not in raw:
            _logger.warning('來源 %s：略過缺少必要欄位的一筆資料 %s', self.name, str(raw)[:120])
            return None
        try:
            row = {
                'ts': self._parse_ts(raw[self.key_timestamp]),
                'value': self._parse_value(raw[self.key_value]),
            }
        except (TypeError, ValueError) as exc:
            _logger.warning('來源 %s：一筆資料轉型失敗（%s）%s', self.name, exc, str(raw)[:120])
            return None
        if self.key_seq and raw.get(self.key_seq) is not None:
            try:
                row['seq_no'] = int(raw[self.key_seq])
            except (TypeError, ValueError):
                pass
        if self.key_hash and raw.get(self.key_hash):
            row['hash'] = str(raw[self.key_hash])
        return row

    def _parse_value(self, value):
        """單位換算只在這裡做一次。"""
        number = float(value)
        return number / CM_PER_M if self.value_unit == 'cm' else number

    def _parse_ts(self, value):
        """來源時間 → naive UTC。時區換算只在這裡做一次。

        三種來源寫法都吃：datetime 物件（postgres 回傳的）、Unix 秒數、ISO 8601 字串。
        字串沒帶時區標記時，用來源設定的時區解讀——這就是「來源時區」那個欄位存在的理由。
        """
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))

        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)

        tz_name = (self.ts_timezone or 'UTC').strip()
        if tz_name.upper() == 'UTC':
            return parsed
        import pytz
        return pytz.timezone(tz_name).localize(parsed).astimezone(
            pytz.UTC).replace(tzinfo=None)

    def _format_query_time(self, moment):
        if self.param_time_format == 'epoch':
            return int(moment.replace(tzinfo=timezone.utc).timestamp())
        return moment.strftime('%Y-%m-%dT%H:%M:%SZ')

    # ==================== 撈取 ====================

    def action_pull_now(self):
        """後台按鈕：立刻撈一次。設定完想馬上知道對不對的時候用。"""
        self.pull()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('撈取完成'),
                'message': _('狀態：%(state)s %(err)s',
                             state=dict(self._fields['sync_state'].selection)[self.sync_state],
                             err=self.last_error or ''),
                'type': 'success' if self.sync_state == 'ok' else 'warning',
            },
        }

    def pull(self):
        """逐一設備撈取。一台失敗不拖累其他台。"""
        now = fields.Datetime.now()
        for source in self:
            total_accepted = total_dup = 0
            errors = []
            for device in source.device_ids.filtered('active'):
                try:
                    since = source._window_start(device)
                    rows = source.fetch_rows(device, since, now)
                    if rows:
                        result = device.ingest_readings(rows)
                        total_accepted += result['accepted']
                        total_dup += result['duplicated']
                except Exception as exc:      # noqa: BLE001 —— 一台的問題不該讓整批停擺
                    errors.append('%s: %s' % (device.name, exc))
                    _logger.warning('水位來源 %s 撈取 %s 失敗：%s',
                                    source.name, device.name, exc)
                # 一台一個交易：第二台掛掉，第一台的資料要留下來
                source.env.cr.commit()

            source.write({
                'last_pull_at': now,
                'last_sync_ts': now if not errors else source.last_sync_ts,
                'sync_state': 'error' if errors else 'ok',
                'last_error': ('；'.join(errors))[:500] if errors else False,
            })
            source.env.cr.commit()
            _logger.info('水位來源 %s：收 %s 筆、重複 %s 筆、失敗 %s 台',
                         source.name, total_accepted, total_dup, len(errors))

    def _window_start(self, device):
        """這次要從什麼時候開始撈。

        一律往回多撈 overlap_minutes：對方補寫舊資料、我們自己漏掉一輪，都靠它接住。
        重疊的部分由 (device_id, ts) 唯一鍵擋掉，不會產生重複。
        """
        self.ensure_one()
        if self.last_sync_ts:
            return self.last_sync_ts - timedelta(minutes=self.overlap_minutes or 0)
        if device.last_seen:
            return device.last_seen - timedelta(minutes=self.overlap_minutes or 0)
        return fields.Datetime.now() - timedelta(days=FIRST_PULL_DAYS)

    @api.model
    def _cron_pull(self):
        self.search([('active', '=', True)]).pull()
