# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ReservationNotificationSlip(models.Model):
    """
    通報單 (預約式專用)

    設計特點:
    - 狀態機制: draft -> submitted -> approved -> in_progress -> completed
    - 預算追蹤: estimated_amount (預算) vs settlement_amount (實際)
    - 驗收流程整合
    """
    _name = 'reservation.notification.slip'
    _description = '通報單 (預約式專用)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'slip_no desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='通報單名稱',
        compute='_compute_name', store=True, readonly=False)

    slip_number = fields.Char(
        string='通報單編號', required=True, copy=False, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('reservation.notification.slip') or '/')

    project_id = fields.Many2one(
        'supervision.project', string='所屬工程', required=True,
        domain=[('project_type', '=', 'reservation')],
        tracking=True,
        help='僅可選擇預約式工程')

    slip_no = fields.Integer(
        string='通報單次', required=True, default=1,
        help='本工程的第幾次通報單')

    # === 編製資訊 ===
    compiler_id = fields.Many2one(
        'res.users', string='編製人員',
        default=lambda self: self.env.uid,
        tracking=True)

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='project_id.company_id', store=True)

    location = fields.Char(
        string='工程地點', required=True,
        help='本次通報單的施工地點')

    location_detail = fields.Text(
        string='詳細位置說明')

    # === 日期與工期 ===
    survey_date = fields.Date(
        string='工程會勘日期',
        help='現場會勘日期')

    planned_start_date = fields.Date(
        string='預定開工日期', tracking=True)

    planned_end_date = fields.Date(
        string='預定完工日期',
        compute='_compute_planned_end_date', store=True, readonly=False)

    planned_duration = fields.Integer(
        string='預定工期(日曆天)',
        help='預定施工天數')

    actual_start_date = fields.Date(
        string='實際開工日期', tracking=True)

    actual_end_date = fields.Date(
        string='實際竣工日期', tracking=True)

    actual_duration = fields.Integer(
        string='實際使用工期',
        compute='_compute_actual_duration', store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue_days', store=True)

    proposal_countdown = fields.Integer(
        string='提案結束天數倒數',
        compute='_compute_countdown')

    # === 預算與結算 (v5.1) ===
    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='project_id.currency_id', store=True)

    estimated_amount = fields.Monetary(
        string='預估金額 (預算)',
        currency_field='currency_id',
        tracking=True,
        help='本通報單的預算金額，參考工程範疇量預估')

    settlement_amount = fields.Monetary(
        string='結算金額 (實際)',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='本通報單的實際結算金額，由明細彙總')

    budget_variance = fields.Monetary(
        string='預算差異',
        currency_field='currency_id',
        compute='_compute_settlement_amount', store=True,
        help='settlement_amount - estimated_amount')

    budget_variance_rate = fields.Float(
        string='差異率 (%)',
        compute='_compute_settlement_amount', store=True,
        digits=(5, 2),
        help='(settlement_amount / estimated_amount - 1) x 100')

    # === 設計與施工概述 ===
    design_summary = fields.Text(
        string='設計概述',
        help='本通報單施工內容概述')

    completion_summary = fields.Text(
        string='完工概述',
        help='竣工時的施工成果說明')

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已送出'),
        ('approved', '已核准'),
        ('in_progress', '執行中'),
        ('completed', '已完成'),
        ('cancel', '取消'),
    ], string='通報單狀態', default='draft', tracking=True, index=True,
       help='通報單生命週期: draft -> submitted -> approved -> in_progress -> completed')

    work_status = fields.Selection([
        ('pending', '待施工'),
        ('working', '施工中'),
        ('completed', '已竣工'),
        ('accepted', '已驗收'),
    ], string='施作狀態', compute='_compute_work_status', store=True)

    # === 驗收關聯 ===
    acceptance_id = fields.Many2one(
        'notification.acceptance', string='驗收單',
        help='關聯的驗收單據')

    acceptance_ids = fields.One2many(
        'notification.acceptance', 'slip_id', string='驗收紀錄')

    acceptance_count = fields.Integer(
        string='驗收次數',
        compute='_compute_acceptance_count')

    # === 明細關聯 ===
    detail_line_ids = fields.One2many(
        'reservation.notification.slip.line', 'slip_id',
        string='詳細表項目')

    line_count = fields.Integer(
        string='項目數量',
        compute='_compute_line_count')

    # === 備註 ===
    notes = fields.Html(string='備註說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('slip_number_unique', 'UNIQUE(slip_number)', '通報單編號必須唯一！'),
        ('project_slip_no_unique', 'UNIQUE(project_id, slip_no)',
         '同一工程的通報單次不可重複！'),
        ('planned_dates_check',
         'CHECK(planned_end_date IS NULL OR planned_start_date IS NULL OR planned_end_date >= planned_start_date)',
         '預定完工日必須晚於或等於開工日！'),
    ]

    # === 計算方法 ===
    @api.depends('slip_no', 'location')
    def _compute_name(self):
        for rec in self:
            location_str = rec.location or ''
            rec.name = f'第{rec.slip_no}次通報單 - {location_str}'

    @api.depends('planned_start_date', 'planned_duration')
    def _compute_planned_end_date(self):
        for rec in self:
            if rec.planned_start_date and rec.planned_duration:
                rec.planned_end_date = rec.planned_start_date + timedelta(days=rec.planned_duration - 1)
            elif not rec.planned_end_date:
                rec.planned_end_date = False

    @api.depends('actual_start_date', 'actual_end_date')
    def _compute_actual_duration(self):
        for rec in self:
            if rec.actual_start_date and rec.actual_end_date:
                delta = rec.actual_end_date - rec.actual_start_date
                rec.actual_duration = delta.days + 1
            else:
                rec.actual_duration = 0

    @api.depends('planned_end_date', 'actual_end_date')
    def _compute_overdue_days(self):
        for rec in self:
            if rec.planned_end_date and rec.actual_end_date:
                delta = rec.actual_end_date - rec.planned_end_date
                rec.overdue_days = max(0, delta.days)
            else:
                rec.overdue_days = 0

    def _compute_countdown(self):
        today = fields.Date.today()
        for rec in self:
            if rec.planned_end_date and rec.state in ('approved', 'in_progress'):
                delta = rec.planned_end_date - today
                rec.proposal_countdown = delta.days
            else:
                rec.proposal_countdown = 0

    @api.depends('detail_line_ids.actual_amount')
    def _compute_settlement_amount(self):
        for slip in self:
            slip.settlement_amount = sum(slip.detail_line_ids.mapped('actual_amount'))
            slip.budget_variance = slip.settlement_amount - slip.estimated_amount
            if slip.estimated_amount:
                slip.budget_variance_rate = ((slip.settlement_amount / slip.estimated_amount) - 1) * 100
            else:
                slip.budget_variance_rate = 0.0

    @api.depends('state', 'actual_start_date', 'actual_end_date', 'acceptance_id')
    def _compute_work_status(self):
        for rec in self:
            if rec.acceptance_id and rec.acceptance_id.state == 'accept':
                rec.work_status = 'accepted'
            elif rec.actual_end_date:
                rec.work_status = 'completed'
            elif rec.actual_start_date:
                rec.work_status = 'working'
            else:
                rec.work_status = 'pending'

    @api.depends('acceptance_ids')
    def _compute_acceptance_count(self):
        for rec in self:
            rec.acceptance_count = len(rec.acceptance_ids)

    @api.depends('detail_line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.detail_line_ids)

    # === onchange 方法 ===
    @api.onchange('project_id')
    def _onchange_project_id(self):
        """計算下一個通報單次數"""
        if self.project_id:
            existing = self.search([
                ('project_id', '=', self.project_id.id)
            ], order='slip_no desc', limit=1)
            self.slip_no = (existing.slip_no + 1) if existing else 1

    @api.onchange('planned_duration')
    def _onchange_planned_duration(self):
        """更新預定完工日"""
        if self.planned_start_date and self.planned_duration:
            self.planned_end_date = self.planned_start_date + timedelta(days=self.planned_duration - 1)

    # === 約束驗證 ===
    @api.constrains('actual_start_date', 'actual_end_date')
    def _check_actual_dates(self):
        for rec in self:
            if rec.actual_start_date and rec.actual_end_date:
                if rec.actual_end_date < rec.actual_start_date:
                    raise ValidationError('實際竣工日必須晚於或等於實際開工日')

    @api.constrains('project_id')
    def _check_project_type(self):
        for rec in self:
            if rec.project_id and rec.project_id.project_type != 'reservation':
                raise ValidationError('通報單僅適用於預約式工程')

    # === 狀態動作方法 ===
    def action_submit(self):
        """提交通報單"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態可以提交')
            if not rec.detail_line_ids:
                raise ValidationError('請先填寫詳細表項目')
            if not rec.location:
                raise ValidationError('請填寫工程地點')
            rec.write({'state': 'submitted'})

    def action_approve(self):
        """核准通報單"""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('只有已送出狀態可以核准')
            rec.write({'state': 'approved'})

    def action_start(self):
        """開始執行"""
        for rec in self:
            if rec.state != 'approved':
                raise UserError('只有已核准狀態可以開始執行')
            vals = {'state': 'in_progress'}
            if not rec.actual_start_date:
                vals['actual_start_date'] = fields.Date.today()
            rec.write(vals)

    def action_complete(self):
        """完成通報單"""
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError('只有執行中狀態可以標記完成')
            # 檢查是否所有項目都已完成
            if any(line.qty_remaining > 0 for line in rec.detail_line_ids):
                raise ValidationError('尚有未完成驗收的工作項目')
            vals = {'state': 'completed'}
            if not rec.actual_end_date:
                vals['actual_end_date'] = fields.Date.today()
            rec.write(vals)

    def action_cancel(self):
        """取消通報單"""
        for rec in self:
            if rec.state == 'completed':
                raise ValidationError('已完成的通報單無法取消')
            if rec.acceptance_ids.filtered(lambda a: a.state == 'accept'):
                raise ValidationError('已有驗收紀錄的通報單無法取消')
            rec.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """重設為草稿 (僅限取消狀態)"""
        for rec in self:
            if rec.state != 'cancel':
                raise ValidationError('僅取消狀態可重設為草稿')
            rec.write({'state': 'draft'})

    def action_return_to_draft(self):
        """退回草稿 (用於已送出狀態)"""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('只有已送出狀態可以退回草稿')
            rec.write({'state': 'draft'})

    # === 視圖動作 ===
    def action_view_acceptances(self):
        """查看驗收紀錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '驗收紀錄',
            'res_model': 'notification.acceptance',
            'view_mode': 'list,form',
            'domain': [('slip_id', '=', self.id)],
            'context': {'default_slip_id': self.id},
        }

    def action_create_acceptance(self):
        """建立驗收單"""
        self.ensure_one()
        if self.state not in ('in_progress', 'approved'):
            raise UserError('只有核准或執行中狀態可以建立驗收單')

        # 檢查是否還有待驗收項目
        lines_to_accept = self.detail_line_ids.filtered(lambda l: l.qty_remaining > 0)
        if not lines_to_accept:
            raise UserError('沒有待驗收的項目')

        return {
            'type': 'ir.actions.act_window',
            'name': '新增驗收單',
            'res_model': 'notification.acceptance',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('slip_number', '/') == '/':
                vals['slip_number'] = self.env['ir.sequence'].next_by_code(
                    'reservation.notification.slip') or '/'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError('只有草稿或取消狀態的通報單可以刪除')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'slip_number': self.env['ir.sequence'].next_by_code('reservation.notification.slip') or '/',
            'state': 'draft',
            'actual_start_date': False,
            'actual_end_date': False,
            'acceptance_id': False,
        })
        # 計算新的 slip_no
        if self.project_id:
            existing = self.search([
                ('project_id', '=', self.project_id.id)
            ], order='slip_no desc', limit=1)
            default['slip_no'] = (existing.slip_no + 1) if existing else 1
        return super().copy(default)

    def name_get(self):
        result = []
        for rec in self:
            name = f'[{rec.slip_number}] {rec.name}'
            result.append((rec.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', '|',
                      ('slip_number', operator, name),
                      ('name', operator, name),
                      ('location', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
