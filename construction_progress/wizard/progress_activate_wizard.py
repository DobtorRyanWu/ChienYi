# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProgressActivateWizard(models.TransientModel):
    """進度表啟用精靈 - 啟用並批量建立施工日誌"""
    _name = 'progress.activate.wizard'
    _description = '進度表啟用精靈'

    schedule_id = fields.Many2one(
        'progress.schedule',
        string='進度表',
        required=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        related='schedule_id.project_id',
        string='工程案件',
        readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='填表人',
        required=True,
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid),
             ('company_id', '=', self.env.company.id)],
            limit=1),
        help='日誌的填表人（員工）',
    )

    start_date = fields.Date(
        related='schedule_id.start_date',
        string='開工日期',
        readonly=True,
    )
    end_date = fields.Date(
        related='schedule_id.adjusted_end_date',
        string='完工日期',
        readonly=True,
    )

    # === 日誌統計 ===
    existing_log_count = fields.Integer(
        string='已存在日誌數',
        compute='_compute_log_counts',
    )
    new_log_count_preview = fields.Integer(
        string='預計新建日誌數',
        compute='_compute_log_counts',
    )

    @api.depends('start_date', 'end_date', 'employee_id')
    def _compute_log_counts(self):
        for wiz in self:
            if not wiz.start_date or not wiz.end_date:
                wiz.existing_log_count = 0
                wiz.new_log_count_preview = 0
                continue

            sup_project = wiz.schedule_id.project_id
            start = wiz.start_date
            end = wiz.end_date

            # 註：不再以「今天」夾住非首版的起日——「跳過已存在日誌」(下方 existing_dates)
            #     已足以保護既有/鎖定的歷史日誌；用今天夾住反而會漏建「完工日已過但
            #     尚未建立」的延伸期日誌（例如以過去時間軸補登時）。一律用進度表起日。
            # 查詢範圍內已存在的日誌
            existing_dates = set()
            if sup_project and wiz.employee_id:
                existing_dates = set(
                    self.env['daily.log.sheet'].search([
                        ('supervision_project_id', '=', sup_project.id),
                        ('employee_id', '=', wiz.employee_id.id),
                        ('company_id', '=', self.env.company.id),
                        ('log_date', '>=', start),
                        ('log_date', '<=', end),
                    ]).mapped('log_date')
                )
            wiz.existing_log_count = len(existing_dates)

            # 計算新建數量（日期範圍內每天都建立）
            total_days = (end - start).days + 1
            wiz.new_log_count_preview = total_days - len(existing_dates)

    def action_confirm(self):
        """確認啟用並建立日誌"""
        self.ensure_one()

        if not self.employee_id:
            raise UserError('請選擇填表人')

        schedule = self.schedule_id

        # 1. 啟用進度表
        schedule._do_activate()

        # 2. 批量建立日誌
        created_count = self._create_daily_logs()

        # 3. 批量建立施工排程
        schedule_count = self._create_weekly_schedules()

        # 4. 自動產生估驗計價單（若模組已安裝且有設定週期）
        estimate_count = 0
        if hasattr(self, 'generate_estimates') and self.generate_estimates:
            estimate_count = self._create_estimates()

        _logger.info(
            '啟用進度表完成：工程=%s, 日誌=%d, 週排程=%d, 估驗=%d',
            schedule.project_id.code, created_count, schedule_count, estimate_count
        )

        # 返回進度表表單
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': schedule.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context),
        }

    def _create_daily_logs(self):
        """批量建立施工日誌（非首版時僅處理啟用日之後的日期）"""
        schedule = self.schedule_id
        sup_project = schedule.project_id
        start = self.start_date
        end = self.end_date

        if not start or not end:
            return 0

        # 註：非首版不再以「今天」夾住起日。下方「跳過已存在日誌」(existing_dates) 已
        #     保護既有/鎖定的歷史日誌不被重建；用今天夾住會漏建延伸期（完工日已過但
        #     尚未建立）的日誌。一律以進度表起日為範圍、靠 skip-existing 保護歷史。
        if start > end:
            return 0

        # 查詢範圍內已存在的日誌
        existing_logs = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', sup_project.id),
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.env.company.id),
            ('log_date', '>=', start),
            ('log_date', '<=', end),
        ])
        existing_dates = set(existing_logs.mapped('log_date'))

        # 準備待建立的日期（每天都建立）
        dates_to_create = []
        current = start
        while current <= end:
            if current not in existing_dates:
                dates_to_create.append(current)
            current += timedelta(days=1)

        # 批量建立新日誌
        created_count = 0
        if dates_to_create:
            DailyLog = self.env['daily.log.sheet'].with_context(
                tracking_disable=True,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
            )
            vals_list = [{
                'supervision_project_id': sup_project.id,
                'employee_id': self.employee_id.id,
                'company_id': self.env.company.id,
                'log_date': date,
            } for date in dates_to_create]
            DailyLog.create(vals_list)
            created_count = len(dates_to_create)

        _logger.info(
            '批量建立 %d 筆施工日誌：工程=%s, 期間=%s ~ %s',
            created_count, sup_project.code, start, end
        )

        return created_count

    def _create_weekly_schedules(self):
        """批量建立施工排程"""
        schedule = self.schedule_id
        sup_project = schedule.project_id
        start = self.start_date
        end = self.end_date

        if not start or not end:
            return 0

        # 對齊到周一（start 所在那周的周一）
        week_start = start - timedelta(days=start.weekday())

        # 查詢已存在的排程（避免重複）
        existing_starts = set(
            self.env['construction.weekly.schedule'].search([
                ('supervision_project_id', '=', sup_project.id),
            ]).mapped('week_start')
        )

        # 準備待建立的排程
        vals_list = []
        while week_start <= end:
            if week_start not in existing_starts:
                vals_list.append({
                    'supervision_project_id': sup_project.id,
                    'week_start': week_start,
                    'week_mode': 'project',
                    'state': 'draft',
                })
            week_start += timedelta(days=7)

        if not vals_list:
            return 0

        # 批量建立，停用追蹤以提升效能
        WeeklySchedule = self.env['construction.weekly.schedule'].with_context(
            tracking_disable=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
        )

        schedules = WeeklySchedule.create(vals_list)

        _logger.info(
            '批量建立 %d 筆施工排程：工程=%s, 期間=%s ~ %s',
            len(schedules), sup_project.code, start, end
        )

        return len(schedules)
