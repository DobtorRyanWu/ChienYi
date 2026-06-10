# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class PaymentClaim(models.Model):
    """
    請款單

    設計說明 (v5.0):
    - 統一向業主（政府機關）請款
    - 支援服務費（監造）和工程款（廠商）兩種類型
    - 基於估驗計價或驗收單產生
    """
    _name = 'payment.claim'
    _description = '請款單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # === 基本資訊 ===
    name = fields.Char(
        '請款單號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('payment.claim') or '/'
    )
    project_id = fields.Many2one(
        'supervision.project',
        '所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        readonly=True,
        index=True
    )

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company',
        '請款公司',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='提出請款的公司（設計監造或施工廠商）',
        readonly=True
    )

    # === 請款類型 ===
    claim_type = fields.Selection([
        ('service_fee', '服務費'),      # 設計監造單位
        ('construction', '工程款'),     # 施工廠商
    ], string='請款類型', required=True, tracking=True,
       compute='_compute_claim_type', store=True, readonly=False,
       precompute=True)

    @api.depends('company_id', 'company_id.company_type')
    def _compute_claim_type(self):
        """根據公司類型自動設定請款類型"""
        for claim in self:
            if claim.company_id and hasattr(claim.company_id, 'company_type'):
                if claim.company_id.company_type == 'supervision':
                    claim.claim_type = 'service_fee'
                else:
                    claim.claim_type = 'construction'
            elif not claim.claim_type:
                claim.claim_type = 'construction'

    # === 請款對象 (業主) ===
    authority_id = fields.Many2one(
        'res.partner',
        '請款對象',
        tracking=True,
        help='政府機關，為付款方'
    )

    # === 請款基礎 ===
    estimate_ids = fields.Many2many(
        'payment.estimate',
        'claim_estimate_rel',
        'claim_id',
        'estimate_id',
        string='關聯估驗單',
        domain="[('state', '=', 'approved')]",
        help='此請款單基於哪些已核定的估驗單'
    )

    acceptance_ids = fields.Many2many(
        'work.acceptance',
        'claim_acceptance_rel',
        'claim_id',
        'acceptance_id',
        string='關聯驗收單',
        domain="[('contractor_company_id', '=', company_id), ('state', '=', 'accepted')]"
    )

    # === 金額 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    claim_amount = fields.Monetary(
        '請款金額',
        required=True,
        tracking=True
    )
    retention_amount = fields.Monetary(
        '保留款',
        default=0.0,
        tracking=True
    )
    deduction_amount = fields.Monetary(
        '扣款金額',
        default=0.0,
        help='罰款、逾期違約金等扣款'
    )
    net_amount = fields.Monetary(
        '實付金額',
        compute='_compute_net_amount',
        store=True
    )

    @api.depends('claim_amount', 'retention_amount', 'deduction_amount')
    def _compute_net_amount(self):
        """計算實付金額"""
        for claim in self:
            claim.net_amount = claim.claim_amount - claim.retention_amount - claim.deduction_amount

    # === 期次資訊 ===
    claim_period = fields.Integer(
        '請款期次',
        tracking=True
    )
    period_start = fields.Date('起始日期')
    period_end = fields.Date('截止日期')

    # === 發票資訊 ===
    invoice_number = fields.Char('發票號碼')
    invoice_date = fields.Date('發票日期')
    invoice_amount = fields.Monetary('發票金額')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'payment_claim_attachment_rel',
        'claim_id',
        'attachment_id',
        string='請款文件'
    )
    note = fields.Text('備註')

    # === 簽核流程 ===
    submitter_id = fields.Many2one(
        'res.users',
        '提送者',
        readonly=True
    )
    submit_date = fields.Datetime(
        '提送日期',
        readonly=True
    )
    approver_id = fields.Many2one(
        'res.users',
        '核准者',
        readonly=True
    )
    approve_date = fields.Datetime(
        '核准日期',
        readonly=True
    )
    approve_comment = fields.Text('核准意見')
    payment_date = fields.Date(
        '付款日期',
        tracking=True
    )
    payment_reference = fields.Char(
        '付款編號',
        help='銀行匯款編號或支票號碼'
    )

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('approved', '已核准'),
        ('paid', '已付款'),
        ('rejected', '退回'),
        ('cancelled', '取消'),
    ], default='draft', tracking=True, string='狀態')

    # === onchange ===
    @api.onchange('estimate_ids')
    def _onchange_estimate_ids(self):
        """估驗單變更時計算請款金額"""
        if self.estimate_ids:
            self.claim_amount = sum(self.estimate_ids.mapped('subtotal'))
            # 取得最大期次
            if self.estimate_ids:
                self.claim_period = max(self.estimate_ids.mapped('estimate_no'))

    # === 約束檢查 ===
    @api.constrains('claim_amount')
    def _check_claim_amount(self):
        """驗證請款金額"""
        for claim in self:
            if claim.claim_amount <= 0:
                raise ValidationError('請款金額必須大於零')

    @api.constrains('acceptance_ids', 'company_id')
    def _check_acceptance_company(self):
        """驗證驗收單歸屬公司"""
        for claim in self:
            for acceptance in claim.acceptance_ids:
                if acceptance.contractor_company_id != claim.company_id:
                    raise ValidationError(
                        f'驗收單 {acceptance.name} 不屬於 {claim.company_id.name}'
                    )

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        """驗證期間合理性"""
        for claim in self:
            if claim.period_start and claim.period_end:
                if claim.period_start > claim.period_end:
                    raise ValidationError('起始日期不可晚於截止日期')

    # === 動作方法 ===
    def action_submit(self):
        """提送請款"""
        for claim in self:
            claim._validate_before_submit()
            claim.write({
                'state': 'submitted',
                'submitter_id': self.env.uid,
                'submit_date': fields.Datetime.now(),
            })
        return True

    def _validate_before_submit(self):
        """提送前驗證"""
        self.ensure_one()
        if not self.claim_amount:
            raise UserError('請填寫請款金額')
        if not self.authority_id:
            raise UserError('請填寫請款對象（業主）')

    def action_approve(self):
        """核准請款"""
        self.write({
            'state': 'approved',
            'approver_id': self.env.uid,
            'approve_date': fields.Datetime.now(),
        })
        return True

    def action_mark_paid(self):
        """標記已付款"""
        for claim in self:
            if not claim.payment_date:
                claim.payment_date = fields.Date.today()
            claim.write({'state': 'paid'})
        return True

    def action_reject(self):
        """退回請款"""
        self.write({'state': 'rejected'})
        return True

    def action_cancel(self):
        """取消請款"""
        for claim in self:
            if claim.state == 'paid':
                raise UserError('已付款的請款單不可取消')
            claim.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        """重設為草稿"""
        for claim in self:
            if claim.state == 'paid':
                raise UserError('已付款的請款單不可重設')
            claim.write({
                'state': 'draft',
                'submitter_id': False,
                'submit_date': False,
                'approver_id': False,
                'approve_date': False,
            })
        return True

    # === 報表動作 ===
    def action_print_claim(self):
        """列印請款單"""
        self.ensure_one()
        # TODO: 實作報表列印
        return {
            'type': 'ir.actions.act_window_close',
        }

    # === 計算統計 ===
    def _get_claim_statistics(self):
        """取得請款統計資訊"""
        self.ensure_one()
        return {
            'claim_type_display': dict(self._fields['claim_type'].selection).get(self.claim_type),
            'state_display': dict(self._fields['state'].selection).get(self.state),
            'net_ratio': (self.net_amount / self.claim_amount * 100) if self.claim_amount else 0,
        }
