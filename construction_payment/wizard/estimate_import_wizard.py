# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command
from odoo.exceptions import UserError


class EstimateImportWizard(models.TransientModel):
    """
    匯入工程案件 Wizard

    操作流程：
    1. 選擇「所屬工程」
    2. 自動載入該工程的契約工項（非彙總項）
    3. 同時帶入施工日誌累計完成數量（截至估驗日期）
    4. 使用者編輯「本次估驗數量」
    5. 點「完成匯入」寫入估驗單
    """
    _name = 'estimate.import.wizard'
    _description = '匯入工程案件'

    estimate_id = fields.Many2one(
        'payment.estimate',
        '目標估驗單',
        required=True,
        readonly=True
    )
    estimate_date = fields.Date(
        '估驗日期',
        required=True,
        default=fields.Date.context_today,
        help='估驗截止日期，施工日誌累計以此日期為節點'
    )
    project_id = fields.Many2one(
        'supervision.project',
        '所屬工程',
        required=True
    )
    project_type = fields.Selection(
        related='project_id.project_type',
        readonly=True
    )
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        '通報單',
        domain="[('project_id', '=', project_id), ('state', '!=', 'closed')]",
        help='預約式工程：選擇通報單後載入工項'
    )
    contract_no = fields.Char(
        '契約編號',
        related='project_id.contract_no',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    contract_amount = fields.Monetary(
        '契約金額',
        related='project_id.contract_amount',
        readonly=True
    )
    line_ids = fields.One2many(
        'estimate.import.wizard.line',
        'wizard_id',
        '工項明細'
    )

    @api.onchange('estimate_date')
    def _onchange_estimate_date(self):
        """估驗日期變更時，重新計算可估驗數量"""
        if not self.line_ids or not self.estimate_date:
            return
        DailyLogLine = self.env['daily.log.line']
        for line in self.line_ids:
            if line.task_id:
                last_log = DailyLogLine.search([
                    ('work_item_id', '=', line.task_id.id),
                    ('date', '<=', self.estimate_date),
                ], order='date desc, id desc', limit=1)
                line.available_qty = last_log.cumulative_qty if last_log else 0.0

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """選擇工程後自動載入工項（一般式）或等待選擇通報單（預約式）"""
        self.line_ids = [(5, 0, 0)]  # 清空
        self.slip_id = False
        if not self.project_id:
            return

        # 預約式工程：等待選擇通報單
        if self.project_id.project_type == 'reservation':
            return

        # 一般式工程：直接載入契約工項
        self._load_tasks_from_project()

    @api.onchange('slip_id')
    def _onchange_slip_id(self):
        """選擇通報單後，從通報單明細載入工項"""
        self.line_ids = [(5, 0, 0)]  # 清空
        if not self.slip_id:
            return

        slip = self.slip_id
        if not slip.detail_line_ids:
            return {'warning': {
                'title': '提示',
                'message': '此通報單尚未建立詳細表項目',
            }}

        EstimateLine = self.env['payment.estimate.line']
        new_lines = []
        for seq, slip_line in enumerate(slip.detail_line_ids, start=1):
            task = slip_line.task_id
            if not task:
                continue

            contract_qty = task.original_planned_qty or task.planned_qty

            # 取得前期累計估驗數量（已核定）
            prev_lines = EstimateLine.search([
                ('task_id', '=', task.id),
                ('estimate_id.project_id', '=', self.project_id.id),
                ('estimate_id.state', '=', 'approved'),
            ])
            previous_estimate_qty = sum(prev_lines.mapped('estimate_qty'))

            new_lines.append(Command.create({
                'sequence': seq,
                'task_id': task.id,
                'contract_qty': contract_qty,
                'approved_qty': task.planned_qty,
                'unit_price': task.unit_price,
                'available_qty': slip_line.actual_qty,
                'previous_estimate_qty': previous_estimate_qty,
                'estimate_qty': 0.0,
            }))

        self.line_ids = new_lines

    def _load_tasks_from_project(self):
        """從工程直接載入契約工項（一般式工程用）"""
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.project_id.id),
            ('active', '=', True),
        ], order='sequence, item_no')

        if not tasks:
            return {'warning': {
                'title': '提示',
                'message': '此工程案件尚未建立契約工項',
            }}

        DailyLogLine = self.env['daily.log.line']
        EstimateLine = self.env['payment.estimate.line']

        new_lines = []
        for seq, task in enumerate(tasks, start=1):
            contract_qty = task.original_planned_qty or task.planned_qty

            available_qty = 0.0
            if self.estimate_date:
                last_log = DailyLogLine.search([
                    ('work_item_id', '=', task.id),
                    ('date', '<=', self.estimate_date),
                ], order='date desc, id desc', limit=1)
                available_qty = last_log.cumulative_qty if last_log else 0.0

            prev_lines = EstimateLine.search([
                ('task_id', '=', task.id),
                ('estimate_id.project_id', '=', self.project_id.id),
                ('estimate_id.state', '=', 'approved'),
            ])
            previous_estimate_qty = sum(prev_lines.mapped('estimate_qty'))

            new_lines.append(Command.create({
                'sequence': seq,
                'task_id': task.id,
                'contract_qty': contract_qty,
                'approved_qty': task.planned_qty,
                'unit_price': task.unit_price,
                'available_qty': available_qty,
                'previous_estimate_qty': previous_estimate_qty,
                'estimate_qty': 0.0,
            }))

        self.line_ids = new_lines

    def action_cancel(self):
        """取消匯入，返回估驗單"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'payment.estimate',
            'res_id': self.estimate_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_import(self):
        """完成匯入，將資料寫入估驗單"""
        self.ensure_one()
        if not self.project_id:
            raise UserError('請選擇所屬工程')
        if not self.line_ids:
            raise UserError('此工程案件沒有可匯入的工項')

        estimate = self.estimate_id

        # 計算次數與名稱（首次設定 project_id 時）
        if not estimate.project_id:
            count = self.env['payment.estimate'].search_count([
                ('project_id', '=', self.project_id.id)
            ])
            estimate_no = count + 1
        else:
            estimate_no = estimate.estimate_no

        # 建立估驗明細
        line_vals = []
        for wiz_line in self.line_ids:
            line_vals.append(Command.create({
                'task_id': wiz_line.task_id.id,
                'sequence': wiz_line.sequence,
                'contract_qty': wiz_line.contract_qty,
                'approved_qty': wiz_line.approved_qty,
                'unit_price': wiz_line.unit_price,
                'estimate_qty': wiz_line.estimate_qty,
                'note': wiz_line.note,
            }))

        write_vals = {
            'project_id': self.project_id.id,
            'estimate_date': self.estimate_date,
            'estimate_no': estimate_no,
            'name': f'第{estimate_no}次估驗計價',
            'line_ids': line_vals,
        }
        if self.slip_id:
            write_vals['slip_id'] = self.slip_id.id
        estimate.write(write_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'payment.estimate',
            'res_id': estimate.id,
            'view_mode': 'form',
            'target': 'current',
        }


class EstimateImportWizardLine(models.TransientModel):
    """匯入工程案件明細"""
    _name = 'estimate.import.wizard.line'
    _description = '匯入工程案件明細'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'estimate.import.wizard',
        '匯入 Wizard',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer('序號', default=10)

    # === 工項 ===
    task_id = fields.Many2one(
        'project.task',
        '工項',
        required=True
    )
    description = fields.Char(
        '項目及說明',
        related='task_id.name',
        readonly=True
    )
    parent_item_name = fields.Char(
        '父工項路徑',
        compute='_compute_parent_item_name',
        readonly=True
    )
    item_no = fields.Char(
        '項目編號',
        related='task_id.item_no',
        readonly=True
    )
    unit = fields.Char(
        '單位',
        related='task_id.unit',
        readonly=True
    )

    # === 數量資訊（view 層級 readonly）===
    contract_qty = fields.Float(
        '契約數量',
        digits=(16, 4),
        help='原始契約數量（變更前）'
    )
    approved_qty = fields.Float(
        '變更後核定數量',
        digits=(16, 4)
    )
    unit_price = fields.Float(
        '單價',
        digits=(16, 2)
    )
    available_qty = fields.Float(
        '本次可估驗數量',
        digits=(16, 4),
        help='施工日誌截至估驗日期的累計完成數量'
    )
    previous_estimate_qty = fields.Float(
        '前期累計估驗',
        digits=(16, 4),
        help='歷次已核定估驗的數量合計'
    )

    # === 可編輯欄位 ===
    estimate_qty = fields.Float(
        '本次估驗數量',
        digits=(16, 4),
        help='本次估驗的數量'
    )

    # === 計算欄位 ===
    estimate_amount = fields.Float(
        '本次估驗金額',
        digits=(16, 2),
        compute='_compute_estimate_amount',
        readonly=True
    )
    cumulative_estimate_qty = fields.Float(
        '累計估驗數量',
        digits=(16, 4),
        compute='_compute_estimate_amount',
        readonly=True
    )

    # === 備註 ===
    note = fields.Text('備註')

    @api.depends('task_id.parent_id', 'task_id.parent_id.full_item_path')
    def _compute_parent_item_name(self):
        for line in self:
            if line.task_id and line.task_id.parent_id:
                line.parent_item_name = line.task_id.parent_id.full_item_path or ''
            else:
                line.parent_item_name = ''

    @api.depends('estimate_qty', 'unit_price', 'previous_estimate_qty')
    def _compute_estimate_amount(self):
        for line in self:
            line.estimate_amount = line.unit_price * line.estimate_qty
            line.cumulative_estimate_qty = line.previous_estimate_qty + line.estimate_qty
