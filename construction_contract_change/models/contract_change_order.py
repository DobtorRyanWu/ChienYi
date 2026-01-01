# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class ContractChangeOrder(models.Model):
    """
    契約變更單

    設計說明 (v5.2): 參考 OCA project_version 設計模式
    - 追蹤金額、數量、工期變更
    - 支援新增、修改、刪除工項
    - 累計計算當前契約狀態

    狀態流程:
    draft -> submitted -> reviewing -> approved -> applied
                                   -> rejected
    """
    _name = 'contract.change.order'
    _description = '契約變更單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, create_date desc'

    # === 基本資訊 ===
    name = fields.Char(
        string='變更編號',
        required=True,
        copy=False,
        readonly=True,
        default='/',
        tracking=True,
        help='系統自動編號')

    sequence = fields.Integer(
        string='序號',
        default=10,
        help='變更順序')

    project_id = fields.Many2one(
        'supervision.project',
        string='工程案件',
        required=True,
        ondelete='cascade',
        tracking=True,
        domain="[('state', 'in', ['construction', 'completion', 'acceptance'])]",
        help='關聯的工程案件')

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        help='管理公司 (繼承自工程案件)')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='project_id.currency_id',
        store=True)

    # === 變更資訊 ===
    change_reason = fields.Selection([
        ('design', '設計變更'),
        ('site_condition', '現場條件變更'),
        ('owner_request', '業主需求'),
        ('regulation', '法規要求'),
        ('price_adjustment', '物價調整'),
        ('other', '其他'),
    ], string='變更原因',
       required=True,
       default='design',
       tracking=True)

    change_reason_detail = fields.Text(
        string='變更說明',
        tracking=True,
        help='詳細說明變更原因與內容')

    change_date = fields.Date(
        string='變更日期',
        default=fields.Date.context_today,
        tracking=True)

    # === 原始契約資訊 (快照) ===
    original_contract_amount = fields.Monetary(
        string='變更前契約金額',
        currency_field='currency_id',
        readonly=True,
        help='執行變更前的契約金額')

    original_duration = fields.Integer(
        string='變更前工期(日)',
        readonly=True,
        help='執行變更前的契約工期')

    # === 本次變更金額 ===
    change_amount = fields.Monetary(
        string='本次變更金額',
        currency_field='currency_id',
        compute='_compute_change_totals',
        store=True,
        help='本次變更增減金額 (正:增加, 負:減少)')

    change_amount_rate = fields.Float(
        string='變更比率 (%)',
        compute='_compute_change_totals',
        store=True,
        digits=(5, 2),
        help='變更金額佔原契約金額的百分比')

    # === 本次變更工期 ===
    change_duration = fields.Integer(
        string='本次變更工期(日)',
        default=0,
        tracking=True,
        help='工期增減天數 (正:展延, 負:縮短)')

    # === 變更後金額 ===
    new_contract_amount = fields.Monetary(
        string='變更後契約金額',
        currency_field='currency_id',
        compute='_compute_new_amounts',
        store=True,
        help='變更後的契約總金額')

    new_duration = fields.Integer(
        string='變更後工期(日)',
        compute='_compute_new_amounts',
        store=True,
        help='變更後的契約總工期')

    # === 變更明細 ===
    line_ids = fields.One2many(
        'contract.change.order.line',
        'change_order_id',
        string='變更明細',
        copy=True)

    line_count = fields.Integer(
        string='明細筆數',
        compute='_compute_line_count')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('applied', '已套用'),
        ('rejected', '已駁回'),
    ], string='狀態',
       default='draft',
       tracking=True,
       index=True)

    # === 審核資訊 ===
    submitted_by_id = fields.Many2one(
        'res.users',
        string='提送人',
        readonly=True)

    submitted_date = fields.Datetime(
        string='提送時間',
        readonly=True)

    reviewed_by_id = fields.Many2one(
        'res.users',
        string='審核人',
        readonly=True)

    reviewed_date = fields.Datetime(
        string='審核時間',
        readonly=True)

    approved_by_id = fields.Many2one(
        'res.users',
        string='核定人',
        readonly=True)

    approved_date = fields.Datetime(
        string='核定時間',
        readonly=True)

    applied_by_id = fields.Many2one(
        'res.users',
        string='套用人',
        readonly=True)

    applied_date = fields.Datetime(
        string='套用時間',
        readonly=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        readonly=True)

    # === 備註 ===
    notes = fields.Html(
        string='備註')

    # === 計算欄位 ===
    @api.depends('line_ids')
    def _compute_line_count(self):
        for order in self:
            order.line_count = len(order.line_ids)

    @api.depends('line_ids.change_amount')
    def _compute_change_totals(self):
        """計算本次變更總金額與比率"""
        for order in self:
            order.change_amount = sum(order.line_ids.mapped('change_amount'))
            if order.original_contract_amount:
                order.change_amount_rate = (
                    order.change_amount / order.original_contract_amount) * 100
            else:
                order.change_amount_rate = 0.0

    @api.depends('original_contract_amount', 'change_amount',
                 'original_duration', 'change_duration')
    def _compute_new_amounts(self):
        """計算變更後金額與工期"""
        for order in self:
            order.new_contract_amount = (
                order.original_contract_amount + order.change_amount)
            order.new_duration = order.original_duration + order.change_duration

    # === Onchange ===
    @api.onchange('project_id')
    def _onchange_project_id(self):
        """選擇工程時，自動填入原始契約資訊"""
        if self.project_id:
            # 取得當前契約金額 (含已核定變更)
            self.original_contract_amount = (
                self.project_id.current_contract_amount or
                self.project_id.contract_amount or 0.0)
            self.original_duration = (
                self.project_id.current_duration or
                self.project_id.contract_duration or 0)

    # === 約束 ===
    @api.constrains('change_duration')
    def _check_change_duration(self):
        """檢查工期變更合理性"""
        for order in self:
            if order.original_duration and order.change_duration:
                new_duration = order.original_duration + order.change_duration
                if new_duration < 0:
                    raise ValidationError(
                        '變更後工期不可為負數！'
                        f'原工期 {order.original_duration} 日 + '
                        f'變更 {order.change_duration} 日 = {new_duration} 日')

    @api.constrains('line_ids')
    def _check_line_ids(self):
        """檢查變更明細"""
        for order in self:
            if order.state != 'draft' and not order.line_ids:
                raise ValidationError('契約變更單必須至少包含一筆變更明細！')

    # === 狀態動作 ===
    def action_submit(self):
        """提送審查"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以提送！')
        if not self.line_ids:
            raise UserError('請先新增變更明細！')

        # 快照原始契約資訊
        if not self.original_contract_amount:
            self.original_contract_amount = (
                self.project_id.current_contract_amount or
                self.project_id.contract_amount or 0.0)
        if not self.original_duration:
            self.original_duration = (
                self.project_id.current_duration or
                self.project_id.contract_duration or 0)

        self.write({
            'state': 'submitted',
            'submitted_by_id': self.env.uid,
            'submitted_date': fields.Datetime.now(),
        })

    def action_review(self):
        """開始審查"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError('只有已提送狀態可以開始審查！')

        self.write({
            'state': 'reviewing',
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_approve(self):
        """核定通過"""
        self.ensure_one()
        if self.state != 'reviewing':
            raise UserError('只有審查中狀態可以核定！')

        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })

    def action_reject(self):
        """開啟駁回精靈"""
        self.ensure_one()
        if self.state not in ('submitted', 'reviewing'):
            raise UserError('只有已提送或審查中狀態可以駁回！')

        return {
            'type': 'ir.actions.act_window',
            'name': '駁回變更單',
            'res_model': 'contract.change.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_change_order_id': self.id,
            },
        }

    def action_do_reject(self, reason):
        """執行駁回"""
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'rejection_reason': reason,
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_apply(self):
        """套用變更"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('只有已核定狀態可以套用變更！')

        # 套用變更至工項
        self._apply_changes_to_tasks()

        # 更新專案契約金額與工期
        self._update_project_contract()

        self.write({
            'state': 'applied',
            'applied_by_id': self.env.uid,
            'applied_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '套用成功',
                'message': f'已套用契約變更 {self.name}',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reset_draft(self):
        """重設為草稿"""
        self.ensure_one()
        if self.state not in ('submitted', 'rejected'):
            raise UserError('只有已提送或已駁回狀態可以重設為草稿！')

        self.write({
            'state': 'draft',
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'rejection_reason': False,
        })

    # === 套用變更邏輯 ===
    def _apply_changes_to_tasks(self):
        """套用變更至工項"""
        self.ensure_one()
        ProjectTask = self.env['project.task']

        for line in self.line_ids:
            if line.change_type == 'add':
                # 新增工項
                ProjectTask.create({
                    'project_id': self.project_id.project_id.id,
                    'name': line.item_name,
                    'item_no': line.item_no,
                    'planned_qty': line.new_qty,
                    'unit': line.unit,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                })
            elif line.change_type == 'modify' and line.task_id:
                # 修改工項
                line.task_id.write({
                    'planned_qty': line.new_qty,
                    'unit_price': line.new_unit_price,
                    'change_order_id': self.id,
                })
            elif line.change_type == 'delete' and line.task_id:
                # 標記刪除 (不實際刪除，保留歷史)
                line.task_id.write({
                    'active': False,
                    'change_order_id': self.id,
                })

    def _update_project_contract(self):
        """更新專案契約金額與工期"""
        self.ensure_one()
        project = self.project_id

        # 更新契約金額
        vals = {
            'contract_amount': self.new_contract_amount,
        }

        # 更新契約完工日 (如有工期變更)
        if self.change_duration and project.contract_end_date:
            new_end = project.contract_end_date + timedelta(days=self.change_duration)
            vals['contract_end_date'] = new_end

        project.write(vals)

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contract.change.order') or '/'
        return super().create(vals_list)

    def unlink(self):
        for order in self:
            if order.state not in ('draft', 'rejected'):
                raise UserError('只有草稿或已駁回的變更單可以刪除！')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': '/',
            'state': 'draft',
            'submitted_by_id': False,
            'submitted_date': False,
            'reviewed_by_id': False,
            'reviewed_date': False,
            'approved_by_id': False,
            'approved_date': False,
            'applied_by_id': False,
            'applied_date': False,
            'rejection_reason': False,
        })
        return super().copy(default)

    # === 檢視動作 ===
    def action_view_lines(self):
        """查看變更明細"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '變更明細',
            'res_model': 'contract.change.order.line',
            'view_mode': 'list,form',
            'domain': [('change_order_id', '=', self.id)],
            'context': {
                'default_change_order_id': self.id,
            },
        }


class ContractChangeRejectWizard(models.TransientModel):
    """駁回精靈"""
    _name = 'contract.change.reject.wizard'
    _description = '契約變更駁回精靈'

    change_order_id = fields.Many2one(
        'contract.change.order',
        string='變更單',
        required=True)

    rejection_reason = fields.Text(
        string='駁回原因',
        required=True)

    def action_confirm(self):
        """確認駁回"""
        self.ensure_one()
        self.change_order_id.action_do_reject(self.rejection_reason)
        return {'type': 'ir.actions.act_window_close'}
