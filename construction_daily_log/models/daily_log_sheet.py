# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import datetime, time

import babel.dates
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DailyLogSheet(models.Model):
    """
    Construction Daily Log Sheet - Reference hr_timesheet_sheet design

    Sheet pattern: Aggregates multiple days of daily log lines
    Supports 4-state workflow: new -> draft -> confirm -> done
    Multi-company isolation for contractor access control
    """
    _name = 'daily.log.sheet'
    _description = 'Construction Daily Log Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'
    _rec_name = 'complete_name'

    # === Basic Information ===
    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    complete_name = fields.Char(
        string='Complete Name',
        compute='_compute_complete_name',
        store=True,
    )

    # === Project Reference ===
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    project_type = fields.Selection(
        related='project_id.project_type',
        string='Project Type',
        store=True,
        readonly=True,
    )

    # === Multi-Company Architecture (v5.0) ===
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='Construction company for data isolation',
    )

    # Related tasks for validation
    task_ids = fields.Many2many(
        'project.task',
        string='Related Tasks',
        domain="[('project_id', '=', project_id)]",
        help='Tasks recorded in this daily log sheet',
    )

    # Reservation type specific
    notification_slip_id = fields.Many2one(
        'notification.slip',
        string='Notification Slip',
        domain="[('project_id', '=', project_id)]",
        help='For reservation type projects',
    )

    # === Period (Reference hr_timesheet_sheet) ===
    date_start = fields.Date(
        string='Start Date',
        required=True,
        index=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_end = fields.Date(
        string='End Date',
        required=True,
        index=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    sheet_range = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string='Period Range', default='daily', required=True)

    # === Employee Information ===
    employee_id = fields.Many2one(
        'hr.employee',
        string='Submitted By',
        required=True,
        default=lambda self: self._default_employee(),
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        related='employee_id.user_id',
        store=True,
        readonly=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )

    # === Daily Log Lines (Aggregates multiple days) ===
    line_ids = fields.One2many(
        'daily.log.line',
        'sheet_id',
        string='Daily Log Lines',
    )

    # === Statistics ===
    total_worker_count = fields.Integer(
        string='Total Workers',
        compute='_compute_totals',
        store=True,
    )
    total_equipment_count = fields.Integer(
        string='Total Equipment',
        compute='_compute_totals',
        store=True,
    )
    total_work_hours = fields.Float(
        string='Total Work Hours',
        compute='_compute_totals',
        store=True,
    )

    # === Weather Records (Daily) ===
    weather_ids = fields.One2many(
        'daily.log.weather',
        'sheet_id',
        string='Weather Records',
    )

    # === State Workflow (Reference hr_timesheet_sheet) ===
    state = fields.Selection([
        ('new', 'New'),
        ('draft', 'Draft'),
        ('confirm', 'Pending Review'),
        ('done', 'Approved'),
    ], string='Status', default='new', tracking=True, required=True, index=True)

    # === Review Information ===
    reviewer_id = fields.Many2one(
        'res.users',
        string='Reviewer',
        tracking=True,
        readonly=True,
    )
    review_date = fields.Datetime(
        string='Review Date',
        readonly=True,
    )
    review_policy = fields.Selection([
        ('supervisor', 'Supervisor'),
        ('manager', 'Manager'),
    ], string='Review Policy', default='supervisor')
    can_review = fields.Boolean(
        string='Can Review',
        compute='_compute_can_review',
    )

    # === Progress Information ===
    has_progress_change = fields.Boolean(
        string='Has Progress Change',
        default=False,
        help='Mark if there is progress update today',
    )
    actual_progress = fields.Float(
        string='Actual Progress (%)',
        digits=(5, 2),
    )

    # === Notes ===
    work_summary = fields.Text(
        string='Work Summary',
        help='Summary of work done during this period',
    )
    notes = fields.Text(
        string='Notes',
        help='Additional notes or remarks',
    )

    # -------------------------------------------------------------------------
    # Default Methods
    # -------------------------------------------------------------------------

    def _default_employee(self):
        """Get default employee for current user"""
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', 'in', [self.env.company.id, False]),
        ], limit=1, order='company_id ASC')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('date_start', 'date_end')
    def _compute_name(self):
        """Compute sheet name based on date range"""
        locale = self.env.context.get('lang') or self.env.user.lang or 'en_US'
        for sheet in self:
            if not sheet.date_start or not sheet.date_end:
                sheet.name = 'New'
                continue

            if sheet.date_start == sheet.date_end:
                # Single day
                sheet.name = babel.dates.format_skeleton(
                    skeleton='MMMEd',
                    datetime=datetime.combine(sheet.date_start, time.min),
                    locale=locale,
                )
            else:
                # Date range
                start_str = sheet.date_start.strftime('%Y-%m-%d')
                end_str = sheet.date_end.strftime('%Y-%m-%d')
                sheet.name = f'{start_str} ~ {end_str}'

    @api.depends('name', 'employee_id', 'project_id')
    def _compute_complete_name(self):
        """Compute complete display name"""
        for sheet in self:
            parts = [sheet.name or 'New']
            if sheet.project_id:
                parts.append(sheet.project_id.name)
            if sheet.employee_id:
                parts.append(sheet.employee_id.name)
            sheet.complete_name = ' - '.join(parts)

    @api.depends('line_ids.worker_count', 'line_ids.equipment_count', 'line_ids.unit_amount')
    def _compute_totals(self):
        """Compute total statistics from lines"""
        for sheet in self:
            sheet.total_worker_count = sum(sheet.line_ids.mapped('worker_count'))
            sheet.total_equipment_count = sum(sheet.line_ids.mapped('equipment_count'))
            sheet.total_work_hours = sum(sheet.line_ids.mapped('unit_amount'))

    @api.depends('review_policy', 'state')
    def _compute_can_review(self):
        """Compute if current user can review this sheet"""
        for sheet in self:
            sheet.can_review = self.env.user in sheet._get_possible_reviewers()

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        """Validate date range"""
        for sheet in self:
            if sheet.date_start and sheet.date_end:
                if sheet.date_start > sheet.date_end:
                    raise ValidationError(
                        'Start date cannot be later than end date.'
                    )

    @api.constrains('date_start', 'date_end', 'company_id', 'employee_id')
    def _check_overlapping_sheets(self):
        """Check for overlapping sheets"""
        for sheet in self:
            domain = [
                ('id', '!=', sheet.id),
                ('date_start', '<=', sheet.date_end),
                ('date_end', '>=', sheet.date_start),
                ('employee_id', '=', sheet.employee_id.id),
                ('company_id', '=', sheet.company_id.id),
                ('project_id', '=', sheet.project_id.id),
            ]
            overlapping = self.search(domain, limit=1)
            if overlapping:
                raise ValidationError(
                    f'Overlapping sheet exists: {overlapping.complete_name}'
                )

    @api.constrains('company_id', 'employee_id')
    def _check_company_employee(self):
        """Validate company and employee consistency"""
        for sheet in self.sudo():
            if (sheet.company_id and sheet.employee_id.company_id and
                    sheet.company_id != sheet.employee_id.company_id):
                raise ValidationError(
                    'Company in sheet and employee must be the same.'
                )

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Update company when employee changes"""
        if self.employee_id:
            company = self.employee_id.company_id or self.env.company
            self.company_id = company

    @api.onchange('date_start', 'sheet_range')
    def _onchange_date_range(self):
        """Auto-calculate end date based on range"""
        if self.date_start and self.sheet_range:
            if self.sheet_range == 'daily':
                self.date_end = self.date_start
            elif self.sheet_range == 'weekly':
                self.date_end = self.date_start + relativedelta(days=6)
            elif self.sheet_range == 'monthly':
                self.date_end = self.date_start + relativedelta(months=1, days=-1)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Clear notification slip when project changes"""
        if self.project_id:
            self.notification_slip_id = False

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_possible_reviewers(self):
        """Get users who can review this sheet"""
        self.ensure_one()
        reviewers = self.env['res.users'].browse(SUPERUSER_ID)

        # Add HR managers
        hr_manager_group = self.env.ref('hr.group_hr_manager', raise_if_not_found=False)
        if hr_manager_group:
            reviewers |= hr_manager_group.users

        # Add timesheet approvers
        timesheet_approver_group = self.env.ref(
            'hr_timesheet.group_hr_timesheet_approver',
            raise_if_not_found=False
        )
        if timesheet_approver_group:
            reviewers |= timesheet_approver_group.users

        return reviewers

    def _check_can_review(self):
        """Check if current user can review"""
        sheets_cannot_review = self.filtered(lambda s: not s.can_review)
        if sheets_cannot_review:
            raise UserError(
                'You do not have permission to review these sheets.'
            )

    def _check_sheet_validity(self):
        """Validate sheet before submission"""
        for sheet in self:
            if not sheet.line_ids:
                raise UserError(
                    'Cannot submit empty daily log. Please add at least one line.'
                )

    def _get_dates(self):
        """Get list of dates in the sheet range"""
        self.ensure_one()
        if not self.date_start or not self.date_end:
            return []
        if self.date_end < self.date_start:
            return []

        dates = []
        current = self.date_start
        while current <= self.date_end:
            dates.append(current)
            current += relativedelta(days=1)
        return dates

    # -------------------------------------------------------------------------
    # CRUD Methods
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Create and automatically transition to draft state"""
        sheets = super().create(vals_list)
        # Auto transition to draft
        sheets.filtered(lambda s: s.state == 'new').write({'state': 'draft'})
        return sheets

    def write(self, vals):
        """Override write to handle state transitions"""
        res = super().write(vals)
        return res

    def unlink(self):
        """Prevent deletion of confirmed/done sheets"""
        for sheet in self:
            if sheet.state in ('confirm', 'done'):
                raise UserError(
                    f'Cannot delete submitted or approved sheet: {sheet.complete_name}'
                )
        return super().unlink()

    def copy(self, default=None):
        """Prevent sheet duplication by default"""
        if not self.env.context.get('allow_copy_sheet'):
            raise UserError('Duplicating daily log sheets is not allowed.')
        return super().copy(default=default)

    # -------------------------------------------------------------------------
    # State Action Methods
    # -------------------------------------------------------------------------

    def action_draft(self):
        """Reset to draft state"""
        sheets = self.filtered(lambda s: s.state == 'done')
        if not sheets:
            raise UserError('Can only reset approved sheets to draft.')
        self._check_can_review()
        sheets.write({
            'state': 'draft',
            'reviewer_id': False,
            'review_date': False,
        })
        return True

    def action_confirm(self):
        """Submit for review"""
        self._check_sheet_validity()
        self.write({'state': 'confirm'})
        # Subscribe reviewers
        self._subscribe_reviewers()
        return True

    def action_done(self):
        """Approve the sheet"""
        sheets = self.filtered(lambda s: s.state == 'confirm')
        if not sheets:
            raise UserError('Can only approve sheets pending review.')
        self._check_can_review()
        sheets.write({
            'state': 'done',
            'reviewer_id': self.env.uid,
            'review_date': fields.Datetime.now(),
        })
        return True

    def action_refuse(self):
        """Reject the sheet back to draft"""
        sheets = self.filtered(lambda s: s.state == 'confirm')
        if not sheets:
            raise UserError('Can only refuse sheets pending review.')
        self._check_can_review()
        sheets.write({
            'state': 'draft',
            'reviewer_id': False,
            'review_date': False,
        })
        return True

    def _subscribe_reviewers(self):
        """Subscribe possible reviewers to sheet notifications"""
        for sheet in self.sudo():
            reviewers = sheet._get_possible_reviewers()
            if reviewers:
                partner_ids = reviewers.mapped('partner_id').ids
                sheet.message_subscribe(partner_ids=partner_ids)

    # -------------------------------------------------------------------------
    # Action Methods
    # -------------------------------------------------------------------------

    def action_view_lines(self):
        """Action to view daily log lines"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Daily Log Lines',
            'res_model': 'daily.log.line',
            'view_mode': 'list,form',
            'domain': [('sheet_id', '=', self.id)],
            'context': {
                'default_sheet_id': self.id,
                'default_project_id': self.project_id.id,
                'default_employee_id': self.employee_id.id,
            },
        }

    def action_add_weather(self):
        """Action to add weather record for each day"""
        self.ensure_one()
        if self.state not in ('new', 'draft'):
            raise UserError('Can only add weather records in draft state.')

        # Create weather records for dates without records
        existing_dates = set(self.weather_ids.mapped('date'))
        new_weather_vals = []

        for date in self._get_dates():
            if date not in existing_dates:
                new_weather_vals.append({
                    'sheet_id': self.id,
                    'date': date,
                })

        if new_weather_vals:
            self.env['daily.log.weather'].create(new_weather_vals)

        return True

    # -------------------------------------------------------------------------
    # Tracking
    # -------------------------------------------------------------------------

    def _track_subtype(self, init_values):
        """Track state changes for notifications"""
        self.ensure_one()
        if 'state' in init_values:
            if self.state == 'confirm':
                return self.env.ref(
                    'construction_daily_log.mt_daily_log_confirmed',
                    raise_if_not_found=False
                )
            elif self.state == 'done':
                return self.env.ref(
                    'construction_daily_log.mt_daily_log_approved',
                    raise_if_not_found=False
                )
        return super()._track_subtype(init_values)
