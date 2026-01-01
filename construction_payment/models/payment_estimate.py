# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class PaymentEstimate(models.Model):
    """
    估驗計價

    設計說明 (v5.0): 不依賴 purchase 模組，獨立設計
    - 分期估驗計畫與累計追蹤
    - 施工廠商提交，監造審查
    - 支援預算 vs 實際對比分析
    """
    _name = 'payment.estimate'
    _description = '估驗計價'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'estimate_no asc, id desc'

    # === 基本資訊 ===
    name = fields.Char(
        '估驗期次',
        required=True,
        tracking=True,
        help='例如：第一期估驗、第二期估驗'
    )
    project_id = fields.Many2one(
        'supervision.project',
        '所屬工程',
        required=True,
        tracking=True,
        readonly=True,
        index=True
    )

    # === 多公司架構 (v5.0) ===
    company_id = fields.Many2one(
        'res.company',
        '提送公司',
        required=True,
        default=lambda self: self.env.company,
        domain="[('company_type', '=', 'contractor')]",
        tracking=True,
        help='提送此估驗的施工廠商',
        readonly=True
    )

    # === 估驗期間 ===
    period_start = fields.Date(
        '起始日期',
        tracking=True
    )
    period_end = fields.Date(
        '截止日期',
        tracking=True
    )
    estimate_no = fields.Integer(
        '期次',
        required=True,
        default=1,
        tracking=True
    )
    is_final = fields.Boolean(
        '是否為尾款',
        default=False,
        tracking=True,
        help='勾選表示此為最後一期尾款結算'
    )

    # === 關聯驗收單 ===
    acceptance_ids = fields.Many2many(
        'work.acceptance',
        'estimate_acceptance_rel',
        'estimate_id',
        'acceptance_id',
        string='關聯驗收單',
        domain="[('contractor_company_id', '=', company_id), ('state', '=', 'accepted')]",
        help='此次估驗涵蓋的驗收單'
    )

    # === 金額 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )

    # 計價項目
    line_ids = fields.One2many(
        'payment.estimate.line',
        'estimate_id',
        '計價明細',
        copy=True
    )

    # === 合計 (參考 invoice_plan 累計設計) ===
    subtotal = fields.Monetary(
        '本期估驗金額',
        compute='_compute_totals',
        store=True,
        tracking=True
    )
    cumulative_amount = fields.Monetary(
        '累計估驗金額',
        compute='_compute_totals',
        store=True,
        tracking=True
    )
    contract_total = fields.Monetary(
        '契約總價',
        related='project_id.contract_amount',
        store=True
    )
    completion_rate = fields.Float(
        '估驗進度 (%)',
        compute='_compute_totals',
        store=True,
        digits=(5, 2),
        help='累計估驗金額 / 契約總價'
    )
    retention_rate = fields.Float(
        '保留款比例 (%)',
        default=5.0,
        tracking=True
    )
    retention = fields.Monetary(
        '保留款',
        compute='_compute_totals',
        store=True
    )
    payable_amount = fields.Monetary(
        '應付金額',
        compute='_compute_totals',
        store=True,
        help='本期估驗金額 - 保留款'
    )

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'payment_estimate_attachment_rel',
        'estimate_id',
        'attachment_id',
        string='佐證資料'
    )

    # === 簽核 ===
    submitter_id = fields.Many2one(
        'res.users',
        '提送者',
        readonly=True
    )
    submit_date = fields.Datetime(
        '提送日期',
        readonly=True
    )
    reviewer_id = fields.Many2one(
        'res.users',
        '審查者',
        readonly=True
    )
    review_date = fields.Datetime(
        '審查日期',
        readonly=True
    )
    review_comment = fields.Text('審查意見')
    approver_id = fields.Many2one(
        'res.users',
        '核定者',
        readonly=True
    )
    approve_date = fields.Datetime(
        '核定日期',
        readonly=True
    )

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('revision', '補正'),
        ('recommended', '建議核定'),
        ('approved', '已核定'),
        ('paid', '已撥付'),
    ], default='draft', tracking=True, string='狀態')

    # === 計算欄位 ===
    @api.depends('line_ids.current_amount', 'line_ids.cumulative_amount',
                 'retention_rate', 'contract_total')
    def _compute_totals(self):
        """計算合計 (參考 invoice_plan)"""
        for rec in self:
            rec.subtotal = sum(rec.line_ids.mapped('current_amount'))
            rec.cumulative_amount = sum(rec.line_ids.mapped('cumulative_amount'))
            rec.retention = rec.subtotal * (rec.retention_rate / 100)
            rec.payable_amount = rec.subtotal - rec.retention
            if rec.contract_total:
                rec.completion_rate = (rec.cumulative_amount / rec.contract_total) * 100
            else:
                rec.completion_rate = 0.0

    # === 約束檢查 ===
    @api.constrains('estimate_no', 'project_id', 'company_id')
    def _check_estimate_no(self):
        """驗證期次連續性與唯一性"""
        for rec in self:
            # 檢查同一專案同一公司的期次唯一性
            domain = [
                ('project_id', '=', rec.project_id.id),
                ('company_id', '=', rec.company_id.id),
                ('estimate_no', '=', rec.estimate_no),
                ('id', '!=', rec.id),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    f'估驗期次 {rec.estimate_no} 已存在，請使用其他期次'
                )

            # 檢查期次連續性
            if rec.estimate_no > 1:
                prev_domain = [
                    ('project_id', '=', rec.project_id.id),
                    ('company_id', '=', rec.company_id.id),
                    ('estimate_no', '=', rec.estimate_no - 1),
                    ('state', 'not in', ['draft', 'revision']),
                ]
                if self.search_count(prev_domain) == 0:
                    raise ValidationError(
                        f'請先完成第 {rec.estimate_no - 1} 期估驗後，才能提送第 {rec.estimate_no} 期'
                    )

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        """驗證期間合理性"""
        for rec in self:
            if rec.period_start and rec.period_end:
                if rec.period_start > rec.period_end:
                    raise ValidationError('起始日期不可晚於截止日期')

    # === 動作方法 ===
    def action_submit(self):
        """提送估驗"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('請先新增計價明細')
            rec.write({
                'state': 'submitted',
                'submitter_id': self.env.uid,
                'submit_date': fields.Datetime.now(),
            })
        return True

    def action_start_review(self):
        """開始審查"""
        self.write({
            'state': 'reviewing',
            'reviewer_id': self.env.uid,
        })
        return True

    def action_request_revision(self):
        """要求補正"""
        self.write({'state': 'revision'})
        return True

    def action_recommend(self):
        """建議核定"""
        self.write({
            'state': 'recommended',
            'review_date': fields.Datetime.now(),
        })
        return True

    def action_approve(self):
        """核定"""
        for rec in self:
            rec.write({
                'state': 'approved',
                'approver_id': self.env.uid,
                'approve_date': fields.Datetime.now(),
            })
            # 更新工項的實際完成數量
            rec._update_task_actual_qty()
        return True

    def _update_task_actual_qty(self):
        """核定後更新工項的實際完成數量"""
        self.ensure_one()
        for line in self.line_ids:
            if hasattr(line.task_id, 'actual_qty'):
                # 累加本期完成數量到工項
                line.task_id.actual_qty = line.cumulative_qty

    def action_mark_paid(self):
        """標記已撥付"""
        self.write({'state': 'paid'})
        return True

    def action_reset_to_draft(self):
        """重設為草稿"""
        for rec in self:
            if rec.state in ('approved', 'paid'):
                raise UserError('已核定或已撥付的估驗單不可重設')
            rec.write({
                'state': 'draft',
                'submitter_id': False,
                'submit_date': False,
                'reviewer_id': False,
                'review_date': False,
                'approver_id': False,
                'approve_date': False,
            })
        return True

    # === 從驗收單帶入明細 ===
    def action_load_from_acceptance(self):
        """從關聯驗收單載入明細"""
        self.ensure_one()
        if not self.acceptance_ids:
            raise UserError('請先選擇關聯驗收單')

        # 收集驗收單中的工項
        existing_tasks = self.line_ids.mapped('task_id')
        new_lines = []

        for acceptance in self.acceptance_ids:
            for acc_line in acceptance.line_ids:
                if acc_line.task_id not in existing_tasks:
                    # 計算前期累計
                    previous_qty = self._get_previous_qty(acc_line.task_id)

                    new_lines.append(Command.create({
                        'task_id': acc_line.task_id.id,
                        'previous_qty': previous_qty,
                        'current_qty': acc_line.accepted_qty,
                    }))
                    existing_tasks |= acc_line.task_id

        if new_lines:
            self.write({'line_ids': new_lines})
        else:
            raise UserError('所有驗收工項已存在於計價明細中')

        return True

    def _get_previous_qty(self, task):
        """取得工項的前期累計數量"""
        domain = [
            ('task_id', '=', task.id),
            ('estimate_id.project_id', '=', self.project_id.id),
            ('estimate_id.company_id', '=', self.company_id.id),
            ('estimate_id.state', '=', 'approved'),
            ('estimate_id.estimate_no', '<', self.estimate_no),
        ]
        previous_lines = self.env['payment.estimate.line'].search(domain)
        return sum(previous_lines.mapped('current_qty'))

    # === 建立請款單 ===
    def action_create_claim(self):
        """建立請款單"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('只有已核定的估驗單才能建立請款單')

        return {
            'type': 'ir.actions.act_window',
            'name': '建立請款單',
            'res_model': 'payment.claim',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.project_id.id,
                'default_company_id': self.company_id.id,
                'default_estimate_ids': [Command.set([self.id])],
                'default_claim_amount': self.payable_amount,
                'default_claim_period': self.estimate_no,
            },
            'target': 'current',
        }


class PaymentEstimateLine(models.Model):
    """
    估驗計價明細

    設計說明 (v5.1):
    - 關聯契約工項 (task_id) 用於預算追蹤
    - 實際完成數量用於計算 task 的 actual_qty
    - 契約數量/單價來自工項的預算欄位
    """
    _name = 'payment.estimate.line'
    _description = '估驗計價明細'
    _order = 'sequence, id'

    # === 關聯 ===
    estimate_id = fields.Many2one(
        'payment.estimate',
        '估驗單',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer('序號', default=10)

    # === 工項關聯 (v5.1) ===
    task_id = fields.Many2one(
        'project.task',
        '契約工項',
        required=True,
        help='關聯契約工項，用於預算 vs 實際追蹤'
    )

    # === 從工項帶出 (預算資料) ===
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

    # === 預算欄位 (從工項帶出) ===
    planned_qty = fields.Float(
        '契約數量',
        digits='Product Unit of Measure',
        help='契約預算數量'
    )
    unit_price = fields.Float(
        '契約單價',
        digits='Product Price'
    )
    planned_amount = fields.Float(
        '契約金額',
        compute='_compute_planned_amount',
        store=True,
        digits='Product Price',
        help='契約預算金額 (上限)'
    )

    # === 實際完成欄位 ===
    previous_qty = fields.Float(
        '前期累計數量',
        digits='Product Unit of Measure'
    )
    current_qty = fields.Float(
        '本期完成數量',
        digits='Product Unit of Measure',
        required=True,
        help='本期實際完成數量'
    )
    cumulative_qty = fields.Float(
        '累計完成數量',
        compute='_compute_amounts',
        store=True,
        digits='Product Unit of Measure'
    )

    current_amount = fields.Float(
        '本期金額',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )
    cumulative_amount = fields.Float(
        '累計金額',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )

    # === 對比分析 ===
    completion_rate = fields.Float(
        '完成率 (%)',
        compute='_compute_amounts',
        store=True,
        digits=(5, 2),
        help='累計金額 / 契約金額 x 100'
    )
    over_budget = fields.Boolean(
        '超出預算',
        compute='_compute_amounts',
        store=True
    )

    note = fields.Text('備註')

    # === 計算欄位 ===
    @api.depends('planned_qty', 'unit_price')
    def _compute_planned_amount(self):
        """計算契約金額"""
        for line in self:
            line.planned_amount = line.planned_qty * line.unit_price

    @api.depends('previous_qty', 'current_qty', 'unit_price', 'planned_amount')
    def _compute_amounts(self):
        """計算金額與完成率"""
        for line in self:
            line.cumulative_qty = line.previous_qty + line.current_qty
            line.current_amount = line.current_qty * line.unit_price
            line.cumulative_amount = line.cumulative_qty * line.unit_price

            if line.planned_amount:
                line.completion_rate = (line.cumulative_amount / line.planned_amount) * 100
                line.over_budget = line.cumulative_amount > line.planned_amount
            else:
                line.completion_rate = 0.0
                line.over_budget = False

    # === onchange ===
    @api.onchange('task_id')
    def _onchange_task_id(self):
        """工項變更時帶入契約資訊"""
        if self.task_id:
            # 從工項帶入契約數量和單價
            if hasattr(self.task_id, 'planned_qty'):
                self.planned_qty = self.task_id.planned_qty
            if hasattr(self.task_id, 'unit_price'):
                self.unit_price = self.task_id.unit_price

            # 計算前期累計
            if self.estimate_id and self.estimate_id.project_id:
                self.previous_qty = self.estimate_id._get_previous_qty(self.task_id)

    # === 約束檢查 ===
    @api.constrains('current_qty')
    def _check_current_qty(self):
        """驗證本期數量"""
        for line in self:
            if line.current_qty < 0:
                raise ValidationError('本期完成數量不可為負數')

    @api.constrains('cumulative_qty', 'planned_qty')
    def _check_over_estimate(self):
        """警告：累計數量超過契約數量"""
        for line in self:
            if line.cumulative_qty > line.planned_qty and line.planned_qty > 0:
                # 超估警告 (不阻擋，但記錄)
                if line.estimate_id:
                    line.estimate_id.message_post(
                        body=f'警告：項目 {line.item_no or line.task_id.name} '
                             f'累計估驗數量 ({line.cumulative_qty}) 超過契約數量 ({line.planned_qty})'
                    )
