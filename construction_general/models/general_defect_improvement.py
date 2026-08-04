# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


# 照片資料表收斂（2026-07-31）：原本這裡有兩個類別 ——
#   GeneralDefectImprovementPhoto（照片行中間表，image=Binary(attachment=True)）
#   SupervisionPhotoGeneralDefectCascade（把照片行註冊進反向級聯名單）
# 連同整套「解鎖欄位附件 / 反向刪 supervision.photo / 遞迴防護」機制一併移除：
# 照片現在就是 supervision.photo 本身，靠 general_defect_id 掛在缺失上
# （見 models/supervision_photo.py），沒有中間表、沒有同步。


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
    # photo.sync.mixin 已隨照片資料表收斂退場
    _inherit = ['construction.daily.defect.mixin', 'mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
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
        'project.project',
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

    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='負責改善的施工廠商')

    # === 照片 (新結構) ===
    # 照片收斂：直接就是 supervision.photo，photo_stage 搬到那邊，三個 domain 語意不變
    photo_ids = fields.One2many(
        'supervision.photo',
        'general_defect_id',
        string='所有照片')

    before_photo_ids = fields.One2many(
        'supervision.photo',
        'general_defect_id',
        string='矯正及預防前照片',
        domain=[('photo_stage', '=', 'before')])

    during_photo_ids = fields.One2many(
        'supervision.photo',
        'general_defect_id',
        string='矯正及預防中照片',
        domain=[('photo_stage', '=', 'during')])

    after_photo_ids = fields.One2many(
        'supervision.photo',
        'general_defect_id',
        string='矯正及預防後照片',
        domain=[('photo_stage', '=', 'after')])

    # === 其他附件 (保留，非照片附件) ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關文件附件',
        help='非照片類型的其他附件文件')

    def _attachment_default_category(self):
        """缺失改善附件 → 12-文書資料 / 06-缺失改善"""
        return self.env.ref(
            'construction_supervision_base.cat_12_06',
            raise_if_not_found=False) or super()._attachment_default_category()

    # === 向後兼容欄位 (保留舊欄位名，用於數據遷移) ===
    # 兩個 legacy M2M 欄位（general_defect_photo_rel / general_improvement_photo_rel）
    # 已隨照片收斂移除 —— 兩張中間表實測皆為 0 筆，註解本來就寫「不要直接使用」。

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
    # `_cron_check_overdue` / `_cron_send_overdue_notification` 已上收到共用的
    # construction.daily.defect.mixin（原本一般式/預約式各寫一份且行為不一致）。
    # 排程註冊在 construction_general/data/ir_cron_data.xml。

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
        # 照片行的 defect_improvement_id 是 ondelete='cascade'，PostgreSQL 會直接
        # 砍掉照片行、**不會**呼叫照片行的 Python unlink()，導致上面那套
        # 「順便刪 supervision.photo + 欄位附件」整條不會跑，留下照片管理裡看得到、
        # 點下去卻 404 的孤兒照片與孤兒 filestore 檔案。
        # 這裡明確先走一次 ORM unlink，讓那條邏輯生效。
        self.photo_ids.unlink()
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

    # 照片資料表收斂後，_get_photo_sync_config() 與 _auto_sync_photos() 覆寫
    # 都已移除（原本約 110 行）：照片本來就是 supervision.photo。
