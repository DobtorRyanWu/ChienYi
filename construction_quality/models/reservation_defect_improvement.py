# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
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
    """
    _name = 'reservation.defect.improvement'
    _description = '預約式缺失改善 (通報單內)'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
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

    # === 驗收關聯 ===
    acceptance_id = fields.Many2one(
        'notification.acceptance',
        string='關聯驗收單',
        help='若為驗收時發現的缺失')

    # === 基本資料 ===
    record_no = fields.Char(
        string='紀錄表編號',
        copy=False,
        readonly=True,
        compute='_compute_record_no',
        store=True,
        index=True)

    # === 記錄類型標識 ===
    record_type = fields.Selection([
        ('supervision', '監造'),
        ('contractor', '營造'),
    ], string='記錄類型', required=True, default='supervision',
       tracking=True, index=True,
       help='標識此記錄屬於監造視角或營造視角')

    sequence_number = fields.Integer(
        string='當日序號',
        required=True,
        default=1,
        help='當天同工程同類型的序號，可手動修改')

    # === 檢查類型 ===
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety_env', '安衛及環境清潔檢查'),
    ], string='檢查類型', required=True, default='construction', tracking=True)

    # === 單位資訊 ===
    discovery_unit = fields.Char(
        string='發現單位',
        help='發現缺失的單位名稱')

    improvement_unit = fields.Char(
        string='執行改善單位',
        help='負責改善的單位名稱')

    # === 人員資訊 ===
    discovery_user_id = fields.Many2one(
        'res.users',
        string='發現人',
        tracking=True,
        help='發現缺失的人員')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True,
        help='負責改善的人員')

    # === 日期 ===
    found_date = fields.Date(
        string='發現日期',
        default=fields.Date.today,
        tracking=True,
        help='發現缺失的日期')

    improvement_date = fields.Date(
        string='實際改善日期',
        tracking=True,
        help='實際完成改善的日期')

    # === 日期（原有） ===
    notification_date = fields.Date(
        string='通知改善日期',
        default=fields.Date.today,
        tracking=True)

    deadline = fields.Date(
        string='限定完成改善日期',
        tracking=True)

    closure_date = fields.Date(
        string='結案日期',
        tracking=True)

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue',
        store=True)

    @api.depends('deadline', 'state', 'closure_date')
    def _compute_overdue(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ('conform', 'corrected'):
                # 已結案，不算逾期
                record.is_overdue = False
                record.overdue_days = 0
            elif record.deadline:
                if record.closure_date:
                    # 已結案，檢查是否逾期結案
                    record.is_overdue = record.closure_date > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (record.closure_date - record.deadline).days
                    else:
                        record.overdue_days = 0
                else:
                    # 未結案
                    record.is_overdue = today > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (today - record.deadline).days
                    else:
                        record.overdue_days = 0
            else:
                record.is_overdue = False
                record.overdue_days = 0

    # === 罰款資訊 ===
    is_fined = fields.Boolean(
        string='是否已罰款',
        default=False,
        tracking=True,
        help='標記此缺失是否已進行罰款處理')

    fine_amount = fields.Monetary(
        string='罰款金額',
        currency_field='currency_id',
        help='罰款金額')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        default=lambda self: self.env.company.currency_id)

    fine_note = fields.Text(
        string='罰款說明',
        help='罰款原因及相關說明')

    # === 缺失內容 ===
    defect_description = fields.Text(
        string='缺失具體情形',
        required=True,
        tracking=True)

    defect_location = fields.Char(
        string='缺失位置')

    defect_cause = fields.Text(
        string='缺失發生原因')

    improvement_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    prevention_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

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

    # === 確認資訊 ===
    confirmer_id = fields.Many2one(
        'res.users',
        string='確認人',
        tracking=True)

    confirm_date = fields.Date(
        string='確認日期')

    confirm_comment = fields.Text(
        string='確認意見')

    # === 編號前綴設定 ===
    supervision_prefix = fields.Char(
        string='監造編號前綴',
        help='監造單位使用的編號前綴')

    contractor_prefix = fields.Char(
        string='營造編號前綴',
        help='營造廠商使用的編號前綴')

    # === 狀態 (監造視角) ===
    state = fields.Selection([
        ('conform', '符合要求'),
        ('corrected', '已矯正'),
        ('uncorrected', '未矯正'),
        ('overdue', '逾時未矯正'),
        ('other', '其他'),
    ], string='缺失狀態', default='uncorrected', tracking=True)

    # === 動作方法 ===
    def action_mark_corrected(self):
        """標記已矯正"""
        for record in self:
            if record.state not in ('uncorrected', 'overdue'):
                raise UserError('只有未矯正或逾時未矯正狀態可以標記為已矯正')
            if not record.improvement_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'corrected',
                'closure_date': fields.Date.today(),
                'confirmer_id': self.env.uid,
                'confirm_date': fields.Date.today(),
            })

    def action_mark_conform(self):
        """標記符合要求"""
        for record in self:
            record.write({
                'state': 'conform',
                'closure_date': fields.Date.today(),
                'confirmer_id': self.env.uid,
                'confirm_date': fields.Date.today(),
            })

    def action_mark_overdue(self):
        """標記逾時未矯正"""
        for record in self:
            if record.state != 'uncorrected':
                raise UserError('只有未矯正狀態可以標記為逾時')
            record.state = 'overdue'

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('corrected', 'conform'):
                raise UserError('只有已矯正或符合要求狀態可以重新開啟')
            record.write({
                'state': 'uncorrected',
                'closure_date': False,
            })

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失"""
        today = fields.Date.today()
        overdue_records = self.search([
            ('state', '=', 'uncorrected'),
            ('deadline', '<', today),
        ])
        for record in overdue_records:
            record.state = 'overdue'

    # === 編號生成輔助方法 ===
    def _get_minguo_date_string(self, date_obj):
        """將西元日期轉換為民國年格式字串 YYYMMDD"""
        if not date_obj:
            return ''
        minguo_year = date_obj.year - 1911
        return f"{minguo_year}{date_obj.month:02d}{date_obj.day:02d}"

    def _get_check_type_prefix(self, check_type):
        """取得檢查類型對應的首字"""
        check_type_map = {
            'construction': '施',
            'safety_env': '安',
        }
        return check_type_map.get(check_type, '施')

    def _get_daily_sequence(self, project_id, found_date, check_type, record_type, exclude_id=None):
        """計算當天同工程同類型的下一個序號"""
        # 確保同一 transaction 內剛建立的記錄已寫入 DB
        self.flush_model()
        domain = [
            ('project_id', '=', project_id),
            ('found_date', '=', found_date),
            ('check_type', '=', check_type),
            ('record_type', '=', record_type),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))

        existing = self.search(domain, order='sequence_number desc', limit=1)
        return existing[0].sequence_number + 1 if existing else 1

    @api.onchange('project_id', 'found_date', 'check_type', 'record_type')
    def _onchange_sequence_fields(self):
        """工程、日期、類型變更時，即時計算下一個可用序號"""
        if self.project_id and self.found_date:
            self.sequence_number = self._get_daily_sequence(
                self.project_id.id,
                self.found_date,
                self.check_type or 'construction',
                self.record_type or 'supervision',
            )

    @api.depends('project_id', 'found_date', 'check_type', 'record_type', 'sequence_number')
    def _compute_record_no(self):
        """自動生成缺失編號：編號前綴-檢查類型首字+民國年月日_序號"""
        for record in self:
            if not record.project_id or not record.found_date:
                record.record_no = '/'
                continue

            # 從配置表查詢工程的前綴設定
            prefix_config = self.env['defect.improvement.prefix.config'].search([
                ('project_id', '=', record.project_id.id)
            ], limit=1)

            if not prefix_config:
                raise UserError(
                    f'工程「{record.project_id.name}」尚未設定缺失改善編號前綴。\n'
                    f'請至「品質管理 > 缺失改善 > 編號前綴設定」進行設定。'
                )

            # 根據記錄類型取得對應前綴
            if record.record_type == 'supervision':
                prefix = prefix_config.supervision_prefix
            else:
                prefix = prefix_config.contractor_prefix

            check_prefix = self._get_check_type_prefix(record.check_type)
            date_str = self._get_minguo_date_string(record.found_date)
            record.record_no = f"{prefix}-{check_prefix}{date_str}_{record.sequence_number}"

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

            # 確保 record_type 從 context 帶入（由選單決定）
            if 'record_type' not in vals and self.env.context.get('default_record_type'):
                vals['record_type'] = self.env.context['default_record_type']

            # 若仍未設定則使用預設值
            if not vals.get('record_type'):
                vals['record_type'] = 'supervision'

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

    def write(self, vals):
        """修改記錄時，若影響編號則重新計算"""
        result = super().write(vals)

        # 若修改影響編號的欄位，觸發重新計算
        if any(field in vals for field in ['sequence_number', 'found_date',
                                             'check_type', 'record_type', 'project_id']):
            self._compute_record_no()

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

    # === SQL 約束 ===
    _sql_constraints = [
        ('record_no_unique', 'UNIQUE(record_no)',
         '缺失編號必須唯一！'),
        ('unique_sequence_per_day',
         'UNIQUE(project_id, found_date, check_type, record_type, sequence_number)',
         '同一天同工程同類型的序號不能重複！'),
    ]
