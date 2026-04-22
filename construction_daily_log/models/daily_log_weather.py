# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DailyLogWeather(models.Model):
    """
    Daily Weather Record for Construction Daily Log

    Records weather conditions for each day in the daily log sheet period.
    Includes morning and afternoon weather, work duration, and progress info.
    """
    _name = 'daily.log.weather'
    _description = 'Daily Log Weather Record'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # === Relationship ===
    sheet_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌表單',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        related='sheet_id.project_id',
        string='專案',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='sheet_id.company_id',
        string='公司',
        store=True,
        readonly=True,
    )

    # === Date ===
    date = fields.Date(
        string='日期',
        required=True,
        index=True,
    )
    day_week = fields.Selection([
        ('0', '星期一'),
        ('1', '星期二'),
        ('2', '星期三'),
        ('3', '星期四'),
        ('4', '星期五'),
        ('5', '星期六'),
        ('6', '星期日'),
    ], string='星期', compute='_compute_day_week', store=True)

    # === Weather Conditions ===
    weather_am = fields.Selection([
        ('sunny', '晴'),
        ('cloudy', '多雲'),
        ('overcast', '陰'),
        ('rainy', '雨'),
        ('heavy_rain', '大雨'),
        ('typhoon', '颱風'),
        ('foggy', '霧'),
    ], string='上午天氣')
    weather_pm = fields.Selection([
        ('sunny', '晴'),
        ('cloudy', '多雲'),
        ('overcast', '陰'),
        ('rainy', '雨'),
        ('heavy_rain', '大雨'),
        ('typhoon', '颱風'),
        ('foggy', '霧'),
    ], string='下午天氣')

    # === Temperature ===
    temperature_high = fields.Float(
        string='最高溫度',
        digits=(4, 1),
        help='最高溫度(攝氏)',
    )
    temperature_low = fields.Float(
        string='最低溫度',
        digits=(4, 1),
        help='最低溫度(攝氏)',
    )

    # === Work Status ===
    is_workday = fields.Boolean(
        string='是否施工',
        default=True,
        help='這一天是否進行施工',
    )
    work_stopped_reason = fields.Selection([
        ('rain', '下雨'),
        ('typhoon', '颱風'),
        ('holiday', '休假'),
        ('material', '材料短缺'),
        ('other', '其他'),
    ], string='停工原因', help='如果停工的原因')
    work_stop_note = fields.Char(
        string='停工原因說明',
        size=256,
    )

    # === Duration Information ===
    approved_duration = fields.Integer(
        string='核定工期(天)',
        compute='_compute_approved_duration',
        store=True,
        help='專案核定總工期(天數)',
    )
    cumulative_duration = fields.Integer(
        string='累計工期(天)',
        compute='_compute_duration',
        store=True,
        help='截至此日的累計工作天數',
    )
    remaining_duration = fields.Integer(
        string='剩餘工期(天)',
        compute='_compute_duration',
        store=True,
        help='剩餘工作天數',
    )

    # === Progress Information ===
    planned_progress = fields.Float(
        string='預定進度 (%)',
        digits=(5, 2),
        help='預定累計進度百分比',
    )
    actual_progress = fields.Float(
        string='實際進度 (%)',
        digits=(5, 2),
        help='實際累計進度百分比',
    )
    has_progress_change = fields.Boolean(
        string='進度有變更',
        default=False,
        help='標記這一天進度是否有更新',
    )
    progress_variance = fields.Float(
        string='進度差異 (%)',
        compute='_compute_progress_variance',
        store=True,
        digits=(5, 2),
        help='實際與預定進度的差異',
    )

    # === Display Name ===
    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True,
    )

    # === Notes ===
    notes = fields.Text(
        string='備註',
        help='其他天氣或工作備註',
    )

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('date')
    def _compute_day_week(self):
        """Compute day of week from date"""
        for record in self:
            if record.date:
                record.day_week = str(record.date.weekday())
            else:
                record.day_week = False

    @api.depends('sheet_id.supervision_project_id.contract_duration')
    def _compute_approved_duration(self):
        """Compute approved duration from supervision project"""
        for record in self:
            if record.sheet_id and record.sheet_id.supervision_project_id:
                record.approved_duration = record.sheet_id.supervision_project_id.contract_duration or 0
            else:
                record.approved_duration = 0

    @api.depends('date', 'sheet_id.supervision_project_id.contract_start_date', 'approved_duration')
    def _compute_duration(self):
        """Compute cumulative and remaining duration"""
        for record in self:
            supervision_project = record.sheet_id.supervision_project_id if record.sheet_id else False
            if record.date and supervision_project and supervision_project.contract_start_date:
                # Calculate cumulative days from project start
                delta = record.date - supervision_project.contract_start_date
                record.cumulative_duration = delta.days + 1

                # Calculate remaining days
                approved = record.approved_duration or 0
                record.remaining_duration = max(0, approved - record.cumulative_duration)
            else:
                record.cumulative_duration = 0
                record.remaining_duration = record.approved_duration or 0

    @api.depends('planned_progress', 'actual_progress')
    def _compute_progress_variance(self):
        """Compute progress variance (actual - planned)"""
        for record in self:
            record.progress_variance = record.actual_progress - record.planned_progress

    @api.depends('date', 'weather_am', 'weather_pm')
    def _compute_display_name(self):
        """Compute display name"""
        weather_labels = {
            'sunny': '晴',
            'cloudy': '多雲',
            'overcast': '陰',
            'rainy': '雨',
            'heavy_rain': '大雨',
            'typhoon': '颱風',
            'foggy': '霧',
        }
        for record in self:
            parts = []
            if record.date:
                parts.append(record.date.strftime('%Y-%m-%d'))
            weather_parts = []
            if record.weather_am:
                weather_parts.append(f"AM: {weather_labels.get(record.weather_am, record.weather_am)}")
            if record.weather_pm:
                weather_parts.append(f"PM: {weather_labels.get(record.weather_pm, record.weather_pm)}")
            if weather_parts:
                parts.append(' / '.join(weather_parts))
            record.display_name = ' - '.join(parts) if parts else 'New'

    # -------------------------------------------------------------------------
    # Constraint Methods
    # -------------------------------------------------------------------------

    @api.constrains('sheet_id', 'date')
    def _check_date_in_sheet_range(self):
        """Validate date is within sheet date range"""
        for record in self:
            if record.sheet_id and record.date:
                if (record.date < record.sheet_id.date_start or
                        record.date > record.sheet_id.date_end):
                    raise ValidationError(
                        f'天氣日期 {record.date} 超出表單日期範圍 '
                        f'({record.sheet_id.date_start} - {record.sheet_id.date_end})。'
                    )

    @api.constrains('sheet_id', 'date')
    def _check_unique_date(self):
        """Ensure only one weather record per date per sheet"""
        for record in self:
            if record.sheet_id and record.date:
                duplicates = self.search([
                    ('id', '!=', record.id),
                    ('sheet_id', '=', record.sheet_id.id),
                    ('date', '=', record.date),
                ])
                if duplicates:
                    raise ValidationError(
                        f'{record.date} 的天氣記錄已存在於此表單中。'
                    )

    @api.constrains('planned_progress', 'actual_progress')
    def _check_progress_values(self):
        """Validate progress values are between 0 and 100"""
        for record in self:
            if record.planned_progress < 0 or record.planned_progress > 100:
                raise ValidationError(
                    '預定進度必須介於 0 到 100 之間。'
                )
            if record.actual_progress < 0 or record.actual_progress > 100:
                raise ValidationError(
                    '實際進度必須介於 0 到 100 之間。'
                )

    @api.constrains('temperature_high', 'temperature_low')
    def _check_temperature(self):
        """Validate temperature range"""
        for record in self:
            if record.temperature_high and record.temperature_low:
                if record.temperature_low > record.temperature_high:
                    raise ValidationError(
                        '最低溫度不能高於最高溫度。'
                    )

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('is_workday')
    def _onchange_is_workday(self):
        """Clear work stop reason when it's a workday"""
        if self.is_workday:
            self.work_stopped_reason = False
            self.work_stop_note = False

    @api.onchange('actual_progress')
    def _onchange_actual_progress(self):
        """Mark progress change when actual progress is modified"""
        if self.actual_progress:
            self.has_progress_change = True

    # -------------------------------------------------------------------------
    # Business Methods
    # -------------------------------------------------------------------------

    def action_copy_weather_from_previous(self):
        """Copy weather from previous day"""
        self.ensure_one()
        if not self.sheet_id:
            return False

        # Find previous weather record
        previous = self.search([
            ('sheet_id', '=', self.sheet_id.id),
            ('date', '<', self.date),
        ], order='date desc', limit=1)

        if previous:
            self.write({
                'weather_am': previous.weather_am,
                'weather_pm': previous.weather_pm,
            })
        return True

    def action_mark_holiday(self):
        """Mark as holiday (non-workday)"""
        self.write({
            'is_workday': False,
            'work_stopped_reason': 'holiday',
        })
        return True

    def action_mark_rain_stop(self):
        """Mark as work stopped due to rain"""
        self.write({
            'is_workday': False,
            'work_stopped_reason': 'rain',
        })
        return True
