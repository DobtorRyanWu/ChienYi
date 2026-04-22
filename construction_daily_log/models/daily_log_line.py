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
    _order = 'sheet_id, sequence, date desc, id desc'

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

    # === Work Item Reference ===
    work_item_id = fields.Many2one(
        'project.task',
        string='施工項目',
        required=True,
        domain="[('project_id', '=', project_id), ('is_summary_item', '=', False), ('active', '=', True)]",
        help='只能選擇最細項工項（無子項的工項）',
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
        related='work_item_id.parent_id.name',
        string='父工項名稱',
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
        related='work_item_id.planned_qty',
        string='契約數量',
        readonly=True,
        digits=(16, 4),
        store=True,
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
        if self.work_item_id:
            self.name = f'施工記錄 - {self.work_item_id.name}'
    
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

        return super().create(vals_list)

    def write(self, vals):
        """Override write to sync with analytic line"""
        return super().write(vals)

    def unlink(self):
        """Delete analytic lines when deleting daily log lines"""
        analytic_lines = self.mapped('analytic_line_id')
        res = super().unlink()
        # Also delete orphan analytic lines
        analytic_lines.exists().unlink()
        return res

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
