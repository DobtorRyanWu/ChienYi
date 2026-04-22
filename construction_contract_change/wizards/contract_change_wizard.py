# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command
from odoo.exceptions import UserError


class ContractChangeWizardLine(models.TransientModel):
    """契約變更精靈明細"""
    _name = 'contract.change.wizard.line'
    _description = '契約變更精靈明細'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'contract.change.wizard',
        required=True,
        ondelete='cascade')

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 工項關聯 ===
    task_id = fields.Many2one(
        'project.task',
        string='原工項',
        help='修改/刪除時選擇既有工項')

    parent_task_id = fields.Many2one(
        'project.task',
        string='父工項',
        help='新增時選擇父工項')

    # === 工項資訊 ===
    item_no = fields.Char(
        string='工項編號')

    item_name = fields.Char(
        string='工項名稱')

    # === 變更類型 ===
    change_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('delete', '刪除'),
    ], string='變更類型')

    # === 數量單價 ===
    unit = fields.Char(string='單位')

    original_qty = fields.Float(
        string='原數量',
        digits=(16, 4),
        readonly=True)

    original_unit_price = fields.Float(
        string='原單價',
        digits=(16, 2),
        readonly=True)

    original_amount = fields.Float(
        string='原金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True)

    new_qty = fields.Float(
        string='新數量',
        digits=(16, 4))

    new_unit_price = fields.Float(
        string='新單價',
        digits=(16, 2))

    new_amount = fields.Float(
        string='新金額',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True)

    change_amount = fields.Float(
        string='金額增減',
        digits=(16, 2),
        compute='_compute_amounts',
        store=True)

    currency_id = fields.Many2one(
        'res.currency',
        related='wizard_id.currency_id',
        readonly=True)

    # === 計算方法 ===
    @api.depends('original_qty', 'original_unit_price',
                 'new_qty', 'new_unit_price', 'change_type')
    def _compute_amounts(self):
        """計算金額"""
        for line in self:
            line.original_amount = line.original_qty * line.original_unit_price

            if line.change_type == 'delete':
                line.new_amount = 0.0
                line.change_amount = -line.original_amount
            elif line.change_type == 'add':
                line.new_amount = line.new_qty * line.new_unit_price
                line.change_amount = line.new_amount
            elif line.change_type == 'modify':
                line.new_amount = line.new_qty * line.new_unit_price
                line.change_amount = line.new_amount - line.original_amount
            else:
                # 變更類型為空 = 不變更
                line.new_amount = 0.0
                line.change_amount = 0.0

    # === Onchange ===
    @api.onchange('task_id')
    def _onchange_task_id(self):
        """選擇原工項時，自動填入資訊"""
        if self.task_id:
            self.item_no = self.task_id.item_no
            self.item_name = self.task_id.name
            self.unit = self.task_id.unit
            self.original_qty = self.task_id.planned_qty
            self.original_unit_price = self.task_id.unit_price

            if self.change_type == 'modify':
                self.new_qty = self.task_id.planned_qty
                self.new_unit_price = self.task_id.unit_price

    @api.onchange('change_type')
    def _onchange_change_type(self):
        """變更類型改變時的處理"""
        if self.change_type == 'add':
            self.task_id = False
            self.original_qty = 0.0
            self.original_unit_price = 0.0
        elif self.change_type == 'modify' and self.task_id:
            self.new_qty = self.original_qty
            self.new_unit_price = self.original_unit_price
        elif self.change_type == 'delete':
            self.new_qty = 0.0
            self.new_unit_price = 0.0
        elif not self.change_type:
            self.new_qty = 0.0
            self.new_unit_price = 0.0

    @api.onchange('parent_task_id')
    def _onchange_parent_task_id(self):
        """選擇父工項時自動填入單位"""
        if self.change_type == 'add' and self.parent_task_id:
            if self.parent_task_id.unit:
                self.unit = self.parent_task_id.unit


class ContractChangeWizard(models.TransientModel):
    """契約變更精靈 - 匯入工程案件並管理變更明細"""
    _name = 'contract.change.wizard'
    _description = '匯入工程案件精靈'

    change_order_id = fields.Many2one(
        'contract.change.order',
        string='契約變更單',
        required=True,
        readonly=True)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        domain="[('state', 'in', ['construction', 'completion', 'acceptance'])]",
        help='選擇要匯入的工程案件')

    wizard_line_ids = fields.One2many(
        'contract.change.wizard.line',
        'wizard_id',
        string='工項列表')

    # === 單價調整比例 ===
    adjust_rate = fields.Float(
        string='單價調整比例 (%)',
        default=100.0,
        help='統一調整所有工項的單價。\n'
             '計算方式：新單價 = 原單價 × 比例%\n'
             '範例：輸入 80 表示原單價打八折，輸入 120 表示加價兩成')

    # === 統計欄位 ===
    modify_count = fields.Integer(
        string='修改項數',
        compute='_compute_statistics')

    delete_count = fields.Integer(
        string='刪除項數',
        compute='_compute_statistics')

    add_count = fields.Integer(
        string='新增項數',
        compute='_compute_statistics')

    total_change_amount = fields.Float(
        string='總變更金額',
        digits=(16, 2),
        compute='_compute_statistics')

    currency_id = fields.Many2one(
        'res.currency',
        related='change_order_id.currency_id',
        readonly=True)

    # === 計算統計 ===
    @api.depends('wizard_line_ids.change_type',
                 'wizard_line_ids.change_amount')
    def _compute_statistics(self):
        """計算統計資訊"""
        for wizard in self:
            lines_with_change = wizard.wizard_line_ids.filtered('change_type')
            wizard.modify_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'modify'))
            wizard.delete_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'delete'))
            wizard.add_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'add'))
            wizard.total_change_amount = sum(
                lines_with_change.mapped('change_amount'))

    # === 核心：選擇工程後自動載入工項 ===
    @api.onchange('project_id')
    def _onchange_project_id(self):
        """選擇工程後，自動載入所有契約工項"""
        if not self.project_id:
            self.wizard_line_ids = [Command.clear()]
            return

        # 搜尋該工程的所有工項
        tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('active', '=', True),
        ], order='sequence, item_no')

        lines = [Command.clear()]
        seq = 10
        for task in tasks:
            lines.append(Command.create({
                'sequence': seq,
                'task_id': task.id,
                'parent_task_id': task.parent_id.id if task.parent_id else False,
                'item_no': task.item_no,
                'item_name': task.name,
                'unit': task.unit or '',
                'original_qty': task.planned_qty or 0.0,
                'original_unit_price': task.unit_price or 0.0,
                'new_qty': task.planned_qty or 0.0,
                'new_unit_price': task.unit_price or 0.0,
            }))
            seq += 10
        self.wizard_line_ids = lines

        # 重設調整比例
        self.adjust_rate = 100.0

    # === 套用比例調整 ===
    def action_apply_rate(self):
        """一次調整所有工項：新單價 = 原單價 × (比例 / 100)"""
        self.ensure_one()
        if self.adjust_rate <= 0:
            raise UserError('調整比例必須大於 0！')

        rate = self.adjust_rate / 100  # 例如 80 → 0.8
        for line in self.wizard_line_ids:
            if line.task_id:  # 只調整既有工項（非新增）
                line.change_type = 'modify'
                line.new_unit_price = line.original_unit_price * rate

        return {'type': 'ir.actions.do_nothing'}

    # === 新增工項行 ===
    def action_add_new_line(self):
        """添加新的新增工項行"""
        self.ensure_one()
        max_sequence = max(self.wizard_line_ids.mapped('sequence') or [0])

        self.env['contract.change.wizard.line'].create({
            'wizard_id': self.id,
            'sequence': max_sequence + 10,
            'change_type': 'add',
        })
        return {'type': 'ir.actions.do_nothing'}

    # === 取消返回 ===
    def action_cancel(self):
        """取消並返回變更單"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contract.change.order',
            'res_id': self.change_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # === 確認儲存 ===
    def action_confirm(self):
        """確認並生成變更明細"""
        self.ensure_one()

        if not self.project_id:
            raise UserError('請先選擇所屬工程！')

        # 只處理有變更類型的記錄
        lines_to_save = self.wizard_line_ids.filtered('change_type')
        if not lines_to_save:
            raise UserError('請至少設定一個變更類型！')

        # 1. 寫入 project_id 與契約資訊到變更單
        vals = {'project_id': self.project_id.id}

        if not self.change_order_id.original_contract_amount:
            vals['original_contract_amount'] = (
                self.project_id.current_contract_amount or
                self.project_id.contract_amount or 0.0)
        if not self.change_order_id.original_duration:
            vals['original_duration'] = (
                self.project_id.current_duration or
                self.project_id.contract_duration or 0)

        self.change_order_id.write(vals)

        # 2. 刪除原有的所有變更明細
        self.change_order_id.line_ids.unlink()

        # 3. 批量創建變更明細
        for line in lines_to_save:
            self._create_change_order_line(line)

        # 4. 跳轉回變更單表單
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contract.change.order',
            'res_id': self.change_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_change_order_line(self, wizard_line):
        """根據 wizard line 創建變更明細記錄"""
        vals = {
            'change_order_id': self.change_order_id.id,
            'sequence': wizard_line.sequence,
            'change_type': wizard_line.change_type,
            'item_no': wizard_line.item_no,
            'item_name': wizard_line.item_name,
            'unit': wizard_line.unit,
        }

        if wizard_line.change_type == 'add':
            vals.update({
                'parent_task_id': wizard_line.parent_task_id.id if wizard_line.parent_task_id else False,
                'new_qty': wizard_line.new_qty,
                'new_unit_price': wizard_line.new_unit_price,
                'original_qty': 0.0,
                'original_unit_price': 0.0,
            })
        else:
            vals.update({
                'task_id': wizard_line.task_id.id,
                'parent_task_id': wizard_line.parent_task_id.id if wizard_line.parent_task_id else False,
                'original_qty': wizard_line.original_qty,
                'original_unit_price': wizard_line.original_unit_price,
            })

            if wizard_line.change_type == 'modify':
                vals.update({
                    'new_qty': wizard_line.new_qty,
                    'new_unit_price': wizard_line.new_unit_price,
                })
            elif wizard_line.change_type == 'delete':
                vals.update({
                    'new_qty': 0.0,
                    'new_unit_price': 0.0,
                })

        self.env['contract.change.order.line'].create(vals)
