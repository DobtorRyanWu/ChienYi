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
    _order = 'date desc, id desc'

    # === Delegation Inheritance ===
    analytic_line_id = fields.Many2one(
        'account.analytic.line',
        string='Analytic Line',
        required=True,
        ondelete='cascade',
        auto_join=True,
        help='Link to the underlying analytic line',
    )

    # === Sheet Relationship ===
    sheet_id = fields.Many2one(
        'daily.log.sheet',
        string='Daily Log Sheet',
        ondelete='cascade',
        index=True,
    )
    sheet_state = fields.Selection(
        related='sheet_id.state',
        string='Sheet Status',
        store=True,
        readonly=True,
    )

    # === Day of Week (Reference hr_timesheet_day_week) ===
    day_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', compute='_compute_day_week', store=True)

    # === Work Item Reference ===
    work_item_id = fields.Many2one(
        'project.task',
        string='Work Item',
        domain="[('project_id', '=', project_id)]",
        help='The specific task or work item being worked on',
    )

    # === Completion Information ===
    completion_qty = fields.Float(
        string='Completed Quantity',
        digits=(12, 2),
        help='Quantity of work completed',
    )
    completion_unit = fields.Char(
        string='Unit',
        size=32,
        help='Unit of measurement for completion quantity',
    )
    completion_percentage = fields.Float(
        string='Completion %',
        digits=(5, 2),
        help='Percentage of work completed (0-100)',
    )

    # === Manpower and Equipment ===
    worker_count = fields.Integer(
        string='Worker Count',
        default=0,
        help='Number of workers assigned',
    )
    equipment_count = fields.Integer(
        string='Equipment Count',
        default=0,
        help='Number of equipment units used',
    )
    material_note = fields.Text(
        string='Material Notes',
        help='Notes about materials used',
    )

    # === Work Description ===
    work_description = fields.Text(
        string='Work Description',
        help='Detailed description of work performed',
    )
    location = fields.Char(
        string='Location',
        size=256,
        help='Work location within the project site',
    )

    # === Issue Tracking ===
    has_issue = fields.Boolean(
        string='Has Issues',
        default=False,
        help='Mark if there were any issues during work',
    )
    issue_description = fields.Text(
        string='Issue Description',
        help='Description of issues encountered',
    )

    # === Computed Fields ===
    company_id = fields.Many2one(
        related='sheet_id.company_id',
        string='Company',
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

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('completion_percentage')
    def _check_completion_percentage(self):
        """Validate completion percentage is between 0 and 100"""
        for line in self:
            if line.completion_percentage < 0 or line.completion_percentage > 100:
                raise ValidationError(
                    'Completion percentage must be between 0 and 100.'
                )

    @api.constrains('worker_count', 'equipment_count')
    def _check_counts(self):
        """Validate counts are non-negative"""
        for line in self:
            if line.worker_count < 0:
                raise ValidationError('Worker count cannot be negative.')
            if line.equipment_count < 0:
                raise ValidationError('Equipment count cannot be negative.')

    @api.constrains('sheet_id', 'date')
    def _check_date_in_sheet_range(self):
        """Validate line date is within sheet date range"""
        for line in self:
            if line.sheet_id and line.date:
                if (line.date < line.sheet_id.date_start or
                        line.date > line.sheet_id.date_end):
                    raise ValidationError(
                        f'Line date {line.date} is outside sheet date range '
                        f'({line.sheet_id.date_start} - {line.sheet_id.date_end}).'
                    )

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
                self.date = self.sheet_id.date_start

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Create daily log lines with analytic line"""
        for vals in vals_list:
            # Ensure required fields for analytic line
            if 'name' not in vals or not vals.get('name'):
                vals['name'] = 'Daily Log Entry'

            # Get sheet info for defaults
            sheet_id = vals.get('sheet_id')
            if sheet_id:
                sheet = self.env['daily.log.sheet'].browse(sheet_id)
                if not vals.get('project_id'):
                    vals['project_id'] = sheet.project_id.id
                if not vals.get('employee_id'):
                    vals['employee_id'] = sheet.employee_id.id
                if not vals.get('date'):
                    vals['date'] = sheet.date_start
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

    def action_view_analytic_line(self):
        """View the underlying analytic line"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Analytic Line',
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
        string='Daily Log Lines',
        readonly=True,
    )
    is_daily_log = fields.Boolean(
        string='Is Daily Log',
        compute='_compute_is_daily_log',
        store=True,
    )

    @api.depends('daily_log_line_ids')
    def _compute_is_daily_log(self):
        """Check if this analytic line is linked to a daily log"""
        for line in self:
            line.is_daily_log = bool(line.daily_log_line_ids)
