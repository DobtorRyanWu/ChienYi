# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


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

    # === 多公司架構 ===
    company_id = fields.Many2one(
        'res.company', string='管理公司', required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'supervision')]",
        tracking=True,
        help='負責管理此專案的設計監造單位')

    contractor_company_ids = fields.Many2many(
        'res.company', 'supervision_project_contractor_rel',
        'project_id', 'company_id',
        string='承包廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='參與此專案的施工廠商公司')

    # === 業主資訊 ===
    authority_id = fields.Many2one(
        'res.partner', string='業主/主辦機關', required=True,
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
        string='契約金額', currency_field='currency_id', tracking=True)

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        default=lambda self: self.env.company.currency_id)

    contract_start_date = fields.Date(string='契約開工日', tracking=True)
    contract_end_date = fields.Date(string='契約完工日', tracking=True)

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

    # === 工程位置 ===
    location = fields.Char(string='工程地點')
    location_detail = fields.Text(string='詳細位置說明')
    latitude = fields.Float(string='緯度', digits=(10, 7))
    longitude = fields.Float(string='經度', digits=(10, 7))

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('preparing', '籌備中'),
        ('pending_approval', '待核定'),
        ('construction', '施工中'),
        ('completion', '已竣工'),
        ('acceptance', '驗收中'),
        ('closed', '已結案'),
        ('suspended', '停工'),
        ('terminated', '終止'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 進度資訊 ===
    planned_progress = fields.Float(
        string='預定進度 (%)',
        compute='_compute_progress', store=True)

    actual_progress = fields.Float(
        string='實際進度 (%)', tracking=True)

    progress_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
    ], string='進度狀態', compute='_compute_progress_status', store=True)

    @api.depends('contract_start_date', 'contract_end_date')
    def _compute_progress(self):
        """計算預定進度 (依時間比例)"""
        today = fields.Date.today()
        for project in self:
            if project.contract_start_date and project.contract_end_date:
                if today < project.contract_start_date:
                    project.planned_progress = 0.0
                elif today > project.contract_end_date:
                    project.planned_progress = 100.0
                else:
                    total_days = (project.contract_end_date - project.contract_start_date).days
                    elapsed_days = (today - project.contract_start_date).days
                    if total_days > 0:
                        project.planned_progress = (elapsed_days / total_days) * 100
                    else:
                        project.planned_progress = 0.0
            else:
                project.planned_progress = 0.0

    @api.depends('planned_progress', 'actual_progress')
    def _compute_progress_status(self):
        for project in self:
            diff = project.actual_progress - project.planned_progress
            if diff > 2:
                project.progress_status = 'ahead'
            elif diff < -2:
                project.progress_status = 'delayed'
            else:
                project.progress_status = 'on_track'

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
    def action_prepare(self):
        """開始籌備"""
        for project in self:
            if project.state != 'draft':
                raise UserError('只有草稿狀態可以開始籌備')
            project.state = 'preparing'

    def action_submit_approval(self):
        """提交核定"""
        for project in self:
            if project.state != 'preparing':
                raise UserError('只有籌備中狀態可以提交核定')
            project.state = 'pending_approval'

    def action_approve(self):
        """核定開工"""
        for project in self:
            if project.state != 'pending_approval':
                raise UserError('只有待核定狀態可以核定開工')
            if not project.contract_start_date:
                raise ValidationError('請先設定契約開工日')
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

    def action_reset_draft(self):
        """重設為草稿"""
        for project in self:
            if project.state not in ('preparing', 'pending_approval'):
                raise UserError('只有籌備中或待核定狀態可以重設為草稿')
            project.state = 'draft'

    # === 檢視動作 ===
    def action_view_documents(self):
        """查看文件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '工程文件',
            'res_model': 'supervision.document',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_tasks(self):
        """查看工項"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '契約工項',
            'res_model': 'project.task',
            'view_mode': 'tree,kanban,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {
                'default_project_id': self.project_id.id,
                'search_default_group_by_assigned_company': 1,
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
