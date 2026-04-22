# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta, datetime


class SupervisionProject(models.Model):
    """
    工程案件主檔

    設計特點：
    - 委派繼承 project.project，自動繼承分析帳戶
    - 支援一般式與預約式兩種工程類型
    - 多公司架構：管理公司(設計監造) + 承包廠商
    """
    _name = 'supervision.project'
    _description = '工程案件主檔'
    _inherits = {'project.project': 'project_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code desc, id desc'

    # === 關聯原生專案 ===
    project_id = fields.Many2one(
        'project.project', string='專案',
        required=True, ondelete='cascade', auto_join=True,
        help='關聯 Odoo 原生專案，自動繼承分析帳戶')

    # === 基本資料 ===
    code = fields.Char(
        string='工程編號', required=True, copy=False, index=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('supervision.project') or '/')

    # === 工程類型 ===
    project_type = fields.Selection([
        ('general', '一般式'),
        ('reservation', '預約式'),
    ], string='工程類型', required=True, default='general', tracking=True,
       help='一般式: 單一工程案件管理; 預約式: 多通報單工程管理')

    # === 年份 ===
    @api.model
    def _get_year_selection(self):
        """生成民國年選項列表 (當前年份±15年)"""
        current_minguo = datetime.now().year - 1911
        return [(str(y), f'民國 {y} 年') 
                for y in range(current_minguo - 15, current_minguo + 16)]

    year = fields.Selection(
        selection=_get_year_selection,
        string='年份',
        default=lambda self: str(datetime.now().year - 1911),
        required=True,
        index=True,
        tracking=True,
        help='工程案件所屬民國年度')

    # === 多公司架構 ===
    company_id = fields.Many2one(
        'res.company', string='管理公司（系統）', required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'supervision')]",
        tracking=True,
        help='負責管理此專案的設計監造單位（多公司存取控制用）')

    management_company_name = fields.Char(
        string='管理公司',
        tracking=True,
        help='負責管理此專案的設計監造單位名稱（自由輸入）')

    contractor_company_ids = fields.Many2many(
        'res.company', 'supervision_project_contractor_rel',
        'project_id', 'company_id',
        string='承包廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='參與此專案的施工廠商公司')

    # === 業主資訊 ===
    authority_id = fields.Many2one(
        'res.partner', string='業主/主辦機關',
        domain="[('partner_type', '=', 'authority')]",
        tracking=True,
        help='政府機關，為請款對象')

    authority_contact_id = fields.Many2one(
        'res.partner', string='機關承辦人',
        domain="[('parent_id', '=', authority_id)]",
        help='機關承辦聯絡人')

    # === 契約資訊 ===
    contract_no = fields.Char(string='契約編號', tracking=True)

    contract_amount = fields.Monetary(
        string='契約金額',
        currency_field='currency_id',
        compute='_compute_contract_amount',
        inverse='_inverse_contract_amount',
        store=True,
        tracking=True,
        help='從工項自動計算，草稿/籌備階段可手動輸入')

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        default=lambda self: self.env.company.currency_id)

    contract_start_date = fields.Date(string='契約開工日', tracking=True)
    contract_end_date = fields.Date(
        string='預定契約完工日',
        tracking=True,
        help='最新調整後完工日，隨進度表啟用自動更新',
    )
    original_contract_end_date = fields.Date(
        string='原始契約完工日',
        tracking=True,
        readonly=True,
        help='初始契約完工日，作為進度表展延計算基準',
    )

    contract_duration = fields.Integer(
        string='契約工期(日)',
        compute='_compute_contract_duration', store=True)

    @api.depends('contract_start_date', 'contract_end_date')
    def _compute_contract_duration(self):
        for project in self:
            if project.contract_start_date and project.contract_end_date:
                delta = project.contract_end_date - project.contract_start_date
                project.contract_duration = delta.days + 1
            else:
                project.contract_duration = 0

    # 原始核定工期：開工時凍結，不隨展延變動（由 action_construct 設定）
    original_duration = fields.Integer(
        string='原始核定工期(日)',
        default=0,
        tracking=True,
        help='初始核定工期（開工時自動凍結），作為進度表展延計算基準',
    )

    # === 工期展延 ===
    extension_duration = fields.Integer(
        string='累計核准展延工期(日)',
        default=0,
        tracking=True,
        help='由進度表啟用時自動累計，請勿手動修改',
    )

    total_approved_duration = fields.Integer(
        string='總核定工期(日)',
        compute='_compute_total_approved_duration',
        store=True,
        help='原契約工期 + 核准展延工期',
    )

    @api.depends('contract_duration', 'extension_duration')
    def _compute_total_approved_duration(self):
        """計算總核定工期"""
        for project in self:
            project.total_approved_duration = (
                (project.contract_duration or 0) + 
                (project.extension_duration or 0)
            )

    @api.depends('task_ids.planned_amount', 'task_ids.active')
    def _compute_contract_amount(self):
        """從工項計算契約金額"""
        for project in self:
            if project.task_count > 0:
                # 有工項：自動從工項計算
                project.contract_amount = sum(
                    project.task_ids.filtered('active').mapped('planned_amount'))
                
                # 首次計算時，如果沒有原始金額則設定
                if not project.original_contract_amount:
                    project.original_contract_amount = project.contract_amount
            # 無工項：保留手動輸入的值（不做任何事）

    def _inverse_contract_amount(self):
        """只允許在特定條件下手動設定"""
        for project in self:
            # 檢查是否允許手動修改
            if project.task_count > 0:
                raise UserError(
                    '已匯入工項，契約金額自動從工項計算，無法手動修改！\n'
                    f'當前工項總額：{project.contract_amount:,.0f}'
                )
            if project.state != 'draft':
                raise UserError(
                    '只有未開始階段可以手動設定契約金額！\n'
                    f'當前狀態：{dict(self._fields["state"].selection)[project.state]}'
                )
            # 如果通過檢查，Odoo 會自動寫入

    # === 實際日期 ===
    actual_start_date = fields.Date(string='實際開工日', tracking=True)
    actual_end_date = fields.Date(string='實際完工日', tracking=True)

    actual_duration = fields.Integer(
        string='實際工期(日)',
        compute='_compute_actual_duration', store=True)

    @api.depends('actual_start_date', 'actual_end_date')
    def _compute_actual_duration(self):
        for project in self:
            if project.actual_start_date and project.actual_end_date:
                delta = project.actual_end_date - project.actual_start_date
                project.actual_duration = delta.days + 1
            else:
                project.actual_duration = 0

    # === 人員資訊 ===
    supervision_engineer_id = fields.Many2one(
        'res.users', string='監造工程師',
        domain="[('company_id', '=', company_id)]",
        tracking=True)

    site_manager_id = fields.Many2one(
        'res.users', string='工地主任',
        help='施工廠商指派的工地主任')

    # === 活動指派設定 ===
    activity_default_user_id = fields.Many2one(
        'res.users', string='預設活動負責人',
        help='未指定專屬負責人時，活動預設指派給此人')
    activity_test_user_id = fields.Many2one(
        'res.users', string='檢試驗負責人',
        help='檢試驗相關活動的負責人')
    activity_inspection_user_id = fields.Many2one(
        'res.users', string='自主檢查負責人',
        help='自主檢查相關活動的負責人')

    def _get_activity_user(self, activity_category='default'):
        """
        取得活動指派對象

        優先順序：專屬負責人 > 預設負責人 > 監造工程師 > 專案負責人
        :param activity_category: 'test', 'inspection', 'default'
        """
        self.ensure_one()
        if activity_category == 'test' and self.activity_test_user_id:
            return self.activity_test_user_id
        if activity_category == 'inspection' and self.activity_inspection_user_id:
            return self.activity_inspection_user_id
        if self.activity_default_user_id:
            return self.activity_default_user_id
        if self.supervision_engineer_id:
            return self.supervision_engineer_id
        return self.user_id or self.env.user

    # === 工程位置 ===
    location = fields.Char(string='工程地點')
    location_detail = fields.Text(string='詳細位置說明')
    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '未開始'),
        ('construction', '施工中'),
        ('completion', '已竣工'),
        ('acceptance', '驗收中'),
        ('closed', '已結案'),
        ('suspended', '停工'),
        ('terminated', '終止'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 初始化設定指標 ===
    INIT_STATUS_SELECTION = [
        ('pending', '待設定'),
        ('done', '已完成'),
        ('not_required', '不適用'),
    ]

    init_equipment_status = fields.Selection(
        INIT_STATUS_SELECTION, string='人機管理', default='pending')
    init_inspection_status = fields.Selection(
        INIT_STATUS_SELECTION, string='自主檢查', default='pending')
    init_test_status = fields.Selection(
        INIT_STATUS_SELECTION, string='檢試驗設定', default='pending')
    init_template_status = fields.Selection(
        INIT_STATUS_SELECTION, string='樣板', default='pending')
    init_schedule_status = fields.Selection(
        INIT_STATUS_SELECTION, string='進度表', default='pending')
    init_prefix_status = fields.Selection(
        INIT_STATUS_SELECTION, string='編號前綴設定', default='pending')

    # === 初始化循序確認 ===
    INIT_STEP_ORDER = ['equipment', 'inspection', 'prefix', 'test', 'template', 'schedule']

    init_current_step = fields.Selection([
        ('equipment', '人機管理'),
        ('inspection', '自主檢查'),
        ('prefix', '編號前綴設定'),
        ('test', '檢試驗'),
        ('template', '樣板'),
        ('schedule', '進度表'),
        ('done', '全部完成'),
    ], compute='_compute_init_current_step', string='當前初始化步驟')

    all_init_done = fields.Boolean(
        compute='_compute_init_current_step', string='初始化全部完成')

    # === 初始化數量統計 ===
    init_equipment_count = fields.Integer(
        compute='_compute_init_counts', string='人機項目數')
    init_inspection_count = fields.Integer(
        compute='_compute_init_counts', string='自主檢查類型數')
    init_test_count = fields.Integer(
        compute='_compute_init_counts', string='檢試驗項目數')
    init_template_count = fields.Integer(
        compute='_compute_init_counts', string='樣板數')
    init_prefix_count = fields.Integer(
        compute='_compute_init_counts', string='編號前綴數')

    @api.depends('init_equipment_status', 'init_inspection_status', 'init_prefix_status',
                 'init_test_status', 'init_template_status', 'init_schedule_status')
    def _compute_init_current_step(self):
        for rec in self:
            current = 'done'
            for step in self.INIT_STEP_ORDER:
                if getattr(rec, f'init_{step}_status') == 'pending':
                    current = step
                    break
            rec.init_current_step = current
            rec.all_init_done = (current == 'done')

    def _compute_init_counts(self):
        """安全計算各初始化功能的記錄數量（模組未安裝時回傳 0）"""
        def safe_count(model_name, domain):
            if model_name in self.env:
                return self.env[model_name].search_count(domain)
            return 0

        for rec in self:
            pid = rec.id
            rec.init_equipment_count = safe_count(
                'personnel.type', [])
            rec.init_inspection_count = safe_count(
                'self.inspection.type', [('project_id', '=', pid)])
            rec.init_test_count = safe_count(
                'supervision.test.standard', [('project_id', '=', pid)])
            rec.init_template_count = safe_count(
                'document.template', [('project_id', '=', pid)])
            rec.init_prefix_count = safe_count(
                'defect.improvement.prefix.config', [('project_id', '=', pid)])

    # === 初始化設定動作 ===
    def _init_set_status(self, field_name, value):
        """通用：設定初始化狀態"""
        self.ensure_one()
        self[field_name] = value

    def _init_goto(self, model_name, display_name, project_field='project_id'):
        """通用：跳轉到功能 list view"""
        self.ensure_one()
        # 檢查目標模組是否已安裝
        if model_name not in self.env:
            raise UserError(
                f'「{display_name}」功能模組尚未安裝，請先安裝對應模組。'
            )
        action = {
            'type': 'ir.actions.act_window',
            'name': display_name,
            'res_model': model_name,
            'view_mode': 'list,form',
        }
        if project_field:
            action['domain'] = [(project_field, '=', self.id)]
            action['context'] = {f'default_{project_field}': self.id}
        return action

    # 人機管理（全域設定，不按 project 過濾）
    def action_init_goto_equipment(self):
        return self._init_goto('personnel.type', '人員機具設定', project_field=None)

    def action_init_done_equipment(self):
        self._init_set_status('init_equipment_status', 'done')

    def action_init_skip_equipment(self):
        self._init_set_status('init_equipment_status', 'not_required')

    # 自主檢查
    def action_init_goto_inspection(self):
        return self._init_goto('self.inspection.type', '自主檢查設定')

    def action_init_done_inspection(self):
        self._init_set_status('init_inspection_status', 'done')

    def action_init_skip_inspection(self):
        self._init_set_status('init_inspection_status', 'not_required')

    # 檢試驗設定
    def action_init_goto_test(self):
        return self._init_goto('supervision.test.standard', '檢試驗設定')

    def action_init_done_test(self):
        self._init_set_status('init_test_status', 'done')

    def action_init_skip_test(self):
        self._init_set_status('init_test_status', 'not_required')

    # 樣板
    def action_init_goto_template(self):
        return self._init_goto('document.template', '樣板管理', project_field=None)

    def action_init_done_template(self):
        self._init_set_status('init_template_status', 'done')

    def action_init_skip_template(self):
        self._init_set_status('init_template_status', 'not_required')

    # 編號前綴設定
    def action_init_goto_prefix(self):
        return self._init_goto('defect.improvement.prefix.config', '編號前綴設定')

    def action_init_done_prefix(self):
        self._init_set_status('init_prefix_status', 'done')

    def action_init_skip_prefix(self):
        self._init_set_status('init_prefix_status', 'not_required')

    # 進度表
    def action_init_goto_schedule(self):
        return self._init_goto('progress.schedule', '進度表')

    def action_init_done_schedule(self):
        self._init_set_status('init_schedule_status', 'done')

    def action_init_skip_schedule(self):
        self._init_set_status('init_schedule_status', 'not_required')

    # 回上一步
    def action_init_go_back(self):
        """回到上一步確認"""
        self.ensure_one()
        order = self.INIT_STEP_ORDER
        # 找到當前步驟的索引
        current_idx = len(order)  # 預設：全部完成
        for i, step in enumerate(order):
            if getattr(self, f'init_{step}_status') == 'pending':
                current_idx = i
                break
        if current_idx <= 0:
            raise UserError('已經是第一步了')
        prev_step = order[current_idx - 1]
        self._init_set_status(f'init_{prev_step}_status', 'pending')

    # === 預算與成本 ===
    budget_amount = fields.Monetary(
        string='預算金額', currency_field='currency_id')

    actual_cost = fields.Monetary(
        string='實際成本', currency_field='currency_id',
        compute='_compute_actual_cost', store=True)

    budget_usage_rate = fields.Float(
        string='預算使用率 (%)',
        compute='_compute_budget_usage_rate', store=True)

    @api.depends('task_ids.actual_amount')
    def _compute_actual_cost(self):
        for project in self:
            project.actual_cost = sum(project.task_ids.mapped('actual_amount'))

    @api.depends('budget_amount', 'actual_cost')
    def _compute_budget_usage_rate(self):
        for project in self:
            if project.budget_amount:
                project.budget_usage_rate = (project.actual_cost / project.budget_amount) * 100
            else:
                project.budget_usage_rate = 0.0

    # === 關聯欄位 ===
    document_ids = fields.One2many(
        'supervision.document', 'project_id', string='相關文件')

    document_count = fields.Integer(
        string='文件數', compute='_compute_document_count')

    @api.depends('document_ids')
    def _compute_document_count(self):
        for project in self:
            project.document_count = len(project.document_ids)

    # === 工項統計 ===
    task_count = fields.Integer(
        string='工項數', compute='_compute_task_statistics')

    assigned_task_count = fields.Integer(
        string='已分配工項', compute='_compute_task_statistics')

    completed_task_count = fields.Integer(
        string='已完成工項', compute='_compute_task_statistics')

    @api.depends('task_ids', 'task_ids.assigned_company_id', 'task_ids.assignment_state')
    def _compute_task_statistics(self):
        for project in self:
            tasks = project.task_ids
            project.task_count = len(tasks)
            project.assigned_task_count = len(tasks.filtered(lambda t: t.assigned_company_id))
            project.completed_task_count = len(tasks.filtered(
                lambda t: t.assignment_state in ('completed', 'accepted')))

    # === 備註 ===
    notes = fields.Html(string='備註說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', '工程編號必須唯一！'),
        ('contract_dates_check',
         'CHECK(contract_end_date >= contract_start_date)',
         '契約完工日必須晚於或等於開工日！'),
    ]

    # === 狀態動作 ===
    def action_approve(self):
        """開始施工"""
        for project in self:
            if project.state != 'draft':
                raise UserError('只有未開始狀態可以開始施工')
            if not project.contract_start_date:
                raise ValidationError('請先設定契約開工日')

            # 檢查初始化設定是否都已完成（不可有 pending）
            init_fields = {
                '人機管理': project.init_equipment_status,
                '自主檢查': project.init_inspection_status,
                '編號前綴設定': project.init_prefix_status,
                '檢試驗設定': project.init_test_status,
                '樣板': project.init_template_status,
                '進度表': project.init_schedule_status,
            }
            pending_items = [name for name, status in init_fields.items()
                             if status == 'pending']
            if pending_items:
                raise UserError(
                    f'以下初始化設定尚未完成：{", ".join(pending_items)}\n'
                    '請完成設定或標記為「不適用」後才能開始施工。'
                )

            # 凍結原始契約金額、完工日、工期
            if not project.original_contract_amount:
                project.original_contract_amount = project.contract_amount or 0.0
            if not project.original_contract_end_date and project.contract_end_date:
                project.original_contract_end_date = project.contract_end_date
            if not project.original_duration and project.contract_duration:
                project.original_duration = project.contract_duration

            project.state = 'construction'
            if not project.actual_start_date:
                project.actual_start_date = fields.Date.today()

    def action_complete(self):
        """竣工"""
        for project in self:
            if project.state != 'construction':
                raise UserError('只有施工中狀態可以竣工')
            project.state = 'completion'
            if not project.actual_end_date:
                project.actual_end_date = fields.Date.today()

    def action_accept(self):
        """進入驗收"""
        for project in self:
            if project.state != 'completion':
                raise UserError('只有已竣工狀態可以進入驗收')
            project.state = 'acceptance'

    def action_close(self):
        """結案"""
        for project in self:
            if project.state != 'acceptance':
                raise UserError('只有驗收中狀態可以結案')
            project.state = 'closed'

    def action_suspend(self):
        """停工"""
        for project in self:
            if project.state not in ('construction', 'completion'):
                raise UserError('只有施工中或已竣工狀態可以停工')
            project.state = 'suspended'

    def action_resume(self):
        """復工"""
        for project in self:
            if project.state != 'suspended':
                raise UserError('只有停工狀態可以復工')
            project.state = 'construction'

    def action_terminate(self):
        """終止"""
        for project in self:
            if project.state in ('closed', 'terminated'):
                raise UserError('已結案或已終止的專案無法再次終止')
            project.state = 'terminated'

    # === 檢視動作 ===
    def action_view_documents(self):
        """查看文件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '工程文件',
            'res_model': 'supervision.document',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_tasks(self):
        """查看工項（含匯入的工項）"""
        self.ensure_one()
        
        tree_view_id = self.env.ref('construction_supervision_base.view_task_tree_project_specific').id
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 契約工項',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'views': [(tree_view_id, 'list'), (False, 'form')],
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {
                'default_project_id': self.project_id.id,
            },
        }

    def action_import_tender(self):
        """開啟契約標單匯入精靈"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入契約標單',
            'res_model': 'tender.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('supervision.project') or '/'
        return super().create(vals_list)

    def unlink(self):
        for project in self:
            if project.state not in ('draft', 'terminated'):
                raise UserError('只有草稿或已終止的專案可以刪除')
        return super().unlink()

    def name_get(self):
        result = []
        for project in self:
            name = f'[{project.code}] {project.name}'
            result.append((project.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', ('code', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
