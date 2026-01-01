# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError


class ProgressSchedule(models.Model):
    """
    進度表

    對應舊系統：進度表 (最新頁面/列表頁面)
    業務說明：
    - 每個專案可有多版進度表，最新一版為使用中
    - 支援每周、每兩周、自訂三種計算模式
    - 實際進度從施工日誌自動帶入
    """
    _name = 'progress.schedule'
    _description = '進度表'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'version desc'

    # === 基本資訊 ===
    name = fields.Char(
        string='名稱',
        compute='_compute_name',
        store=True,
    )
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    version = fields.Integer(
        string='版本',
        default=1,
        required=True,
        tracking=True,
    )
    change_date = fields.Date(
        string='變更時間',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    change_reason = fields.Text(
        string='變更原因',
        help='記錄本版本進度表變更的原因',
    )

    # === 多公司架構 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True,
    )

    # === 工期資訊 (從專案帶入) ===
    start_date = fields.Date(
        string='開工日期',
        related='project_id.contract_start_date',
        store=True,
        readonly=True,
    )
    original_end_date = fields.Date(
        string='原定完工日期',
        related='project_id.contract_end_date',
        readonly=True,
    )
    duration_extension = fields.Integer(
        string='累計工期展延(日)',
        default=0,
        tracking=True,
        help='因契約變更、天候等因素累計展延天數',
    )
    adjusted_end_date = fields.Date(
        string='調整後完工日期',
        compute='_compute_adjusted_end_date',
        store=True,
    )
    approved_duration = fields.Integer(
        string='核定工期',
        related='project_id.contract_duration',
        readonly=True,
    )
    total_duration = fields.Integer(
        string='總工期(含展延)',
        compute='_compute_total_duration',
        store=True,
    )

    @api.depends('original_end_date', 'duration_extension')
    def _compute_adjusted_end_date(self):
        """計算調整後完工日期"""
        for rec in self:
            if rec.original_end_date:
                rec.adjusted_end_date = rec.original_end_date + timedelta(
                    days=rec.duration_extension)
            else:
                rec.adjusted_end_date = False

    @api.depends('approved_duration', 'duration_extension')
    def _compute_total_duration(self):
        """計算總工期（含展延）"""
        for rec in self:
            rec.total_duration = (rec.approved_duration or 0) + rec.duration_extension

    # === 計算模式 ===
    calculation_mode = fields.Selection([
        ('weekly', '每周'),
        ('biweekly', '每兩周'),
        ('custom', '自訂'),
    ], string='計算模式', default='weekly', required=True, tracking=True)

    # === 進度明細 ===
    line_ids = fields.One2many(
        'progress.schedule.line',
        'schedule_id',
        string='進度明細',
        copy=True,
    )
    line_count = fields.Integer(
        string='明細筆數',
        compute='_compute_line_count',
    )

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    # === 進度統計 ===
    current_cumulative_planned = fields.Float(
        string='目前累計預定進度 (%)',
        compute='_compute_current_progress',
        store=True,
        digits=(5, 2),
    )
    current_cumulative_actual = fields.Float(
        string='目前累計實際進度 (%)',
        compute='_compute_current_progress',
        store=True,
        digits=(5, 2),
    )
    current_variance = fields.Float(
        string='目前進度差異 (%)',
        compute='_compute_current_progress',
        store=True,
        digits=(5, 2),
    )
    current_variance_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
    ], string='目前進度狀態', compute='_compute_current_progress', store=True)

    @api.depends('line_ids.cumulative_planned', 'line_ids.cumulative_actual',
                 'line_ids.date_end')
    def _compute_current_progress(self):
        """計算目前進度（取最接近今日且已過的區間）"""
        today = fields.Date.today()
        for rec in self:
            # 找到最接近今日且已過的區間
            applicable_lines = rec.line_ids.filtered(
                lambda l: l.date_end and l.date_end <= today
            ).sorted(key=lambda l: l.date_end, reverse=True)

            if applicable_lines:
                current_line = applicable_lines[0]
                rec.current_cumulative_planned = current_line.cumulative_planned
                rec.current_cumulative_actual = current_line.cumulative_actual
                rec.current_variance = current_line.variance
                rec.current_variance_status = current_line.variance_status
            else:
                rec.current_cumulative_planned = 0.0
                rec.current_cumulative_actual = 0.0
                rec.current_variance = 0.0
                rec.current_variance_status = 'on_track'

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '使用中'),
        ('archived', '已歸檔'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 備註 ===
    notes = fields.Html(string='備註說明')

    # === 名稱計算 ===
    @api.depends('project_id', 'version')
    def _compute_name(self):
        for rec in self:
            if rec.project_id:
                rec.name = f'{rec.project_id.name} - 進度表 v{rec.version}'
            else:
                rec.name = f'進度表 v{rec.version}'

    # === SQL 約束 ===
    _sql_constraints = [
        ('version_positive', 'CHECK(version > 0)', '版本號必須為正數'),
        ('duration_extension_non_negative', 'CHECK(duration_extension >= 0)',
         '累計工期展延不可為負數'),
        ('unique_project_version', 'UNIQUE(project_id, version)',
         '同一工程的進度表版本號不可重複'),
    ]

    # =========================================================================
    # 動作方法
    # =========================================================================

    def action_generate_lines(self):
        """根據計算模式自動產生進度區間"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以產生進度區間')
        if not self.start_date or not self.adjusted_end_date:
            raise ValidationError('請先確認工程已設定開工日期與完工日期')

        # 清除現有明細
        self.line_ids.unlink()

        # 自訂模式不自動產生
        if self.calculation_mode == 'custom':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '自訂模式',
                    'message': '自訂模式請手動新增進度區間',
                    'type': 'info',
                    'sticky': False,
                }
            }

        # 決定間隔天數
        if self.calculation_mode == 'weekly':
            interval = 7
        else:  # biweekly
            interval = 14

        lines = []
        current_date = self.start_date
        sequence = 1

        while current_date < self.adjusted_end_date:
            end_date = min(
                current_date + timedelta(days=interval - 1),
                self.adjusted_end_date
            )
            lines.append({
                'schedule_id': self.id,
                'sequence': sequence,
                'date_start': current_date,
                'date_end': end_date,
                'planned_progress': 0.0,
            })
            current_date = end_date + timedelta(days=1)
            sequence += 1

        if lines:
            self.env['progress.schedule.line'].create(lines)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '產生完成',
                'message': f'已產生 {len(lines)} 個進度區間',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_add_line(self):
        """新增一筆自訂時間區間（自訂模式使用）"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以新增進度區間')

        max_seq = max(self.line_ids.mapped('sequence') or [0])

        # 決定預設日期
        if self.line_ids:
            last_line = self.line_ids.sorted('sequence', reverse=True)[0]
            default_start = last_line.date_end + timedelta(days=1) if last_line.date_end else self.start_date
        else:
            default_start = self.start_date

        default_end = default_start + timedelta(days=6) if default_start else False

        self.env['progress.schedule.line'].create({
            'schedule_id': self.id,
            'sequence': max_seq + 1,
            'date_start': default_start,
            'date_end': default_end,
        })

        return True

    def action_activate(self):
        """設為使用中（其他版本自動歸檔）"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以啟用')
        if not self.line_ids:
            raise ValidationError('進度表必須至少有一筆進度明細')

        # 驗證進度合理性
        total_planned = sum(self.line_ids.mapped('planned_progress'))
        if total_planned <= 0:
            raise ValidationError('請至少填寫一筆預定進度')
        if total_planned > 100:
            raise ValidationError(f'預定進度總和 ({total_planned:.2f}%) 不可超過 100%')

        # 將同專案其他進度表歸檔
        other_schedules = self.search([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
            ('state', '=', 'active'),
        ])
        if other_schedules:
            other_schedules.write({'state': 'archived'})

        self.write({'state': 'active'})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '已啟用',
                'message': '進度表已設為使用中',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_archive(self):
        """歸檔"""
        for rec in self:
            if rec.state == 'archived':
                raise UserError('此進度表已經歸檔')
            rec.write({'state': 'archived'})
        return True

    def action_reset_draft(self):
        """重設為草稿"""
        for rec in self:
            if rec.state not in ('active', 'archived'):
                raise UserError('只有使用中或已歸檔狀態可以重設為草稿')
            rec.write({'state': 'draft'})
        return True

    def action_create_new_version(self):
        """建立新版本"""
        self.ensure_one()

        # 取得同專案最大版本號
        max_version = max(self.search([
            ('project_id', '=', self.project_id.id)
        ]).mapped('version') or [0])

        # 複製進度表
        new_schedule = self.copy({
            'version': max_version + 1,
            'change_date': fields.Date.today(),
            'state': 'draft',
            'change_reason': False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': new_schedule.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_sync_all_lines_from_daily_log(self):
        """同步所有明細的實際進度（從施工日誌）"""
        self.ensure_one()
        synced_count = 0
        for line in self.line_ids:
            if line.action_sync_from_daily_log():
                synced_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '同步完成',
                'message': f'已從施工日誌同步 {synced_count} 筆進度資料',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_lines(self):
        """查看進度明細"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 進度明細',
            'res_model': 'progress.schedule.line',
            'view_mode': 'list,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {
                'default_schedule_id': self.id,
            },
        }

    # =========================================================================
    # CRUD 覆寫
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """建立進度表時自動計算版本號"""
        for vals in vals_list:
            if 'version' not in vals or vals.get('version', 0) <= 0:
                project_id = vals.get('project_id')
                if project_id:
                    existing_schedules = self.search([
                        ('project_id', '=', project_id)
                    ])
                    vals['version'] = len(existing_schedules) + 1
                else:
                    vals['version'] = 1
        return super().create(vals_list)

    def unlink(self):
        """只允許刪除草稿狀態的進度表"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態的進度表可以刪除')
        return super().unlink()

    def copy(self, default=None):
        """複製時重設狀態"""
        default = dict(default or {})
        if 'state' not in default:
            default['state'] = 'draft'
        if 'change_date' not in default:
            default['change_date'] = fields.Date.today()
        return super().copy(default)
