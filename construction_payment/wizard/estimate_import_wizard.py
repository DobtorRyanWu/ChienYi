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
        'project.project',
        '所屬工程',
        required=True
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

    def _get_period_available_qty(self, task):
        """本期可估 = 累計到(本次估驗日) − 累計到(前一張估驗單估驗日)

        彙總項採「一式」慣例回 1。前一張：同工程、估驗日較早、排除本單，不論狀態。
        """
        if not task or not self.estimate_date:
            return 0.0
        if task.is_summary_item:
            return 1.0
        EstimateLine = self.env['payment.estimate.line']
        this_cum = EstimateLine._get_cumulative_qty_at(task, self.estimate_date)
        prev_est = self.env['payment.estimate'].search([
            ('project_id', '=', self.project_id.id),
            ('estimate_date', '<', self.estimate_date),
            ('id', '!=', self.estimate_id.id),
        ], order='estimate_date desc, id desc', limit=1)
        prev_cum = (
            EstimateLine._get_cumulative_qty_at(task, prev_est.estimate_date)
            if prev_est else 0.0
        )
        return this_cum - prev_cum

    @api.onchange('estimate_date')
    def _onchange_estimate_date(self):
        """估驗日期變更時，重新計算可估驗數量（本期完成量）"""
        if not self.line_ids or not self.estimate_date:
            return
        for line in self.line_ids:
            if line.task_id:
                line.available_qty = self._get_period_available_qty(line.task_id)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """選擇工程後自動載入契約工項（一般式／預約式行為一致）

        2026-08-18 移除預約式的「先選通報單再載工項」分支：估驗計價表是契約詳細價目表
        的鏡像（一期一工項一列），與通報單無關，兩式都該直接載全案契約工項。
        原本預約式在此直接 return、一列都不載，是本功能無法建立期別估驗的根因。
        """
        self.line_ids = [(5, 0, 0)]  # 清空
        if not self.project_id:
            return
        self._load_tasks_from_project()

    def _load_tasks_from_project(self):
        """從工程直接載入契約工項（一般式與預約式共用）"""
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.id),
            ('active', '=', True),
        ], order='sequence, item_no')

        if not tasks:
            return {'warning': {
                'title': '提示',
                'message': '此工程案件尚未建立契約工項',
            }}

        EstimateLine = self.env['payment.estimate.line']

        new_lines = []
        for seq, task in enumerate(tasks, start=1):
            # 彙總項：以「一式」呈現（數量固定 1）
            if task.is_summary_item:
                new_lines.append(Command.create({
                    'sequence': seq,
                    'task_id': task.id,
                    'contract_qty': 1.0,
                    'approved_qty': 1.0,
                    'unit_price': 0.0,
                    'available_qty': 1.0,
                    'previous_estimate_qty': 0.0,
                    'estimate_qty': 1.0,
                }))
                continue

            contract_qty = task.original_planned_qty or task.planned_qty
            available_qty = self._get_period_available_qty(task)

            prev_lines = EstimateLine.search([
                ('task_id', '=', task.id),
                ('estimate_id.project_id', '=', self.project_id.id),
                ('estimate_id.state', '=', 'approved'),
                ('estimate_id.estimate_date', '<', self.estimate_date),
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
        EstimateLine = self.env['payment.estimate.line']

        # 建立估驗明細：契約數量/核定數量/單價一律由 task 權威重新產生
        # （精靈畫面這些欄位為 readonly，存檔時不會回傳伺服器，直接讀 wiz_line 會得到 0；
        #   故改以 _prepare_line_vals 依 task 重算，僅本次估驗數量與備註取自使用者輸入）
        line_vals = []
        for wiz_line in self.line_ids:
            if not wiz_line.task_id:
                continue
            vals = EstimateLine._prepare_line_vals(wiz_line.task_id, wiz_line.sequence)
            vals['estimate_qty'] = wiz_line.estimate_qty
            vals['note'] = wiz_line.note
            line_vals.append(Command.create(vals))

        # 次數與名稱由 payment.estimate 依 estimate_date 自動重排（write 帶 estimate_date 觸發）
        estimate.write({
            'project_id': self.project_id.id,
            'estimate_date': self.estimate_date,
            'line_ids': line_vals,
        })

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
        '原始契約數量',
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
