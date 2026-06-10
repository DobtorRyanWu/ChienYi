# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


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
        'supervision.project',
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
        # 自動打標籤（只對有 description 的）
        to_tag = records.filtered(lambda r: r.description)
        if to_tag:
            to_tag.action_auto_tag_from_description()
        return records

    def write(self, vals):
        """寫入照片；若 description 改動，重新跑 auto-tag。"""
        res = super().write(vals)
        if 'description' in vals:
            # 注意：不清空已有 tag，只 append 命中的新 tag
            self.filtered(lambda r: r.description).action_auto_tag_from_description()
        return res

    def unlink(self):
        """刪除照片記錄"""
        # 刪除關聯的附件
        attachments = self.mapped('attachment_id')
        result = super().unlink()
        # 刪除沒有其他關聯的附件
        attachments.unlink()
        return result

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
