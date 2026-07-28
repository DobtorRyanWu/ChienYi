# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class GeneralProgressReport(models.Model):
    """
    一般式進度報告

    設計說明：
    - 定期記錄工程施工進度
    - 支援週報/月報等不同週期
    - 資料自動從施工日誌與進度表同步
    """
    _name = 'general.progress.report'
    _description = '一般式進度報告'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'report_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='報告編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('general.progress.report') or '/')

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
        domain="[('project_type', '=', 'general')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    # === 報告類型 ===
    report_type = fields.Selection([
        ('daily', '日報'),
        ('weekly', '週報'),
        ('biweekly', '雙週報'),
        ('monthly', '月報'),
        ('special', '專案報告'),
    ], string='報告類型', required=True, default='weekly', tracking=True)

    # === 報告期間 ===
    report_date = fields.Date(
        string='報告日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    period_start = fields.Date(
        string='報告期間起',
        required=True,
        tracking=True)

    period_end = fields.Date(
        string='報告期間迄',
        required=True,
        tracking=True)

    # === 報告人 ===
    reporter_id = fields.Many2one(
        'res.users',
        string='報告人',
        default=lambda self: self.env.uid,
        tracking=True)

    # === 進度資訊（從進度表同步，唯讀） ===
    planned_progress = fields.Float(
        string='預定累計進度 (%)',
        digits=(5, 2),
        readonly=True,
        help='來自啟用中進度表，報告期間迄所在區間的累計預定進度')

    actual_progress = fields.Float(
        string='實際累計進度 (%)',
        digits=(5, 2),
        readonly=True,
        help='來自啟用中進度表，報告期間迄所在區間的累計實際進度')

    progress_variance = fields.Float(
        string='進度差異 (%)',
        compute='_compute_progress_variance',
        store=True,
        help='實際進度 - 預定進度，正值表示超前，負值表示落後')

    progress_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
        ('critical', '嚴重落後'),
    ], string='進度狀態',
       compute='_compute_progress_variance',
       store=True)

    @api.depends('planned_progress', 'actual_progress')
    def _compute_progress_variance(self):
        for record in self:
            variance = record.actual_progress - record.planned_progress
            record.progress_variance = variance
            if variance > 3:
                record.progress_status = 'ahead'
            elif variance >= -3:
                record.progress_status = 'on_track'
            elif variance >= -10:
                record.progress_status = 'delayed'
            else:
                record.progress_status = 'critical'

    # === 工期資訊 ===
    contract_duration = fields.Integer(
        string='契約工期(日)',
        related='project_id.contract_duration',
        store=True)

    elapsed_days = fields.Integer(
        string='已施工天數',
        compute='_compute_elapsed_days',
        store=True)

    remaining_days = fields.Integer(
        string='剩餘天數',
        compute='_compute_elapsed_days',
        store=True)

    @api.depends('project_id.actual_start_date', 'project_id.contract_end_date', 'report_date')
    def _compute_elapsed_days(self):
        for record in self:
            if record.project_id.actual_start_date and record.report_date:
                record.elapsed_days = (record.report_date - record.project_id.actual_start_date).days + 1
            else:
                record.elapsed_days = 0

            if record.project_id.contract_end_date and record.report_date:
                remaining = (record.project_id.contract_end_date - record.report_date).days
                record.remaining_days = max(0, remaining)
            else:
                record.remaining_days = 0

    # === 施工概況 ===
    work_summary = fields.Html(
        string='本期施工概況',
        help='本報告期間主要施工內容摘要')

    work_items = fields.Text(
        string='本期施工項目',
        help='列出本期施工的具體工項')

    # === 工項進度明細 ===
    progress_line_ids = fields.One2many(
        'general.progress.report.line',
        'report_id',
        string='工項進度明細')

    # === 品質與安全（從缺失紀錄同步，唯讀） ===
    quality_summary = fields.Text(
        string='品質管理摘要',
        help='本期品質管理執行情況')

    safety_summary = fields.Text(
        string='安全衛生摘要',
        help='本期安全衛生執行情況')

    defect_count = fields.Integer(
        string='本期缺失數',
        readonly=True,
        help='本期在報告區間內發現的缺失數量（自動統計）')

    defect_improved_count = fields.Integer(
        string='本期改善數',
        readonly=True,
        help='本期在報告區間內改善完成的缺失數量（自動統計）')

    # === 天氣與施工日 ===
    work_days = fields.Integer(
        string='本期工作日',
        readonly=True,
        help='本期有施工日誌確認記錄的天數（由同步功能帶入）')

    rain_days = fields.Integer(
        string='本期雨天數',
        readonly=True,
        help='本期天氣記錄為雨天/豪雨/颱風的天數（由同步功能帶入）')

    holiday_days = fields.Integer(
        string='本期假日數',
        help='本期假日天數（手動填寫）')

    # === 同步紀錄 ===
    last_sync_date = fields.Datetime(
        string='最後同步時間',
        readonly=True)

    # === 同步方法 ===
    def action_sync_all(self):
        """一鍵同步：工項數量、累計進度%、缺失統計、施工日數"""
        self.ensure_one()
        if not self.period_start or not self.period_end:
            raise UserError('請先設定報告期間起迄日期')

        self._sync_progress_lines()
        self._sync_cumulative_progress()
        self._sync_defect_counts()
        self._sync_work_days()
        self.last_sync_date = fields.Datetime.now()

    def _sync_progress_lines(self):
        """從施工日誌同步工項數量"""
        DailyLogLine = self.env['daily.log.line']
        valid_states = ('filled', 'auto_locked', 'locked')

        for line in self.progress_line_ids:
            if not line.task_id:
                continue

            # 本次完成數量：報告期間內已確認日誌的 daily_qty 加總
            period_qty = sum(DailyLogLine.search([
                ('work_item_id', '=', line.task_id.id),
                ('date', '>=', self.period_start),
                ('date', '<=', self.period_end),
                ('sheet_state', 'in', valid_states),
            ]).mapped('daily_qty'))

            # 累計完成數量：工程開始至 period_end 所有已確認日誌的 daily_qty 加總
            actual_qty = sum(DailyLogLine.search([
                ('work_item_id', '=', line.task_id.id),
                ('date', '<=', self.period_end),
                ('sheet_state', 'in', valid_states),
            ]).mapped('daily_qty'))

            line.write({
                'period_qty': period_qty,
                'actual_qty': actual_qty,
            })

    def _sync_cumulative_progress(self):
        """從啟用中進度表取得 period_end 所在區間的累計進度"""
        if not self.project_id or not self.period_end:
            return

        schedule = self.env['progress.schedule'].search([
            ('project_id', '=', self.project_id.id),
            ('is_latest_version', '=', True),
            ('state', '=', 'active'),
        ], limit=1)

        if not schedule:
            return

        schedule_line = schedule.line_ids.filtered(
            lambda l: l.date_start <= self.period_end and self.period_end <= l.date_end
        )
        if schedule_line:
            self.write({
                'planned_progress': schedule_line[0].cumulative_planned,
                'actual_progress': schedule_line[0].cumulative_actual,
            })

    def _sync_work_days(self):
        """從施工日誌統計本期工作日與雨天數"""
        if not self.project_id or not self.period_start or not self.period_end:
            return

        valid_states = ('filled', 'auto_locked', 'locked')
        sheets = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('log_date', '>=', self.period_start),
            ('log_date', '<=', self.period_end),
            ('state', 'in', valid_states),
        ])

        rain_weather = ('rainy', 'heavy_rain', 'typhoon')
        rain_days = len(sheets.filtered(
            lambda s: s.weather_am in rain_weather or s.weather_pm in rain_weather
        ))

        self.write({
            'work_days': len(sheets),
            'rain_days': rain_days,
        })

    def _sync_defect_counts(self):
        """從缺失紀錄統計報告期間內的缺失與改善數"""
        if not self.project_id or not self.period_start or not self.period_end:
            return

        Defect = self.env['general.defect.improvement']

        # 本期發現的缺失
        defect_count = Defect.search_count([
            ('project_id', '=', self.project_id.id),
            ('found_date', '>=', self.period_start),
            ('found_date', '<=', self.period_end),
        ])

        # 本期改善完成的缺失。improvement_date 是 Date（不是 Datetime），
        # 可直接用 domain 比對，不必 filtered + .date()。
        improved_count = Defect.search_count([
            ('project_id', '=', self.project_id.id),
            ('improvement_date', '>=', self.period_start),
            ('improvement_date', '<=', self.period_end),
        ])

        self.write({
            'defect_count': defect_count,
            'defect_improved_count': improved_count,
        })

    # === 工項載入方法 ===
    def action_load_task_progress(self):
        """載入工項進度"""
        self.ensure_one()
        if self.progress_line_ids:
            raise UserError('已有進度明細，如需重新載入請先清除')

        if not self.project_id:
            raise UserError('工程未關聯專案')

        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.id),
        ])

        lines = []
        for task in tasks:
            lines.append(Command.create({
                'task_id': task.id,
                'planned_qty': task.planned_qty,
            }))

        if lines:
            self.progress_line_ids = lines

        # 載入後若已設定期間，自動同步一次
        if self.period_start and self.period_end:
            self.action_sync_all()

        return True

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('general.progress.report') or '/'
        return super().create(vals_list)

    # === 約束 ===
    @api.constrains('period_start', 'period_end')
    def _check_period_dates(self):
        for record in self:
            if record.period_start and record.period_end:
                if record.period_end < record.period_start:
                    raise ValidationError('報告期間迄日不得早於起日')

    # === Onchange ===
    @api.onchange('report_type', 'report_date')
    def _onchange_report_period(self):
        """根據報告類型自動設定期間"""
        if self.report_date and self.report_type:
            if self.report_type == 'daily':
                self.period_start = self.report_date
                self.period_end = self.report_date
            elif self.report_type == 'weekly':
                self.period_end = self.report_date
                self.period_start = self.report_date - timedelta(days=6)
            elif self.report_type == 'biweekly':
                self.period_end = self.report_date
                self.period_start = self.report_date - timedelta(days=13)
            elif self.report_type == 'monthly':
                self.period_start = self.report_date.replace(day=1)
                self.period_end = self.report_date


class GeneralProgressReportLine(models.Model):
    """
    一般式進度報告明細

    設計說明：
    - 記錄各工項的進度詳情
    - 數量由 action_sync_all 自動從施工日誌帶入
    """
    _name = 'general.progress.report.line'
    _description = '一般式進度報告明細'
    _order = 'sequence, id'

    # === 關聯 ===
    report_id = fields.Many2one(
        'general.progress.report',
        string='進度報告',
        required=True,
        ondelete='cascade')

    # === 工項資訊 ===
    task_id = fields.Many2one(
        'project.task',
        string='工項',
        required=True)

    sequence = fields.Integer(
        string='序號',
        default=10)

    item_no = fields.Char(
        string='工項編號',
        related='task_id.item_no',
        store=True)

    item_name = fields.Char(
        string='工項名稱',
        related='task_id.name',
        store=True)

    unit = fields.Char(
        string='單位',
        related='task_id.unit',
        store=True)

    # === 數量資訊 ===
    planned_qty = fields.Float(
        string='契約數量',
        digits=(16, 4))

    period_qty = fields.Float(
        string='本次完成數量',
        digits=(16, 4),
        help='本報告期間內完成的數量（由同步功能自動帶入）')

    actual_qty = fields.Float(
        string='累計完成數量',
        digits=(16, 4),
        help='工程開始至報告期間迄的累計完成數量（由同步功能自動帶入）')

    remaining_qty = fields.Float(
        string='剩餘數量',
        compute='_compute_remaining_completion',
        store=True,
        digits=(16, 4))

    completion_rate = fields.Float(
        string='完成率 (%)',
        compute='_compute_remaining_completion',
        store=True,
        digits=(5, 2))

    @api.depends('planned_qty', 'actual_qty')
    def _compute_remaining_completion(self):
        for line in self:
            line.remaining_qty = line.planned_qty - line.actual_qty
            if line.planned_qty:
                line.completion_rate = (line.actual_qty / line.planned_qty) * 100
            else:
                line.completion_rate = 0.0

    # === 備註 ===
    note = fields.Text(string='備註')
