# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ReservationDefectImprovementPhoto(models.Model):
    """預約式缺失改善照片中間表"""
    _name = 'reservation.defect.improvement.photo'
    _description = '預約式缺失改善照片'
    _order = 'upload_time desc, id desc'

    defect_improvement_id = fields.Many2one(
        'reservation.defect.improvement',
        string='缺失改善記錄',
        required=True,
        ondelete='cascade',
        index=True)

    # Direct upload fields (following general pattern)
    image = fields.Binary(
        string='照片',
        attachment=True,
        help='直接上傳照片檔案')

    image_filename = fields.Char(string='檔案名稱')

    # Auto-populated attachment
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='照片檔案記錄',
        ondelete='restrict')

    photo_stage = fields.Selection([
        ('before', '矯正及預防前'),
        ('during', '矯正及預防中'),
        ('after', '矯正及預防後'),
    ], string='照片階段', required=True, default='before')

    upload_time = fields.Datetime(
        string='上傳時間',
        default=fields.Datetime.now,
        required=True,
        help='照片上傳時間，可手動修改')

    description = fields.Text(
        string='照片說明',
        help='此照片的詳細說明')

    # Preview field for display
    image_preview = fields.Binary(
        string='預覽',
        related='image',
        readonly=True)

    _sql_constraints = [
        ('unique_attachment_per_defect',
         'UNIQUE(defect_improvement_id, attachment_id)',
         '同一缺失記錄中不能重複添加相同照片！'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Create photo records and auto-populate attachment_id"""
        records = super().create(vals_list)
        for record in records:
            if record.image and not record.attachment_id:
                # Find the auto-created attachment
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'image'),
                ], limit=1, order='id desc')
                if attachment:
                    record.attachment_id = attachment.id
        return records

    def write(self, vals):
        """Update attachment_id when image changes"""
        res = super().write(vals)
        if 'image' in vals:
            for record in self:
                if record.image and not record.attachment_id:
                    attachment = self.env['ir.attachment'].search([
                        ('res_model', '=', self._name),
                        ('res_id', '=', record.id),
                        ('res_field', '=', 'image'),
                    ], limit=1, order='id desc')
                    if attachment:
                        record.attachment_id = attachment.id
        return res


class ReservationDefectImprovement(models.Model):
    """
    預約式缺失改善 (通報單內)

    設計說明：
    - 綁定於通報單的缺失改善記錄
    - 用於預約式工程的缺失追蹤與改善
    - 與 reservation.notification.slip 關聯
    - 支援驗收缺失關聯

    共用邏輯（欄位群、逾期計算、每日編號、8 個狀態機 action、缺失類別分身欄位、SQL 約束）
    已抽至 construction.daily.defect.mixin，本類別僅保留預約式專屬的關聯與差異行為。
    """
    _name = 'reservation.defect.improvement'
    _description = '預約式缺失改善 (通報單內)'
    _inherit = ['construction.daily.defect.mixin', 'mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
    _order = 'notification_date desc, id desc'

    # === 通報單關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='所屬通報單',
        required=True,
        ondelete='cascade',
        tracking=True)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        related='slip_id.project_id',
        store=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True)

    # === 基本資料 ===
    # 缺失編號：以 defect_no 為 canonical，record_no 保留為 related 別名（既有 view/FK 不斷）
    record_no = fields.Char(
        string='紀錄表編號',
        related='defect_no',
        store=True,
        index=True,
        copy=False,
        readonly=True)

    # === 來源關聯 ===
    source_type = fields.Selection([
        ('slip', '通報單'),
        ('self_inspection', '自主檢查'),
        ('daily_check', '日常巡查'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ], string='缺失來源', default='slip', tracking=True)

    # === 編號前綴設定 ===
    supervision_prefix = fields.Char(
        string='監造編號前綴',
        help='監造單位使用的編號前綴')

    contractor_prefix = fields.Char(
        string='營造編號前綴',
        help='營造廠商使用的編號前綴')

    # === 照片 (新結構) ===
    photo_ids = fields.One2many(
        'reservation.defect.improvement.photo',
        'defect_improvement_id',
        string='所有照片')

    before_photo_ids = fields.One2many(
        'reservation.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防前照片',
        domain=[('photo_stage', '=', 'before')])

    during_photo_ids = fields.One2many(
        'reservation.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防中照片',
        domain=[('photo_stage', '=', 'during')])

    after_photo_ids = fields.One2many(
        'reservation.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防後照片',
        domain=[('photo_stage', '=', 'after')])

    # === 相關文件附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reservation_defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關文件附件',
        help='非照片類型的其他附件文件')

    # 保留舊欄位用於資料遷移
    defect_photo_ids_legacy = fields.Many2many(
        'ir.attachment',
        'reservation_defect_photo_rel',
        'defect_id', 'attachment_id',
        string='缺失照片(舊)')

    improvement_photo_ids_legacy = fields.Many2many(
        'ir.attachment',
        'reservation_improvement_photo_rel',
        'defect_id', 'attachment_id',
        string='改善照片(舊)')

    # === 欄位屬性覆寫（還原預約式與 Mixin(以一般式為 canonical) 的差異）===
    severity = fields.Selection(required=False)
    defect_category = fields.Selection(required=False)
    found_date = fields.Date(required=False, help='發現缺失的日期')
    deadline = fields.Date(string='限定完成改善日期')
    improvement_date = fields.Date(help='實際完成改善的日期')
    discovery_user_id = fields.Many2one(default=False, help='發現缺失的人員')
    responsible_user_id = fields.Many2one(help='負責改善的人員')
    defect_location = fields.Char(help=False)
    defect_cause = fields.Text(help=False)
    improvement_result = fields.Text(help=False)
    state = fields.Selection(string='缺失狀態')

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失並發送提醒"""
        today = fields.Date.today()
        overdue_records = self.search([
            ('state', 'in', ('notified', 'improving')),
            ('deadline', '<', today),
        ])
        for record in overdue_records:
            if record.responsible_user_id:
                partner = record.responsible_user_id.partner_id
                record.message_post(
                    body=(
                        f'缺失 <b>{record.record_no}</b> 已逾期（期限：{record.deadline}），'
                        f'請盡快完成改善。'
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立記錄時自動設定序號"""
        batch_next_seq = {}
        for vals in vals_list:
            # 驗證必要欄位
            if not vals.get('project_id'):
                # 從 slip_id 取得 project_id
                if vals.get('slip_id'):
                    slip = self.env['reservation.notification.slip'].browse(vals['slip_id'])
                    vals['project_id'] = slip.project_id.id
                else:
                    raise UserError('必須指定通報單或工程')

            if not vals.get('found_date'):
                vals['found_date'] = fields.Date.today()

            # record_type 判定（v11）：依建立者的監造/營造身分自動決定
            self._resolve_record_type(vals)

            # 永遠重算序號，確保不重複（不信任傳入的預設值 1）
            key = (
                vals.get('project_id'),
                str(vals.get('found_date')),
                vals.get('check_type', 'construction'),
                vals.get('record_type'),
            )
            if key not in batch_next_seq:
                batch_next_seq[key] = self._get_daily_sequence(
                    vals.get('project_id'),
                    vals.get('found_date'),
                    vals.get('check_type', 'construction'),
                    vals.get('record_type'),
                )
            vals['sequence_number'] = batch_next_seq[key]
            batch_next_seq[key] += 1

        return super().create(vals_list)

    # 缺失「定義」欄位：離開草稿後前台不可再改（防竄改）
    _DEFINITION_FIELDS = (
        'defect_description', 'defect_category', 'severity', 'found_date', 'check_type',
    )

    @api.model
    def _resolve_record_type(self, vals):
        """依建立者監造/營造身分自動判定 record_type（同 general.defect.improvement）"""
        user = self.env.user
        is_sup = user.is_supervision_org
        is_con = user.is_contractor_org
        if is_sup and not is_con:
            vals['record_type'] = 'supervision'
        elif is_con and not is_sup:
            vals['record_type'] = 'contractor'
        elif 'record_type' not in vals and self.env.context.get('default_record_type'):
            vals['record_type'] = self.env.context['default_record_type']
        elif not vals.get('record_type'):
            if user.share:
                raise UserError('您的帳號未設定唯一的監造/營造身分，無法判定缺失單類型，請聯絡管理者')
            vals['record_type'] = 'supervision'

    def write(self, vals):
        """修改記錄時，若影響編號則重新計算"""
        # 防竄改（v11）：前台帳號在缺失離開草稿後，不可再改缺失定義欄位
        if self.env.user.share and any(f in vals for f in self._DEFINITION_FIELDS):
            if self.filtered(lambda r: r.state and r.state != 'draft'):
                raise UserError('缺失已送出，缺失說明、類別、嚴重度等定義欄位不可再修改')

        result = super().write(vals)

        # 若修改影響編號的欄位，觸發重新計算
        if any(field in vals for field in ['sequence_number', 'found_date',
                                             'check_type', 'record_type', 'project_id']):
            self._compute_defect_no()

        return result

    # === 約束 ===
    @api.constrains('deadline', 'notification_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.notification_date:
                if record.deadline < record.notification_date:
                    raise ValidationError('限定完成改善日期不得早於通知改善日期')

    # === 照片自動同步配置 ===
    def _get_photo_sync_config(self):
        """配置照片同步規則 - 適配新結構"""
        return {
            'before_photo_ids': {
                'source_model': 'defect',
                'name_prefix': '缺失照片(矯正前)',
                'description_field': 'defect_description',
                'location_field': 'defect_location',
                'auto_tag': '缺失改善',
            },
            'during_photo_ids': {
                'source_model': 'defect',
                'name_prefix': '改善照片(矯正中)',
                'description_field': 'improvement_action',
                'location_field': 'defect_location',
                'auto_tag': '缺失改善',
            },
            'after_photo_ids': {
                'source_model': 'defect',
                'name_prefix': '改善照片(矯正後)',
                'description_field': 'prevention_action',
                'location_field': 'defect_location',
                'auto_tag': '缺失改善',
            },
        }

    def _auto_sync_photos(self, field_name, config):
        """覆寫父類方法以支援 One2many 中間模型結構"""
        SupervisionPhoto = self.env['supervision.photo']

        for record in self:
            if not hasattr(record, 'project_id') or not record.project_id:
                continue

            # 取得中間模型記錄 (One2many)
            photo_records = getattr(record, field_name, False)
            if not photo_records:
                continue

            for photo_record in photo_records:
                # 從中間模型取得實際的附件
                if not hasattr(photo_record, 'attachment_id') or not photo_record.attachment_id:
                    continue

                attachment = photo_record.attachment_id

                # 檢查是否已同步
                existing = SupervisionPhoto.search([
                    ('attachment_id', '=', attachment.id)
                ], limit=1)

                if existing:
                    # 已存在，更新時間和說明
                    update_vals = {}
                    if hasattr(photo_record, 'upload_time') and photo_record.upload_time:
                        update_vals['shot_at'] = photo_record.upload_time
                    if hasattr(photo_record, 'description') and photo_record.description:
                        update_vals['notes'] = photo_record.description
                    if update_vals:
                        existing.write(update_vals)
                    continue

                # 準備新照片資料
                name_prefix = config.get('name_prefix', '照片')
                record_name = getattr(record, 'record_no', '') or f'ID:{record.id}'
                description_text = f'{name_prefix} - {record_name}'

                # 組合說明文字
                notes_parts = []
                if config.get('description_field'):
                    field_value = getattr(record, config['description_field'], None)
                    if field_value:
                        notes_parts.append(str(field_value))

                # 加入中間模型的說明
                if hasattr(photo_record, 'description') and photo_record.description:
                    notes_parts.append(f"照片說明: {photo_record.description}")

                photo_vals = {
                    'description': description_text,
                    'project_id': record.project_id.id,
                    'attachment_id': attachment.id,
                    'source_model': config.get('source_model', 'other'),
                    'source_id': record.id,
                    'shot_at': photo_record.upload_time if hasattr(photo_record, 'upload_time') else fields.Datetime.now(),
                }

                # 設定備註
                if notes_parts:
                    photo_vals['notes'] = '\n\n'.join(notes_parts)

                # 位置資訊
                if config.get('location_field'):
                    location_value = getattr(record, config['location_field'], None)
                    if location_value:
                        photo_vals['location_description'] = str(location_value)

                # 建立新照片記錄
                SupervisionPhoto.create(photo_vals)
