# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class PaymentEstimate(models.Model):
    """
    估驗計價

    重構版本：
    - 以「匯入工程案件」為核心操作流程
    - 簡化狀態為 草稿→待核定→已核定→已歸檔
    - 移除多公司架構、驗收單關聯、保留款等
    """
    _name = 'payment.estimate'
    _description = '估驗計價'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'estimate_no asc, id desc'

    # === 基本資訊 ===
    name = fields.Char(
        '估驗名稱',
        readonly=True,
        copy=False,
        help='自動產生，格式：第N次估驗計價'
    )
    estimate_no = fields.Integer(
        '次數',
        readonly=True,
        copy=False,
        help='同一工程中自動遞增'
    )

    # === 工程資訊區塊（全部 readonly，由匯入帶入）===
    project_id = fields.Many2one(
        'supervision.project',
        '所屬工程',
        readonly=True,
        tracking=True,
        index=True
    )
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        '通報單',
        readonly=True,
        tracking=True,
        help='預約式工程的關聯通報單'
    )
    contract_no = fields.Char(
        '契約編號',
        related='project_id.contract_no',
        store=True,
        readonly=True
    )
    contract_amount = fields.Monetary(
        '契約金額',
        related='project_id.contract_amount',
        store=True,
        readonly=True
    )

    # === 估驗資訊區塊 ===
    estimate_date = fields.Date(
        '估驗日期',
        tracking=True,
        help='估驗截止日期，施工日誌累計以此日期為節點'
    )
    submitted_date = fields.Datetime(
        '提出日期',
        readonly=True
    )
    submitted_by_id = fields.Many2one(
        'res.users',
        '提出人',
        readonly=True
    )
    approved_by_id = fields.Many2one(
        'res.users',
        '核定人',
        readonly=True
    )
    approved_date = fields.Datetime(
        '核定日期',
        readonly=True
    )

    # === 金額 ===
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    subtotal = fields.Monetary(
        '本次估驗總金額',
        compute='_compute_subtotal',
        store=True,
        tracking=True
    )

    # === 計價明細 ===
    line_ids = fields.One2many(
        'payment.estimate.line',
        'estimate_id',
        '估驗計價表',
        copy=True
    )

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('pending_approval', '待核定'),
        ('approved', '已核定'),
        ('archived', '已歸檔'),
    ], default='draft', tracking=True, string='狀態')

    # === 計算欄位 ===
    @api.depends('line_ids.estimate_amount')
    def _compute_subtotal(self):
        """計算本次估驗總金額"""
        for rec in self:
            rec.subtotal = sum(rec.line_ids.mapped('estimate_amount'))

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        """建立時自動計算次數和名稱"""
        for vals in vals_list:
            project_id = vals.get('project_id')
            if project_id and not vals.get('estimate_no'):
                count = self.search_count([
                    ('project_id', '=', project_id)
                ])
                vals['estimate_no'] = count + 1
            estimate_no = vals.get('estimate_no', 1)
            vals['name'] = f'第{estimate_no}次估驗計價'
        return super().create(vals_list)

    # === 動作方法 ===
    def action_open_import_wizard(self):
        """開啟匯入工程案件 Wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '匯入工程案件',
            'res_model': 'estimate.import.wizard',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_estimate_id': self.id,
            },
        }

    def action_submit_estimate(self):
        """提出估驗"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('請先匯入工程案件')
            rec.write({
                'state': 'pending_approval',
                'submitted_by_id': self.env.uid,
                'submitted_date': fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        """核定"""
        self.write({
            'state': 'approved',
            'approved_by_id': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })
        return True

    def action_archive_estimate(self):
        """歸檔"""
        self.write({'state': 'archived'})
        return True

    def action_reset_to_draft(self):
        """退回草稿"""
        for rec in self:
            if rec.state != 'pending_approval':
                raise UserError('只有「待核定」狀態才能退回草稿')
            # 清空明細與工程資訊，讓使用者可重新匯入
            rec.line_ids.unlink()
            rec.write({
                'state': 'draft',
                'project_id': False,
                'submitted_by_id': False,
                'submitted_date': False,
                'approved_by_id': False,
                'approved_date': False,
            })
        return True


class PaymentEstimateLine(models.Model):
    """
    估驗計價明細

    欄位說明：
    - contract_qty: 原始契約數量（變更前）
    - approved_qty: 變更後核定數量（現行 planned_qty）
    - available_qty: 本次可估驗數量（施工日誌截至估驗日期的累計）
    - estimate_qty: 本次估驗數量（唯一可編輯欄位）
    - cumulative_estimate_qty: 累計估驗數量（歷次已核定 + 本次）
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

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task',
        '工項',
        required=True,
        readonly=True
    )

    # === 工項資訊（readonly）===
    description = fields.Char(
        '項目及說明',
        related='task_id.name',
        store=True,
        readonly=True
    )
    parent_item_name = fields.Char(
        '父項次',
        compute='_compute_parent_item_name',
        store=True,
        readonly=True
    )
    item_no = fields.Char(
        '項目編號',
        related='task_id.item_no',
        store=True,
        readonly=True
    )
    unit = fields.Char(
        '單位',
        related='task_id.unit',
        store=True,
        readonly=True
    )

    # === 數量與單價（readonly，由匯入帶入）===
    contract_qty = fields.Float(
        '契約數量',
        digits=(16, 4),
        readonly=True,
        help='原始契約數量（變更前）'
    )
    approved_qty = fields.Float(
        '變更後核定數量',
        digits=(16, 4),
        readonly=True,
        help='經契約變更後的現行數量'
    )
    unit_price = fields.Float(
        '單價',
        digits=(16, 2),
        readonly=True
    )

    # === 估驗數量（唯一可編輯）===
    estimate_qty = fields.Float(
        '本次估驗數量',
        digits=(16, 4),
        help='本次估驗的數量（唯一可編輯欄位）'
    )

    # === 計算欄位 ===
    available_qty = fields.Float(
        '本次可估驗數量',
        digits=(16, 4),
        compute='_compute_available_qty',
        readonly=True,
        help='施工日誌截至估驗日期的累計完成數量（即時計算，日誌更新後自動反映）'
    )
    cumulative_estimate_qty = fields.Float(
        '累計估驗數量',
        digits=(16, 4),
        compute='_compute_cumulative',
        store=True,
        readonly=True,
        help='歷次已核定估驗的數量合計 + 本次'
    )
    estimate_amount = fields.Float(
        '本次估驗金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True,
        readonly=True,
        help='單價 × 本次估驗數量'
    )
    cumulative_estimate_amount = fields.Float(
        '累計估驗金額',
        digits=(16, 2),
        compute='_compute_cumulative',
        store=True,
        readonly=True,
        help='單價 × 累計估驗數量'
    )

    # === 備註 ===
    note = fields.Text('備註', readonly=True)

    # === 計算方法 ===
    @api.depends('task_id.parent_id', 'task_id.parent_id.item_no')
    def _compute_parent_item_name(self):
        """計算父項次"""
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.item_no or ''
            else:
                line.parent_item_name = ''

    @api.depends('task_id', 'estimate_id.estimate_date')
    def _compute_available_qty(self):
        """計算本次可估驗數量（施工日誌截至估驗日期的累計）"""
        DailyLogLine = self.env['daily.log.line']
        for line in self:
            if not line.task_id or not line.estimate_id.estimate_date:
                line.available_qty = 0.0
                continue
            last_log = DailyLogLine.search([
                ('work_item_id', '=', line.task_id.id),
                ('date', '<=', line.estimate_id.estimate_date),
            ], order='date desc, id desc', limit=1)
            line.available_qty = last_log.cumulative_qty if last_log else 0.0

    @api.depends('estimate_qty', 'unit_price')
    def _compute_amounts(self):
        """計算本次估驗金額"""
        for line in self:
            line.estimate_amount = line.unit_price * line.estimate_qty

    @api.depends('estimate_qty', 'task_id', 'estimate_id.project_id')
    def _compute_cumulative(self):
        """計算累計估驗數量與金額"""
        for line in self:
            if not line.task_id or not line.estimate_id.project_id:
                line.cumulative_estimate_qty = line.estimate_qty
                line.cumulative_estimate_amount = line.unit_price * line.estimate_qty
                continue
            # 查詢同工程同工項已核定估驗的 estimate_qty 總和
            prev_lines = self.search([
                ('task_id', '=', line.task_id.id),
                ('estimate_id.project_id', '=', line.estimate_id.project_id.id),
                ('estimate_id.state', '=', 'approved'),
                ('estimate_id', '!=', line.estimate_id.id),
            ])
            prev_total = sum(prev_lines.mapped('estimate_qty'))
            line.cumulative_estimate_qty = prev_total + line.estimate_qty
            line.cumulative_estimate_amount = line.unit_price * line.cumulative_estimate_qty
