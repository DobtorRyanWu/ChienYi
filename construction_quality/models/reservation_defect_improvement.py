# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

from odoo.addons.construction_quality.models.defect_constants import (
    CHECK_TYPE_PREFIX,
    CHECK_TYPE_TO_CATEGORIES,
    CHECK_TYPE_DEFAULT_CATEGORY,
)


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

    # === 缺失分類 ===
    defect_category = fields.Selection([
        ('material', '材料品質'),
        ('workmanship', '施工品質'),
        ('dimension', '尺寸偏差'),
        ('safety', '安全衛生'),
        ('environment', '環境清潔'),
        ('document', '文件缺漏'),
        ('other', '其他'),
    ], string='缺失類別', default='workmanship', tracking=True)

    # 缺失類別「分身」欄位：依檢查類型只顯示對應子集（畫面用，真值仍寫回 defect_category）
    defect_category_construction = fields.Selection(
        selection=[
            ('material', '材料品質'),
            ('workmanship', '施工品質'),
            ('dimension', '尺寸偏差'),
            ('document', '文件缺漏'),
            ('other', '其他'),
        ],
        string='缺失類別',
        compute='_compute_defect_category_proxy',
        inverse='_inverse_defect_category_proxy')
    defect_category_safety = fields.Selection(
        selection=[
            ('safety', '安全衛生'),
            ('environment', '環境清潔'),
        ],
        string='缺失類別',
        compute='_compute_defect_category_proxy',
        inverse='_inverse_defect_category_proxy')

    severity = fields.Selection([
        ('minor', '輕微'),
        ('moderate', '中等'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ], string='嚴重程度', default='minor', tracking=True)

    responsible_party = fields.Selection([
        ('contractor', '承包商'),
        ('subcontractor', '分包商'),
        ('supplier', '供應商'),
        ('design', '設計單位'),
        ('owner', '業主'),
        ('other', '其他'),
    ], string='責任歸屬', tracking=True)

    improvement_progress = fields.Integer(
        string='改善進度 (%)',
        default=0)

    # === 複查資訊 ===
    recheck_date = fields.Date(string='複查日期', tracking=True)

    recheck_result = fields.Selection([
        ('pass', '通過'),
        ('fail', '不通過'),
        ('pending', '待複查'),
    ], string='複查結果', tracking=True)

    recheck_note = fields.Text(string='複查說明')

    # === 來源關聯 ===
    source_type = fields.Selection([
        ('slip', '通報單'),
        ('self_inspection', '自主檢查'),
        ('daily_check', '日常巡查'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ], string='缺失來源', default='slip', tracking=True)

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
            if record.state in ('improved', 'verified', 'closed'):
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

    improvement_result = fields.Text(string='改善結果說明')

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

    # === 驗證資訊 ===
    verifier_id = fields.Many2one(
        'res.users',
        string='驗證人',
        tracking=True)

    verify_date = fields.Date(string='驗證日期')

    verify_result = fields.Selection([
        ('pass', '驗證通過'),
        ('fail', '驗證不通過'),
    ], string='驗證結果', tracking=True)

    verify_comment = fields.Text(string='驗證意見')

    # === 結案資訊 ===
    closer_id = fields.Many2one('res.users', string='結案人', tracking=True)

    close_comment = fields.Text(string='結案說明')

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 編號前綴設定 ===
    supervision_prefix = fields.Char(
        string='監造編號前綴',
        help='監造單位使用的編號前綴')

    contractor_prefix = fields.Char(
        string='營造編號前綴',
        help='營造廠商使用的編號前綴')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('notified', '已通知'),
        ('improving', '改善中'),
        ('improved', '已改善'),
        ('verified', '已驗證'),
        ('closed', '結案'),
    ], string='缺失狀態', default='draft', tracking=True, index=True)

    # === 動作方法 ===
    def action_notify(self):
        """通知改善: draft → notified"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以通知改善')
            if not record.deadline:
                raise ValidationError('請先設定改善期限')
            record.write({
                'state': 'notified',
                'notification_date': fields.Date.today(),
            })
            if record.responsible_user_id:
                partner = record.responsible_user_id.partner_id
                unit = record.improvement_unit or ''
                record.message_subscribe(partner_ids=partner.ids)
                record.message_post(
                    body=(
                        f'缺失 <b>{record.record_no}</b> 已派發給您'
                        + (f'（執行改善單位：{unit}）' if unit else '') + '，'
                        f'請於 <b>{record.deadline}</b> 前完成改善。<br/>'
                        f'缺失說明：{record.defect_description or "（無）"}'
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_start_improvement(self):
        """開始改善: notified → improving"""
        for record in self:
            if record.state != 'notified':
                raise UserError('只有已通知狀態可以開始改善')
            record.state = 'improving'

    def action_complete_improvement(self):
        """完成改善: improving → improved"""
        for record in self:
            if record.state != 'improving':
                raise UserError('只有改善中狀態可以標記完成')
            if not record.improvement_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'improved',
                'improvement_date': fields.Date.today(),
            })
            if record.discovery_user_id:
                partner = record.discovery_user_id.partner_id
                record.message_post(
                    body=f'缺失 <b>{record.record_no}</b> 已完成改善，請複查。',
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_verify_pass(self):
        """驗證通過: improved → verified"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            record.write({
                'state': 'verified',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'pass',
            })

    def action_verify_fail(self):
        """驗證不通過: improved → improving"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            record.write({
                'state': 'improving',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'fail',
            })

    def action_close(self):
        """結案: verified → closed"""
        for record in self:
            if record.state != 'verified':
                raise UserError('只有已驗證狀態可以結案')
            record.write({
                'state': 'closed',
                'closer_id': self.env.uid,
                'closure_date': fields.Date.today(),
            })

    def action_reopen(self):
        """重新開啟: verified/closed → improving"""
        for record in self:
            if record.state not in ('verified', 'closed'):
                raise UserError('只有已驗證或結案狀態可以重新開啟')
            record.write({
                'state': 'improving',
                'closure_date': False,
            })

    def action_reset_draft(self):
        """退回草稿"""
        for record in self:
            if record.state not in ('notified',):
                raise UserError('只有已通知狀態可以退回草稿')
            record.state = 'draft'

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

    # === 編號生成輔助方法 ===
    def _get_minguo_date_string(self, date_obj):
        """將西元日期轉換為民國年格式字串 YYYMMDD"""
        if not date_obj:
            return ''
        minguo_year = date_obj.year - 1911
        return f"{minguo_year}{date_obj.month:02d}{date_obj.day:02d}"

    def _get_check_type_prefix(self, check_type):
        """取得檢查類型對應的首字（讀共用對應表）"""
        return CHECK_TYPE_PREFIX.get(check_type, '施')

    # === 缺失類別分身欄位：與真值 defect_category 同步 ===
    @api.depends('defect_category')
    def _compute_defect_category_proxy(self):
        """把真值 defect_category 映射到對應檢查類型的分身欄位"""
        cons = CHECK_TYPE_TO_CATEGORIES['construction']
        safe = CHECK_TYPE_TO_CATEGORIES['safety_env']
        for rec in self:
            rec.defect_category_construction = rec.defect_category if rec.defect_category in cons else False
            rec.defect_category_safety = rec.defect_category if rec.defect_category in safe else False

    def _inverse_defect_category_proxy(self):
        """使用者在分身欄位選的值寫回真值 defect_category"""
        for rec in self:
            if rec.check_type == 'safety_env' and rec.defect_category_safety:
                rec.defect_category = rec.defect_category_safety
            elif rec.check_type == 'construction' and rec.defect_category_construction:
                rec.defect_category = rec.defect_category_construction

    @api.onchange('check_type')
    def _onchange_check_type_reset_category(self):
        """切換檢查類型時，若目前缺失類別不合法則重設為該類型預設值"""
        allowed = CHECK_TYPE_TO_CATEGORIES.get(self.check_type, [])
        if self.defect_category not in allowed:
            self.defect_category = CHECK_TYPE_DEFAULT_CATEGORY.get(self.check_type, False)

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
        if not (self.project_id and self.found_date):
            return
        origin = self._origin
        # 編輯已存檔記錄時：只有分組(工程/日期/檢查類型/記錄類型)真的改變才重算；
        # 若切回原分組則保留原序號，避免無謂跳號
        if origin and origin.id:
            same_group = (
                origin.project_id.id == self.project_id.id
                and origin.found_date == self.found_date
                and origin.check_type == self.check_type
                and origin.record_type == self.record_type
            )
            if same_group:
                self.sequence_number = origin.sequence_number
                return
        self.sequence_number = self._get_daily_sequence(
            self.project_id.id,
            self.found_date,
            self.check_type or 'construction',
            self.record_type or 'supervision',
            # 排除自己，避免把自己算進去而跳號
            exclude_id=origin.id if origin else False,
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
