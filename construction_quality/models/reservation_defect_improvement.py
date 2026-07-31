# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


# 照片資料表收斂（2026-07-31）：原本這裡有兩個類別 ——
#   ReservationDefectImprovementPhoto（照片行中間表，image=Binary(attachment=True)）
#   SupervisionPhotoReservationDefectCascade（把照片行註冊進反向級聯名單）
# 連同整套「解鎖欄位附件 / 反向刪 supervision.photo / 遞迴防護」機制一併移除：
# 照片現在就是 supervision.photo 本身，靠 reservation_defect_id 掛在缺失上
# （見 models/supervision_photo.py），沒有中間表、沒有同步，自然也沒有
# 「兩張表互相 RESTRICT 鎖死」那類問題。


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
    # photo.sync.mixin 已隨照片資料表收斂退場
    _inherit = ['construction.daily.defect.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'notification_date desc, id desc'

    # === 通報單關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='所屬通報單',
        required=True,
        ondelete='cascade',
        tracking=True)

    project_id = fields.Many2one(
        'project.project',
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

    # === 照片（收斂後直接就是 supervision.photo）===
    # photo_stage 從舊的照片行搬到 supervision.photo 上，三個 domain 的語意不變。
    photo_ids = fields.One2many(
        'supervision.photo',
        'reservation_defect_id',
        string='所有照片')

    before_photo_ids = fields.One2many(
        'supervision.photo',
        'reservation_defect_id',
        string='矯正及預防前照片',
        domain=[('photo_stage', '=', 'before')])

    during_photo_ids = fields.One2many(
        'supervision.photo',
        'reservation_defect_id',
        string='矯正及預防中照片',
        domain=[('photo_stage', '=', 'during')])

    after_photo_ids = fields.One2many(
        'supervision.photo',
        'reservation_defect_id',
        string='矯正及預防後照片',
        domain=[('photo_stage', '=', 'after')])

    # === 相關文件附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reservation_defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關文件附件',
        help='非照片類型的其他附件文件')

    # 兩個 legacy M2M 欄位（reservation_defect_photo_rel /
    # reservation_improvement_photo_rel）已隨照片收斂移除 —— 兩張中間表實測
    # 皆為 0 筆，且註解本來就寫「數據遷移用，不要直接使用」。

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
    # 原本這裡的 `_cron_check_overdue` 名為「檢查」但實際只發通知、從不刷新 is_overdue，
    # 與一般式的同名方法行為不一致，且沒有任何 ir.cron 註冊它 → 「預約式逾期缺失」選單
    # （domain: is_overdue = True）等於永遠是空的。
    # 已上收到共用的 construction.daily.defect.mixin：
    #   _cron_check_overdue            → 刷新 is_overdue / overdue_days
    #   _cron_send_overdue_notification → 通知負責人
    # 排程註冊在 construction_quality/data/ir_cron_data.xml。

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

    def unlink(self):
        """刪除缺失前，先擋非草稿狀態，再用 ORM 刪掉照片行。

        狀態保護：與一般式 general_defect_improvement.unlink() 同一規則。
        少了它的話，前台對已驗證／結案缺失的「單張照片不可刪」形同虛設 ——
        使用者可以直接把整張缺失連同照片一起刪掉繞過去。
        檢查必須在 photo_ids.unlink() 之前，否則照片會先被刪才報錯（交易雖會
        rollback，但語意混亂且會誤導除錯）。

        照片行的 defect_improvement_id 是 ondelete='cascade'，PostgreSQL 會直接
        砍掉照片行、不會呼叫照片行的 Python unlink()，導致「順便刪 supervision.photo
        + 欄位附件」那條邏輯不會跑，留下孤兒照片與孤兒 filestore 檔案。
        """
        for record in self:
            if record.state not in ('draft',):
                raise UserError('只有草稿狀態的缺失可以刪除')
        self.photo_ids.unlink()
        return super().unlink()

    # === 約束 ===
    @api.constrains('deadline', 'notification_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.notification_date:
                if record.deadline < record.notification_date:
                    raise ValidationError('限定完成改善日期不得早於通知改善日期')

    # 照片資料表收斂後，_get_photo_sync_config() 與 _auto_sync_photos() 覆寫
    # 都已移除：照片本來就是 supervision.photo，不需要再把照片行「同步」成
    # 一份副本。原本那段 70 行的覆寫（去重、組 notes、補位置）的職責，
    # 現在分別由 supervision.photo 的欄位與 _normalize_source_fields() 承擔。
