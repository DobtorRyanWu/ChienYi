# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ContractChangeOrderLine(models.Model):
    """
    契約變更明細

    記錄每個工項的變更內容：新增、修改、刪除
    - add: 新增工項，需填寫完整工項資訊
    - modify: 修改工項，需選擇既有工項並設定新數量/單價
    - delete: 刪除工項，選擇要刪除的工項
    """
    _name = 'contract.change.order.line'
    _description = '契約變更明細'
    _order = 'sequence, id'
    _rec_name = 'item_name'   # 供 parent_line_id 等 M2O 以工項名稱顯示

    # === 關聯 ===
    change_order_id = fields.Many2one(
        'contract.change.order',
        string='變更單',
        required=True,
        ondelete='cascade',
        index=True)

    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        related='change_order_id.project_id',
        store=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='change_order_id.company_id',
        store=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='change_order_id.currency_id',
        store=True)

    # === 輔助欄位：用於 domain 過濾 ===
    # 合併後工程案件即 project.project，此輔助欄位等同 project_id（保留供既有 domain 引用）
    project_project_id = fields.Many2one(
        'project.project',
        string='專案(Odoo)',
        related='project_id',
        store=True,
        help='關聯的 project.project，用於工項過濾')

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 變更類型 ===
    change_type = fields.Selection([
        ('add', '新增'),
        ('modify', '修改'),
        ('zero_out', '歸零'),
        ('delete', '刪除'),
    ], string='變更類型',
       help='新增: 新增工項; 修改: 修改數量/單價; 歸零: 合約縮減（工項保留）; 刪除: 徹底移除工項（修正錯誤登記）; 空白: 彙總項或稅什費（自動計算）')

    # === 彙總項 / 稅什費 旗標 ===
    is_summary_line = fields.Boolean(
        string='彙總項',
        default=False,
        help='標記此明細為彙總項（金額由子工項加總而來）')

    is_tax_misc_line = fields.Boolean(
        string='稅什費項',
        default=False,
        help='標記此明細為稅什費（金額由 tax_misc_rate × 前置項目加總）')

    # === 工項資訊 (既有工項) ===
    task_id = fields.Many2one(
        'project.task',
        string='原工項',
        domain="[('project_id', '=', project_project_id), ('active', '=', True)]",
        help='選擇要修改或刪除的既有工項')

    parent_task_id = fields.Many2one(
        'project.task',
        string='父工項(既有彙總項)',
        domain="[('project_id', '=', project_project_id), ('active', '=', True), ('is_summary_item', '=', True)]",
        help='新增工項時，指定此工項的父項次（用於階層結構，限既有彙總項）')

    is_new_group = fields.Boolean(
        string='新增彙總群組',
        help='本列為「新增的彙總群組（容器）」，本身無量價，供其他新增子項以此為父。')

    # 預備單價項目：套用後會寫進 project.task.exclude_from_contract_amount
    exclude_from_contract_amount = fields.Boolean(
        string='預備單價項目（不計入契約金額）',
        help='勾選後本工項不計入父彙總項加總，也不計入工程的契約金額；\n'
             '但仍是正式契約工項，通報單與估驗計價皆可選用。\n'
             '用於預約式議價新增的單價項目（數量 1、單價議價，不推高契約總額）。')

    parent_line_id = fields.Many2one(
        'contract.change.order.line',
        string='父工項(本次新增)',
        domain="[('change_order_id', '=', change_order_id), ('change_type', '=', 'add'), ('is_new_group', '=', True), ('id', '!=', id)]",
        ondelete='cascade',
        help='當父項是「本次變更新增的彙總群組」（套用前尚不存在 task）時，'
             '以此指向同一變更內的群組新增列；套用時先建群組 task 再掛子項。')

    parent_task_path = fields.Char(
        string='父工項路徑',
        related='parent_task_id.full_item_path',
        readonly=True,
        help='父工項的完整祖先路徑，如：壹 > 一 > (一)')

    # 合併顯示/編輯欄位：既有彙總項(parent_task_id) 或 本次新增群組(parent_line_id) 單一欄。
    # store=False（不佔資料庫），後端仍以上述兩欄為權威來源。
    parent_ref = fields.Reference(
        selection=[('project.task', '既有彙總項'),
                   ('contract.change.order.line', '本次新增群組')],
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
            elif ref._name == 'contract.change.order.line':
                line.parent_line_id = ref.id
                line.parent_task_id = False
            elif ref._name == 'project.task':
                line.parent_task_id = ref.id
                line.parent_line_id = False

    item_level = fields.Integer(
        string='層級',
        compute='_compute_item_level', recursive=True,
        help='0=大項次, 1=次項次, 2=小項次... (從 parent_task_id/parent_line_id 或 task_id 獲取)')

    # === 工項資訊 (新增或顯示用) ===
    item_no = fields.Char(
        string='工項編號',
        help='工項編號，新增時必填')

    display_item_no = fields.Char(
        string='工項編號(顯示)',
        compute='_compute_display_item_no',
        store=False,
        help='非新增工項顯示 task 的葉節點編號，新增工項顯示 item_no')

    item_name = fields.Char(
        string='工項名稱',
        required=True)

    ref_item_code = fields.Char(
        string='參考工項代碼')

    unit = fields.Char(
        string='單位')

    specification = fields.Text(
        string='規格說明')

    # === 原值 (from task_id) ===
    original_qty = fields.Float(
        string='原數量',
        digits=(16, 4),
        help='變更前的契約數量')

    original_unit_price = fields.Float(
        string='原單價',
        digits=(16, 2),
        help='變更前的契約單價')

    original_amount = fields.Float(
        string='原金額',
        digits=(16, 2),
        compute='_compute_original_amount',
        store=True,
        help='原數量 x 原單價')

    # === 新值 ===
    new_qty = fields.Float(
        string='新數量',
        digits=(16, 4),
        help='變更後的數量')

    new_unit_price = fields.Float(
        string='新單價',
        digits=(16, 2),
        help='變更後的單價')

    # 整包費用項（單價欄本來就空白、金額只有整包複價）沒辦法用「數量 × 單價」
    # 表達金額變化。以前只能把整包金額硬塞進「新單價」，那會讓 _apply_changes
    # 把它寫回 task.unit_price，害該工項從 xml_amount 分支掉進「數量 × 單價」分支
    # ——契約金額仍然正確，但下游通報單明細的手填金額閘門會被關掉。
    # 改為：整包項直接編輯「新金額」，新單價欄留空不用。
    is_lump_sum_line = fields.Boolean(
        string='整包費用項',
        related='task_id.is_lump_sum', store=True, readonly=True,
        help='對應的契約工項是整包費用項；金額直接填「新金額」，不經數量 × 單價')

    # 比例項（稅什費、自主品管費…）：金額 = 比例 × 基數，同樣不是「數量 × 單價」。
    # 舊寫法把整包金額 ÷ 數量塞進 new_unit_price，套用後 task.unit_price 會變成
    # 兩千多萬 —— 契約金額因為走比例分支所以仍然正確，但變更設計詳細表那一列會
    # 印成「原金額 0、追加 = 全額」（原單價取自被污染前的 0），且估驗明細會抄到
    # 那個假單價。
    is_rate_line = fields.Boolean(
        string='比例項',
        compute='_compute_is_rate_line', store=True,
        help='對應的契約工項以「比例 × 基數」計算金額（稅什費等）')

    @api.depends('task_id', 'task_id.tax_misc_rate')
    def _compute_is_rate_line(self):
        for line in self:
            line.is_rate_line = bool(line.task_id and line.task_id.tax_misc_rate)

    # change_type='add' 的明細列沒有 task_id，related 讀不到，故另設一個可勾的欄位。
    is_new_lump_sum = fields.Boolean(
        string='新增為整包費用項',
        default=False,
        help='本次新增的工項是整包費用項（單位「式」、只有整包金額、沒有單價）。\n'
             '勾選後改填「新金額」，建立出來的工項會帶「整包費用項」旗標。')

    # 兩種來源合一：既有工項看 task 的旗標，新增列看自己勾的
    is_lump_amount_line = fields.Boolean(
        string='以整包金額計',
        compute='_compute_is_lump_amount_line', store=True,
        help='本列的金額直接填寫，不經「數量 × 單價」')

    @api.depends('is_lump_sum_line', 'is_new_lump_sum', 'is_rate_line', 'change_type')
    def _compute_is_lump_amount_line(self):
        for line in self:
            if line.change_type == 'add':
                line.is_lump_amount_line = line.is_new_lump_sum
            else:
                # 比例項與整包項都不走「數量 × 單價」，金額直接以 new_amount 呈現
                line.is_lump_amount_line = line.is_lump_sum_line or line.is_rate_line

    new_amount = fields.Float(
        string='新金額',
        digits=(16, 2),
        compute='_compute_new_amount',
        store=True, readonly=False,
        help='新數量 x 新單價；整包費用項則直接手動填寫整包金額')

    # === 差異 ===
    qty_change = fields.Float(
        string='數量增減',
        digits=(16, 4),
        compute='_compute_differences',
        store=True,
        help='新數量 - 原數量')

    price_change = fields.Float(
        string='單價增減',
        digits=(16, 2),
        compute='_compute_differences',
        store=True,
        help='新單價 - 原單價')

    change_amount = fields.Float(
        string='金額增減',
        digits=(16, 2),
        compute='_compute_differences',
        store=True,
        help='新金額 - 原金額')

    change_amount_rate = fields.Float(
        string='變動比率 (%)',
        digits=(16, 4),
        compute='_compute_differences',
        store=True,
        help='金額增減 / 原金額（小數，如 0.2567 = 25.67%）')

    # === 備註 ===
    notes = fields.Text(
        string='變更說明',
        help='此項變更的詳細說明')

    # === 計算欄位 ===
    @api.depends('parent_task_id', 'task_id', 'parent_line_id', 'parent_line_id.item_level')
    def _compute_item_level(self):
        """計算工項層級"""
        for line in self:
            if line.change_type == 'add' and line.parent_line_id:
                # 新增工項，父為「本次新增的群組」：父群組層級 + 1
                line.item_level = line.parent_line_id.item_level + 1
            elif line.change_type == 'add' and line.parent_task_id:
                # 新增工項，父為既有彙總項：父工項層級 + 1
                line.item_level = line.parent_task_id.item_level + 1
            elif line.task_id:
                # 修改/刪除：使用原工項層級
                line.item_level = line.task_id.item_level
            else:
                # 頂層工項
                line.item_level = 0

    @api.depends('task_id', 'task_id.display_item_no', 'item_no', 'change_type')
    def _compute_display_item_no(self):
        for line in self:
            if line.change_type == 'add':
                line.display_item_no = line.item_no or ''
            else:
                line.display_item_no = (
                    line.task_id.display_item_no or line.task_id.item_no or line.item_no or ''
                )

    @api.depends('original_qty', 'original_unit_price',
                 'is_lump_sum_line', 'is_rate_line', 'task_id.planned_amount')
    def _compute_original_amount(self):
        for line in self:
            if (line.is_lump_sum_line or line.is_rate_line) and line.task_id:
                # 整包費用項與比例項都沒有單價，「原數量 × 原單價」會是 0，
                # 列印出來的變更設計詳細表那一列原金額就會空掉、追加金額被
                # 誇大成全額。直接取工項的契約金額（整包項＝xml_amount、
                # 比例項＝比例 × 基數，都是該項真正的變更前金額）。
                line.original_amount = round(line.task_id.planned_amount or 0.0, 2)
            else:
                line.original_amount = round(
                    line.original_qty * line.original_unit_price, 2)

    @api.depends('new_qty', 'new_unit_price', 'is_lump_amount_line')
    def _compute_new_amount(self):
        for line in self:
            if line.is_lump_amount_line:
                # 手填：compute + store + readonly=False 的欄位一旦被明確寫入就
                # 不再重算（與 payment_estimate.estimate_amount、
                # notification_slip_line.planned_amount 同一套慣例）。
                # 這裡讀回資料庫現值，避免把使用者填的整包金額歸零。
                line.new_amount = line.new_amount or 0.0
            else:
                line.new_amount = round(line.new_qty * line.new_unit_price, 2)

    @api.depends('original_qty', 'original_unit_price', 'original_amount',
                 'new_qty', 'new_unit_price', 'new_amount', 'change_type')
    def _compute_differences(self):
        for line in self:
            if line.change_type == 'add':
                # 新增：差異 = 新值
                line.qty_change = line.new_qty
                line.price_change = 0.0
                line.change_amount = round(line.new_amount, 2)
            elif line.change_type == 'delete':
                # 刪除：差異 = -原值
                line.qty_change = -line.original_qty
                line.price_change = 0.0
                line.change_amount = round(-line.original_amount, 2)
            else:  # modify 或空白（彙總項/稅什費）
                line.qty_change = line.new_qty - line.original_qty
                line.price_change = line.new_unit_price - line.original_unit_price
                line.change_amount = round(line.new_amount - line.original_amount, 2)

            # 計算變動比率（[0,1] 小數，widget="percentage" 會乘 100 顯示）
            if line.original_amount:
                line.change_amount_rate = (
                    line.change_amount / line.original_amount)
            elif line.change_type == 'add':
                line.change_amount_rate = 1.0  # 新增視為 100% 增加
            else:
                line.change_amount_rate = 0.0

    # === Onchange ===
    @api.onchange('task_id')
    def _onchange_task_id(self):
        """選擇工項時，自動填入原始資訊"""
        if self.task_id:
            self.item_no = self.task_id.display_item_no or self.task_id.item_no
            self.item_name = self.task_id.name
            self.unit = self.task_id.unit
            self.specification = self.task_id.specification
            self.original_qty = self.task_id.planned_qty
            self.original_unit_price = self.task_id.unit_price

            # 修改類型：預設新值 = 原值
            if self.change_type == 'modify':
                self.new_qty = self.task_id.planned_qty
                self.new_unit_price = self.task_id.unit_price
                if self.task_id.is_lump_sum:
                    # 整包費用項沒有單價，預設帶 0 會讓「新金額」變成 0、
                    # 金額增減顯示成 -全額。預設帶原本的整包金額，
                    # 使用者只要把它改成變更後的金額即可。
                    self.new_unit_price = 0.0
                    self.new_amount = round(self.task_id.planned_amount or 0.0, 2)

    @api.onchange('parent_task_id')
    def _onchange_parent_task_id(self):
        """選擇父工項時，自動填入單位和產生工項編號"""
        if self.parent_task_id and self.change_type == 'add':
            # 繼承父工項的單位
            if self.parent_task_id.unit:
                self.unit = self.parent_task_id.unit
            
            # 自動產生工項編號
            if self.project_id and self.project_id:
                self.item_no = self._generate_next_item_no()
    
    def _generate_next_item_no(self):
        """自動產生下一個工項編號"""
        if not self.parent_task_id or not self.project_id:
            return ''
        
        # 搜尋同父工項下的所有子工項
        ProjectTask = self.env['project.task']
        siblings = ProjectTask.search([
            ('project_id', '=', self.project_id.id),
            ('parent_id', '=', self.parent_task_id.id),
            ('active', '=', True)
        ], order='sequence desc, id desc', limit=1)
        
        if not siblings:
            # 沒有兄弟工項，從1開始
            next_number = 1
        else:
            # 從最後一個工項的編號解析並+1
            last_item_no = siblings[0].display_item_no or siblings[0].item_no or ''
            next_number = self._parse_and_increment_item_no(last_item_no)
        
        # 根據層級決定編號格式
        level = self.parent_task_id.item_level + 1
        return self._number_to_chinese(next_number, level)
    
    def _parse_and_increment_item_no(self, item_no):
        """從工項編號解析數字並遞增"""
        if not item_no:
            return 1
        
        # 嘗試轉換中文數字
        num = self._chinese_to_number(item_no)
        if num > 0:
            return num + 1
        
        # 嘗試解析阿拉伯數字
        import re
        match = re.search(r'\d+', item_no)
        if match:
            return int(match.group()) + 1
        
        return 1
    
    def _number_to_chinese(self, num, level):
        """數字轉中文編號（根據層級）"""
        if level == 0:
            # 第一層：壹貳參...
            chinese_upper = ['', '壹', '貳', '參', '肆', '伍', '陸', '柒', '捌', '玖', '拾']
            if num <= 10:
                return chinese_upper[num]
            else:
                if num < 20:
                    return '拾' + (chinese_upper[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_upper[tens] + '拾' + (chinese_upper[ones] if ones else '')
        elif level == 1:
            # 第二層：一二三...
            chinese_lower = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
            if num <= 10:
                return chinese_lower[num]
            else:
                if num < 20:
                    return '十' + (chinese_lower[num - 10] if num > 10 else '')
                else:
                    tens = num // 10
                    ones = num % 10
                    return chinese_lower[tens] + '十' + (chinese_lower[ones] if ones else '')
        elif level == 2:
            # 第三層：(一)(二)... 括號國字
            cl = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
            if num <= 10:
                inner = cl[num]
            else:
                tens, ones = num // 10, num % 10
                inner = cl[min(tens, 10)] + '十' + (cl[ones] if ones else '')
            return '(' + inner + ')'
        else:
            # 第四層及以下：1, 2, 3...
            return str(num)
    
    def _chinese_to_number(self, chinese_str):
        """中文轉數字"""
        if not chinese_str:
            return 0
        
        # 大寫數字對應
        upper_map = {
            '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5,
            '陸': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10
        }
        # 小寫數字對應
        lower_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        # 嘗試直接對應
        if chinese_str in upper_map:
            return upper_map[chinese_str]
        if chinese_str in lower_map:
            return lower_map[chinese_str]
        
        # 嘗試解析組合（如：拾壹、十一）
        result = 0
        if '拾' in chinese_str or '十' in chinese_str:
            parts = chinese_str.replace('拾', '|').replace('十', '|').split('|')
            if len(parts) == 2:
                tens_str, ones_str = parts
                tens = upper_map.get(tens_str, lower_map.get(tens_str, 1 if not tens_str else 0))
                ones = upper_map.get(ones_str, lower_map.get(ones_str, 0))
                result = tens * 10 + ones
        
        return result

    @api.onchange('change_type')
    def _onchange_change_type(self):
        """變更類型改變時，清空或重設欄位"""
        if self.change_type == 'add':
            # 新增：清空原工項關聯與原值
            self.task_id = False
            self.parent_task_id = False
            self.original_qty = 0.0
            self.original_unit_price = 0.0
        elif self.change_type == 'delete' and self.task_id:
            # 刪除：新值設為0
            self.new_qty = 0.0
            self.new_unit_price = 0.0
        elif self.change_type == 'modify' and self.task_id:
            # 修改：新值預設為原值
            self.new_qty = self.original_qty
            self.new_unit_price = self.original_unit_price

    # === 約束 ===
    @api.constrains('change_type', 'task_id')
    def _check_task_required(self):
        """檢查修改/刪除必須選擇工項"""
        for line in self:
            if line.change_type in ('modify', 'delete') and not line.task_id:
                raise ValidationError(
                    '修改或刪除類型必須選擇原工項！')

    @api.constrains('change_type', 'item_no', 'item_name', 'parent_task_id', 'parent_line_id')
    def _check_add_fields(self):
        """檢查新增類型必填欄位"""
        for line in self:
            if line.change_type == 'add':
                if not line.item_no:
                    raise ValidationError('新增工項必須填寫工項編號！')
                if not line.item_name:
                    raise ValidationError('新增工項必須填寫工項名稱！')
                # 防呆：新增工項必須指定父項，否則會落到頂層（item_level=0）污染契約金額。
                # 父項可為「既有彙總項」(parent_task_id) 或「本次新增的群組列」(parent_line_id)。
                # 唯一例外：本身就是「新增的頂層彙總群組」(被其他列以 parent_line_id 指向者)
                # 才允許兩者皆空——由 _is_referenced_as_parent 判定。
                if not line.parent_task_id and not line.parent_line_id:
                    if not line._is_referenced_as_parent():
                        raise ValidationError(
                            f'新增工項「{line.item_name}」必須指定父項（既有彙總項或本次新增的群組）！'
                            '否則會被誤掛為頂層項次，導致契約金額計算錯誤。')

    def _is_referenced_as_parent(self):
        """本列是否被同一變更內其他列以 parent_line_id 指向（即本列為新增的彙總群組）。"""
        self.ensure_one()
        if not self.change_order_id:
            return False
        return bool(self.search_count([
            ('change_order_id', '=', self.change_order_id.id),
            ('parent_line_id', '=', self.id),
        ]))

    @api.constrains('new_qty', 'new_unit_price')
    def _check_positive_values(self):
        """檢查數量與單價"""
        for line in self:
            if line.change_type != 'delete':
                if line.new_qty < 0:
                    raise ValidationError('新數量不可為負數！')
                if line.new_unit_price < 0:
                    raise ValidationError('新單價不可為負數！')

    @api.constrains('task_id', 'change_order_id')
    def _check_unique_task(self):
        """同一變更單不可重複選擇相同工項"""
        for line in self:
            if line.task_id:
                duplicate = self.search([
                    ('change_order_id', '=', line.change_order_id.id),
                    ('task_id', '=', line.task_id.id),
                    ('id', '!=', line.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f'工項 [{line.task_id.item_no}] {line.task_id.name} '
                        f'已存在於此變更單中！')

    # === 名稱顯示 ===
    def name_get(self):
        result = []
        for line in self:
            change_type_label = dict(
                self._fields['change_type'].selection).get(line.change_type, '')
            name = f'[{change_type_label}] {line.item_name}'
            result.append((line.id, name))
        return result
