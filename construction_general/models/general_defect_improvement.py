# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class GeneralDefectImprovementPhoto(models.Model):
    """
    缺失改善照片中間表

    功能：
    - 為每張照片記錄元數據（上傳時間、說明、階段）
    - 支援矯正前中後三階段照片管理
    - 支援直接上傳圖片檔案
    """
    _name = 'general.defect.improvement.photo'
    _description = '缺失改善照片'
    _order = 'upload_time desc, id desc'

    # === 關聯 ===
    defect_improvement_id = fields.Many2one(
        'general.defect.improvement',
        string='缺失改善記錄',
        required=True,
        ondelete='cascade',
        index=True)

    # === 照片上傳欄位 (主要使用) ===
    image = fields.Binary(
        string='照片',
        attachment=True,
        help='直接上傳照片檔案')

    image_filename = fields.Char(
        string='檔案名稱',
        help='照片檔案名稱')

    # === 內部附件關聯 (自動建立) ===
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='照片檔案記錄',
        ondelete='restrict',
        help='系統自動建立的附件記錄')

    # === 照片元數據 ===
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

    # === 預覽欄位 ===
    image_preview = fields.Binary(
        string='預覽',
        related='image',
        readonly=True)

    # === 建立時自動處理附件 ===
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # 當上傳圖片時，自動建立 attachment 記錄
            if record.image and not record.attachment_id:
                # 從 ir.attachment 中找到剛建立的附件
                # (當 attachment=True 時，Odoo 會自動建立附件)
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'image'),
                ], limit=1, order='id desc')
                if attachment:
                    record.attachment_id = attachment.id
        return records

    def write(self, vals):
        result = super().write(vals)
        # 當更新圖片時，更新 attachment 關聯
        for record in self:
            if 'image' in vals and record.image and not record.attachment_id:
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'image'),
                ], limit=1, order='id desc')
                if attachment:
                    record.attachment_id = attachment.id
        return result

    # === 約束 ===
    _sql_constraints = [
        ('unique_attachment_per_defect',
         'UNIQUE(defect_improvement_id, attachment_id)',
         '同一缺失記錄中不能重複添加相同照片！'),
    ]


class GeneralDefectImprovement(models.Model):
    """
    一般式缺失改善

    設計說明：
    - 獨立於通報單的缺失改善記錄
    - 用於一般式工程的缺失追蹤與改善
    - 可從自主檢查或日常巡查開立
    - 完整的改善追蹤流程

    共用邏輯（欄位群、逾期計算、每日編號、8 個狀態機 action、缺失類別分身欄位、SQL 約束）
    已抽至 construction.daily.defect.mixin，本類別僅保留一般式專屬的關聯與差異行為。
    """
    _name = 'general.defect.improvement'
    _description = '一般式缺失改善'
    _inherit = ['construction.daily.defect.mixin', 'mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
    _order = 'notification_date desc, id desc'

    # === 基本資料 ===
    # 缺失編號：以 defect_no 為 canonical，name 保留為 related 別名（既有 view/FK 不斷、_rec_name 維持 name）
    name = fields.Char(
        string='缺失編號',
        related='defect_no',
        store=True,
        index=True,
        copy=False,
        readonly=True)

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        tracking=True,
        index=True,
        domain="[('project_type', '=', 'general')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    task_id = fields.Many2one(
        'project.task',
        string='關聯工項',
        domain="[('project_id', '=', project_id)]",
        help='此缺失關聯的契約工項')

    # === 來源關聯 ===
    source_type = fields.Selection([
        ('self_inspection', '自主檢查'),
        ('daily_check', '日常巡查'),
        ('supervision', '監造抽查'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ], string='缺失來源', required=True, default='daily_check', tracking=True)

    self_inspection_id = fields.Many2one(
        'general.self.inspection',
        string='來源自主檢查',
        domain="[('project_id', '=', project_id)]",
        help='若從自主檢查開立的缺失')

    self_inspection_item_id = fields.Many2one(
        'general.self.inspection.item',
        string='來源檢查項目',
        domain="[('inspection_id', '=', self_inspection_id)]",
        help='自主檢查中的具體缺失項目')

    # 來源自主檢查的檢查編號（供「關聯與備註」頁籤獨立顯示）
    source_inspection_no = fields.Char(
        related='self_inspection_id.name',
        string='檢查編號',
        readonly=True)

    ncr_id = fields.Many2one(
        'supervision.defect',
        string='關聯 NCR',
        domain="[('project_id', '=', project_id)]",
        help='若需關聯 NCR 缺失單')

    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='負責改善的施工廠商')

    # === 照片 (新結構) ===
    photo_ids = fields.One2many(
        'general.defect.improvement.photo',
        'defect_improvement_id',
        string='所有照片')

    before_photo_ids = fields.One2many(
        'general.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防前照片',
        domain=[('photo_stage', '=', 'before')])

    during_photo_ids = fields.One2many(
        'general.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防中照片',
        domain=[('photo_stage', '=', 'during')])

    after_photo_ids = fields.One2many(
        'general.defect.improvement.photo',
        'defect_improvement_id',
        string='矯正及預防後照片',
        domain=[('photo_stage', '=', 'after')])

    # === 其他附件 (保留，非照片附件) ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關文件附件',
        help='非照片類型的其他附件文件')

    # === 向後兼容欄位 (保留舊欄位名，用於數據遷移) ===
    defect_photo_ids_legacy = fields.Many2many(
        'ir.attachment',
        'general_defect_photo_rel',
        'defect_id', 'attachment_id',
        string='缺失照片(舊)',
        help='數據遷移用，不要直接使用')

    improvement_photo_ids_legacy = fields.Many2many(
        'ir.attachment',
        'general_improvement_photo_rel',
        'defect_id', 'attachment_id',
        string='改善照片(舊)',
        help='數據遷移用，不要直接使用')

    # === 狀態機差異行為（覆寫 Mixin hook）===
    # 一般式重新開啟時，額外清除結案人與驗證結果
    def _reopen_extra_vals(self):
        return {
            'closer_id': False,
            'verify_result': False,
        }

    # 一般式退回草稿允許 draft 或 notified 狀態
    _reset_draft_source_states = ('draft', 'notified')
    _reset_draft_error = '只有草稿或已通知狀態可以重設'

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失"""
        today = fields.Date.today()
        # 更新所有未結案且逾期的記錄
        overdue_records = self.search([
            ('state', 'not in', ('improved', 'verified', 'closed')),
            ('deadline', '<', today),
            ('is_overdue', '=', False),
        ])
        # 觸發重新計算
        for record in overdue_records:
            record._compute_overdue()

    @api.model
    def _cron_send_overdue_notification(self):
        """發送逾期通知"""
        overdue_records = self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ('improved', 'verified', 'closed')),
        ])
        for record in overdue_records:
            # 發送訊息通知負責人
            if record.responsible_user_id:
                record.message_post(
                    body=f'缺失 {record.name} 已逾期 {record.overdue_days} 天，請儘速處理！',
                    partner_ids=record.responsible_user_id.partner_id.ids,
                    message_type='notification',
                )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立記錄時自動設定序號"""
        # 追蹤批次內各分組已分配的下一個序號，避免同批次內序號衝突
        # key: (project_id, found_date, check_type, record_type)
        batch_next_seq = {}

        for vals in vals_list:
            # 驗證必要欄位
            if not vals.get('project_id'):
                raise UserError('必須指定工程')
            if not vals.get('found_date'):
                vals['found_date'] = fields.Date.today()

            # record_type 判定（v11）：依建立者的監造/營造身分自動決定，
            # 監造身分只能建監造缺失單、營造身分只能建營造缺失單。
            self._resolve_record_type(vals)

            # 永遠重算序號，確保不重複（不信任傳入的預設值 1）
            key = (
                vals.get('project_id'),
                str(vals.get('found_date')),
                vals.get('check_type', 'construction'),
                vals.get('record_type'),
            )
            if key not in batch_next_seq:
                # 第一次遇到此分組：查 DB 取得下一個可用序號
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
        """依建立者監造/營造身分自動判定 record_type（監造/營造缺失單）

        規則：
        - 單一監造身分 → supervision；單一營造身分 → contractor（強制，覆蓋表單值，防止建錯類型）
        - 後台選單明確帶 default_record_type → 沿用
        - 前台帳號但無唯一監造/營造身分 → 擋下，避免建出別人不能改的單
        - 後台內部用戶無身分 → 維持預設 supervision
        """
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
        # 防竄改（v11）：前台帳號在缺失離開草稿後，不可再改缺失定義欄位；
        # 改善回覆欄位不受限。後台/sudo（env.user 為超級用戶,share=False）不受此限。
        if self.env.user.share and any(f in vals for f in self._DEFINITION_FIELDS):
            if self.filtered(lambda r: r.state and r.state != 'draft'):
                raise UserError('缺失已送出，缺失說明、類別、嚴重度等定義欄位不可再修改')

        result = super().write(vals)

        # 若修改影響編號的欄位，觸發重新計算
        if any(field in vals for field in ['sequence_number', 'found_date',
                                             'check_type', 'record_type', 'project_id']):
            self._compute_defect_no()

        return result

    def unlink(self):
        for record in self:
            if record.state not in ('draft',):
                raise UserError('只有草稿狀態的缺失可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('deadline', 'found_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.found_date:
                if record.deadline < record.found_date:
                    raise ValidationError('改善期限不得早於發現日期')

    @api.constrains('notification_date', 'found_date')
    def _check_notification_date(self):
        for record in self:
            if record.notification_date and record.found_date:
                if record.notification_date < record.found_date:
                    raise ValidationError('通知改善日期不得早於發現日期')

    # === 照片自動同步配置 ===
    def _get_photo_sync_config(self):
        """
        配置照片同步規則 - 適配新結構

        說明：
        - photo.sync.mixin 會自動將照片同步到 supervision.photo 集中管理
        - 新結構使用 One2many 中間模型，需要透過 attachment_id 存取
        - 保留此功能以維持照片集中管理的完整性
        """
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
                'description_field': 'improvement_result',
                'location_field': 'defect_location',
                'auto_tag': '缺失改善',
            },
        }

    # 覆寫 _auto_sync_photos 方法以適配中間模型並正確映射欄位
    def _auto_sync_photos(self, field_name, config):
        """
        覆寫父類方法以支援 One2many 中間模型結構

        關鍵映射：
        - general.defect.improvement.photo.upload_time → supervision.photo.shot_at
        - general.defect.improvement.photo.description → supervision.photo.notes
        - general.defect.improvement.photo.attachment_id → supervision.photo.attachment_id
        """
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
                    # 已存在，更新時間和說明（如果中間模型有提供）
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
                record_name = getattr(record, 'name', '') or f'ID:{record.id}'
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
                    # 使用中間模型的上傳時間，如果沒有則使用當前時間
                    'shot_at': photo_record.upload_time if hasattr(photo_record, 'upload_time') else fields.Datetime.now(),
                }

                # 設定備註（組合的說明文字）
                if notes_parts:
                    photo_vals['notes'] = '\n\n'.join(notes_parts)

                # 位置資訊
                if config.get('location_field'):
                    location_value = getattr(record, config['location_field'], None)
                    if location_value:
                        photo_vals['location_description'] = str(location_value)

                # 建立新照片記錄
                SupervisionPhoto.create(photo_vals)
