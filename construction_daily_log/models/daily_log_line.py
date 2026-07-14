# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyLogLine(models.Model):
    """
    Construction Daily Log Line - Inherits account.analytic.line

    Uses _inherits delegation inheritance pattern to extend
    account.analytic.line with construction-specific fields.
    """
    _name = 'daily.log.line'
    _description = 'Construction Daily Log Line'
    _inherits = {'account.analytic.line': 'analytic_line_id'}
    # 排序：同一日誌內，契約工項(type_order=0) 永遠排在自填項目(type_order=1) 之前；
    # 契約工項間依工項排序，自填項目間依 sequence。與「分批新增的時間先後」無關。
    _order = 'sheet_id, type_order, work_item_sequence, sequence, id'

    # === Delegation Inheritance ===
    analytic_line_id = fields.Many2one(
        'account.analytic.line',
        string='分析帳明細',
        required=True,
        ondelete='cascade',
        auto_join=True,
        help='連結到底層的分析帳明細',
    )

    # === Sheet Relationship ===
    sheet_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌表單',
        ondelete='cascade',
        index=True,
    )
    sheet_state = fields.Selection(
        related='sheet_id.state',
        string='表單狀態',
        store=True,
        readonly=True,
    )
    
    # === Sequence for manual ordering ===
    sequence = fields.Integer(
        string='排序',
        default=10,
        help='用於手動排序明細列表',
    )

    # === Day of Week (Reference hr_timesheet_day_week) ===
    day_week = fields.Selection([
        ('0', '星期一'),
        ('1', '星期二'),
        ('2', '星期三'),
        ('3', '星期四'),
        ('4', '星期五'),
        ('5', '星期六'),
        ('6', '星期日'),
    ], string='星期', compute='_compute_day_week', store=True)

    # === 項目類型：契約工項 / 自填純文字 ===
    entry_type = fields.Selection([
        ('contract', '契約工項'),
        ('extra', '其他項目（自填）'),
    ], string='項目類型', default='contract', required=True,
       help='契約工項：連結契約工項並計算數量／完成率；'
            '其他項目：純文字自填（如「工區復舊」），不登記為契約工項')

    custom_name = fields.Char(
        string='項目說明',
        help='自填項目名稱（如「工區復舊」），僅為文字，不會登記為契約工項',
    )

    type_order = fields.Integer(
        string='類型排序',
        compute='_compute_type_order',
        store=True,
        index=True,
        help='排序用：契約工項(0) 永遠排在自填項目(1) 之前',
    )

    # === Work Item Reference ===
    work_item_id = fields.Many2one(
        'project.task',
        string='施工項目',
        required=False,  # 自填項目(entry_type='extra')不需契約工項
        domain="[('project_id', '=', project_id), ('is_summary_item', '=', False), ('active', '=', True)]",
        help='契約工項類型才需選擇；只能選最細項工項（無子項的工項）',
    )

    # === 內容來自工項（自動帶入）===
    item_no = fields.Char(
        related='work_item_id.item_no',
        string='工項編號',
        readonly=True,
        store=True,
    )
    
    item_name = fields.Char(
        related='work_item_id.name',
        string='工項名稱',
        readonly=True,
        store=True,
    )

    work_item_sequence = fields.Integer(
        related='work_item_id.sequence',
        string='工項排序',
        readonly=True,
        store=True,
    )

    parent_item_id = fields.Many2one(
        related='work_item_id.parent_id',
        string='父工項',
        readonly=True,
        store=True,
    )

    parent_item_name = fields.Char(
        related='work_item_id.parent_id.full_item_path',
        string='父工項路徑',
        readonly=True,
        store=True,
    )

    unit = fields.Char(
        related='work_item_id.unit',
        string='單位',
        readonly=True,
        store=True,
    )
    
    contract_qty = fields.Float(
        string='契約數量',
        compute='_compute_contract_qty',
        store=True,
        readonly=True,
        digits=(16, 4),
        help='依日誌日期取該工項「當時有效」的契約數量（從工項版本 version_ids 依生效日取），'
             '使歷史日誌不被日後契約變更／歸零污染。',
    )
    
    # === 本日完成數量（可編輯）===
    daily_qty = fields.Float(
        string='本日完成數量',
        digits=(16, 4),
        default=0.0,
        help='今日完成的數量',
    )
    
    # === 累計完成數量（計算欄位）===
    cumulative_qty = fields.Float(
        string='累計完成數量',
        compute='_compute_cumulative_qty',
        store=True,
        digits=(16, 4),
        help='截至本日的累計完成數量（包含本日）',
    )
    
    # === 完成率與其他計算欄位 ===
    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_completion_rate',
        store=True,
        digits=(5, 2),
        help='累計完成數量 / 契約數量 * 100',
    )
    
    remaining_qty = fields.Float(
        string='剩餘數量',
        compute='_compute_completion_rate',
        store=True,
        digits=(16, 4),
        help='契約數量 - 累計完成數量',
    )
    
    is_over_contract = fields.Boolean(
        string='超出契約',
        compute='_compute_completion_rate',
        store=True,
        help='累計數量是否超出契約數量',
    )

    # === Work Description ===
    work_description = fields.Text(
        string='備註',
        help='施工備註',
    )
    location = fields.Char(
        string='位置',
        size=256,
        help='工地內的工作位置',
    )

    # === Issue Tracking ===
    has_issue = fields.Boolean(
        string='有問題',
        default=False,
        help='標記工作期間是否有任何問題',
    )
    issue_description = fields.Text(
        string='問題描述',
        help='遇到的問題說明',
    )

    # === Computed Fields ===
    company_id = fields.Many2one(
        related='sheet_id.company_id',
        string='公司',
        store=True,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('date')
    def _compute_day_week(self):
        """Compute day of week from date"""
        for line in self:
            if line.date:
                line.day_week = str(line.date.weekday())
            else:
                line.day_week = False

    @api.depends('entry_type')
    def _compute_type_order(self):
        """契約工項排序值 0、自填項目排序值 1（保證契約恆在自填之前）"""
        for line in self:
            line.type_order = 1 if line.entry_type == 'extra' else 0
    
    @api.depends('work_item_id', 'daily_qty', 'date')
    def _compute_cumulative_qty(self):
        """計算累計完成數量"""
        for line in self:
            if line.work_item_id and line.date:
                # 查詢該工項在此日期之前（含當天）的所有記錄
                domain = [
                    ('work_item_id', '=', line.work_item_id.id),
                    ('date', '<=', line.date),
                    ('id', '!=', line.id or 0),  # 排除自己（避免重複計算）
                ]
                previous_lines = self.search(domain)
                previous_total = sum(previous_lines.mapped('daily_qty'))
                line.cumulative_qty = previous_total + (line.daily_qty or 0.0)
            else:
                line.cumulative_qty = line.daily_qty or 0.0
    
    @api.depends('cumulative_qty', 'contract_qty')
    def _compute_completion_rate(self):
        """計算完成率和剩餘數量"""
        for line in self:
            if line.contract_qty:
                line.completion_rate = (line.cumulative_qty / line.contract_qty) * 100
                line.remaining_qty = line.contract_qty - line.cumulative_qty
                line.is_over_contract = line.cumulative_qty > line.contract_qty
            else:
                line.completion_rate = 0.0
                line.remaining_qty = 0.0
                line.is_over_contract = False

    @api.depends('work_item_id', 'date',
                 'work_item_id.planned_qty', 'work_item_id.original_planned_qty',
                 'work_item_id.version_ids.planned_qty',
                 'work_item_id.version_ids.change_date',
                 'work_item_id.version_ids.version')
    def _compute_contract_qty(self):
        """依日誌日期取該工項「當時有效」的契約數量。
        規則：取「生效日(change_date) <= 日誌日期」且 version>1 的變更版本中、version 最大者；
              若無（日誌日期早於任何契約變更）→ 取原始版本 v1（或 original_planned_qty/planned_qty）。
        ⚠️ v1（原始契約）的 change_date 可能是匯入日（未必等於契約起日），故 v1 不參與日期比對，
           僅作為「尚無契約變更生效」時的基準，避免匯入日晚於日誌日期時取值錯誤。"""
        for line in self:
            task = line.work_item_id
            if not task:
                line.contract_qty = 0.0
                continue
            d = line.date
            versions = task.version_ids
            changes = versions.filtered(
                lambda v: v.version > 1 and v.change_date and d and v.change_date <= d)
            if changes:
                line.contract_qty = max(changes, key=lambda v: v.version).planned_qty
            else:
                v1 = versions.filtered(lambda v: v.version == 1)
                line.contract_qty = (
                    v1[0].planned_qty if v1
                    else (task.original_planned_qty or task.planned_qty))

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('work_item_id')
    def _onchange_work_item_id(self):
        """選擇工項時檢查是否已存在"""
        if self.work_item_id and self.sheet_id:
            existing = self.search([
                ('id', '!=', self.id or 0),
                ('sheet_id', '=', self.sheet_id.id),
                ('work_item_id', '=', self.work_item_id.id),
            ], limit=1)
            if existing:
                return {
                    'warning': {
                        'title': '工項重複',
                        'message': f'工項「{self.work_item_id.name}」在此日誌中已存在！',
                    }
                }
    
    @api.onchange('work_item_id')
    def _onchange_work_item_update_name(self):
        """Update name when work item changes"""
        if self.entry_type == 'contract' and self.work_item_id:
            self.name = f'施工記錄 - {self.work_item_id.name}'

    @api.onchange('entry_type')
    def _onchange_entry_type(self):
        """切換類型時清掉不適用欄位並同步名稱"""
        if self.entry_type == 'extra':
            self.work_item_id = False
            self.daily_qty = 0.0
        else:
            self.custom_name = False
        self._sync_line_name()

    @api.onchange('custom_name')
    def _onchange_custom_name(self):
        """自填項目改名稱時同步顯示名稱"""
        if self.entry_type == 'extra':
            self._sync_line_name()

    def _sync_line_name(self):
        """依類型同步底層 analytic line 的 name"""
        for line in self:
            if line.entry_type == 'extra':
                line.name = f'施工記錄 - {line.custom_name}' if line.custom_name else '施工記錄'
            elif line.work_item_id:
                line.name = f'施工記錄 - {line.work_item_id.name}'
    
    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('work_item_id')
    def _check_is_leaf_item(self):
        """確保只能選擇最細項"""
        for line in self:
            if line.work_item_id and line.work_item_id.is_summary_item:
                raise ValidationError(
                    f'工項「{line.work_item_id.name}」是彙總項目，\n'
                    f'請選擇最細項工項（沒有子項的工項）。'
                )
    
    @api.constrains('work_item_id', 'sheet_id')
    def _check_unique_work_item(self):
        """同一日誌中，同一工項只能出現一次"""
        for line in self:
            if line.work_item_id and line.sheet_id:
                duplicates = self.search([
                    ('id', '!=', line.id),
                    ('sheet_id', '=', line.sheet_id.id),
                    ('work_item_id', '=', line.work_item_id.id),
                ])
                if duplicates:
                    raise ValidationError(
                        f'工項「{line.work_item_id.name}」在此日誌中已存在！\n'
                        f'同一工項在同一天只能記錄一次。'
                    )
    
    @api.constrains('daily_qty')
    def _check_daily_qty(self):
        """檢查數量不可為負"""
        for line in self:
            if line.daily_qty < 0:
                raise ValidationError('本日完成數量不可為負數！')

    @api.constrains('entry_type', 'work_item_id', 'custom_name')
    def _check_entry_type(self):
        """契約工項必須選工項；自填項目必須填說明"""
        for line in self:
            if line.entry_type == 'contract' and not line.work_item_id:
                raise ValidationError('「契約工項」類型必須選擇施工項目。')
            if line.entry_type == 'extra' and not line.custom_name:
                raise ValidationError('「其他項目」類型必須填寫「項目說明」。')

    @api.constrains('sheet_id', 'date')
    def _check_date_in_sheet_range(self):
        """Validate line date is within sheet date range"""
        for line in self:
            if line.sheet_id and line.date:
                if line.date != line.sheet_id.log_date:
                    raise ValidationError(
                        f'明細日期 {line.date} 必須與日誌日期 {line.sheet_id.log_date} 一致。')

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('work_item_id')
    def _onchange_work_item_id(self):
        """Update task and project from work item"""
        if self.work_item_id:
            self.task_id = self.work_item_id
            if self.work_item_id.project_id:
                self.project_id = self.work_item_id.project_id

    @api.onchange('sheet_id')
    def _onchange_sheet_id(self):
        """Auto-fill fields from sheet"""
        if self.sheet_id:
            if not self.project_id:
                self.project_id = self.sheet_id.project_id
            if not self.employee_id:
                self.employee_id = self.sheet_id.employee_id
            if not self.date:
                self.date = self.sheet_id.log_date

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Create daily log lines with analytic line"""
        for vals in vals_list:
            # Ensure required fields for analytic line
            if 'name' not in vals or not vals.get('name'):
                if vals.get('entry_type') == 'extra' and vals.get('custom_name'):
                    vals['name'] = f"施工記錄 - {vals['custom_name']}"
                else:
                    vals['name'] = '施工日誌記錄'

            # Get sheet info for defaults
            sheet_id = vals.get('sheet_id')
            if sheet_id:
                sheet = self.env['daily.log.sheet'].browse(sheet_id)
                if not vals.get('project_id'):
                    vals['project_id'] = sheet.project_id.id
                if not vals.get('employee_id'):
                    vals['employee_id'] = sheet.employee_id.id
                if not vals.get('date'):
                    vals['date'] = sheet.log_date
                if not vals.get('company_id'):
                    vals['company_id'] = sheet.company_id.id

        lines = super().create(vals_list)
        # H3：cumulative_qty 為跨列聚合，新增列（尤其補登較早日期）須重算同工項後續列
        lines._recompute_sibling_cumulative(lines.work_item_id)
        return lines

    _CUMULATIVE_TRIGGER_FIELDS = ('daily_qty', 'date', 'work_item_id')

    def write(self, vals):
        """Override write to sync with analytic line"""
        affected_items = self.work_item_id  # 變更前的工項
        res = super().write(vals)
        # H3：改量/改日期/換工項會影響同工項其他列的累計，需一併重算
        if set(vals) & set(self._CUMULATIVE_TRIGGER_FIELDS):
            self._recompute_sibling_cumulative(affected_items | self.work_item_id)
        return res

    def unlink(self):
        """Delete analytic lines when deleting daily log lines"""
        affected_items = self.work_item_id  # H3：刪列後同工項其餘列累計要重算
        analytic_lines = self.mapped('analytic_line_id')
        res = super().unlink()
        # Also delete orphan analytic lines
        analytic_lines.exists().unlink()
        self.env['daily.log.line']._recompute_sibling_cumulative(affected_items)
        return res

    def _recompute_sibling_cumulative(self, work_items):
        """重算指定工項所有日誌列的 cumulative_qty（含下游 completion_rate 等）。

        cumulative_qty 是「同工項、date<=本列」的跨列聚合但 @api.depends 只列自身欄位，
        故 ORM 不會因兄弟列變動而重算（H3）。這裡顯式觸發同工項全部列重算。
        """
        work_items = work_items.exists()
        if not work_items:
            return
        siblings = self.sudo().search([('work_item_id', 'in', work_items.ids)])
        if siblings:
            siblings.invalidate_recordset(['cumulative_qty'])
            siblings.modified(['daily_qty'])

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_remove_from_sheet(self):
        """從日誌中移除此工項，重新開啟精靈並停留在「已有工項」分頁"""
        self.ensure_one()
        sheet = self.sheet_id
        self.unlink()
        # 建立新 wizard，使用「已有工項」預設分頁的 view
        new_wizard = self.env['daily.log.add.items.wizard'].create({
            'sheet_id': sheet.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.log.add.items.wizard',
            'view_mode': 'form',
            'res_id': new_wizard.id,
            'target': 'new',
            'view_id': self.env.ref(
                'construction_daily_log.daily_log_add_items_wizard_form_existing'
            ).id,
        }

    def action_view_analytic_line(self):
        """View the underlying analytic line"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '分析帳明細',
            'res_model': 'account.analytic.line',
            'view_mode': 'form',
            'res_id': self.analytic_line_id.id,
        }


class AccountAnalyticLine(models.Model):
    """Extend account.analytic.line with daily log reference"""
    _inherit = 'account.analytic.line'

    daily_log_line_ids = fields.One2many(
        'daily.log.line',
        'analytic_line_id',
        string='施工日誌明細',
        readonly=True,
    )
    is_daily_log = fields.Boolean(
        string='是施工日誌',
        compute='_compute_is_daily_log',
        store=True,
    )

    @api.depends('daily_log_line_ids')
    def _compute_is_daily_log(self):
        """Check if this analytic line is linked to a daily log"""
        for line in self:
            line.is_daily_log = bool(line.daily_log_line_ids)
