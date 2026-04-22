# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


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
        domain="[('is_summary_item', '=', True)]",
        help='新增時選擇父工項')

    parent_task_path = fields.Char(
        string='父工項路徑',
        related='parent_task_id.full_item_path',
        readonly=True)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        related='wizard_id.project_id',
        readonly=True)

    # === 工項資訊 ===
    item_no = fields.Char(
        string='工項編號')

    item_name = fields.Char(
        string='工項名稱')

    display_item_name = fields.Char(
        string='工項名稱',
        compute='_compute_display_item_name',
        store=False)

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
        compute='_compute_original_values',
        store=True)

    original_unit_price = fields.Float(
        string='原單價',
        digits=(16, 2),
        compute='_compute_original_values',
        store=True)

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
    @api.depends('change_type', 'task_id', 'task_id.name', 'item_name')
    def _compute_display_item_name(self):
        """工項名稱：有 task_id 則從 task 取，否則用 item_name（新增行）"""
        for line in self:
            if line.task_id:
                line.display_item_name = line.task_id.name
            else:
                line.display_item_name = line.item_name or ''

    @api.depends('task_id', 'task_id.planned_qty', 'task_id.unit_price')
    def _compute_original_values(self):
        """從 task_id 自動帶入原數量與原單價，避免 form 儲存時 readonly 欄位被清空"""
        for line in self:
            if line.task_id:
                line.original_qty = line.task_id.planned_qty
                line.original_unit_price = line.task_id.unit_price
            else:
                line.original_qty = 0.0
                line.original_unit_price = 0.0

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
                # 未設定變更類型：顯示現有金額作參考，變更金額為 0
                line.new_amount = line.new_qty * line.new_unit_price
                line.change_amount = 0.0

    # === Onchange ===
    @api.onchange('task_id')
    def _onchange_task_id(self):
        """選擇原工項時，自動填入資訊"""
        if self.task_id:
            # 使用 display_item_no（葉節點編號），避免存入完整路徑如 "1.1.7"
            self.item_no = self.task_id.display_item_no or self.task_id.item_no
            self.item_name = self.task_id.name
            self.unit = self.task_id.unit
            # original_qty / original_unit_price 由 _compute_original_values 自動計算

            if self.change_type == 'modify':
                self.new_qty = self.task_id.planned_qty
                self.new_unit_price = self.task_id.unit_price

    @api.onchange('change_type')
    def _onchange_change_type(self):
        """變更類型改變時的處理"""
        if self.change_type == 'add':
            self.task_id = False
            # original_qty / original_unit_price 由 _compute_original_values 自動設為 0
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
        """選擇父工項時自動填入單位並產生工項編號"""
        if self.change_type == 'add':
            if self.parent_task_id and self.parent_task_id.unit:
                self.unit = self.parent_task_id.unit
            self.item_no = self._generate_next_item_no()

    def _generate_next_item_no(self):
        """根據父工項自動產生下一個工項編號"""
        if not self.wizard_id.project_id:
            return ''

        pid = self.parent_task_id.id if self.parent_task_id else False

        existing = self.env['project.task'].search([
            ('supervision_project_id', '=', self.wizard_id.project_id.id),
            ('parent_id', '=', pid),
            ('active', '=', True),
        ])
        wizard_adds = self.wizard_id.wizard_line_ids.filtered(
            lambda l: l.change_type == 'add'
            and l.parent_task_id.id == pid
            and l.item_no
            and l.id != self._origin.id
        )
        # 優先使用 display_item_no（葉節點），避免完整路徑（如 "1.1.7"）影響解析
        all_nos = (
            [t.display_item_no or t.item_no for t in existing]
            + list(wizard_adds.mapped('item_no'))
        )
        next_num = max((self._parse_item_no(n) for n in all_nos), default=0) + 1

        # level 0-indexed：0=大寫中文, 1=小寫中文, 2+=阿拉伯數字
        level = (self.parent_task_id.item_level + 1) if self.parent_task_id else 0
        return self._number_to_label(next_num, level)

    def _parse_item_no(self, item_no):
        if not item_no:
            return 0
        # 若含點號（如 "1.1.7"）取末段，避免解析錯誤
        if '.' in item_no:
            item_no = item_no.split('.')[-1]
        upper = {'壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5,
                 '陸': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10}
        lower = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                 '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if item_no in upper:
            return upper[item_no]
        if item_no in lower:
            return lower[item_no]
        if '拾' in item_no or '十' in item_no:
            parts = item_no.replace('拾', '|').replace('十', '|').split('|')
            if len(parts) == 2:
                t, o = parts
                tens = upper.get(t, lower.get(t, 1 if not t else 0))
                ones = upper.get(o, lower.get(o, 0))
                return tens * 10 + ones
        m = re.search(r'\d+', item_no)
        return int(m.group()) if m else 0

    def _number_to_label(self, num, level):
        # 與 contract_change_order_line._number_to_chinese 保持一致（0-indexed）
        if level == 0:
            u = ['', '壹', '貳', '參', '肆', '伍', '陸', '柒', '捌', '玖', '拾']
            if num <= 10:
                return u[num]
            t, o = num // 10, num % 10
            return u[min(t, 10)] + '拾' + (u[o] if o else '')
        elif level == 1:
            l = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
            if num <= 10:
                return l[num]
            t, o = num // 10, num % 10
            return l[min(t, 10)] + '十' + (l[o] if o else '')
        else:
            return str(num)

    @api.constrains('change_type', 'item_no', 'parent_task_id')
    def _check_item_no_unique(self):
        """新增工項時檢查工項編號不可重複"""
        for line in self:
            if line.change_type != 'add' or not line.item_no:
                continue
            pid = line.parent_task_id.id if line.parent_task_id else False
            dup_task = self.env['project.task'].search([
                ('supervision_project_id', '=', line.wizard_id.project_id.id),
                ('parent_id', '=', pid),
                ('item_no', '=', line.item_no),
                ('active', '=', True),
            ], limit=1)
            if dup_task:
                raise ValidationError(
                    f'工項編號 [{line.item_no}] 在父工項下已存在（{dup_task.name}），請修改工項編號！')
            dup_line = line.wizard_id.wizard_line_ids.filtered(
                lambda l: l.id != line.id
                and l.change_type == 'add'
                and l.item_no == line.item_no
                and l.parent_task_id.id == pid
            )
            if dup_line:
                raise ValidationError(
                    f'工項編號 [{line.item_no}] 在本次新增清單中已存在，請修改工項編號！')

    # === 建立時自動定位到正確位置 ===
    @api.model
    def create(self, vals):
        record = super().create(vals)
        if record.change_type == 'add' and record.wizard_id:
            record._position_after_parent()
            record.wizard_id._resequence_wizard_lines()
        return record

    def _position_after_parent(self):
        """將新增工項放到父工項子樹的最後一行之後"""
        wizard = self.wizard_id
        parent = self.parent_task_id

        siblings = wizard.wizard_line_ids.filtered(
            lambda l: l.id != self.id
        ).sorted(lambda l: (l.sequence, l.id))

        last_seq = 0
        if parent:
            # 先找父工項自身的 sequence 作為下界
            for line in siblings:
                if line.task_id and line.task_id.id == parent.id:
                    last_seq = line.sequence
                    break
            # 再找所有屬於 parent 子樹的 lines
            for line in siblings:
                if self._is_in_subtree(line, parent):
                    last_seq = max(last_seq, line.sequence)
        else:
            # 頂層新工項放到所有 lines 最後
            last_seq = max((l.sequence for l in siblings), default=0)

        self.sequence = last_seq + 5

    def _is_in_subtree(self, line, parent_task):
        """判斷 wizard line 是否屬於 parent_task 的子孫"""
        if line.task_id:
            t = line.task_id
            while t.parent_id:
                if t.parent_id.id == parent_task.id:
                    return True
                t = t.parent_id
            return False
        elif line.change_type == 'add' and line.parent_task_id:
            p = line.parent_task_id
            while p:
                if p.id == parent_task.id:
                    return True
                p = p.parent_id
        return False


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
                'item_no': task.display_item_no or task.item_no,
                'item_name': task.name,
                'unit': task.unit or '',
                # original_qty / original_unit_price 由 _compute_original_values 自動帶入
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

        return False

    # === 新增工項行（開啟 wizard.line form dialog） ===
    def action_add_new_line(self):
        """開啟新增工項對話框"""
        self.ensure_one()
        if not self.project_id:
            raise UserError('請先選擇所屬工程！')
        max_seq = max(self.wizard_line_ids.mapped('sequence') or [0])
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contract.change.wizard.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_wizard_id': self.id,
                'default_change_type': 'add',
                'default_sequence': max_seq + 10,
            },
        }

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
        }

        if wizard_line.change_type == 'add':
            # 新增工項：從 wizard 取用戶手動輸入的值
            vals.update({
                'item_no': wizard_line.item_no,
                'item_name': wizard_line.item_name,
                'unit': wizard_line.unit,
                'parent_task_id': wizard_line.parent_task_id.id if wizard_line.parent_task_id else False,
                'new_qty': wizard_line.new_qty,
                'new_unit_price': wizard_line.new_unit_price,
                'original_qty': 0.0,
                'original_unit_price': 0.0,
            })
        else:
            # 修改/刪除：直接從 task_id 讀取，不依賴 wizard 欄位（可能因 readonly 被清空）
            task = wizard_line.task_id
            vals.update({
                'task_id': task.id,
                'item_no': task.item_no or '',
                'item_name': task.name or '',
                'unit': task.unit or '',
                'parent_task_id': wizard_line.parent_task_id.id if wizard_line.parent_task_id else False,
                'original_qty': task.planned_qty or 0.0,
                'original_unit_price': task.unit_price or 0.0,
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

    def _resequence_wizard_lines(self):
        """重排所有工項序號（10, 20, 30…），避免新增後序號衝突"""
        lines = self.wizard_line_ids.sorted(lambda l: (l.sequence, l.id))
        for idx, line in enumerate(lines):
            line.sequence = (idx + 1) * 10
