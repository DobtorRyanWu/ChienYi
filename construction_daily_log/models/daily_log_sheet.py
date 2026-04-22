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
    _inherit = ['mail.thread', 'mail.activity.mixin', 'photo.sync.mixin']
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
        'supervision.project',
        string='工程案件',
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id), ('state', 'in', ['construction', 'completion'])]",
        help='關聯的工程案件',
    )
    
    # 保留 project_id 作為 related 欄位
    project_id = fields.Many2one(
        'project.project',
        string='原生專案',
        related='supervision_project_id.project_id',
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
        help='自動帶入當前登入使用者對應的員工（限當前公司）',
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
    ], string='確認新進勞工是否提報勞工保險(或其他商業保險)資料及安全衛生教育訓練紀錄',
       help='是否已確認新進勞工保險與訓練紀錄')

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
    is_locked = fields.Boolean(
        string='是否已鎖定',
        compute='_compute_is_locked',
        store=True,
        help='日誌日期超過14天自動鎖定',
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
    photo_ids = fields.Many2many(
        'ir.attachment',
        'daily_log_sheet_photo_rel',
        'sheet_id', 'attachment_id',
        string='施工照片',
        help='上傳本日施工現場照片，將自動同步至照片管理模組')

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
        
        if not employee:
            _logger.warning(
                f'User {self.env.uid} ({self.env.user.name}) '
                f'has no hr.employee record in company {self.env.company.name}'
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

    @api.depends('log_date', 'is_unlocked', 'unlock_expires_at')
    def _compute_is_locked(self):
        """計算是否應該鎖定（14天規則）"""
        from datetime import datetime, timedelta
        today = fields.Date.today()
        now = fields.Datetime.now()
        
        for sheet in self:
            if not sheet.log_date:
                sheet.days_since_log = 0
                sheet.is_locked = False
                continue
            
            # 計算距離今天的天數
            days = (today - sheet.log_date).days
            sheet.days_since_log = days
            
            # 檢查是否已解鎖且未過期
            if sheet.is_unlocked and sheet.unlock_expires_at:
                if now < sheet.unlock_expires_at:
                    # 解鎖仍有效
                    sheet.is_locked = False
                    continue
                else:
                    # 解鎖已過期，重新鎖定
                    sheet.sudo().write({
                        'is_unlocked': False,
                        'unlock_expires_at': False,
                    })
            
            # 14天規則
            if days >= 14:
                sheet.is_locked = True
                if not sheet.lock_date:
                    sheet.sudo().lock_date = today
            else:
                sheet.is_locked = False
    
    def _compute_can_unlock(self):
        """計算使用者是否有解鎖權限"""
        for sheet in self:
            user = self.env.user
            sheet.can_unlock = (
                user.has_group('base.group_system') or
                user.has_group('construction_supervision_base.group_supervision_manager') or
                user.has_group('hr.group_hr_manager')
            )

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
        """排程：自動鎖定超過14天的施工日誌"""
        cutoff = fields.Date.today() - timedelta(days=14)
        logs = self.search([
            ('log_date', '<=', cutoff),
            ('state', 'in', ('draft', 'filled')),
            ('is_unlocked', '=', False),
        ])
        if logs:
            logs.write({'state': 'auto_locked'})
            _logger.info('自動鎖定 %d 筆施工日誌（超過14天）', len(logs))

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

    @api.constrains('company_id', 'employee_id')
    def _check_company_employee(self):
        """Validate company and employee consistency"""
        for sheet in self.sudo():
            if (sheet.company_id and sheet.employee_id.company_id and
                    sheet.company_id != sheet.employee_id.company_id):
                raise ValidationError(
                    '日誌表單和員工的公司必須相同。'
                )

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Update company when employee changes"""
        if self.employee_id:
            company = self.employee_id.company_id or self.env.company
            self.company_id = company

    @api.onchange('supervision_project_id')
    def _onchange_supervision_project_id(self):
        """Clear notification slip when project changes"""
        if self.supervision_project_id:
            self.notification_slip_id = False

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------



    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立時確保 employee_id 有值且屬於正確的公司（需求二）"""
        for vals in vals_list:
            # 如果沒有 employee_id，嘗試自動填入
            if 'employee_id' not in vals or not vals.get('employee_id'):
                employee = self._default_employee()
                
                if employee:
                    vals['employee_id'] = employee.id
                else:
                    # 提供明確的錯誤訊息
                    raise UserError(
                        f'無法建立施工日誌！\n\n'
                        f'您的使用者帳號 ({self.env.user.name}) '
                        f'在公司「{self.env.company.name}」中沒有對應的員工資料。\n\n'
                        f'可能的原因：\n'
                        f'1. 您的員工資料尚未建立\n'
                        f'2. 您的員工資料屬於其他公司\n'
                        f'3. 您切換到了錯誤的公司\n\n'
                        f'請依照以下步驟處理：\n'
                        f'1. 確認當前選擇的公司是否正確（右上角公司選擇器）\n'
                        f'2. 進入「人力資源 > 員工」\n'
                        f'3. 確認您的員工資料存在且公司設定為「{self.env.company.name}」\n'
                        f'4. 在員工資料的「工作資訊」頁籤中，設定「相關使用者」為您的帳號\n'
                        f'5. 儲存後重新嘗試建立施工日誌'
                    )
            
            # 額外驗證：employee 的公司必須與當前公司一致
            if vals.get('employee_id'):
                employee = self.env['hr.employee'].browse(vals['employee_id'])
                if employee.company_id and employee.company_id != self.env.company:
                    raise UserError(
                        f'員工公司不符！\n\n'
                        f'員工「{employee.name}」屬於公司「{employee.company_id.name}」，\n'
                        f'但您目前在公司「{self.env.company.name}」中操作。\n\n'
                        f'請切換到正確的公司後再建立施工日誌。'
                    )
        
        sheets = super().create(vals_list)
        # No need for state transition - default is already 'draft'
        return sheets

    def write(self, vals):
        """檢查鎖定狀態，防止修改已鎖定的記錄"""
        # 檢查是否嘗試修改已鎖定的記錄
        locked_sheets = self.filtered(lambda s: s.is_locked and not s.is_unlocked)
        
        # 排除允許在鎖定狀態下修改的欄位
        unlock_fields = {
            'is_unlocked', 'unlocked_by_id', 'unlock_date',
            'unlock_reason', 'unlock_expires_at', 'lock_date',
            'state',  # cron auto_lock 需要修改 state
        }
        
        # 如果有鎖定的記錄，且不是解鎖操作
        if locked_sheets and not (set(vals.keys()) <= unlock_fields):
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
            if sheet.is_locked and not sheet.is_unlocked:
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
        """開啟解鎖精靈"""
        self.ensure_one()
        
        if not self.can_unlock:
            raise UserError(
                '您沒有解鎖權限！\n'
                '只有系統管理員、監造管理者或 HR 經理可以解鎖日誌。'
            )
        
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

    # -------------------------------------------------------------------------
    # 照片自動同步配置
    # -------------------------------------------------------------------------

    def _get_photo_sync_config(self):
        """配置施工日誌照片同步規則"""
        return {
            'photo_ids': {
                'source_model': 'daily_log',
                'name_prefix': '施工日誌照片',
                'description_template': '工程：{record.supervision_project_id.name}\n日期：{record.log_date}',
            },
        }


