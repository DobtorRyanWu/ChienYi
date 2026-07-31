# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import datetime, time, timedelta

import babel.dates
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DailyLogSheet(models.Model):
    """
    Construction Daily Log Sheet - Reference hr_timesheet_sheet design

    修改說明（v2.0）：
    - 改為單日記錄（移除 sheet_range, date_start, date_end）
    - 專案關聯改為 supervision.project
    - 新增工期資訊欄位
    - 新增天氣欄位（weather_am, weather_pm）
    - 新增其餘日誌事項欄位
    - employee_id 預設值改為只搜尋當前公司
    
    Supports 4-state workflow: new -> draft -> confirm -> done
    Multi-company isolation for contractor access control
    """
    _name = 'daily.log.sheet'
    _description = 'Construction Daily Log Sheet'
    # photo.sync.mixin 已隨照片資料表收斂退場（照片就是 supervision.photo 本身）
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state_sequence asc, log_date asc, id asc'
    _rec_name = 'complete_name'

    # === Basic Information ===
    name = fields.Char(
        string='名稱',
        compute='_compute_name',
        store=True,
    )
    complete_name = fields.Char(
        string='完整名稱',
        compute='_compute_complete_name',
        store=True,
    )

    # === Project Reference (需求一：改為直接關聯 supervision.project) ===
    supervision_project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        required=True,
        tracking=True,
        domain="[('state', 'in', ['construction', 'completion'])]",
        help='關聯的工程案件',
    )
    
    # 保留 project_id 作為 related 欄位
    project_id = fields.Many2one(
        'project.project',
        string='原生專案',
        related='supervision_project_id',
        store=True,
        readonly=True,
    )
    
    project_type = fields.Selection(
        related='supervision_project_id.project_type',
        string='專案類型',
        store=True,
        readonly=True,
    )

    # === Multi-Company Architecture (v5.0) ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='施工公司(用於資料隔離)',
    )

    # Related tasks for validation
    task_ids = fields.Many2many(
        'project.task',
        string='相關任務',
        domain="[('project_id', '=', project_id)]",
        help='此日誌中記錄的任務',
    )

    # Reservation type specific
    notification_slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='報備單',
        domain="[('project_id', '=', supervision_project_id)]",
        help='限報備型專案使用',
    )

    # === Period (需求三：改為單日記錄) ===
    log_date = fields.Date(
        string='日誌日期',
        required=True,
        index=True,
        default=fields.Date.context_today,
        tracking=True,
        help='施工日誌記錄日期',
    )

    # === Employee Information (需求二：修改預設值邏輯) ===
    employee_id = fields.Many2one(
        'hr.employee',
        string='提交人員',
        required=True,
        default=lambda self: self._default_employee(),
        tracking=True,
        readonly=True,
        help='自動帶入當前登入使用者對應的員工（優先當前公司，找不到則不限公司）',
    )
    user_id = fields.Many2one(
        'res.users',
        string='使用者',
        related='employee_id.user_id',
        store=True,
        readonly=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='部門',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )

    # === 工期資訊（需求四：從 supervision_project 自動帶入）===
    contract_duration = fields.Integer(
        string='核定工期(日)',
        related='supervision_project_id.contract_duration',
        store=True,
        readonly=True,
        help='契約核定工期',
    )

    extension_duration = fields.Integer(
        string='工期展延(日)',
        related='supervision_project_id.extension_duration',
        store=True,
        readonly=True,
        help='經核准的工期展延天數',
    )

    total_approved_duration = fields.Integer(
        string='總核定工期(日)',
        related='supervision_project_id.total_approved_duration',
        store=True,
        readonly=True,
        help='核定工期 + 工期展延',
    )

    cumulative_duration = fields.Integer(
        string='累計工期(日)',
        compute='_compute_duration_info',
        store=True,
        help='從開工日至本日誌日期的累計天數',
    )

    remaining_duration = fields.Integer(
        string='剩餘工期(日)',
        compute='_compute_duration_info',
        store=True,
        help='剩餘施工天數',
    )

    # === Daily Log Lines ===
    line_ids = fields.One2many(
        'daily.log.line',
        'sheet_id',
        string='施工日誌明細',
    )

    # === 工地材料管理 ===
    material_ids = fields.One2many(
        'daily.log.material',
        'daily_log_id',
        string='工地材料管理',
    )

    # === Weather Records (需求五：改為直接欄位) ===
    weather_am = fields.Selection([
        ('sunny', '晴天'),
        ('cloudy', '多雲'),
        ('overcast', '陰天'),
        ('rainy', '雨天'),
        ('heavy_rain', '豪雨'),
        ('typhoon', '颱風'),
        ('foggy', '霧'),
    ], string='上午天氣', tracking=True)

    weather_pm = fields.Selection([
        ('sunny', '晴天'),
        ('cloudy', '多雲'),
        ('overcast', '陰天'),
        ('rainy', '雨天'),
        ('heavy_rain', '豪雨'),
        ('typhoon', '颱風'),
        ('foggy', '霧'),
    ], string='下午天氣', tracking=True)
    
    # 保留舊的 weather_ids 關聯（向後兼容）
    weather_ids = fields.One2many(
        'daily.log.weather',
        'sheet_id',
        string='天氣記錄（已廢棄）',
    )

    # === 其餘日誌事項（需求六）===

    # (1) 技術士設置要求
    has_technician_requirement = fields.Selection([
        ('yes', '有'),
        ('no', '無'),
    ], string='本日施工項目是否有須依「營造業專業工程特定施工項目應置之技術士種類、比率或人數標準表」規定應設置技術士之專業工程',
       help='請選擇是否需要設置技術士')

    # (2) 工地職業安全衛生事項
    # (一) 施工前檢查事項
    safety_pre_work_education = fields.Selection([
        ('yes', '有'),
        ('no', '無'),
    ], string='實施勤前教育(含工地預防災變及危害告知)',
       help='是否已實施勤前教育')

    safety_labor_insurance_check = fields.Selection([
        ('yes', '有'),
        ('no', '無'),
        ('no_new_worker', '無新進勞工'),
    ], string='確認新進勞工是否提報勞工保險(或其他商業保險)資料及安全衛生教育訓練紀錄',
       help='是否已確認新進勞工保險與訓練紀錄；當日無新進勞工請選「無新進勞工」（本項不適用）')

    safety_ppe_check = fields.Selection([
        ('yes', '有'),
        ('no', '無'),
    ], string='檢查勞工個人防護具',
       help='是否已檢查個人防護具')

    # (二) 其他事項
    safety_other_matters = fields.Text(
        string='其他事項',
        help='工地職業安全衛生其他事項說明')

    # (3) 施工取樣試驗紀錄
    sampling_test_record = fields.Text(
        string='施工取樣試驗紀錄',
        help='記錄當日施工取樣與試驗情況')

    # (4) 通知協力廠商辦理事項
    subcontractor_notification = fields.Text(
        string='通知協力廠商辦理事項',
        help='需通知協力廠商處理的事項')

    # (5) 重要事項紀錄
    important_matters = fields.Text(
        string='重要事項紀錄',
        help='當日重要事項或特殊狀況記錄')

    # === State (Simplified - No Approval Workflow) ===
    state = fields.Selection([
        ('draft', '編輯中'),
        ('filled', '已填寫'),
        ('auto_locked', '自動鎖定'),
        ('locked', '已鎖定'),
    ], string='狀態', default='draft', tracking=True, required=True, index=True,
       help='編輯中→已填寫→已鎖定；超過14天由排程自動鎖定')

    state_sequence = fields.Integer(
        string='狀態排序',
        compute='_compute_state_sequence',
        store=True,
        index=True,
        help='用於排序：編輯中(1) > 已填寫(2) > 自動鎖定(3) > 已鎖定(4)',
    )

    STATE_SEQUENCE_MAP = {
        'draft': 1,
        'filled': 2,
        'auto_locked': 3,
        'locked': 4,
    }

    @api.depends('state')
    def _compute_state_sequence(self):
        for rec in self:
            rec.state_sequence = self.STATE_SEQUENCE_MAP.get(rec.state, 9)

    # === Auto-Lock Mechanism (14 days) ===
    # 自動鎖定天數（估驗/請款數量凍結窗口）。用具名常數取代散落的魔數 14。
    LOCK_DAYS = 14

    is_locked = fields.Boolean(
        string='是否已鎖定',
        compute='_compute_is_locked',
        store=True,
        help='日誌日期超過14天自動鎖定（僅供顯示/搜尋；實際編輯封鎖以 write() 即時判斷為準）',
    )
    
    days_since_log = fields.Integer(
        string='距今天數',
        compute='_compute_is_locked',
        help='日誌日期距離今天的天數',
    )
    
    lock_date = fields.Date(
        string='鎖定日期',
        readonly=True,
        help='日誌被鎖定的日期',
    )
    
    # === Unlock Authorization ===
    is_unlocked = fields.Boolean(
        string='已授權解鎖',
        default=False,
        tracking=True,
        help='高權限者授權臨時解鎖',
    )
    
    unlocked_by_id = fields.Many2one(
        'res.users',
        string='解鎖授權人',
        readonly=True,
        tracking=True,
    )
    
    unlock_date = fields.Datetime(
        string='解鎖時間',
        readonly=True,
    )
    
    unlock_reason = fields.Text(
        string='解鎖原因',
        tracking=True,
    )
    
    unlock_expires_at = fields.Datetime(
        string='解鎖失效時間',
        help='解鎖後依設定時長自動重新鎖定',
    )
    
    can_unlock = fields.Boolean(
        string='可解鎖',
        compute='_compute_can_unlock',
        help='使用者是否有解鎖權限',
    )

    # === Unlock Request Flow ===
    unlock_request_state = fields.Selection([
        ('none', '無申請'),
        ('pending', '待審核'),
        ('approved', '已批准'),
        ('rejected', '已駁回'),
    ], string='解鎖申請狀態', default='none', tracking=True)

    unlock_requested_by_id = fields.Many2one(
        'res.users', string='解鎖申請人', readonly=True)

    unlock_request_duration = fields.Selection([
        ('24', '1天'), ('72', '3天'), ('120', '5天'), ('168', '7天'),
    ], string='申請解鎖時長')

    unlock_request_reason = fields.Text(string='申請解鎖原因')

    # === Progress Information ===
    has_progress_change = fields.Boolean(
        string='有進度變更',
        default=False,
        help='標記是否有進度更新',
    )
    actual_progress = fields.Float(
        string='實際進度 (%)',
        digits=(5, 2),
    )

    # === 施工照片 ===
    # 照片資料表收斂：原本是 Many2many('ir.attachment', 'daily_log_sheet_photo_rel')
    # 再靠 photo.sync.mixin 同步出一份 supervision.photo。收斂後照片就是
    # supervision.photo 本身，沒有中間表也沒有同步，且每張照片天生帶有
    # 說明／材料分類／拍攝地點說明／座標（ir.attachment 放不下這些欄位）。
    photo_ids = fields.One2many(
        'supervision.photo',
        'daily_log_id',
        string='施工照片',
        help='本日施工現場照片')

    # === Notes ===
    work_summary = fields.Text(
        string='工作摘要',
        help='本日工作摘要',
    )
    notes = fields.Text(
        string='備註',
        help='其他附註說明',
    )

    # -------------------------------------------------------------------------
    # Default Methods
    # -------------------------------------------------------------------------

    def _default_employee(self):
        """
        取得當前使用者對應的員工記錄（限當前公司）
        
        設計邏輯（需求二）：
        1. 只搜尋當前公司的員工
        2. 不跨公司搜尋（避免資料混亂）
        3. 沒找到時返回 False，在 create 時統一處理錯誤
        
        業務邏輯說明：
        - 施工日誌屬於特定公司的專案
        - 只有該公司的員工可以填寫
        - 即使是"代為操作"，該員工記錄也必須在該公司下
        """
        employee = self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        # 代操作員可能在當前公司沒有員工資料，但在其他公司有 → 放寬為不限公司
        if not employee:
            employee = self.env['hr.employee'].search([
                ('user_id', '=', self.env.uid),
            ], limit=1)

        if not employee:
            _logger.warning(
                f'User {self.env.uid} ({self.env.user.name}) '
                f'has no hr.employee record in any company'
            )

        return employee

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('log_date', 'employee_id')
    def _compute_name(self):
        """Compute sheet name based on log date"""
        locale = self.env.context.get('lang') or self.env.user.lang or 'en_US'
        for sheet in self:
            if not sheet.log_date:
                sheet.name = 'New'
                continue

            sheet.name = babel.dates.format_skeleton(
                skeleton='MMMEd',
                datetime=datetime.combine(sheet.log_date, time.min),
                locale=locale,
            )

    @api.depends('name', 'employee_id', 'supervision_project_id')
    def _compute_complete_name(self):
        """Compute complete display name"""
        for sheet in self:
            parts = [sheet.name or 'New']
            if sheet.supervision_project_id:
                parts.append(sheet.supervision_project_id.name)
            if sheet.employee_id:
                parts.append(sheet.employee_id.name)
            sheet.complete_name = ' - '.join(parts)

    @api.depends('log_date', 'supervision_project_id.contract_start_date', 
                 'total_approved_duration')
    def _compute_duration_info(self):
        """計算累計與剩餘工期（需求四）"""
        for sheet in self:
            project = sheet.supervision_project_id
            if sheet.log_date and project and project.contract_start_date:
                # 計算累計工期
                delta = sheet.log_date - project.contract_start_date
                sheet.cumulative_duration = delta.days + 1
                
                # 計算剩餘工期
                total = sheet.total_approved_duration or 0
                sheet.remaining_duration = max(0, total - sheet.cumulative_duration)
            else:
                sheet.cumulative_duration = 0
                sheet.remaining_duration = 0

    def _is_validly_unlocked(self, now=None):
        """臨時解鎖是否仍有效（is_unlocked 且未過期）。"""
        self.ensure_one()
        if not self.is_unlocked:
            return False
        if self.unlock_expires_at:
            now = now or fields.Datetime.now()
            return now < self.unlock_expires_at
        # is_unlocked 但無到期時間 → 視為手動長期解鎖（沿用既有語意）
        return True

    def _is_edit_locked(self):
        """即時判斷編輯是否應被封鎖（不信任 stored is_locked，防 stale）。

        這是真正的封鎖判準：write()/unlink() 用它，而非 stored 的 is_locked——
        後者是 store=True compute、無隨時間變動的觸發源，會 stale（H2）。
        """
        self.ensure_one()
        if not self.log_date:
            return False
        if (fields.Date.today() - self.log_date).days < self.LOCK_DAYS:
            return False
        # 過 14 天：唯有「有效臨時解鎖」才可編輯（過期解鎖視同鎖定）
        return not self._is_validly_unlocked()

    @api.depends('log_date', 'is_unlocked', 'unlock_expires_at')
    def _compute_is_locked(self):
        """stored 值僅供顯示/搜尋；真正的編輯封鎖以 _is_edit_locked() 即時判斷。

        注意：此為 store=True compute 但依賴的 log_date/解鎖欄位不隨時間變動，
        stored 值會 stale（H2）。故不在此做任何 write 副作用（原本 compute 內
        以 sudo().write 重置解鎖 / 寫 lock_date 是反模式），改由 _cron_auto_lock 維護。
        """
        today = fields.Date.today()
        now = fields.Datetime.now()
        for sheet in self:
            if not sheet.log_date:
                sheet.days_since_log = 0
                sheet.is_locked = False
                continue
            days = (today - sheet.log_date).days
            sheet.days_since_log = days
            sheet.is_locked = (days >= sheet.LOCK_DAYS) and not sheet._is_validly_unlocked(now)
    
    def _compute_can_unlock(self):
        """計算使用者是否有解鎖權限"""
        for sheet in self:
            user = self.env.user
            sheet.can_unlock = (
                user.has_group('base.group_system') or
                user.has_group('construction_supervision_base.group_supervision_manager') or
                user.has_group('hr.group_hr_manager') or
                # 前台老闆/主管 + 監造代操：可直接解鎖（限時、有記錄）
                user.has_group('construction_supervision_base.group_portal_subscriber') or
                user.has_group('construction_supervision_base.group_portal_leader') or
                user.has_group('construction_supervision_base.group_operator')
            )

    def portal_unlock(self, hours=72, reason=None):
        """限時解鎖（前台/後台共用）：寫入解鎖記錄，到期自動重新鎖定。

        呼叫端須自行確認來源使用者可解鎖；本方法亦以 can_unlock 二次守門。
        回傳解鎖到期時間。
        """
        self.ensure_one()
        if not self.can_unlock:
            raise UserError('您沒有解鎖權限！')
        expires_at = fields.Datetime.now() + timedelta(hours=hours)
        vals = {
            'is_unlocked': True,
            'unlocked_by_id': self.env.uid,
            'unlock_date': fields.Datetime.now(),
            'unlock_reason': reason or '解鎖',
            'unlock_expires_at': expires_at,
        }
        # 自動鎖定的日誌解鎖後恢復為編輯中
        if self.state == 'auto_locked':
            vals['state'] = 'draft'
        self.write(vals)
        return expires_at

    # -------------------------------------------------------------------------
    # 狀態切換方法
    # -------------------------------------------------------------------------

    def action_mark_filled(self):
        """標記為已填寫（允許無明細，代表當日無施工）"""
        for sheet in self:
            sheet.state = 'filled'

    def action_revert_to_draft(self):
        """退回編輯中"""
        for sheet in self:
            sheet.state = 'draft'

    # -------------------------------------------------------------------------
    # 自動鎖定排程（Cron Job）
    # -------------------------------------------------------------------------

    def _cron_auto_lock(self):
        """排程：自動鎖定超過14天的施工日誌，並維護 stored is_locked 顯示值。"""
        today = fields.Date.today()
        now = fields.Datetime.now()
        cutoff = today - timedelta(days=self.LOCK_DAYS)

        # 0) 重置已過期的臨時解鎖（原本靠 compute 內 sudo().write，已移除該副作用）
        expired = self.search([
            ('is_unlocked', '=', True),
            ('unlock_expires_at', '!=', False),
            ('unlock_expires_at', '<', now),
        ])
        if expired:
            expired.write({'is_unlocked': False, 'unlock_expires_at': False})

        # 1) 狀態機：draft/filled 過期 → auto_locked
        logs = self.search([
            ('log_date', '<=', cutoff),
            ('state', 'in', ('draft', 'filled')),
            ('is_unlocked', '=', False),
        ])
        if logs:
            logs.write({'state': 'auto_locked'})
            _logger.info('自動鎖定 %d 筆施工日誌（超過14天）', len(logs))

        # 2) 刷新 stored is_locked 顯示值（stored compute 無時間觸發會 stale）
        stale = self.search([
            ('log_date', '<=', cutoff),
            ('is_locked', '=', False),
            ('is_unlocked', '=', False),
        ])
        if stale:
            stale.invalidate_recordset(['is_locked'])
            stale.modified(['log_date'])  # 觸發 stored compute 重算並落庫
            _logger.info('刷新 %d 筆 stale 的 is_locked 顯示值', len(stale))

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('log_date', 'company_id', 'employee_id', 'supervision_project_id')
    def _check_overlapping_sheets(self):
        """Check for overlapping sheets（需求三：改為檢查同一天）"""
        for sheet in self:
            domain = [
                ('id', '!=', sheet.id),
                ('log_date', '=', sheet.log_date),
                ('employee_id', '=', sheet.employee_id.id),
                ('company_id', '=', sheet.company_id.id),
                ('supervision_project_id', '=', sheet.supervision_project_id.id),
            ]
            overlapping = self.search(domain, limit=1)
            if overlapping:
                raise ValidationError(
                    f'同一專案在同一天已存在日誌: {overlapping.complete_name}'
                )

    # 註：原 _check_company_employee（日誌公司必須等於員工公司）已移除。
    # 代操作員跨公司建立日誌時，員工（提交人）與專案/日誌可屬不同公司，
    # 日誌公司改為跟隨「選定的專案」，不再與員工公司綁定。

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('supervision_project_id')
    def _onchange_supervision_project_id(self):
        """Clear notification slip when project changes; 公司跟隨選定的專案"""
        if self.supervision_project_id:
            self.notification_slip_id = False
            if self.supervision_project_id.company_id:
                self.company_id = self.supervision_project_id.company_id

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------



    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立時確保 employee_id 有值（不限公司）；公司跟隨選定的專案（代操作員可跨公司）"""
        for vals in vals_list:
            # 如果沒有 employee_id，嘗試自動填入（不限公司）
            if 'employee_id' not in vals or not vals.get('employee_id'):
                employee = self._default_employee()

                if employee:
                    vals['employee_id'] = employee.id
                else:
                    # 使用者在任何公司都沒有員工資料 → 提示建立
                    raise UserError(
                        f'無法建立施工日誌！\n\n'
                        f'您的使用者帳號 ({self.env.user.name}) '
                        f'沒有對應的員工（hr.employee）資料。\n\n'
                        f'請依照以下步驟處理：\n'
                        f'1. 進入「人力資源 > 員工」\n'
                        f'2. 建立一筆您的員工資料\n'
                        f'3. 在員工資料的「工作資訊」頁籤中，設定「相關使用者」為您的帳號\n'
                        f'4. 儲存後重新嘗試建立施工日誌'
                    )

            # 公司跟隨選定的專案：代操作員跨公司時，日誌歸屬專案所屬公司
            if vals.get('supervision_project_id'):
                project = self.env['project.project'].browse(
                    vals['supervision_project_id'])
                if project.company_id:
                    vals['company_id'] = project.company_id.id

        sheets = super().create(vals_list)
        # No need for state transition - default is already 'draft'
        return sheets

    def write(self, vals):
        """檢查鎖定狀態：鎖定只凍結「使用者輸入欄位」，不阻擋系統重算「衍生計算欄位」。"""
        # 用即時判斷（_is_edit_locked）而非 stale 的 stored is_locked（H2）
        locked_sheets = self.filtered(lambda s: s._is_edit_locked())

        if locked_sheets:
            # 解鎖管理欄位 + state（cron 自動鎖定需改 state）
            # 含解鎖「申請」相關欄位：鎖定中的日誌本來就需要透過「申請解鎖 → 審核」
            # 流程才能解鎖，故這些欄位必須允許在鎖定狀態下寫入，否則申請與審核都會被擋。
            unlock_fields = {
                'is_unlocked', 'unlocked_by_id', 'unlock_date',
                'unlock_reason', 'unlock_expires_at', 'lock_date',
                'state',
                'unlock_request_state', 'unlock_requested_by_id',
                'unlock_request_reason', 'unlock_request_duration',
            }
            # 計算（衍生）欄位：如「本日預定進度／有無進度變更／變更後本日預定進度／
            # 完成率」等，是依「當下核定計畫」推導出來的值。新版進度表啟用時系統會重算
            # 這些欄位，屬「衍生視圖更新」而非「竄改歷史輸入」，故允許寫入已鎖定日誌。
            # 真正受鎖定保護的是「使用者輸入欄位」（本日完成數量、天氣、人機、備註…）。
            computed_fields = {n for n, f in self._fields.items() if f.compute}
            # A（2026-07-14）：照片為附加證據，不改動日誌的「使用者輸入欄位」內容，
            # 故鎖定（超過 14 天）後仍允許「補照片」（歷史建檔需求）。
            # 真正受鎖定保護的輸入欄位（完成數量/天氣/人機/備註…）不受此影響。
            photo_fields = {'photo_ids'}
            blocked = set(vals.keys()) - unlock_fields - computed_fields - photo_fields
            if blocked:
                raise UserError(
                    '無法修改已鎖定的日誌！\n\n'
                    f'以下日誌已鎖定（超過14天）：\n' +
                    '\n'.join([f'- {s.complete_name}' for s in locked_sheets]) +
                    '\n\n請聯繫管理員申請解鎖。'
                )

        res = super().write(vals)
        return res

    def unlink(self):
        """防止刪除已鎖定的日誌"""
        for sheet in self:
            if sheet._is_edit_locked():
                raise UserError(
                    f'無法刪除已鎖定的日誌: {sheet.complete_name}\n'
                    f'請先申請解鎖。'
                )
        return super().unlink()

    def copy(self, default=None):
        """Prevent sheet duplication by default"""
        if not self.env.context.get('allow_copy_sheet'):
            raise UserError('不允許複製施工日誌表單。')
        return super().copy(default=default)

    # -------------------------------------------------------------------------
    # Lock/Unlock Action Methods
    # -------------------------------------------------------------------------

    def action_unlock(self):
        """開啟解鎖精靈（有權限者直接解鎖，無權限者提出申請）"""
        self.ensure_one()

        if not self.is_locked:
            raise UserError('此日誌尚未鎖定，無需解鎖。')

        # 開啟解鎖精靈
        return {
            'type': 'ir.actions.act_window',
            'name': '解鎖日誌',
            'res_model': 'daily.log.unlock.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sheet_id': self.id,
            },
        }

    def action_approve_unlock_request(self):
        """批准解鎖申請"""
        self.ensure_one()
        if not self.can_unlock:
            raise UserError('您沒有解鎖權限！')
        hours = int(self.unlock_request_duration)
        expires_at = fields.Datetime.now() + timedelta(hours=hours)
        self.write({
            'is_unlocked': True,
            'unlocked_by_id': self.env.uid,
            'unlock_date': fields.Datetime.now(),
            'unlock_reason': self.unlock_request_reason,
            'unlock_expires_at': expires_at,
            'unlock_request_state': 'approved',
        })
        if self.state == 'auto_locked':
            self.state = 'draft'
        if self.unlock_requested_by_id and self.unlock_requested_by_id.partner_id:
            self.message_post(
                body=f'✅ 解鎖申請已批准，有效至 {expires_at.strftime("%Y-%m-%d %H:%M")}',
                partner_ids=[self.unlock_requested_by_id.partner_id.id],
                message_type='notification',
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '已批准',
                'message': f'解鎖申請已批准，有效至 {expires_at.strftime("%Y-%m-%d %H:%M")}',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reject_unlock_request(self):
        """駁回解鎖申請"""
        self.ensure_one()
        if not self.can_unlock:
            raise UserError('您沒有解鎖權限！')
        self.write({'unlock_request_state': 'rejected'})
        if self.unlock_requested_by_id and self.unlock_requested_by_id.partner_id:
            self.message_post(
                body='❌ 解鎖申請已駁回',
                partner_ids=[self.unlock_requested_by_id.partner_id.id],
                message_type='notification',
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '已駁回',
                'message': '解鎖申請已駁回',
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_relock(self):
        """重新鎖定日誌"""
        self.ensure_one()
        
        if not self.can_unlock:
            raise UserError('您沒有權限執行此操作。')
        
        self.write({
            'is_unlocked': False,
            'unlock_expires_at': False,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '已重新鎖定',
                'message': '日誌已重新鎖定',
                'type': 'success',
            }
        }
    
    def action_add_items_wizard(self):
        """開啟批次新增工項精靈"""
        self.ensure_one()

        # 檢查是否已鎖定
        if self.is_locked and not self.is_unlocked:
            raise UserError(
                '日誌已鎖定，無法新增工項！\n'
                '請先申請解鎖。'
            )

        # 先建立 wizard 記錄（含 lines），確保資料在資料庫中
        # 這樣 One2many 列表才能使用原生勾選框（含全選）
        wizard = self.env['daily.log.add.items.wizard'].create({
            'sheet_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': '新增施工項目',
            'res_model': 'daily.log.add.items.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_view_lines(self):
        """Action to view daily log lines"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '施工日誌明細',
            'res_model': 'daily.log.line',
            'view_mode': 'list,form',
            'domain': [('sheet_id', '=', self.id)],
            'context': {
                'default_sheet_id': self.id,
                'default_project_id': self.project_id.id,
                'default_employee_id': self.employee_id.id,
            },
        }

    # 照片資料表收斂後不再需要 _get_photo_sync_config()：照片就是
    # supervision.photo 本身（photo_ids 是 One2many），沒有「同步」這件事。


