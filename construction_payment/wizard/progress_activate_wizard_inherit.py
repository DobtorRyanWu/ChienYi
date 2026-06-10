# -*- coding: utf-8 -*-

import logging
from datetime import timedelta
from calendar import monthrange

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProgressActivateWizardPayment(models.TransientModel):
    """擴展進度表啟用精靈，加入自動產生估驗計價單功能"""
    _inherit = 'progress.activate.wizard'

    # === 估驗計價設定 ===
    generate_estimates = fields.Boolean(
        string='同步產生估驗計價單',
        default=True,
        help='依據工程案件的估驗週期，自動產生估驗計價單',
    )
    valuation_cycle = fields.Selection(
        related='project_id.valuation_cycle',
        string='估驗週期',
        readonly=True,
    )
    valuation_cycle_days = fields.Integer(
        related='project_id.valuation_cycle_days',
        readonly=True,
    )
    estimate_count_preview = fields.Integer(
        string='預計產生估驗單數',
        compute='_compute_estimate_count_preview',
    )

    @api.depends('start_date', 'end_date', 'valuation_cycle',
                 'valuation_cycle_days', 'generate_estimates')
    def _compute_estimate_count_preview(self):
        for wiz in self:
            if (not wiz.generate_estimates or not wiz.valuation_cycle
                    or not wiz.start_date or not wiz.end_date):
                wiz.estimate_count_preview = 0
                continue
            periods = wiz._calculate_estimate_periods()
            # 扣除已存在的
            existing_dates = set(
                self.env['payment.estimate'].search([
                    ('project_id', '=', wiz.project_id.id),
                ]).mapped('estimate_date')
            )
            wiz.estimate_count_preview = len(
                [d for d in periods if d not in existing_dates]
            )

    def _calculate_estimate_periods(self):
        """計算估驗日期清單（各期截止日）"""
        start = self.start_date
        end = self.end_date
        cycle = self.valuation_cycle

        if not start or not end or not cycle:
            return []

        periods = []
        if cycle == 'monthly':
            # 自然月：每月最後一天
            current = start
            while current <= end:
                year, month = current.year, current.month
                last_day = monthrange(year, month)[1]
                month_end = current.replace(day=last_day)
                period_end = min(month_end, end)
                periods.append(period_end)
                # 移到下個月第一天
                if month == 12:
                    current = current.replace(year=year + 1, month=1, day=1)
                else:
                    current = current.replace(month=month + 1, day=1)
        elif cycle == 'biweekly':
            current = start
            while current <= end:
                period_end = min(current + timedelta(days=13), end)
                periods.append(period_end)
                current = period_end + timedelta(days=1)
        elif cycle == 'custom':
            days = self.valuation_cycle_days or 30
            current = start
            while current <= end:
                period_end = min(current + timedelta(days=days - 1), end)
                periods.append(period_end)
                current = period_end + timedelta(days=1)

        return periods

    def _create_estimates(self):
        """批次建立估驗計價單（含空白明細行）"""
        project = self.schedule_id.project_id
        if not project.valuation_cycle:
            return 0

        periods = self._calculate_estimate_periods()
        if not periods:
            return 0

        # 查詢已存在的估驗計價單（避免重複）
        existing_dates = set(
            self.env['payment.estimate'].search([
                ('project_id', '=', project.id),
            ]).mapped('estimate_date')
        )

        # 取得所有工項（含彙總項，彙總列以「一式」呈現）
        tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', project.id),
            ('active', '=', True),
        ], order='sequence, id')

        created_count = 0
        PaymentEstimate = self.env['payment.estimate'].with_context(
            tracking_disable=True,
            mail_create_nolog=True,
        )
        PaymentEstimateLine = self.env['payment.estimate.line'].with_context(
            tracking_disable=True,
        )

        for est_date in periods:
            if est_date in existing_dates:
                continue

            # 建立估驗計價單（estimate_no 和 name 由 create 自動計算）
            estimate = PaymentEstimate.create({
                'project_id': project.id,
                'estimate_date': est_date,
            })

            # 建立明細行（葉節點 estimate_qty=0、彙總列「一式」qty=1）
            if tasks:
                line_vals = []
                for idx, task in enumerate(tasks, 1):
                    vals = PaymentEstimateLine._prepare_line_vals(task, idx * 10)
                    vals['estimate_id'] = estimate.id
                    line_vals.append(vals)
                PaymentEstimateLine.create(line_vals)

            created_count += 1

        _logger.info(
            '批量建立 %d 筆估驗計價單：工程=%s',
            created_count, project.code
        )

        return created_count
