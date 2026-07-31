# -*- coding: utf-8 -*-

import logging
from io import BytesIO

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Pillow 是官方 odoo:18.0 image 內建（實測 10.2.0），不需額外安裝。
# 仍做保護性 import：缺了只是讀不到 EXIF，不該讓整個模組載不起來。
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None
    _logger.warning('Pillow 不可用，照片 EXIF GPS 解析功能停用')

# EXIF 的 GPS IFD 指標 tag（TIFF 標準 34853）。GPS IFD 內：
# 1=GPSLatitudeRef('N'/'S')、2=GPSLatitude(度,分,秒)、
# 3=GPSLongitudeRef('E'/'W')、4=GPSLongitude(度,分,秒)
EXIF_GPS_IFD_TAG = 0x8825
EXIF_GPS_LAT_REF, EXIF_GPS_LAT = 1, 2
EXIF_GPS_LNG_REF, EXIF_GPS_LNG = 3, 4

# 呼叫端「明確指定要繼承座標」時放進 context 的兩個鍵。
# 只有工程告示牌（同步端）與通報單照片（前台 controller）會帶；
# 其餘照片入口一律不帶 —— 見 _fallback_coordinates() 的說明。
CTX_FALLBACK_LAT = 'photo_fallback_latitude'
CTX_FALLBACK_LNG = 'photo_fallback_longitude'

# 反向級聯的遞迴防護旗標（**已無實際作用，僅保留避免外部 import 失敗**）。
#
# 照片資料表收斂前，supervision.photo 與兩張缺失照片行表互相持有 RESTRICT FK，
# 刪除時兩邊會互相呼叫對方的 unlink()，需要這個 context 旗標防止無限遞迴。
# 收斂後照片行表已不存在，沒有第二方可以互相呼叫，這個機制整個不需要了。
PHOTO_CASCADE_CTX = 'photo_cascade_in_progress'


class SupervisionPhoto(models.Model):
    """
    工程照片管理

    對應舊系統: image
    設計參考: document_knowledge 模組 ir.attachment 擴展

    功能特點:
    - 照片檔案存儲使用 ir.attachment
    - 支援 GPS 位置資訊記錄
    - 來源追蹤 (可關聯到日誌、檢查、缺失等)
    - 多標籤分類
    """
    _name = 'supervision.photo'
    _description = '工程照片'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'shot_at desc, id desc'

    # === 基本資訊 ===
    name = fields.Char(
        string='照片摘要',
        compute='_compute_name',
        store=True,
        tracking=True,
        help='自動從詳細說明或檔案名稱產生的簡短摘要')
    
    description = fields.Text(
        string='照片說明',
        help='詳細說明此照片的內容、拍攝目的、相關資訊等')

    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help='舊系統欄位: project')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        help='照片所屬工程的管理公司')

    # === 照片檔案 ===
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='照片檔案',
        required=True,
        ondelete='restrict',
        help='照片附件檔案')

    image = fields.Binary(
        string='預覽圖',
        related='attachment_id.datas',
        readonly=True,
        help='照片預覽')

    image_filename = fields.Char(
        string='檔案名稱',
        related='attachment_id.name',
        readonly=True)

    mimetype = fields.Char(
        string='檔案類型',
        related='attachment_id.mimetype',
        readonly=True)

    file_size = fields.Integer(
        string='檔案大小',
        related='attachment_id.file_size',
        readonly=True,
        help='檔案大小 (bytes)')

    extension = fields.Char(
        string='副檔名',
        compute='_compute_extension',
        store=True,
        help='舊系統欄位: extension')

    @api.depends('attachment_id.name')
    def _compute_extension(self):
        """計算副檔名"""
        for photo in self:
            if photo.attachment_id and photo.attachment_id.name:
                name = photo.attachment_id.name
                if '.' in name:
                    photo.extension = name.rsplit('.', 1)[-1].lower()
                else:
                    photo.extension = ''
            else:
                photo.extension = ''

    # === 拍攝資訊 (舊系統欄位) ===
    shot_at = fields.Datetime(
        string='拍攝日期',
        default=fields.Datetime.now,
        tracking=True,
        help='舊系統欄位: shotAt')

    shot_date = fields.Date(
        string='拍攝日期(日)',
        compute='_compute_shot_date',
        store=True,
        help='用於按日期分組查詢')

    @api.depends('shot_at')
    def _compute_shot_date(self):
        """計算拍攝日期 (僅日期部分)"""
        for photo in self:
            if photo.shot_at:
                photo.shot_date = photo.shot_at.date()
            else:
                photo.shot_date = False
    
    @api.depends('description', 'attachment_id.name')
    def _compute_name(self):
        """自動產生照片摘要"""
        for photo in self:
            if photo.description:
                # 從說明中擷取前50字作為摘要
                desc_text = photo.description.strip()
                if len(desc_text) > 50:
                    photo.name = desc_text[:50] + '...'
                else:
                    photo.name = desc_text
            elif photo.attachment_id and photo.attachment_id.name:
                # 如果沒有說明，使用檔案名稱
                photo.name = photo.attachment_id.name
            else:
                # 都沒有就用預設名稱
                photo.name = '未命名照片'

    # === 工程案件位置資訊 (唯讀) ===
    project_location = fields.Char(
        string='工程地點',
        related='project_id.location',
        store=True,
        readonly=True,
        help='此照片所屬工程案件的地點')

    project_latitude = fields.Float(
        string='工程緯度',
        related='project_id.latitude',
        store=True,
        readonly=True,
        digits=(10, 7),
        help='工程案件的GPS緯度座標')

    project_longitude = fields.Float(
        string='工程經度',
        related='project_id.longitude',
        store=True,
        readonly=True,
        digits=(10, 7),
        help='工程案件的GPS經度座標')

    # === 照片拍攝位置資訊 (舊系統欄位) ===
    gps_location = fields.Char(
        string='拍攝GPS位置',
        help='舊系統欄位: gpsLocation，格式: 緯度,經度\n此為照片實際拍攝位置，與工程案件位置可能不同')

    latitude = fields.Float(
        string='緯度',
        digits=(10, 7),
        compute='_compute_gps_coordinates',
        inverse='_inverse_gps_coordinates',
        store=True,
        help='GPS 緯度座標')

    longitude = fields.Float(
        string='經度',
        digits=(10, 7),
        compute='_compute_gps_coordinates',
        inverse='_inverse_gps_coordinates',
        store=True,
        help='GPS 經度座標')

    # === 來源掛載（照片資料表收斂）===
    # 過去照片散在 12 張表：2 張缺失照片行子模型 + 9 張 M2M 中間表 + 本表。
    # 現在收斂成本表一張，各業務模組在這裡加自己的 Many2one（加「欄」不是加
    # 「表」），業務模型端改用 One2many 指回來，因此不再需要「同步」這個概念。
    #
    # 注意：source_model / source_id 是舊的字串+整數假關聯，保留供既有查詢與
    # 前台篩選相容；新的來源判斷一律以各模組的 Many2one 為準。
    photo_stage = fields.Selection([
        ('before', '矯正及預防前'),
        ('during', '矯正及預防中'),
        ('after', '矯正及預防後'),
    ], string='照片階段', index=True,
       help='缺失改善專用：區分矯正前／中／後三階段。其他來源的照片留空。')

    signboard_project_id = fields.Many2one(
        'project.project',
        string='工程告示牌所屬工程',
        ondelete='cascade',
        index=True,
        help='這張照片是該工程的「工程告示牌」照片。\n'
             '與 project_id（所屬工程，每張照片都有）不同：後者是歸屬，'
             '本欄位是「身分」——只有告示牌照片會填。')

    gps_source = fields.Selection([
        ('input', '前台輸入'),
        ('exif', '照片 EXIF'),
        ('inherit', '沿用工程／通報單'),
    ], string='座標來源', readonly=True, index=True,
       help='座標是怎麼來的。\n'
            '前台輸入：定位鈕、手動填寫，或批次上傳頁的前端 EXIF 解析。\n'
            '照片 EXIF：伺服器端從照片檔案讀出的真實拍攝地點。\n'
            '沿用工程／通報單：照片本身沒有 GPS，改用工程案件或通報單的座標'
            '（僅工程告示牌與通報單照片會這樣做）——屬推定位置，不是實拍位置。')

    @api.depends('gps_location')
    def _compute_gps_coordinates(self):
        """從 GPS 位置字串解析緯度和經度"""
        for photo in self:
            if photo.gps_location:
                try:
                    parts = photo.gps_location.split(',')
                    if len(parts) == 2:
                        photo.latitude = float(parts[0].strip())
                        photo.longitude = float(parts[1].strip())
                    else:
                        photo.latitude = 0.0
                        photo.longitude = 0.0
                except (ValueError, AttributeError):
                    photo.latitude = 0.0
                    photo.longitude = 0.0
            else:
                photo.latitude = 0.0
                photo.longitude = 0.0

    def _inverse_gps_coordinates(self):
        """從緯度和經度組合 GPS 位置字串"""
        for photo in self:
            if photo.latitude or photo.longitude:
                photo.gps_location = f"{photo.latitude},{photo.longitude}"
            else:
                photo.gps_location = False

    # === 照片分類 ===
    # 舊欄位（保留向後相容，但新流程都使用 category_id）
    # 既有 A 標 58 張資料的值會在 migration 中遷移到 category_id
    category = fields.Selection([
        ('STL', '鋼筋'), ('CON', '混凝土'), ('FRM', '模板'),
        ('PIP', '管線'), ('ELC', '電氣'), ('DEF', '缺失'),
        ('EXC', '開挖'), ('BKF', '回填'), ('PAV', '鋪面'),
        ('DRN', '排水'), ('OTH', '其他'),
    ], string='材料分類 (舊)',
       help='舊版固定分類，已由 category_id 取代。保留供既有資料相容')

    category_id = fields.Many2one(
        'supervision.photo.category',
        string='材料分類',
        help='照片的材料/工項分類（可在後台 supervision.photo.category 自由維護）',
        ondelete='restrict',
        index=True,
    )

    construction_phase = fields.Selection([
        ('before', '施工前'),
        ('during', '施工中'),
        ('after', '施工後'),
        ('defect', '缺失'),
        ('acceptance', '驗收'),
    ], string='施工階段',
       help='照片對應的施工階段')

    location_code = fields.Char(
        string='位置編碼',
        help='照片拍攝位置的編碼（如樁號、座標代碼）')

    # === 來源追蹤 (舊系統欄位) ===
    source_model = fields.Selection([
        ('daily_log', '施工日誌'),
        ('inspection', '自主檢查'),
        ('defect', '缺失改善'),
        ('test', '檢試驗'),
        ('acceptance', '驗收'),
        ('notification', '通報單'),
        ('other', '其他'),
    ], string='來源分類',
       tracking=True,
       help='舊系統欄位: sourceModel')

    source_id = fields.Integer(
        string='來源記錄ID',
        index=True,
        help='舊系統欄位: source，關聯來源記錄的ID')

    source_ref = fields.Char(
        string='來源參照',
        compute='_compute_source_ref',
        help='來源記錄的參考說明')

    @api.depends('source_model', 'source_id')
    def _compute_source_ref(self):
        """計算來源參照說明"""
        source_labels = dict(self._fields['source_model'].selection)
        for photo in self:
            if photo.source_model and photo.source_id:
                label = source_labels.get(photo.source_model, photo.source_model)
                photo.source_ref = f"{label} #{photo.source_id}"
            else:
                photo.source_ref = False

    # === 標籤 (舊系統欄位: tags) ===
    tag_ids = fields.Many2many(
        'supervision.photo.tag',
        'supervision_photo_tag_rel',
        'photo_id',
        'tag_id',
        string='標籤',
        help='照片分類標籤')

    # === 上傳者資訊 ===
    creator_id = fields.Many2one(
        'res.users',
        string='上傳者',
        default=lambda self: self.env.uid,
        readonly=True,
        tracking=True,
        help='舊系統欄位: creator')

    creator_company_id = fields.Many2one(
        'res.company',
        string='上傳者公司',
        related='creator_id.company_id',
        store=True,
        help='上傳者所屬公司')

    upload_date = fields.Datetime(
        string='上傳時間',
        default=fields.Datetime.now,
        readonly=True,
        help='照片上傳系統時間')

    # === 其他資訊 ===
    location_description = fields.Char(
        string='拍攝地點說明',
        help='照片拍攝地點的文字說明')

    notes = fields.Text(
        string='備註',
        help='其他補充說明')

    active = fields.Boolean(
        string='啟用',
        default=True,
        help='取消勾選可歸檔此照片')

    # === 業務方法 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立照片記錄；若有 description，建立後自動打標籤。"""
        for vals in vals_list:
            # 確保上傳時間
            if 'upload_date' not in vals:
                vals['upload_date'] = fields.Datetime.now()
        records = super().create(vals_list)
        # 來源欄位正規化：掛在來源上（例如告示牌）卻沒指定所屬工程時自動補上，
        # 否則照片不會出現在該工程的照片清單，也拿不到工程座標當 fallback。
        records._normalize_source_fields()
        # 座標補完：EXIF → 呼叫端明確指定的繼承來源。放在 super() 之後才讀得到
        # attachment_id 的二進位，也才看得到 compute 算完的 latitude/longitude。
        records._resolve_missing_coordinates()
        # 自動打標籤（只對有 description 的）
        to_tag = records.filtered(lambda r: r.description)
        if to_tag:
            to_tag.action_auto_tag_from_description()
        return records

    # === 來源正規化 ===
    @api.model
    def _photo_source_field_map(self):
        """{來源模型名: 本模型上對應的 Many2one 欄位名}

        照片收斂後，上傳端要知道「這張照片該掛在哪個欄位」。各模組 _inherit
        本模型後 `super()` 再加自己的一條 —— 上游不必知道下游有哪些模型，
        模型改名時也會立刻在自己的模組裡爆掉，而不是靜默失效。

        `project.project` → `signboard_project_id`：把工程案件當「來源記錄」
        傳進上傳流程的，只有工程告示牌那一條路由。要注意這**不是**
        `project_id`（所屬工程，每張照片都有）—— 兩者語意不同，
        所以不能靠「comodel 是 project.project」自動推導，必須明寫。
        """
        return {'project.project': 'signboard_project_id'}

    def _photo_source_project(self):
        """從來源欄位推出這張照片該歸屬哪個工程案件，推不出來回空 recordset。

        各模組覆寫時務必先 `res = super()._photo_source_project()`、有值就回傳，
        否則後掛載的模組會蓋掉前面的判斷。
        """
        self.ensure_one()
        return self.signboard_project_id

    def _photo_source_model_code(self):
        """從來源欄位推出 source_model 的值（相容既有篩選與前台查詢）。"""
        self.ensure_one()
        return 'other' if self.signboard_project_id else False

    def _normalize_source_fields(self):
        """掛了來源卻沒填所屬工程 / 來源分類時，自動補齊。

        不覆蓋已有的值 —— 呼叫端明確指定的優先。
        """
        for photo in self:
            vals = {}
            if not photo.project_id:
                project = photo._photo_source_project()
                if project:
                    vals['project_id'] = project.id
            if not photo.source_model:
                code = photo._photo_source_model_code()
                if code:
                    vals['source_model'] = code
            if vals:
                photo.write(vals)

    # === 座標補完 ===
    def _resolve_missing_coordinates(self):
        """照片沒有座標時，依序嘗試補上；每一層都先驗範圍才寫。

        順位：
          1. 建立時就帶了座標（定位鈕／手填／前端 EXIF）→ 保留，只補記來源
          2. 伺服器端讀照片檔案的 EXIF GPS → 真實拍攝地點，對所有照片都適用
          3. 呼叫端以 context 明確指定的繼承座標 → 只有告示牌與通報單會帶
          4. 都沒有 → 留空（不猜）

        全程不 raise：EXIF 壞掉、檔案讀不到都只記 warning，
        絕不能讓照片因此建不出來。
        """
        for photo in self:
            try:
                if photo.latitude or photo.longitude:
                    if not photo.gps_source:
                        photo.gps_source = 'input'
                    continue

                coords, source = photo._exif_coordinates(), 'exif'
                if not coords:
                    coords, source = photo._fallback_coordinates(), 'inherit'
                if not coords:
                    continue

                lat, lng = coords
                # 寫 gps_location（源頭欄位）而非 latitude/longitude：後兩者是
                # compute+store，其 compute 在 gps_location 為空時會把值強制歸零。
                photo.write({
                    'gps_location': f'{lat},{lng}',
                    'gps_source': source,
                })
                _logger.info(
                    '照片座標補完 - Photo ID: %s, 來源: %s, 座標: %s,%s',
                    photo.id, source, lat, lng)
            except Exception as e:
                _logger.warning(
                    '照片座標補完失敗（略過，不影響照片建立）- Photo ID: %s, Error: %s',
                    photo.id, e)

    @api.model
    def _backfill_missing_coordinates(self, limit=None):
        """把「座標還是空的」既有照片補上兜底座標。

        座標兜底全面化（2026-07-31）之前上傳的照片，當時的規則是只有工程
        告示牌與通報單會繼承，其餘一律留空 —— 那些照片現在仍是 0,0，
        且因為前台地圖與後台 photo_map 的 domain 都是 `latitude != 0`，
        它們**永遠不會出現在地圖上**。

        這裡對它們重跑一次 `_resolve_missing_coordinates()`：
        EXIF 仍優先（舊照片當初可能因為別的原因沒讀到），讀不到才用兜底。
        已經有座標的照片完全不碰。

        回傳實際補上座標的張數。可重複執行。
        """
        photos = self.with_context(active_test=False).search(
            [('latitude', '=', 0), ('longitude', '=', 0)], limit=limit)
        before = len(photos)
        photos._resolve_missing_coordinates()
        filled = len(photos.filtered(lambda p: p.latitude or p.longitude))
        _logger.info('照片座標回填：掃描 %s 張、補上 %s 張', before, filled)
        return filled

    def _exif_coordinates(self):
        """從附件的 JPEG EXIF 讀 GPS，回 (lat, lng) 或 None。"""
        self.ensure_one()
        att = self.attachment_id
        if Image is None or not att:
            return None
        # 只處理 JPEG：PNG 規格沒有 GPS 欄位，開檔純屬浪費
        if 'jpeg' not in (att.mimetype or '').lower():
            return None
        raw = att.raw
        if not raw:
            return None
        with Image.open(BytesIO(raw)) as img:
            gps = img.getexif().get_ifd(EXIF_GPS_IFD_TAG)
        if not gps:
            return None
        lat = self._dms_to_degrees(gps.get(EXIF_GPS_LAT), gps.get(EXIF_GPS_LAT_REF))
        lng = self._dms_to_degrees(gps.get(EXIF_GPS_LNG), gps.get(EXIF_GPS_LNG_REF))
        return self._validated_coordinates(lat, lng)

    def _fallback_coordinates(self):
        """照片沒有 GPS 時的座標兜底，由精確往粗略退。

        **2026-07-31 範圍變更**：使用者原本指定只有工程告示牌與通報單會繼承，
        現在改為 **每一張照片最後都要有座標** —— 依序試通報單、工程告示牌，
        最後一律退到所屬工程案件的經緯度。

        原本限縮範圍的理由是「把工程中心點寫進 latitude 會讓實拍位置與推定
        位置在地圖上無法分辨」。那個顧慮由 `gps_source` 欄位解掉了：
        繼承來的一律標成 `inherit`（顯示「沿用工程／通報單」），
        地圖與清單都分得出來，所以全面兜底是安全的。

        順位：
          1. `_geo_fallback_source()` 給的精確來源（通報單 > 告示牌工程）
          2. 呼叫端以 context 指定（收斂前的舊途徑，保留相容）
          3. **所屬工程案件**（最後兜底，每張照片都有 project_id）

        任何一層的座標都要先過 `_validated_coordinates`：來源本身可能填錯
        （實際發生過緯度填成 121.51），也可能根本沒填（0,0 視為未填）。
        全部落空就留空 —— 不會憑空捏造座標。
        """
        self.ensure_one()
        # 1) 精確來源（各模組註冊，通報單優先於告示牌所屬工程）
        source = self._geo_fallback_source()
        if source:
            coords = self._validated_coordinates(
                source.latitude or 0.0, source.longitude or 0.0)
            if coords:
                return coords
        # 2) 呼叫端以 context 指定（收斂前的舊途徑，保留相容）
        ctx = self.env.context
        lat, lng = ctx.get(CTX_FALLBACK_LAT), ctx.get(CTX_FALLBACK_LNG)
        if lat is not None and lng is not None:
            try:
                coords = self._validated_coordinates(float(lat), float(lng))
            except (TypeError, ValueError):
                coords = None
            if coords:
                return coords
        # 3) 最後兜底：所屬工程案件
        # 放在最後而不是併進 _geo_fallback_source()，是因為那個方法是各模組
        # 覆寫的接力鏈（每一棒都 super() 先問前一棒、有值就回傳）。把「一定
        # 有值」的 project_id 放進基底會讓第一棒就命中，後面的通報單／告示牌
        # 判斷永遠跑不到 —— 精確來源反而被最粗略的蓋掉。
        project = self.project_id
        if project:
            return self._validated_coordinates(
                project.latitude or 0.0, project.longitude or 0.0)
        return None

    def _geo_fallback_source(self):
        """回傳「可以把座標借給這張照片」的**精確**來源，沒有就回空 recordset。

        這裡只放比工程案件中心點更精確的來源（通報單的施工地點、告示牌所屬
        工程）。工程案件本身**不要**放進來 —— 它是 `_fallback_coordinates()`
        最後那一層的兜底，放進來會讓這條接力鏈第一棒就命中，後面的模組再也
        沒機會提供更精確的座標。

        各模組覆寫時務必先 `res = super()._geo_fallback_source()`、有值就直接
        回傳，否則後掛載的模組會把前面的判斷整個蓋掉。

        本方法只負責「挑出來源」，範圍檢查交給 _validated_coordinates —— 來源
        的座標可能是錯的（使用者實際填過緯度 121.51），不能無條件相信。
        """
        self.ensure_one()
        return self.signboard_project_id

    @staticmethod
    def _dms_to_degrees(dms, ref):
        """EXIF 的 (度, 分, 秒) + 方位字元 → 十進位度。無法解析回 None。"""
        if not dms:
            return None
        try:
            parts = [float(x) for x in dms]
        except (TypeError, ValueError):
            return None
        if len(parts) < 3:
            return None
        degrees = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
        if isinstance(ref, bytes):
            ref = ref.decode('ascii', 'ignore')
        if (ref or '').strip().upper() in ('S', 'W'):
            degrees = -degrees
        return degrees

    @staticmethod
    def _validated_coordinates(lat, lng):
        """把關座標合理性，不合理回 None（換下一個來源，而不是 raise）。

        沒有這一關的話，非法值會在寫入時撞 _check_gps_coordinates 的
        ValidationError，讓整張照片建不出來 —— 補座標是加值功能，
        不該有能力讓上傳失敗。
        """
        if lat is None or lng is None:
            return None
        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
            return None
        # (0, 0) 是「未填」的慣用表示，與 _check_gps_coordinates 的判斷一致
        if not lat and not lng:
            return None
        return (lat, lng)

    # 座標欄位：任何一個被改動，就代表這組座標是人改的
    _GEO_VALUE_FIELDS = ('latitude', 'longitude', 'gps_location')

    def write(self, vals):
        """寫入照片。

        兩件附帶處理：
        1. description 改動 → 重新跑 auto-tag
        2. **座標被人工改動 → gps_source 跟著改成「前台輸入」**

        第 2 點原本沒做：`_resolve_missing_coordinates()` 只在 `create()` 跑，
        所以之後在後台把一張 `gps_source='inherit'`（沿用工程座標）的照片
        手動改成正確的實際座標，來源欄位仍然顯示「沿用工程／通報單」——
        看起來像推定值，實際上是人工確認過的精確座標，稽核時會誤判。
        """
        # 呼叫端自己指定了 gps_source 就尊重它（_resolve_missing_coordinates()
        # 寫 exif／inherit 時會連 gps_source 一起帶，不能被這裡蓋掉）
        if 'gps_source' not in vals and any(f in vals for f in self._GEO_VALUE_FIELDS):
            # 逐筆比對舊值：Odoo 常把整份表單的欄位都送進 write，
            # 值沒變也會出現在 vals 裡 —— 那不算「人工改動」。
            changed = self.filtered(
                lambda p: any(
                    f in vals and p[f] != vals[f] for f in self._GEO_VALUE_FIELDS))
            res = super().write(vals)
            for photo in changed:
                # 改成空座標 = 把座標清掉，來源也該一起清掉
                photo.gps_source = 'input' if (photo.latitude or photo.longitude) else False
        else:
            res = super().write(vals)

        if 'description' in vals:
            # 注意：不清空已有 tag，只 append 命中的新 tag
            self.filtered(lambda r: r.description).action_auto_tag_from_description()
        return res

    def unlink(self):
        """刪除照片；連帶回收沒人再引用的附件。

        照片資料表收斂後，這裡大幅簡化了。收斂前全庫有 3 個指向 ir_attachment
        的 RESTRICT FK（本表 + 兩張缺失照片行表），三者互相鎖死，才需要一整套
        「S→L→A 順序 + PHOTO_CASCADE_CTX 遞迴防護 + 反向級聯刪照片行」的機制。
        兩張照片行表已隨收斂移除，現在只剩本表一個 RESTRICT，順序問題消失。

        仍保留的是「附件回收」：attachment_id 是 required + ondelete=restrict，
        照片刪掉後那張 ir.attachment 不會自己消失，不回收就變成孤兒檔案。
        但同一張附件可能被多筆照片共用（去重邏輯允許），所以要先確認沒人再
        引用才刪。
        """
        # 必須在 super() 之前抓：之後 self 已死，mapped() 會拿到空 recordset
        attachments = self.mapped('attachment_id')
        result = super().unlink()
        self._unlink_free_attachments(attachments)
        return result

    def _unlink_free_attachments(self, attachments):
        """只刪掉「已經沒有任何 supervision.photo 引用」的附件。"""
        attachments = attachments.exists()
        if not attachments:
            return
        # 前面的 unlink 必須先落到 DB，下面的 search 才看得到正確狀態
        self.env.flush_all()
        # active_test=False：已封存的照片同樣持有 FK，漏掉會誤判成「無人引用」
        # 而撞 IntegrityError
        still_used = self.sudo().with_context(active_test=False).search(
            [('attachment_id', 'in', attachments.ids)]).mapped('attachment_id')
        free = attachments - still_used
        if free:
            free.sudo().unlink()

    # === 自動打標籤規則 ===
    # 每條規則：(canonical_tag_name, [keywords_that_hit_it], color_key)
    # 長詞優先（避免「雙孔箱涵-基礎鋼筋綁紮」只抓到「箱涵」）
    # canonical_tag_name 就是實際建立的 supervision.photo.tag 名稱；
    # keywords 中任一命中 description 就產生這個 tag
    _AUTO_TAG_RULES = [
        # ── 地點（color_loc = 顏色 index 2 橙）────────────────────
        ('雙孔箱涵',   ['雙孔箱涵'], 'color_loc'),
        ('三合橋',     ['三合橋'], 'color_loc'),
        ('磺港路',     ['磺港路'], 'color_loc'),
        ('人行道',     ['人行道'], 'color_loc'),
        ('既有河道',   ['既有河道'], 'color_loc'),
        ('臨路側',     ['臨路側'], 'color_loc'),
        ('木棧橋',     ['木棧橋'], 'color_loc'),
        ('木棧道',     ['木棧道'], 'color_loc'),
        ('座台',       ['座台'], 'color_loc'),
        ('伸縮縫',     ['伸縮縫'], 'color_loc'),
        ('側溝',       ['側溝'], 'color_loc'),
        ('橋面板',     ['橋面板'], 'color_loc'),
        # ── 工項（color_task = 顏色 index 10 綠）──────────────────
        ('混凝土澆置', ['混凝土澆置'], 'color_task'),
        ('鋼筋綁紮',   ['鋼筋綁紮'], 'color_task'),
        ('模板作業',   ['模板組立', '模板施作'], 'color_task'),
        ('緣石作業',   ['緣石施作', '路緣石施作', '路緣石擺設', '緣石擺設'], 'color_task'),
        ('透水紙模鋪設', ['透水紙模鋪設', '透水紙膜鋪設', '紙模鋪設']
         , 'color_task'),  # 第三項為錯字常見寫法
        ('透水磚鋪設', ['透水磚鋪設'], 'color_task'),
        ('破碎篩分',   ['破碎篩分', '破碎'], 'color_task'),
        ('地坪作業',   ['地坪施作', '地坪泥作', '石材地坪'], 'color_task'),
        ('AC鋪設',     ['AC鋪設'], 'color_task'),
        ('鋼線網鋪設', ['鋼線網鋪設'], 'color_task'),
        ('頂板澆置',   ['頂板澆置'], 'color_task'),
        ('界石施作',   ['界石施作'], 'color_task'),
        ('陰井施作',   ['陰井施作'], 'color_task'),
        ('扶手安裝',   ['扶手安裝'], 'color_task'),
        ('欄杆施作',   ['欄杆施作'], 'color_task'),
        ('座台泥作',   ['座台泥作'], 'color_task'),
        ('碎石回填',   ['碎石回填'], 'color_task'),
        ('花土回填',   ['花土回填'], 'color_task'),
        ('植筋',       ['植筋'], 'color_task'),
        ('砌石',       ['砌石'], 'color_task'),
        ('植栽',       ['植栽'], 'color_task'),
        ('固床工',     ['固床工'], 'color_task'),
        ('木棧道修復', ['木棧道修復'], 'color_task'),
        ('淺溝格柵',   ['淺溝格柵'], 'color_task'),
    ]
    # 顏色索引：2=橙(地點), 10=綠(工項)
    _AUTO_TAG_COLORS = {'color_loc': 2, 'color_task': 10}

    def _get_or_create_photo_tag(self, tag_name, color_key):
        """取得或建立指定名稱的 supervision.photo.tag。"""
        Tag = self.env['supervision.photo.tag'].sudo()
        tag = Tag.search([('name', '=', tag_name)], limit=1)
        if not tag:
            tag = Tag.create({
                'name': tag_name,
                'color': self._AUTO_TAG_COLORS.get(color_key, 0),
            })
        return tag

    def action_auto_tag_from_description(self):
        """掃 description 自動打地點/工項標籤（Many2many tag_ids）。

        規則：
        - 遍歷 _AUTO_TAG_RULES 的每條 (tag_name, keywords, color)
        - 只要 keywords 任一命中 description 就 get-or-create tag_name
        - 已經在 tag_ids 的不重複加入

        Returns:
            dict: {str(photo_id): [added_tag_names]}
        """
        added = {}
        for photo in self:
            desc = photo.description or ''
            if not desc:
                continue
            new_tags = self.env['supervision.photo.tag']
            for tag_name, keywords, color_key in self._AUTO_TAG_RULES:
                if any(kw in desc for kw in keywords):
                    tag = self._get_or_create_photo_tag(tag_name, color_key)
                    if tag.id not in photo.tag_ids.ids:
                        new_tags |= tag
            if new_tags:
                photo.tag_ids = [(4, t.id) for t in new_tags]
                added[str(photo.id)] = new_tags.mapped('name')
        return added

    @api.model
    def action_auto_tag_all(self):
        """對所有 active 照片跑 auto-tag（Odoo UI 按鈕用）。"""
        photos = self.search([('active', '=', True), ('description', '!=', False)])
        result = photos.action_auto_tag_from_description()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '自動打標籤完成',
                'message': f'掃描 {len(photos)} 張照片，新增標籤到 {len(result)} 張',
                'sticky': False,
            }
        }

    def action_view_on_map(self):
        """在地圖上查看照片位置"""
        self.ensure_one()
        if not self.latitude or not self.longitude:
            raise UserError('此照片沒有 GPS 位置資訊！')

        # 返回 Google Maps URL
        map_url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        return {
            'type': 'ir.actions.act_url',
            'url': map_url,
            'target': 'new',
        }

    def action_download(self):
        """下載照片"""
        self.ensure_one()
        if not self.attachment_id:
            raise UserError('此照片沒有關聯的檔案！')

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'self',
        }

    # === 約束驗證 ===
    @api.constrains('latitude', 'longitude')
    def _check_gps_coordinates(self):
        """驗證 GPS 座標範圍"""
        for photo in self:
            if photo.latitude:
                if not -90 <= photo.latitude <= 90:
                    raise ValidationError('緯度必須在 -90 到 90 之間！')
            if photo.longitude:
                if not -180 <= photo.longitude <= 180:
                    raise ValidationError('經度必須在 -180 到 180 之間！')

    @api.constrains('shot_at')
    def _check_shot_at(self):
        """驗證拍攝日期不能在未來"""
        now = fields.Datetime.now()
        for photo in self:
            if photo.shot_at and photo.shot_at > now:
                raise ValidationError('拍攝日期不能在未來！')
    
    # === 搜尋功能增強 ===
    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """支援搜尋 name、description 和 image_filename 欄位"""
        domain = domain or []
        if name:
            domain = ['|', '|', 
                      ('name', operator, name), 
                      ('description', operator, name),
                      ('image_filename', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
