# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
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
    """
    _name = 'general.defect.improvement'
    _description = '一般式缺失改善'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
    _order = 'notification_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='缺失編號',
        copy=False,
        readonly=True,
        compute='_compute_name',
        store=True,
        index=True)

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

    ncr_id = fields.Many2one(
        'supervision.defect',
        string='關聯 NCR',
        domain="[('project_id', '=', project_id)]",
        help='若需關聯 NCR 缺失單')

    # === 檢查類型 ===
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety_env', '安衛及環境清潔檢查'),
    ], string='檢查類型', required=True, default='construction', tracking=True)

    # === 缺失分類 ===
    defect_category = fields.Selection([
        ('material', '材料品質'),
        ('workmanship', '施工品質'),
        ('dimension', '尺寸偏差'),
        ('safety', '安全衛生'),
        ('environment', '環境清潔'),
        ('document', '文件缺漏'),
        ('other', '其他'),
    ], string='缺失類別', required=True, default='workmanship', tracking=True)

    severity = fields.Selection([
        ('minor', '輕微'),
        ('moderate', '中等'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ], string='嚴重程度', required=True, default='minor', tracking=True)

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

    # === 單位資訊 ===
    discovery_unit = fields.Char(
        string='發現單位',
        help='發現缺失的單位名稱')

    discovery_user_id = fields.Many2one(
        'res.users',
        string='發現人',
        default=lambda self: self.env.uid,
        tracking=True)

    improvement_unit = fields.Char(
        string='執行改善單位',
        help='負責改善的單位名稱')

    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='負責改善的施工廠商')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True,
        help='負責執行改善的人員')

    # === 日期 ===
    found_date = fields.Date(
        string='發現日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    notification_date = fields.Date(
        string='通知改善日期',
        default=fields.Date.today,
        tracking=True)

    deadline = fields.Date(
        string='改善期限',
        tracking=True)

    improvement_date = fields.Date(
        string='實際改善日期',
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

    # === 缺失內容 ===
    defect_location = fields.Char(
        string='缺失位置',
        help='發生缺失的具體位置')

    defect_description = fields.Text(
        string='缺失具體情形',
        required=True,
        tracking=True)

    defect_cause = fields.Text(
        string='缺失發生原因',
        help='分析缺失發生的根本原因')

    # === 改善資訊 ===
    improvement_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    prevention_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

    improvement_result = fields.Text(
        string='改善結果說明',
        help='改善完成後的結果說明')

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

    # === 複查資訊 ===
    recheck_date = fields.Date(string='複查日期', tracking=True)

    recheck_result = fields.Selection([
        ('pass', '通過'),
        ('fail', '不通過'),
        ('pending', '待複查'),
    ], string='複查結果', tracking=True)

    recheck_note = fields.Text(string='複查說明')

    # === 驗證資訊 ===
    verifier_id = fields.Many2one(
        'res.users',
        string='驗證人',
        tracking=True)

    verify_date = fields.Date(
        string='驗證日期')

    verify_result = fields.Selection([
        ('pass', '驗證通過'),
        ('fail', '驗證不通過'),
    ], string='驗證結果', tracking=True)

    verify_comment = fields.Text(
        string='驗證意見')

    # === 結案資訊 ===
    closer_id = fields.Many2one(
        'res.users',
        string='結案人',
        tracking=True)

    close_comment = fields.Text(
        string='結案說明')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('notified', '已通知'),
        ('improving', '改善中'),
        ('improved', '已改善'),
        ('verified', '已驗證'),
        ('closed', '結案'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 動作方法 ===
    def action_notify(self):
        """通知改善"""
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
                        f'缺失 <b>{record.name}</b> 已派發給您'
                        + (f'（執行改善單位：{unit}）' if unit else '') + '，'
                        f'請於 <b>{record.deadline}</b> 前完成改善。<br/>'
                        f'缺失說明：{record.defect_description or "（無）"}'
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_start_improvement(self):
        """開始改善"""
        for record in self:
            if record.state != 'notified':
                raise UserError('只有已通知狀態可以開始改善')
            record.state = 'improving'

    def action_complete_improvement(self):
        """完成改善"""
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
                    body=f'缺失 <b>{record.name}</b> 已完成改善，請複查。',
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_verify_pass(self):
        """驗證通過"""
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
        """驗證不通過"""
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
        """結案"""
        for record in self:
            if record.state != 'verified':
                raise UserError('只有已驗證狀態可以結案')
            record.write({
                'state': 'closed',
                'closer_id': self.env.uid,
                'closure_date': fields.Date.today(),
            })

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('verified', 'closed'):
                raise UserError('只有已驗證或結案狀態可以重新開啟')
            record.write({
                'state': 'improving',
                'closure_date': False,
                'closer_id': False,
                'verify_result': False,
            })

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('draft', 'notified'):
                raise UserError('只有草稿或已通知狀態可以重設')
            record.state = 'draft'

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

    # === 序號即時計算 ===
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
        # 確保同一 transaction 內剛建立的記錄已寫入 DB，避免查不到而重複序號
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

    @api.depends('project_id', 'found_date', 'check_type', 'record_type', 'sequence_number')
    def _compute_name(self):
        """自動生成缺失編號：編號前綴-檢查類型首字+民國年月日_序號"""
        for record in self:
            if not record.project_id or not record.found_date:
                record.name = '/'
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
            record.name = f"{prefix}-{check_prefix}{date_str}_{record.sequence_number}"

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

    def write(self, vals):
        """修改記錄時，若影響編號則重新計算"""
        result = super().write(vals)

        # 若修改影響編號的欄位，觸發重新計算
        if any(field in vals for field in ['sequence_number', 'found_date',
                                             'check_type', 'record_type', 'project_id']):
            self._compute_name()

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

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)',
         '缺失編號必須唯一！'),
        ('unique_sequence_per_day',
         'UNIQUE(project_id, found_date, check_type, record_type, sequence_number)',
         '同一天同工程同類型的序號不能重複！'),
    ]
