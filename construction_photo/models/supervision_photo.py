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
        string='照片說明',
        required=True,
        tracking=True,
        help='舊系統欄位: description')

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

    # === GPS 位置資訊 (舊系統欄位) ===
    gps_location = fields.Char(
        string='GPS位置',
        help='舊系統欄位: gpsLocation，格式: 緯度,經度')

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
        """建立照片記錄"""
        for vals in vals_list:
            # 確保上傳時間
            if 'upload_date' not in vals:
                vals['upload_date'] = fields.Datetime.now()
        return super().create(vals_list)

    def unlink(self):
        """刪除照片記錄"""
        # 刪除關聯的附件
        attachments = self.mapped('attachment_id')
        result = super().unlink()
        # 刪除沒有其他關聯的附件
        attachments.unlink()
        return result

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
