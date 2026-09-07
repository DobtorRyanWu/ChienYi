# -*- coding: utf-8 -*-
"""水位監測站主檔。

兩個設計決定，改動前先看這裡：

1. 警戒分級依經濟部水利署河川水位警戒，由輕到重是 三級 → 二級 → 一級
   （三級＝預估 2 小時內到達高灘地；二級＝預估 5 小時內到達計畫洪水位／堤頂；
   一級＝預估 2 小時內到達計畫洪水位／堤頂）。三個門檻都可留空，代表該站沒訂那一級。

2. 「水位等級」(level_state) 是 stored compute，只跟 last_value 與門檻有關，是純函數，
   不會過期。「斷線」(is_offline) 依賴當下時間，**故意不落地**——落地的時間相關狀態
   會出現「資料庫寫著正常、其實三小時沒訊號」的假狀態，且要靠 cron 才救得回來。
"""

import hashlib
import hmac
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# 預設斷線判定門檻（分鐘）。平時採樣多為 10 分鐘一筆，取兩個週期多一點當預設。
DEFAULT_OFFLINE_MINUTES = 30

# 上報金鑰長度（bytes，token_urlsafe 會轉成約 1.3 倍長度的字串）
API_KEY_BYTES = 32

# 經緯度合法範圍
LATITUDE_LIMIT = 90.0
LONGITUDE_LIMIT = 180.0

# 設備時鐘與伺服器差多少秒視為異常（斷網期間靠設備 RTC 打時間戳，飄掉就無法舉證）
CLOCK_DRIFT_ALERT_SEC = 60

# 服務等級（對應 DM 的三種等級）
LEVEL_BASIC = 'basic'
LEVEL_ADVANCED = 'advanced'
LEVEL_FLAGSHIP = 'flagship'
# 等級的高低次序，用來判斷「有沒有含某個等級以上的功能」
SERVICE_LEVEL_RANK = {LEVEL_BASIC: 1, LEVEL_ADVANCED: 2, LEVEL_FLAGSHIP: 3}


class WaterLevelDevice(models.Model):
    _name = 'water.level.device'
    _description = '水位監測站'
    _inherit = ['mail.thread']
    _order = 'project_id, seq, id'

    name = fields.Char(string='站名', required=True, tracking=True)
    site_id = fields.Many2one(
        'water.level.site', string='監測場域',
        required=True, ondelete='restrict', index=True, tracking=True)
    # ⚠️ ondelete 從 cascade 改成 restrict：cascade 會讓「刪工程案件」在資料庫層
    #    連坐刪光該案所有水位紀錄，而且完全不報錯，直接繞過 unlink() 的保護。
    #    這套系統對客戶承諾「依法保存兩年」，這條路徑必須堵死。
    # ⚠️ 這是實體欄位不是 related：改成 related store 會讓 reading.project_id
    #    （也是 stored related）跟著級聯重算上千萬列，而且 ingest 的原生 SQL
    #    明寫了這個欄位。值由 site 帶入，一致性靠下面的 constrains 保證。
    project_id = fields.Many2one(
        'project.project', string='工程案件',
        ondelete='restrict', index=True, tracking=True,
        help='由監測場域帶入。社區場域的設備此欄為空。')
    tank_id = fields.Many2one(
        'water.level.tank', string='蓄水池',
        ondelete='set null', index=True,
        help='社區場域用：這台設備裝在哪一個蓄水池。工程測站留空。')
    seq = fields.Integer(
        string='上下游序', default=10,
        help='數字小的在上游。前台站台列依此排序，看得出水從哪邊來。')
    map_label = fields.Char(
        string='地圖標籤', size=4,
        help='前台地圖上這個站要顯示的短代號（例如 A1）。'
             '留空就顯示「上下游序」——那是數字，對看畫面的人通常沒有意義。'
             '標記圖示只有 26×26 像素，所以最多四個字。')
    active = fields.Boolean(string='啟用', default=True)
    is_demo = fields.Boolean(
        string='示範資料', default=False, copy=False, index=True, tracking=True,
        help='示範資料：這台的讀數不是真實量測值，而是系統依歷史樣本合成的。打勾只是標示，不影響任何排程與稽核——**不要**改用 active=False 當標記，那會讓資料悄悄脫離稽核卻仍留在庫裡。')
    demo_baseline_device_id = fields.Many2one(
        'water.level.device', string='示範基線借用自',
        ondelete='set null', copy=False,
        help='這台沒有自己的歷史時，向哪一台借水文形狀（同一條河的鄰近測站）。'
             '斷面高程差請填在「基準高程」——合成器內部全程使用被借那台的值域，'
             '高程差只在寫入時加一次。留空代表用自己的歷史。')
    demo_profile = fields.Text(
        string='示範資料統計輪廓', copy=False,
        help='JSON：這台歷史序列的 p_zero／sigma／min／max，供示範資料合成器產生擬真讀數。'
             '由匯入腳本算一次寫入，之後不再變動。')

    # === 資料來源（pull 模式）===
    # 設備自己打進來（push）時這兩欄留空；由我們去對方資料庫撈時才需要。
    # 兩種模式並存：同一台設備不會同時用兩種，但整個系統要能同時服務兩種客戶。
    source_id = fields.Many2one(
        'water.level.source', string='資料來源',
        ondelete='restrict', index=True,
        help='留空代表這台設備自己把資料打進來（push）。')
    remote_key = fields.Char(
        string='來源端識別值',
        help='這台設備在對方系統裡的識別值，對應來源設定的「關鍵字：設備」。')

    device_uid = fields.Char(
        string='設備碼', required=True, index=True, copy=False, tracking=True,
        help='機器上報時放在 X-Device-Uid 標頭的識別碼，全庫唯一。')

    # === 位置 ===
    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))

    # === 水位換算與警戒 ===
    datum_elevation = fields.Float(
        string='基準高程(m)', digits=(10, 3),
        help='感測器量到的是壓力或距離，不是絕對高程。上報值加上本欄才是水位高程。')
    alert_direction = fields.Selection(
        [('high', '高水位（漲水危險）'),
         ('low', '低水位（缺水危險）'),
         ('both', '高低都要')],
        string='警戒方向', default='high', required=True,
        help='工程河川看漲水、社區蓄水池看缺水。預設 high，工程端行為與 v1 相同。')

    # 高水位三級（經濟部水利署河川水位警戒，數字越小越嚴重）
    level_3 = fields.Float(string='三級警戒水位(m)', digits=(10, 3))
    level_2 = fields.Float(string='二級警戒水位(m)', digits=(10, 3))
    level_1 = fields.Float(string='一級警戒水位(m)', digits=(10, 3))

    # 低水位三級（缺水，數字越小越嚴重：low_1 最低最嚴重）
    low_level_3 = fields.Float(string='低水位注意(m)', digits=(10, 3))
    low_level_2 = fields.Float(string='低水位警戒(m)', digits=(10, 3))
    low_level_1 = fields.Float(string='嚴重缺水水位(m)', digits=(10, 3))

    expected_interval_min = fields.Integer(
        string='期望取樣間隔(分鐘)', default=1,
        help='這台設備多久應該有一筆。來源沒有流水號時，缺號偵測靠這把尺——'
             '沉默超過這個間隔的數倍就視為缺口。DM 對社區客戶的規格是每分鐘一筆。')

    offline_after_min = fields.Integer(
        string='斷線判定(分鐘)', default=DEFAULT_OFFLINE_MINUTES,
        help='超過這個時間沒收到新資料就視為斷線。')

    # === 最新狀態 ===
    last_value = fields.Float(string='最新水位(m)', digits=(10, 3), readonly=True)
    last_seen = fields.Datetime(string='最後上報時間', readonly=True, index=True)

    level_state = fields.Selection(
        [('normal', '正常'),
         ('low3', '低水位注意'),
         ('low2', '低水位警戒'),
         ('low1', '嚴重缺水'),
         ('lv3', '三級警戒'),
         ('lv2', '二級警戒'),
         ('lv1', '一級警戒')],
        string='水位等級', default='normal',
        compute='_compute_level_state', store=True, tracking=True)
    is_offline = fields.Boolean(
        string='斷線', compute='_compute_is_offline',
        help='依最後上報時間與斷線判定門檻即時計算，不落地。')

    # === 服務等級（DM 三種等級，一台一個價，所以放在設備不放場域）===
    service_level = fields.Selection(
        [(LEVEL_BASIC, '基本｜合規記錄'),
         (LEVEL_ADVANCED, '進階｜事件保全'),
         (LEVEL_FLAGSHIP, '旗艦｜即時告警與韌性')],
        string='服務等級', default=LEVEL_BASIC, required=True, tracking=True)

    # ⚠️ 這三個是**商業開關，不是安全邊界**。不得拿它們去省掉完整性檢查——
    #    客戶沒買進階不代表可以讓他的資料被竄改而不留痕跡。
    feature_event_capture = fields.Boolean(
        string='含事件保全', compute='_compute_features')
    feature_hash_chain = fields.Boolean(
        string='含雜湊鏈驗證', compute='_compute_features')
    feature_realtime_alert = fields.Boolean(
        string='含即時告警', compute='_compute_features')

    # === 序號與雜湊鏈游標（明細在 reading，這裡只放鏈尾，省得每次查表）===
    last_seq_no = fields.Integer(string='最後序號', readonly=True, copy=False)
    last_chain_hash = fields.Char(string='鏈尾雜湊', readonly=True, copy=False)
    chain_verified_seq = fields.Integer(
        string='已驗證到序號', readonly=True, copy=False,
        help='雜湊鏈驗證的進度游標。每日 cron 只驗這之後的增量。')
    chain_hash_origin = fields.Selection(
        [('device', '設備端計算'),
         ('server', '伺服器代算')],
        string='雜湊來源', default='device',
        help='伺服器代算的鏈只證明資料庫內部一致，不能證明來源未被竄改。報表必須誠實標示。')

    # === 現場韌性狀態（旗艦等級的賣點，由設備隨上報帶回來）===
    power_source = fields.Selection(
        [('mains', '市電'), ('ups', '不斷電系統'), ('battery', '電池')],
        string='電源', readonly=True)
    on_backup_power = fields.Boolean(string='使用備援電力', readonly=True)
    battery_percent = fields.Float(string='電池電量(%)', digits=(5, 1), readonly=True)
    comm_type = fields.Char(string='通訊方式', readonly=True)
    comm_path = fields.Selection(
        [('primary', '主線路'), ('backup', '備援線路')],
        string='目前線路', readonly=True)
    signal_dbm = fields.Integer(string='訊號強度(dBm)', readonly=True)
    firmware_version = fields.Char(string='韌體版本', readonly=True)
    model_version = fields.Char(string='辨識模型版本', readonly=True)
    firmware_target_version = fields.Char(
        string='指定韌體版本',
        help='宣告式更新：Odoo 只宣告要哪一版，設備自己去取。Odoo 不存也不推二進位。')
    model_target_version = fields.Char(string='指定模型版本')
    local_buffer_count = fields.Integer(
        string='設備本地待送筆數', readonly=True,
        help='斷網期間堆在設備上還沒送出來的筆數。')
    clock_drift_sec = fields.Float(
        string='時鐘偏移(秒)', digits=(10, 1), readonly=True)
    last_health_ts = fields.Datetime(string='最後健康回報', readonly=True)

    # 後台地圖用。leaflet_map view 只吃 Binary 影像當標記，不能用 CSS 上色，
    # 所以顏色要在後端畫成圖（見 water_level_marker.py）。
    marker_icon = fields.Binary(
        string='地圖標記', compute='_compute_marker_icon')
    # ⚠️ leaflet_map（OCA web_view_leaflet_map）是為 res.partner 寫的，controller 會
    #    **無條件** search_read 這個欄位名（res.partner 的 date_localization 來自
    #    base_geolocalize）。模型沒有它就直接 ValueError、地圖一個標記都畫不出來。
    #    這裡的用途只有一個：讓標記圖的 /web/image 快取失效。
    date_localization = fields.Datetime(
        string='圖資更新時間', compute='_compute_date_localization')

    reading_ids = fields.One2many(
        'water.level.reading', 'device_id', string='水位紀錄')
    reading_count = fields.Integer(
        string='紀錄筆數', compute='_compute_reading_count')

    # === 上報金鑰（只存雜湊，明文只在產生當下顯示一次）===
    api_key_hash = fields.Char(string='上報金鑰雜湊', readonly=True, copy=False)
    has_api_key = fields.Boolean(
        string='已設定上報金鑰', compute='_compute_has_api_key')

    _sql_constraints = [
        ('device_uid_uniq', 'unique(device_uid)', '設備碼已存在，請換一個。'),
    ]

    # ==================== Compute ====================

    @api.depends('service_level')
    def _compute_features(self):
        for device in self:
            rank = SERVICE_LEVEL_RANK.get(device.service_level, 1)
            device.feature_event_capture = rank >= SERVICE_LEVEL_RANK[LEVEL_ADVANCED]
            device.feature_hash_chain = rank >= SERVICE_LEVEL_RANK[LEVEL_ADVANCED]
            device.feature_realtime_alert = rank >= SERVICE_LEVEL_RANK[LEVEL_FLAGSHIP]

    @api.depends('last_value', 'alert_direction',
                 'level_1', 'level_2', 'level_3',
                 'low_level_1', 'low_level_2', 'low_level_3')
    def _compute_level_state(self):
        """水位等級：由重到輕比對，未訂該級（0）視為沒有這條線。

        高水位與低水位分開判斷，由 alert_direction 決定要看哪一邊。
        門檻順序由 constrains 保證（低三級 ≤ 高三級），所以兩邊不會同時成立。
        """
        for device in self:
            value = device.last_value
            state = 'normal'
            if device.alert_direction in ('high', 'both'):
                if device.level_1 and value >= device.level_1:
                    state = 'lv1'
                elif device.level_2 and value >= device.level_2:
                    state = 'lv2'
                elif device.level_3 and value >= device.level_3:
                    state = 'lv3'
            if state == 'normal' and device.alert_direction in ('low', 'both'):
                if device.low_level_1 and value <= device.low_level_1:
                    state = 'low1'
                elif device.low_level_2 and value <= device.low_level_2:
                    state = 'low2'
                elif device.low_level_3 and value <= device.low_level_3:
                    state = 'low3'
            device.level_state = state

    # 這個 compute 依賴「現在幾點」，本來就不能 store。但 depends 還是要寫：
    # 少了它，同一個交易裡改完 last_seen 之後讀 is_offline 會拿到快取的舊值
    # （每個 HTTP request 是新的 env 所以前台看起來正常，但批次程式與測試會中招）。
    @api.depends('last_seen', 'offline_after_min')
    def _compute_is_offline(self):
        now = fields.Datetime.now()
        for device in self:
            if not device.last_seen:
                device.is_offline = True
                continue
            limit_min = device.offline_after_min or DEFAULT_OFFLINE_MINUTES
            elapsed_min = (now - device.last_seen).total_seconds() / 60.0
            device.is_offline = elapsed_min > limit_min

    def _compute_date_localization(self):
        for device in self:
            device.date_localization = device.write_date

    @api.depends('level_state', 'is_offline')
    def _compute_marker_icon(self):
        from .water_level_marker import color_for_level_state, marker_image
        for device in self:
            device.marker_icon = marker_image(
                color_for_level_state(device.level_state, device.is_offline))

    def _compute_reading_count(self):
        self.reading_count = 0
        saved = self.filtered(lambda d: isinstance(d.id, int))
        if not saved:
            return
        groups = self.env['water.level.reading']._read_group(
            [('device_id', 'in', saved.ids)],
            groupby=['device_id'],
            aggregates=['__count'],
        )
        counts = {device.id: count for device, count in groups}
        for device in saved:
            device.reading_count = counts.get(device.id, 0)

    def _compute_has_api_key(self):
        for device in self:
            device.has_api_key = bool(device.api_key_hash)

    # ==================== Constrains ====================

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        """比照 supervision_project 的慣例：0 視為未填，放行。"""
        for device in self:
            if device.latitude and not -LATITUDE_LIMIT <= device.latitude <= LATITUDE_LIMIT:
                raise ValidationError(_('緯度必須介於 -90 到 90 之間。'))
            if device.longitude and not -LONGITUDE_LIMIT <= device.longitude <= LONGITUDE_LIMIT:
                raise ValidationError(_('經度必須介於 -180 到 180 之間。'))

    @api.constrains('site_id', 'project_id')
    def _check_site_project_consistency(self):
        """設備的 project_id 必須與場域一致；社區場域的設備不得有 project_id。"""
        for device in self:
            expected = device.site_id.project_id
            if device.project_id != expected:
                raise ValidationError(_(
                    '設備「%(name)s」的工程案件與場域「%(site)s」不一致。'
                    '這個欄位由場域帶入，不要手動改。',
                    name=device.name, site=device.site_id.name))

    @api.constrains('site_id', 'tank_id')
    def _check_tank_site(self):
        for device in self:
            if device.tank_id and device.tank_id.site_id != device.site_id:
                raise ValidationError(_(
                    '設備「%(name)s」的蓄水池不屬於場域「%(site)s」。',
                    name=device.name, site=device.site_id.name))

    @api.onchange('site_id')
    def _onchange_site_id(self):
        self.project_id = self.site_id.project_id
        if self.tank_id and self.tank_id.site_id != self.site_id:
            self.tank_id = False

    @api.model_create_multi
    def create(self, vals_list):
        """沒帶 project_id 就從場域補上，帶錯的由 constrains 擋下。"""
        sites = self.env['water.level.site'].browse([
            vals.get('site_id') for vals in vals_list if vals.get('site_id')])
        by_id = {site.id: site for site in sites}
        for vals in vals_list:
            site = by_id.get(vals.get('site_id'))
            if site and 'project_id' not in vals:
                vals['project_id'] = site.project_id.id or False
        return super().create(vals_list)

    @api.constrains('level_1', 'level_2', 'level_3',
                    'low_level_1', 'low_level_2', 'low_level_3')
    def _check_alert_levels(self):
        """由低到高：嚴重缺水 ≤ 低水位警戒 ≤ 低水位注意 ≤ 三級 ≤ 二級 ≤ 一級。

        留空（0）的那級不參與比較。低水位那三級的嚴重度方向與高水位相反
        （low_1 最低最嚴重），但在數線上仍然是由小到大排列。
        """
        for device in self:
            ordered = [
                (device.low_level_1, '嚴重缺水'),
                (device.low_level_2, '低水位警戒'),
                (device.low_level_3, '低水位注意'),
                (device.level_3, '三級'),
                (device.level_2, '二級'),
                (device.level_1, '一級'),
            ]
            filled = [(value, label) for value, label in ordered if value]
            for (low, low_label), (high, high_label) in zip(filled, filled[1:]):
                if low > high:
                    raise ValidationError(_(
                        '%(low)s水位不可高於%(high)s水位。'
                        '由低到高的正確順序是：嚴重缺水 → 低水位警戒 → 低水位注意 → 三級 → 二級 → 一級。',
                        low=low_label, high=high_label))

    # ==================== 雜湊鏈 ====================

    @staticmethod
    def chain_hash(device_uid, seq_no, ts, raw_value, prev_hash):
        """計算一筆讀值的鏈雜湊。**這是與設備端的契約，改一個字元兩邊就對不上。**

        定義（UTF-8 編碼後取 sha256 十六進位小寫）：
            device_uid | seq_no | ts(ISO8601 UTC, 秒精度, 帶 Z) | raw_value(小數三位) | prev_hash

        三個容易對不上的地方，契約文件裡有 golden vector 可以對：
        * raw_value 一律格式化成三位小數（3.4 要寫成 "3.400"）
        * ts 用 "%Y-%m-%dT%H:%M:%SZ"，不帶毫秒、不帶時區偏移
        * 第一筆的 prev_hash 用空字串

        用的是**設備原始上報值**不是換算後的水位高程：設備算雜湊時還不知道
        我們的基準高程，而且基準高程之後可能修正——鏈不能因為我們改設定就全紅。
        """
        payload = '%s|%s|%s|%.3f|%s' % (
            device_uid or '',
            seq_no if seq_no is not None else '',
            ts.strftime('%Y-%m-%dT%H:%M:%SZ') if ts else '',
            raw_value or 0.0,
            prev_hash or '',
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    # ==================== 上報金鑰 ====================

    @staticmethod
    def _hash_api_key(raw_key):
        """金鑰是高熵隨機字串，用 sha256 即可，不需要慢雜湊（沒有字典攻擊面）。"""
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    def _verify_api_key(self, raw_key):
        """定時比對，避免以回應時間反推金鑰。"""
        self.ensure_one()
        if not self.api_key_hash or not raw_key:
            return False
        return hmac.compare_digest(self.api_key_hash, self._hash_api_key(raw_key))

    def action_generate_api_key(self):
        """產生新的上報金鑰。明文只在這一刻顯示，資料庫只留雜湊。"""
        self.ensure_one()
        raw_key = secrets.token_urlsafe(API_KEY_BYTES)
        self.sudo().write({'api_key_hash': self._hash_api_key(raw_key)})
        self.message_post(body=_('已重新產生上報金鑰（舊金鑰即刻失效）。'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('新的上報金鑰'),
                'message': _(
                    '設備碼 %(uid)s 的金鑰：%(key)s\n'
                    '請立刻複製，關掉這則通知就再也看不到（資料庫只存雜湊）。',
                    uid=self.device_uid, key=raw_key),
                'sticky': True,
                'type': 'warning',
            },
        }

    # ==================== 對外／對內共用的寫入路徑 ====================

    def ingest_readings(self, rows):
        """寫入一批水位讀值，回傳寫入結果與要請設備補送的區間。

        :param rows: [{'ts': datetime(naive UTC), 'value': float,
                       'seq_no': int|None, 'hash': str|None}, ...]
                     為相容 v1，也吃 [(ts, value), ...] 的 2-tuple。
        :return: {'accepted', 'duplicated', 'ack_seq', 'resend', 'backfill'}

        走原生 SQL 的理由：一次可能進幾百筆，ORM create() 每筆都要跑 constraint 與
        compute，慢一個量級。重複的 (device_id, ts) 與 (device_id, seq_no) 由唯一約束
        擋掉，不報錯只略過，所以設備補傳、重送同一批都是安全的。

        controller（push）與未來可能的 cron（pull）共用這支，換方向不用改寫入邏輯。
        """
        self.ensure_one()
        rows = self._normalize_rows(rows)
        if not rows:
            return {'accepted': 0, 'duplicated': 0, 'ack_seq': self.last_seq_no,
                    'resend': [], 'backfill': False}

        from psycopg2.extras import execute_values

        now = fields.Datetime.now()
        # 感測器送來的是量測值，加上基準高程才是水位高程。換算只在這裡做一次，
        # 之後從資料庫到畫面都不要再動它（警戒門檻也是用高程比較）。
        # raw_value 原樣保留：雜湊鏈是對原始值算的，而且基準高程日後可能修正。
        offset = self.datum_elevation or 0.0
        # 社區設備沒有工程案件。Odoo 的空 M2O 回傳 False，直接塞進 integer 欄位
        # 會變成 boolean 型別不符——要轉成 None 讓它進 NULL。
        project_id = self.project_id.id or None

        # 補送判斷以伺服器時間為準。設備可以在 payload 裡自稱是補送，但那只是提示——
        # 讓設備決定「這批要不要觸發告警」，等於把告警開關交給現場。
        newest_ts = max(row['ts'] for row in rows)
        backfill = bool(self.last_seen and newest_ts <= self.last_seen)

        self._fill_server_hashes(rows, backfill)
        values = [
            (self.id, project_id, row['ts'], row['value'] + offset, row['value'],
             row.get('seq_no'), row.get('hash'), now)
            for row in rows
        ]
        # project_id 是 stored related，走原生 SQL 不會自動填，所以這裡明寫進去。
        # fetch=True 不能省：execute_values 預設 page_size=100，會把一批拆成多個
        # INSERT 送出，這時 cr.rowcount 只剩最後一個 statement 的筆數（288 筆會回報 88）。
        inserted = execute_values(
            self.env.cr,
            """
            INSERT INTO water_level_reading
                (device_id, project_id, ts, value, raw_value, seq_no, chain_hash, received_at)
            VALUES %s
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            values,
            fetch=True,
        )
        accepted = len(inserted)
        self.env['water.level.reading'].invalidate_model()

        self._advance_cursor(rows, backfill)
        seqs = [row['seq_no'] for row in rows if row.get('seq_no') is not None]
        if seqs:
            self.env['water.level.gap']._close_filled(self, seqs)

        return {
            'accepted': accepted,
            'duplicated': len(rows) - accepted,
            'ack_seq': self.last_seq_no,
            'resend': self.env['water.level.gap']._pending_ranges(self),
            'backfill': backfill,
        }

    def _fill_server_hashes(self, rows, backfill):
        """設備算不出雜湊時由伺服器代算。

        代算的鏈只證明「資料庫內部一致」——有 DB 權限的人改完重算就好，
        所以站點會被標成 server 來源，報表上要誠實顯示這個差別（見 chain_hash_origin）。

        只在「序號與游標連續且不是補送」時才算：鏈上有洞還硬算，等於製造一條
        看起來完整、其實接不起來的鏈，比沒有更糟。
        """
        if self.chain_hash_origin != 'server' or backfill:
            return
        with_seq = sorted((row for row in rows if row.get('seq_no') is not None),
                          key=lambda row: row['seq_no'])
        if not with_seq or with_seq[0]['seq_no'] != (self.last_seq_no or 0) + 1:
            return
        prev = self.last_chain_hash or ''
        expected_seq = with_seq[0]['seq_no']
        for row in with_seq:
            if row['seq_no'] != expected_seq:
                break
            if not row.get('hash'):
                row['hash'] = self.chain_hash(
                    self.device_uid, row['seq_no'], row['ts'], row['value'], prev)
            prev = row['hash']
            expected_seq += 1

    @staticmethod
    def _normalize_rows(rows):
        """v1 的 (ts, value) 與 v2 的 dict 統一成 dict，讓舊呼叫端不用改。"""
        out = []
        for row in rows or []:
            if isinstance(row, dict):
                out.append(row)
            else:
                ts, value = row
                out.append({'ts': ts, 'value': value})
        return out

    def _advance_cursor(self, rows, backfill):
        """推進最新狀態與序號游標，並在向前跳號時開缺口。

        缺口只在「向前跳號」時開：本批最小序號 > 游標 + 1。補送批次帶的是舊序號，
        走不到這裡——否則每次補送都會再開一個新缺口，永遠收斂不了。
        """
        offset = self.datum_elevation or 0.0
        vals = {}
        newest = max(rows, key=lambda row: row['ts'])
        if not backfill:
            vals.update(last_seen=newest['ts'], last_value=newest['value'] + offset)

        seqs = sorted(row['seq_no'] for row in rows if row.get('seq_no') is not None)
        if seqs:
            cursor = self.last_seq_no or 0
            if seqs[0] > cursor + 1 and cursor:
                self.env['water.level.gap']._open_gap(self, cursor + 1, seqs[0] - 1)
            # 本批自己內部的跳號也要開缺口
            for prev, nxt in zip(seqs, seqs[1:]):
                if nxt > prev + 1:
                    self.env['water.level.gap']._open_gap(self, prev + 1, nxt - 1)
            if seqs[-1] > cursor:
                vals['last_seq_no'] = seqs[-1]
                last_row = max((row for row in rows if row.get('seq_no') == seqs[-1]),
                               key=lambda row: row['ts'])
                if last_row.get('hash'):
                    vals['last_chain_hash'] = last_row['hash']
        if vals:
            self.sudo().write(vals)

    def update_health(self, health):
        """設備隨上報帶回來的韌性狀態。欄位缺就不動，不要用預設值覆蓋掉既有資訊。"""
        self.ensure_one()
        if not health:
            return
        mapping = {
            'power_source': 'power_source',
            'on_backup_power': 'on_backup_power',
            'battery_percent': 'battery_percent',
            'comm_type': 'comm_type',
            'comm_path': 'comm_path',
            'signal_dbm': 'signal_dbm',
            'firmware_version': 'firmware_version',
            'model_version': 'model_version',
            'local_buffer_count': 'local_buffer_count',
            'clock_drift_sec': 'clock_drift_sec',
        }
        vals = {field: health[key] for key, field in mapping.items() if key in health}
        if vals:
            vals['last_health_ts'] = fields.Datetime.now()
            self.sudo().write(vals)

    def desired_versions(self):
        """宣告式更新：只告訴設備我們要哪一版，設備自己去取。Odoo 不存也不推二進位。"""
        self.ensure_one()
        desired = {}
        if self.firmware_target_version:
            desired['firmware'] = self.firmware_target_version
        if self.model_target_version:
            desired['model'] = self.model_target_version
        return desired

    def action_view_readings(self):
        """站點表單上的「水位紀錄」按鈕。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s 的水位紀錄', self.name),
            'res_model': 'water.level.reading',
            'view_mode': 'graph,list',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id, 'search_default_last_day': 1},
        }

    def unlink(self):
        for device in self:
            if device.reading_count:
                raise UserError(_(
                    '「%(name)s」已有 %(count)s 筆水位紀錄，不能刪除。'
                    '要停用請取消「啟用」，紀錄要保留給監造報告舉證用。',
                    name=device.name, count=device.reading_count))
        return super().unlink()
