# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class WorkAcceptance(models.Model):
    """
    工項驗收單

    設計說明 (v5.0): 監造驗收施工廠商完成的工項
    - 不依賴 purchase 模組，獨立設計驗收流程
    - 驗收通過後，廠商可提交估驗計價
    - 支援部分驗收與完工驗收
    """
    _name = 'work.acceptance'
    _description = '工項驗收單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # === 基本資訊 ===
    name = fields.Char(
        '驗收單號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('work.acceptance') or '/'
    )
    project_id = fields.Many2one(
        'supervision.project',
        '所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        readonly=True
    )

    # === 多公司架構 (v5.0) ===
    contractor_company_id = fields.Many2one(
        'res.company',
        '施工廠商',
        required=True,
        tracking=True,
        domain="[('company_type', '=', 'contractor')]",
        help='被驗收的施工廠商',
        readonly=True
    )

    # === 驗收資訊 ===
    acceptance_date = fields.Date(
        '驗收日期',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    acceptance_type = fields.Selection([
        ('partial', '部分驗收'),
        ('final', '完工驗收'),
    ], string='驗收類型', required=True, default='partial', tracking=True)

    # === 驗收人員 (監造單位) ===
    acceptor_id = fields.Many2one(
        'res.users',
        '驗收人員',
        default=lambda self: self.env.uid,
        tracking=True,
        help='執行驗收的監造人員'
    )
    witness_ids = fields.Many2many(
        'res.users',
        'work_acceptance_witness_rel',
        'acceptance_id',
        'user_id',
        string='會同人員'
    )

    # === 驗收明細 ===
    line_ids = fields.One2many(
        'work.acceptance.line',
        'acceptance_id',
        '驗收明細',
        copy=True
    )

    # === 驗收結果 ===
    has_defect = fields.Boolean(
        '有缺失',
        compute='_compute_has_defect',
        store=True
    )
    defect_count = fields.Integer(
        '缺失數量',
        compute='_compute_has_defect',
        store=True
    )
    # defect_ids 需要 supervision.defect 模型存在，暫時註解
    # defect_ids = fields.One2many('supervision.defect', 'acceptance_id', '驗收缺失')

    # === 金額彙總 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    total_contract_amount = fields.Monetary(
        '契約總金額',
        compute='_compute_totals',
        store=True
    )
    total_accepted_amount = fields.Monetary(
        '驗收總金額',
        compute='_compute_totals',
        store=True
    )

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'work_acceptance_attachment_rel',
        'acceptance_id',
        'attachment_id',
        string='驗收資料'
    )
    note = fields.Text('備註')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('inspecting', '檢驗中'),
        ('pending_fix', '待改善'),
        ('accepted', '已驗收'),
        ('rejected', '退回'),
    ], default='draft', tracking=True, string='狀態')

    # === 計算欄位 ===
    @api.depends('line_ids.acceptance_result')
    def _compute_has_defect(self):
        """計算是否有缺失"""
        for rec in self:
            fail_lines = rec.line_ids.filtered(
                lambda l: l.acceptance_result in ('conditional', 'fail')
            )
            rec.has_defect = len(fail_lines) > 0
            rec.defect_count = len(fail_lines.filtered(lambda l: l.acceptance_result == 'fail'))

    @api.depends('line_ids.contract_amount', 'line_ids.accepted_amount')
    def _compute_totals(self):
        """計算金額合計"""
        for rec in self:
            rec.total_contract_amount = sum(rec.line_ids.mapped('contract_amount'))
            rec.total_accepted_amount = sum(rec.line_ids.mapped('accepted_amount'))

    # === 約束檢查 ===
    @api.constrains('line_ids')
    def _check_lines(self):
        """驗證明細行"""
        for rec in self:
            if rec.state != 'draft' and not rec.line_ids:
                raise ValidationError('驗收單必須至少有一項驗收明細')

    # === 動作方法 ===
    def action_start_inspection(self):
        """開始檢驗"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('請先新增驗收明細')
            rec.write({'state': 'inspecting'})
        return True

    def action_accept(self):
        """驗收通過"""
        for rec in self:
            rec._check_can_accept()
            rec.write({'state': 'accepted'})
            # 更新工項狀態（如果有 assignment_state 欄位）
            for line in rec.line_ids:
                if hasattr(line.task_id, 'assignment_state'):
                    line.task_id.write({'assignment_state': 'accepted'})
        return True

    def _check_can_accept(self):
        """檢查是否可以驗收通過"""
        self.ensure_one()
        # 檢查是否有未解決的缺失
        fail_lines = self.line_ids.filtered(lambda l: l.acceptance_result == 'fail')
        if fail_lines:
            raise UserError(
                '有 %d 項工項驗收不合格，無法完成驗收。\n'
                '請先處理不合格項目或將結果改為「有條件合格」。' % len(fail_lines)
            )

    def action_request_fix(self):
        """要求改善"""
        for rec in self:
            if not rec.has_defect:
                raise UserError('沒有需要改善的項目')
            rec.write({'state': 'pending_fix'})
        return True

    def action_reject(self):
        """驗收退回"""
        self.write({'state': 'rejected'})
        return True

    def action_reset_to_draft(self):
        """重設為草稿"""
        self.write({'state': 'draft'})
        return True

    # === 建立關聯估驗單 ===
    def action_create_estimate(self):
        """建立估驗計價"""
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError('只有已驗收的驗收單才能建立估驗計價')

        return {
            'type': 'ir.actions.act_window',
            'name': '建立估驗計價',
            'res_model': 'payment.estimate',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.project_id.id,
                'default_company_id': self.contractor_company_id.id,
                'default_acceptance_ids': [Command.set([self.id])],
            },
            'target': 'current',
        }


class WorkAcceptanceLine(models.Model):
    """工項驗收明細"""
    _name = 'work.acceptance.line'
    _description = '工項驗收明細'
    _order = 'sequence, id'

    # === 關聯 ===
    acceptance_id = fields.Many2one(
        'work.acceptance',
        '驗收單',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer('序號', default=10)

    task_id = fields.Many2one(
        'project.task',
        '工項',
        required=True,
        # domain 需配合前端動態過濾
        help='選擇要驗收的契約工項'
    )

    # === 工項資訊 (從 task_id 帶出) ===
    item_no = fields.Char(
        '項次',
        related='task_id.item_no',
        store=True,
        readonly=True
    )
    description = fields.Char(
        '項目說明',
        related='task_id.name',
        store=True,
        readonly=True
    )
    unit = fields.Char(
        '單位',
        related='task_id.unit',
        store=True,
        readonly=True
    )

    # === 數量追蹤 ===
    contract_qty = fields.Float(
        '原始契約數量',
        digits='Product Unit of Measure',
        help='原始契約數量（變更前）'
    )
    previous_accepted_qty = fields.Float(
        '前期累計驗收',
        digits='Product Unit of Measure',
        help='之前已驗收的累計數量'
    )
    completed_qty = fields.Float(
        '本期完成數量',
        digits='Product Unit of Measure',
        required=True,
        help='本期施工完成的數量'
    )
    accepted_qty = fields.Float(
        '本次驗收數量',
        digits='Product Unit of Measure',
        required=True,
        help='本次驗收通過的數量'
    )
    remaining_qty = fields.Float(
        '剩餘數量',
        compute='_compute_remaining',
        store=True,
        digits='Product Unit of Measure'
    )

    # === 金額 ===
    unit_price = fields.Float(
        '單價',
        digits='Product Price',
        help='契約單價'
    )
    contract_amount = fields.Float(
        '契約金額',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )
    accepted_amount = fields.Float(
        '驗收金額',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )

    # === 驗收結果 ===
    acceptance_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '有條件合格'),
        ('fail', '不合格'),
    ], string='驗收結果', default='pass', required=True)
    defect_description = fields.Text('缺失說明')
    note = fields.Text('備註')

    # === 計算欄位 ===
    @api.depends('contract_qty', 'previous_accepted_qty', 'accepted_qty')
    def _compute_remaining(self):
        """計算剩餘數量"""
        for line in self:
            cumulative = line.previous_accepted_qty + line.accepted_qty
            line.remaining_qty = line.contract_qty - cumulative

    @api.depends('contract_qty', 'accepted_qty', 'unit_price')
    def _compute_amounts(self):
        """計算金額"""
        for line in self:
            line.contract_amount = line.contract_qty * line.unit_price
            line.accepted_amount = line.accepted_qty * line.unit_price

    # === onchange ===
    @api.onchange('task_id')
    def _onchange_task_id(self):
        """工項變更時帶入相關資訊"""
        if self.task_id:
            # 從工項帶入契約數量和單價
            if hasattr(self.task_id, 'planned_qty'):
                self.contract_qty = self.task_id.planned_qty
            if hasattr(self.task_id, 'unit_price'):
                self.unit_price = self.task_id.unit_price

            # 計算前期累計驗收數量
            previous_lines = self.env['work.acceptance.line'].search([
                ('task_id', '=', self.task_id.id),
                ('acceptance_id.state', '=', 'accepted'),
                ('id', '!=', self._origin.id if self._origin else 0),
            ])
            self.previous_accepted_qty = sum(previous_lines.mapped('accepted_qty'))

    @api.onchange('completed_qty')
    def _onchange_completed_qty(self):
        """完成數量變更時預設驗收數量等於完成數量"""
        if self.completed_qty and not self.accepted_qty:
            self.accepted_qty = self.completed_qty

    # === 約束檢查 ===
    @api.constrains('accepted_qty', 'completed_qty')
    def _check_qty(self):
        """驗證數量合理性"""
        for line in self:
            if line.accepted_qty < 0:
                raise ValidationError('驗收數量不可為負數')
            if line.accepted_qty > line.completed_qty:
                raise ValidationError(
                    f'項目 {line.item_no or line.task_id.name}: '
                    f'驗收數量 ({line.accepted_qty}) 不可超過完成數量 ({line.completed_qty})'
                )

    @api.constrains('accepted_qty', 'contract_qty', 'previous_accepted_qty')
    def _check_over_contract(self):
        """警告累計驗收超過契約數量"""
        for line in self:
            cumulative = line.previous_accepted_qty + line.accepted_qty
            if cumulative > line.contract_qty and line.contract_qty > 0:
                # 發出警告但不阻擋（可能有追加工程）
                line.acceptance_id.message_post(
                    body=f'注意：項目 {line.item_no or line.task_id.name} '
                         f'累計驗收數量 ({cumulative}) 已超過契約數量 ({line.contract_qty})'
                )
