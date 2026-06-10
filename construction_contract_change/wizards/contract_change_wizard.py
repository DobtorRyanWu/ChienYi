# -*- coding: utf-8 -*-
import re
import logging
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ContractChangeWizardLine(models.TransientModel):
    """契約變更精靈明細"""
    _name = 'contract.change.wizard.line'
    _description = '契約變更精靈明細'
    _order = 'sequence, id'
    _rec_name = 'item_name'   # 供 parent_line_id 等 M2O 以工項名稱顯示/搜尋

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
        string='父工項(既有彙總項)',
        domain="[('is_summary_item', '=', True)]",
        help='新增時選擇父工項')

    parent_task_path = fields.Char(
        string='父工項路徑',
        related='parent_task_id.full_item_path',
        readonly=True)

    is_new_group = fields.Boolean(
        string='新增彙總群組',
        help='勾選表示本列是「新增的彙總群組（容器）」，本身無數量單價，'
             '供其他新增子項以此為父。')

    parent_line_id = fields.Many2one(
        'contract.change.wizard.line',
        string='父工項(本次新增)',
        domain="[('wizard_id', '=', wizard_id), ('change_type', '=', 'add'), ('is_new_group', '=', True), ('id', '!=', id)]",
        ondelete='cascade',
        help='當父項是「本次變更新增的彙總群組」（尚未存在 task）時，'
             '指向同一精靈內已勾選「新增彙總群組」的列。')

    # 合併顯示/編輯欄位：把「既有彙總項(parent_task_id)」與「本次新增群組(parent_line_id)」
    # 合成單一欄位。store=False（不佔資料庫），後端仍以上述兩個欄位為權威來源。
    parent_ref = fields.Reference(
        selection=[('project.task', '既有彙總項'),
                   ('contract.change.wizard.line', '本次新增群組')],
        string='父工項',
        compute='_compute_parent_ref',
        inverse='_inverse_parent_ref',
        store=False,
        help='父工項：既有彙總項 或 本次新增的彙總群組（擇一，依所選對象自動歸位）。')

    @api.depends('parent_task_id', 'parent_line_id')
    def _compute_parent_ref(self):
        for line in self:
            if line.parent_line_id:
                line.parent_ref = line.parent_line_id
            elif line.parent_task_id:
                line.parent_ref = line.parent_task_id
            else:
                line.parent_ref = False

    def _inverse_parent_ref(self):
        """單欄選擇後自動歸位：選到「本次新增群組」→ parent_line_id；
        選到「既有彙總項」→ parent_task_id；兩者互斥（清空另一個）。"""
        for line in self:
            ref = line.parent_ref
            if not ref:
                line.parent_task_id = False
                line.parent_line_id = False
            elif ref._name == 'contract.change.wizard.line':
                line.parent_line_id = ref.id
                line.parent_task_id = False
            elif ref._name == 'project.task':
                line.parent_task_id = ref.id
                line.parent_line_id = False

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

    ref_item_code = fields.Char(
        string='參考工項代碼')

    display_item_name = fields.Char(
        string='工項名稱',
        compute='_compute_display_item_name',
        store=False)

    # === 變更類型 ===
    change_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('zero_out', '歸零'),
        ('delete', '刪除'),
    ], string='變更類型')

    is_summary_item = fields.Boolean(
        string='彙總項目',
        compute='_compute_is_summary_item',
        store=False,
        help='是否為彙總項目（有子工項）；彙總項不可直接修改，由子項自動累加')

    @api.depends('task_id', 'task_id.child_ids')
    def _compute_is_summary_item(self):
        for line in self:
            line.is_summary_item = bool(line.task_id and line.task_id.child_ids)

    is_tax_misc_item = fields.Boolean(
        string='稅什費工項',
        compute='_compute_is_tax_misc_item',
        store=False,
        help='是否為稅什費工項；金額由比例自動計算，不使用 qty × price')

    @api.depends('task_id', 'task_id.tax_misc_rate')
    def _compute_is_tax_misc_item(self):
        for line in self:
            line.is_tax_misc_item = bool(line.task_id and line.task_id.tax_misc_rate)

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
                 'new_qty', 'new_unit_price', 'change_type',
                 'task_id', 'task_id.planned_amount', 'task_id.child_ids',
                 'wizard_id.wizard_line_ids.new_qty',
                 'wizard_id.wizard_line_ids.new_unit_price',
                 'wizard_id.wizard_line_ids.change_type',
                 'wizard_id.wizard_line_ids.task_id',
                 'wizard_id.wizard_line_ids.parent_task_id',
                 'wizard_id.wizard_line_ids.parent_line_id')
    def _compute_amounts(self):
        """計算金額
        原金額：有 task_id 者一律取 task.planned_amount
        新金額：
          - 分類項（task.child_ids 非空）：遞迴加總直接子節點 + 直屬新增工項
            （每層只彙總下一層，避免越層重複計算）
          - 葉節點：依 change_type 用 new_qty × new_unit_price 計算
        """
        # 建立每個 wizard 的查詢字典，避免重複遍歷 wizard_line_ids
        wizard_cache = {}  # wizard_id -> (lines_by_task_id, add_lines_by_parent)

        def get_wizard_data(wizard):
            wid = wizard.id
            if wid not in wizard_cache:
                lines_by_task_id = {}
                add_lines_by_parent = {}        # parent_task_id.id -> [add wl]（父為既有 task）
                add_lines_by_parent_line = {}   # parent_line_id.id -> [add wl]（父為本次新群組列）
                for wl in wizard.wizard_line_ids:
                    if wl.task_id:
                        lines_by_task_id[wl.task_id.id] = wl
                    if wl.change_type == 'add' and wl.parent_task_id:
                        add_lines_by_parent.setdefault(wl.parent_task_id.id, []).append(wl)
                    if wl.change_type == 'add' and wl.parent_line_id:
                        add_lines_by_parent_line.setdefault(wl.parent_line_id.id, []).append(wl)
                wizard_cache[wid] = (lines_by_task_id, add_lines_by_parent, add_lines_by_parent_line)
            return wizard_cache[wid]

        def compute_add_line_amount(add_wl, albp_line):
            """新增列金額：若為群組（有子新增列）→遞迴加總子項；否則 qty×price。"""
            children = albp_line.get(add_wl.id, [])
            if children:
                return sum(compute_add_line_amount(c, albp_line) for c in children)
            return (add_wl.new_qty or 0.0) * (add_wl.new_unit_price or 0.0)

        def compute_task_amount(task, lines_by_task_id, albp, albp_line):
            """遞迴計算 task 的變更後金額（直接子節點加總，避免越層彙總）"""
            if task.child_ids:
                # 分類項：加總直接子節點
                total = sum(
                    compute_task_amount(c, lines_by_task_id, albp, albp_line)
                    for c in task.child_ids)
                # 加上直屬此分類的新增工項（含「新增彙總群組」→遞迴其子項）
                for add_wl in albp.get(task.id, []):
                    total += compute_add_line_amount(add_wl, albp_line)
                return total
            elif task.tax_misc_rate and task.parent_id:
                # 稅什費：比例 × 同層前置項目加總
                rate = task.tax_misc_rate / 100.0
                siblings = task.parent_id.child_ids.sorted('sequence')
                preceding_sum = sum(
                    compute_task_amount(s, lines_by_task_id, albp, albp_line)
                    for s in siblings
                    if s.sequence < task.sequence
                )
                return round(preceding_sum * rate, 2)
            else:
                # 一般葉節點：依 wizard line 的 change_type 計算
                wl = lines_by_task_id.get(task.id)
                if wl:
                    if wl.change_type in ('modify', 'add'):
                        return (wl.new_qty or 0.0) * (wl.new_unit_price or 0.0)
                    elif wl.change_type in ('zero_out', 'delete'):
                        return 0.0
                    # 未變更：沿用原始金額
                    return task.planned_amount or 0.0
                return task.planned_amount or 0.0

        for line in self:
            # --- 原金額：統一從 task.planned_amount 取得 ---
            if line.task_id:
                line.original_amount = line.task_id.planned_amount
            else:
                # 新增工項（change_type='add'，無 task_id）
                line.original_amount = 0.0

            # --- 新金額 ---
            if line.task_id and line.task_id.child_ids:
                # 分類項：遞迴加總（直接子節點 + 直屬新增工項）
                lines_by_task_id, albp, albp_line = get_wizard_data(line.wizard_id)
                new_total = compute_task_amount(line.task_id, lines_by_task_id, albp, albp_line)
                _logger.info('[_compute_amounts] %s new_amount=%.2f', line.task_id.name, new_total)
                line.new_amount = new_total
                line.change_amount = new_total - line.original_amount
            elif line.task_id and line.task_id.tax_misc_rate:
                # 稅什費：比例 × 同層前置項目加總（非 qty × price）
                lines_by_task_id, albp, albp_line = get_wizard_data(line.wizard_id)
                new_total = compute_task_amount(line.task_id, lines_by_task_id, albp, albp_line)
                line.new_amount = new_total
                line.change_amount = new_total - line.original_amount
            else:
                # 葉節點或新增工項：依 change_type 計算
                if line.change_type in ('delete', 'zero_out'):
                    line.new_amount = 0.0
                    line.change_amount = -line.original_amount
                elif line.change_type == 'add':
                    # 新增群組（被子新增列以 parent_line_id 指向）→ 金額=子項加總
                    _, _, albp_line = get_wizard_data(line.wizard_id)
                    children = albp_line.get(line.id, [])
                    if children:
                        line.new_amount = sum(
                            compute_add_line_amount(c, albp_line) for c in children)
                    else:
                        line.new_amount = (line.new_qty or 0.0) * (line.new_unit_price or 0.0)
                    line.change_amount = line.new_amount
                elif line.change_type == 'modify':
                    line.new_amount = (line.new_qty or 0.0) * (line.new_unit_price or 0.0)
                    line.change_amount = line.new_amount - line.original_amount
                else:
                    # 未設變更類型：新金額 = 原金額，變更金額為 0
                    line.new_amount = line.original_amount
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
        elif self.change_type in ('delete', 'zero_out'):
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

    @api.onchange('parent_line_id')
    def _onchange_parent_line_id(self):
        """選擇「本次新增群組」為父時，依群組層級重算工項編號（修正選後編號未更新）。"""
        if self.change_type == 'add' and self.parent_line_id:
            self.item_no = self._generate_next_item_no()

    def _generate_next_item_no(self):
        """產生下一個工項編號（資料驅動：呼叫 project.task._gen_item_no，依該專案現有
        同層編號格式骨架產生，不寫死層級格式）。支援父為既有彙總項或本次新增群組。"""
        if not self.wizard_id.project_id:
            return ''
        Task = self.env['project.task']
        sid = self.wizard_id.project_id.id

        if self.parent_line_id:
            # 父為「本次新增的群組」（尚非 task）：層級 = 群組層級 + 1
            grp = self.parent_line_id
            grp_level = (grp.parent_task_id.item_level + 1) if grp.parent_task_id else 0
            target_level = grp_level + 1
            sibs = self.wizard_id.wizard_line_ids.filtered(
                lambda l: l.change_type == 'add'
                and l.parent_line_id.id == grp.id
                and l.item_no and l.id != self._origin.id)
            sibling_nos = list(sibs.mapped('item_no'))
            parent_item_no = grp.item_no or ''
        else:
            pt = self.parent_task_id
            target_level = (pt.item_level + 1) if pt else 0
            pid = pt.id if pt else False
            existing = Task.search([
                ('supervision_project_id', '=', sid),
                ('parent_id', '=', pid), ('active', '=', True)])
            wiz_sibs = self.wizard_id.wizard_line_ids.filtered(
                lambda l: l.change_type == 'add'
                and (l.parent_task_id.id or False) == pid
                and l.item_no and l.id != self._origin.id)
            sibling_nos = list(existing.mapped('display_item_no')) + list(wiz_sibs.mapped('item_no'))
            parent_item_no = (pt.item_no or '') if pt else ''

        level_nos = Task.search([
            ('supervision_project_id', '=', sid),
            ('item_level', '=', target_level), ('active', '=', True)]).mapped('display_item_no')
        return Task._gen_item_no(sibling_nos, list(level_nos), parent_item_no)

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

    @api.constrains('change_type', 'item_no', 'parent_task_id', 'parent_line_id')
    def _check_item_no_unique(self):
        """新增工項時檢查工項編號不可重複（判重範圍＝同一父項；父項以
        parent_task_id「與」parent_line_id 共同界定，故不同新群組下可各自 1、2…）"""
        for line in self:
            if line.change_type != 'add' or not line.item_no:
                continue
            pid = line.parent_task_id.id if line.parent_task_id else False
            plid = line.parent_line_id.id if line.parent_line_id else False
            # 父為「本次新增群組」(parent_line_id)時，該群組尚非 task，不與既有 task 比對
            if not plid:
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
                and (l.parent_task_id.id or False) == pid
                and (l.parent_line_id.id or False) == plid
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

    # === 稅什費設定 ===
    tax_misc_rate = fields.Float(
        string='稅什費比例 (%)',
        digits=(12, 8),
        help='稅什費的計算比例（%）。\n'
             '計算公式：稅什費金額 = 同層前置分類複價新合計 × 比例%\n'
             '此值由匯入 XLSX 時自動帶入。')

    # === 統計欄位 ===
    modify_count = fields.Integer(
        string='修改項數',
        compute='_compute_statistics')

    zero_out_count = fields.Integer(
        string='歸零項數',
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

    reconciliation_report = fields.Text(
        string='金額核對報告', readonly=True)
    show_reconciliation_report = fields.Boolean(
        string='顯示核對報告', default=False)

    # === 計算統計 ===
    @api.depends('wizard_line_ids.change_type',
                 'wizard_line_ids.change_amount')
    def _compute_statistics(self):
        """計算統計資訊"""
        for wizard in self:
            lines_with_change = wizard.wizard_line_ids.filtered('change_type')
            wizard.modify_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'modify'))
            wizard.zero_out_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'zero_out'))
            wizard.delete_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'delete'))
            wizard.add_count = len(
                lines_with_change.filtered(lambda l: l.change_type == 'add'))
            wizard.total_change_amount = sum(
                lines_with_change.mapped('change_amount'))

    def action_close_reconciliation(self):
        self.show_reconciliation_report = False

    def action_open_reconciliation(self):
        self.show_reconciliation_report = True

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

        # 帶入稅什費比例（從工項的 tax_misc_rate 欄位讀取）
        tax_task = tasks.filtered(lambda t: '稅什費' in (t.name or ''))
        self.tax_misc_rate = tax_task[0].tax_misc_rate if tax_task else 0.0

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

    # === 從檔案匯入變更 ===
    def action_open_file_import_wizard(self):
        """開啟契約變更檔案匯入精靈（XLSX / XML）"""
        self.ensure_one()
        if not self.project_id:
            raise UserError('請先選擇工程案件後再使用檔案匯入功能')
        return {
            'type': 'ir.actions.act_window',
            'name': '從檔案匯入契約變更',
            'res_model': 'contract.change.file.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_wizard_id': self.id,
            },
        }

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

        # 有 change_type 的明細行（葉節點、新增工項）
        explicit_lines = self.wizard_line_ids.filtered('change_type')
        # 彙總項與稅什費：金額有實質變化者自動納入（不需使用者手動設定 change_type）
        auto_lines = self.wizard_line_ids.filtered(
            lambda l: not l.change_type
            and l.task_id
            and (l.is_summary_item or l.is_tax_misc_item)
            and abs(l.change_amount) > 0.01
        )
        lines_to_save = explicit_lines | auto_lines
        if not lines_to_save:
            raise UserError('沒有需要儲存的變更項目！')

        # 1. 寫入 project_id 與契約資訊到變更單
        vals = {'project_id': self.project_id.id}

        if not self.change_order_id.original_contract_amount:
            vals['original_contract_amount'] = (
                self.project_id.current_contract_amount or
                self.project_id.contract_amount or 0.0)
        self.change_order_id.write(vals)

        # 2. 刪除原有的所有變更明細
        self.change_order_id.line_ids.unlink()

        # 3. 創建變更明細（拓樸順序：父群組先於子項，子項才能回填 parent_line_id）
        wl2ol = {}                       # wizard_line.id -> 已建 order.line
        pending = list(lines_to_save)
        guard = 0
        while pending:
            guard += 1
            if guard > 50:
                raise UserError('變更明細父子關係解析超過上限，疑有循環參照。')
            progressed = False
            still = []
            for line in pending:
                if line.change_type == 'add' and line.parent_line_id:
                    pol = wl2ol.get(line.parent_line_id.id)
                    if not pol:
                        still.append(line)      # 父群組明細尚未建立 → 下一輪
                        continue
                    ol = self._create_change_order_line(line, parent_order_line=pol)
                else:
                    ol = self._create_change_order_line(line)
                if ol:
                    wl2ol[line.id] = ol
                progressed = True
            pending = still
            if pending and not progressed:
                raise UserError(
                    '變更明細新增項找不到父群組（缺父或循環）：%s'
                    % '、'.join(l.item_name or '?' for l in pending))

        # 4. 跳轉回變更單表單
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contract.change.order',
            'res_id': self.change_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_change_order_line(self, wizard_line, parent_order_line=None):
        """根據 wizard line 創建變更明細記錄，回傳建立的 order.line。
        parent_order_line：父為「本次新增群組」時，已建立的父 order.line（用於 parent_line_id）。"""
        vals = {
            'change_order_id': self.change_order_id.id,
            'sequence': wizard_line.sequence,
            'change_type': wizard_line.change_type,
        }

        if not wizard_line.change_type and wizard_line.task_id:
            # 彙總項或稅什費（無 change_type）：以 qty=1, price=合計金額 記錄
            # 不設 change_type（留空，與精靈一致）
            task = wizard_line.task_id
            is_tax = wizard_line.is_tax_misc_item
            is_sum = wizard_line.is_summary_item

            # 稅什費：優先使用 xml_amount（XML 直接讀入的正確值）
            # 避免 planned_amount 因 XML 的 <Quantity>=0 而為 0 的問題
            if is_tax:
                original_total = round(task.xml_amount or task.planned_amount or 0.0, 2)
            else:
                original_total = round(task.planned_amount or 0.0, 2)

            vals.update({
                'task_id': task.id,
                'item_no': task.item_no or '',
                'item_name': task.name or '',
                'unit': task.unit or '',
                'parent_task_id': (wizard_line.parent_task_id.id
                                   if wizard_line.parent_task_id else False),
                'original_qty': 1.0,
                'original_unit_price': original_total,
                'new_qty': 1.0,
                'new_unit_price': round(wizard_line.new_amount or 0.0, 2),
                'is_summary_line': is_sum,
                'is_tax_misc_line': is_tax,
            })
            return self.env['contract.change.order.line'].create(vals)

        elif wizard_line.change_type == 'add':
            # 新增工項：從 wizard 取用戶手動輸入的值（單位先標準化，明細顯示一致）
            vals.update({
                'item_no': wizard_line.item_no,
                'item_name': wizard_line.item_name,
                'ref_item_code': wizard_line.ref_item_code or '',
                'unit': self.env['project.task']._normalize_unit_display(wizard_line.unit),
                'parent_task_id': wizard_line.parent_task_id.id if wizard_line.parent_task_id else False,
                'new_qty': wizard_line.new_qty,
                'new_unit_price': wizard_line.new_unit_price,
                'original_qty': 0.0,
                'original_unit_price': 0.0,
                'is_new_group': wizard_line.is_new_group,
            })
            # 父為「本次新增群組」：指向已建立的父 order.line（parent_line_id）
            if parent_order_line is not None:
                vals['parent_line_id'] = parent_order_line.id
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
            elif wizard_line.change_type in ('delete', 'zero_out'):
                vals.update({
                    'new_qty': 0.0,
                    'new_unit_price': 0.0,
                })

        ol = self.env['contract.change.order.line'].create(vals)

        # 刪除（delete）：封存 project.task，使其從工項列表消失
        # 歸零（zero_out）：工項保留，僅記錄數量歸零
        if wizard_line.change_type == 'delete' and wizard_line.task_id:
            wizard_line.task_id.write({'active': False})
        return ol

    def _resequence_wizard_lines(self):
        """重排所有工項序號（10, 20, 30…），避免新增後序號衝突"""
        lines = self.wizard_line_ids.sorted(lambda l: (l.sequence, l.id))
        for idx, line in enumerate(lines):
            line.sequence = (idx + 1) * 10
