# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import date, datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SupervisionProjectProgress(models.Model):
    """
    擴展工程案件主檔 - 新增進度表相關欄位

    業務說明：
    - 在專案上顯示關聯的進度表
    - 提供快速存取使用中進度表的功能
    - 顯示目前進度狀態摘要
    """
    _inherit = 'project.project'

    # === 進度表關聯 ===
    schedule_ids = fields.One2many(
        'progress.schedule',
        'project_id',
        string='進度表',
    )
    schedule_count = fields.Integer(
        string='進度表數量',
        compute='_compute_schedule_count',
    )
    active_schedule_id = fields.Many2one(
        'progress.schedule',
        string='使用中進度表',
        compute='_compute_active_schedule',
        store=True,
    )

    # === 本日進度資訊（從今日日誌取得）===
    daily_planned_progress = fields.Float(
        string='本日預定進度(%)',
        compute='_compute_daily_progress',
        digits=(5, 2),
        help='今日在當前區間內應該完成的進度（當日份額，不含累計）',
    )
    daily_actual_progress = fields.Float(
        string='本日實際進度(%)',
        compute='_compute_daily_progress',
        digits=(5, 2),
        help='今日施工完成的進度增量',
    )

    @api.depends('active_schedule_id', 'active_schedule_id.line_ids')
    def _compute_daily_progress(self):
        """計算本日進度（從施工日誌取得）"""
        today = fields.Date.today()
        DailyLogSheet = self.env['daily.log.sheet']
        
        for project in self:
            if not project.active_schedule_id:
                project.daily_planned_progress = 0.0
                project.daily_actual_progress = 0.0
                continue
            
            # 找到今日所在的進度區間
            current_line = project.active_schedule_id.line_ids.filtered(
                lambda l: l.date_start and l.date_end and 
                         l.date_start <= today <= l.date_end
            )
            
            if current_line:
                line = current_line[0]
                
                # 計算本日預定進度（當日份額）
                total_days = (line.date_end - line.date_start).days + 1
                daily_rate = line.planned_progress / total_days
                project.daily_planned_progress = daily_rate
                
                # 查找今日的施工日誌（daily.log.sheet 無 'done' 狀態，
                # 權威狀態為 draft/filled/auto_locked/locked；
                # 取「已填寫以上」才計入本日實際進度，草稿不計）
                today_log = DailyLogSheet.search([
                    ('supervision_project_id', '=', project.id),
                    ('log_date', '=', today),
                    ('state', 'in', ['filled', 'auto_locked', 'locked']),
                ], limit=1)
                
                if today_log:
                    project.daily_actual_progress = today_log.daily_actual_progress
                else:
                    project.daily_actual_progress = 0.0
            else:
                project.daily_planned_progress = 0.0
                project.daily_actual_progress = 0.0

    # === 進度摘要 (從使用中進度表帶入) ===
    schedule_cumulative_planned = fields.Float(
        string='進度表累計預定進度 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )
    schedule_cumulative_actual = fields.Float(
        string='進度表累計實際進度 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )
    schedule_variance = fields.Float(
        string='進度差異 (%)',
        compute='_compute_schedule_progress',
        digits=(5, 2),
    )

    # === 進度圖表 (用於 widget) ===
    progress_chart = fields.Char(
        string='進度圖表',
        compute='_compute_progress_chart',
        help='進度圖表占位符欄位',
    )

    @api.depends('schedule_ids')
    def _compute_schedule_count(self):
        for project in self:
            project.schedule_count = len(project.schedule_ids)

    @api.depends('schedule_ids.state')
    def _compute_active_schedule(self):
        for project in self:
            active = project.schedule_ids.filtered(lambda s: s.state == 'active')
            project.active_schedule_id = active[0] if active else False

    @api.depends('active_schedule_id', 'active_schedule_id.current_cumulative_planned',
                 'active_schedule_id.current_cumulative_actual',
                 'active_schedule_id.current_variance')
    def _compute_schedule_progress(self):
        for project in self:
            if project.active_schedule_id:
                project.schedule_cumulative_planned = project.active_schedule_id.current_cumulative_planned
                project.schedule_cumulative_actual = project.active_schedule_id.current_cumulative_actual
                project.schedule_variance = project.active_schedule_id.current_variance
            else:
                project.schedule_cumulative_planned = 0.0
                project.schedule_cumulative_actual = 0.0
                project.schedule_variance = 0.0

    @api.depends('active_schedule_id')
    def _compute_progress_chart(self):
        """進度圖表占位符"""
        for project in self:
            project.progress_chart = 'chart'

    # =========================================================================
    # 動作方法
    # =========================================================================

    def action_view_schedules(self):
        """查看進度表"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 進度表',
            'res_model': 'progress.schedule',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
            },
        }

    def action_view_active_schedule(self):
        """查看使用中進度表"""
        self.ensure_one()
        if not self.active_schedule_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '提示',
                    'message': '此工程尚未建立使用中的進度表',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'progress.schedule',
            'res_id': self.active_schedule_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_schedule(self):
        """建立新進度表"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '建立進度表',
            'res_model': 'progress.schedule',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
            },
            'target': 'current',
        }

    def _interpolate_progress(self, target_date, lines, period_start):
        """
        線性內插法計算指定日期的進度

        Args:
            target_date: 目標日期
            lines: 排序後的進度明細（已按 date_end 排序）
            period_start: 版本期間開始日期

        Returns:
            (planned_progress, actual_progress) 元組
        """
        from datetime import timedelta

        # 找到目標日期所在的區間
        prev_cumulative_planned = 0.0
        prev_cumulative_actual = 0.0
        current_line = None

        for line in lines:
            if line.date_start and line.date_end:
                # 如果目標日期在這個區間內
                if line.date_start <= target_date <= line.date_end:
                    current_line = line
                    break
                # 如果目標日期在這個區間之後，記錄前一個區間的累計值
                elif target_date > line.date_end:
                    prev_cumulative_planned = line.cumulative_planned
                    prev_cumulative_actual = line.cumulative_actual

        # 如果沒找到區間（目標日期在最後一個區間之後或第一個區間之前）
        if not current_line:
            # 目標日期在第一個區間之前
            if target_date < lines[0].date_start if lines and lines[0].date_start else False:
                return (0.0, 0.0)
            # 目標日期在最後一個區間之後
            return (prev_cumulative_planned, prev_cumulative_actual)

        # 線性內插計算
        date_range = (current_line.date_end - current_line.date_start).days
        if date_range == 0:
            # 單日區間，直接返回累計值
            return (current_line.cumulative_planned, current_line.cumulative_actual)

        # 計算目標日期在區間中的比例
        days_elapsed = (target_date - current_line.date_start).days
        ratio = days_elapsed / date_range

        # 內插計算
        planned = prev_cumulative_planned + (current_line.cumulative_planned - prev_cumulative_planned) * ratio
        actual = prev_cumulative_actual + (current_line.cumulative_actual - prev_cumulative_actual) * ratio

        return (planned, actual)

    def get_progress_chart_data(self):
        """
        獲取跨版本進度圖表數據（使用線性內插法）

        返回格式：{
            'dates': ['2024-01-01', '2024-01-08', ...],
            'planned': [10, 20, 30, ...],
            'actual': [8, 18, 28, ...],
            'today': '2024-01-15',
            'version_changes': [...]
        }

        核心邏輯：
        - 使用線性內插法計算區間內每一天的進度
        - v1: 開工日 → v2啟用日當天
        - v2: v2啟用日 → v3啟用日當天
        - 在版本更迭的那一天，會同時存在兩個點（v1 內插值 + v2 內插值）
        """
        from datetime import timedelta

        self.ensure_one()

        if not self.schedule_ids:
            return {
                'dates': [],
                'planned': [],
                'actual': [],
                'today': fields.Date.today().isoformat(),
                'version_changes': [],
            }

        all_schedules = self.schedule_ids.sorted('version')

        # === 步驟 1：確定每個版本的有效期間 ===
        # 使用 effective_change_date（有校正時 = correction_date，否則 = change_date）
        # 確保計畫基準校正的轉折點反映在圖表上
        version_periods = []
        for idx, schedule in enumerate(all_schedules):
            if not schedule.line_ids:
                continue

            # 開始日期
            if idx == 0:
                start_date = schedule.start_date
            else:
                start_date = schedule.effective_change_date or schedule.change_date

            # 結束日期
            if idx < len(all_schedules) - 1:
                next_schedule = all_schedules[idx + 1]
                next_boundary = next_schedule.effective_change_date or next_schedule.change_date
                end_date = next_boundary if next_boundary else schedule.adjusted_end_date
            else:
                end_date = schedule.adjusted_end_date

            version_periods.append({
                'schedule': schedule,
                'start_date': start_date,
                'end_date': end_date,
                'version': schedule.version,
            })

        # === 步驟 2：使用線性內插法生成每一天的數據點 ===
        data_points = []
        version_changes = []

        for period in version_periods:
            schedule = period['schedule']
            start_date = period['start_date']
            end_date = period['end_date']
            version = period['version']

            if not start_date or not end_date:
                continue

            # 記錄版本變更點（使用 effective_change_date，有校正時指向 correction_date）
            if version > 1:
                boundary = schedule.effective_change_date or schedule.change_date
                version_changes.append({
                    'date': boundary.isoformat() if boundary else None,
                    'version': version,
                    'reason': schedule.change_reason or f'進度表版本 v{version}',
                    'change_orders': [co.name for co in schedule.related_change_order_ids] if schedule.related_change_order_ids else [],
                })

            # 排序明細行
            sorted_lines = schedule.line_ids.sorted('date_end')

            # 只收集版本層級的關鍵日期（移除區間起訖日，減少圓點擁擠）
            key_dates = set()
            key_dates.add(start_date)  # 版本開始日
            key_dates.add(end_date)    # 版本結束日

            # 今日（如果在範圍內）
            today = fields.Date.today()
            if start_date <= today <= end_date:
                key_dates.add(today)

            # 生成該版本有效期間內的每一天數據（使用內插法）
            current_date = start_date
            while current_date <= end_date:
                planned, actual = self._interpolate_progress(current_date, sorted_lines, start_date)

                # 判斷是否為關鍵點
                is_key_point = current_date in key_dates

                data_points.append({
                    'date': current_date,
                    'planned': planned,
                    'actual': actual,
                    'version': version,
                    'is_key': is_key_point,
                })
                current_date += timedelta(days=1)

        # === 步驟 3：排序並提取最終數據 ===
        data_points.sort(key=lambda x: (x['date'], x['version']))

        # 直接使用 ISO 日期格式（供 Chart.js 時間軸使用）
        dates = [point['date'].isoformat() for point in data_points]
        planned = [round(point['planned'], 2) for point in data_points]
        actual = [round(point['actual'], 2) for point in data_points]
        point_types = ['key' if point['is_key'] else 'normal' for point in data_points]

        return {
            'dates': dates,
            'planned': planned,
            'actual': actual,
            'point_types': point_types,
            'today': fields.Date.today().isoformat(),
            'version_changes': version_changes,
        }

    # =========================================================================
    # 儀表板 API
    # =========================================================================

    def get_project_dashboard_data(self):
        """取得單一案件的儀表板統合資料（各區塊獨立錯誤隔離）"""
        self.ensure_one()
        result = {}
        for key, method in [
            ('basic_info', self._dashboard_basic_info),
            ('duration_info', self._dashboard_duration_info),
            ('progress_summary', self._dashboard_progress_summary),
            ('change_order_summary', self._dashboard_change_order_summary),
            ('defect_summary', self._dashboard_defect_summary),
            ('test_summary', self._dashboard_test_summary),
            ('review_summary', self._dashboard_review_summary),
        ]:
            try:
                result[key] = method()
            except Exception as e:
                _logger.warning(
                    "Dashboard %s error for project %s: %s", key, self.id, e)
                result[key] = None
        return result

    def _dashboard_basic_info(self):
        """基本資訊"""
        type_labels = dict(self._fields['project_type'].selection)
        return {
            'project_type': self.project_type,
            'project_type_label': type_labels.get(self.project_type, ''),
            'code': self.code or '-',
            'contract_amount': self.contract_amount,
        }

    def _dashboard_progress_summary(self):
        """進度摘要（從使用中進度表）"""
        schedule = self.active_schedule_id
        if not schedule:
            return None

        # 強制重算（stored computed 不會因日期改變自動觸發）
        schedule._compute_current_progress()

        status_labels = {
            'ahead': '超前',
            'on_track': '正常',
            'delayed': '落後',
        }
        return {
            'cumulative_planned': schedule.current_cumulative_planned,
            'cumulative_actual': schedule.current_cumulative_actual,
            'variance': schedule.current_variance,
            'variance_status': schedule.current_variance_status,
            'variance_status_label': status_labels.get(
                schedule.current_variance_status, ''),
            'schedule_version': schedule.version,
        }

    def _dashboard_duration_info(self):
        """工期資訊"""
        return {
            'contract_start_date': self.contract_start_date.isoformat() if self.contract_start_date else None,
            'contract_end_date': self.contract_end_date.isoformat() if self.contract_end_date else None,
            'total_approved_duration': self.total_approved_duration,
        }

    def _dashboard_change_order_summary(self):
        """契約變更摘要"""
        if 'contract.change.order' not in self.env:
            return None

        ChangeOrder = self.env['contract.change.order']
        all_orders = ChangeOrder.search([
            ('project_id', '=', self.id),
        ])
        if not all_orders:
            return {
                'total_count': 0,
                'current_sequence': 0,
                'cumulative_change_amount': 0.0,
            }

        # 已套用的變更單
        applied_orders = all_orders.filtered(
            lambda o: o.state == 'applied')
        # 目前使用中的（最新已套用的）
        latest_applied = applied_orders.sorted(
            'sequence', reverse=True)[:1]

        return {
            'total_count': len(all_orders),
            'current_sequence': latest_applied.sequence if latest_applied else 0,
            'cumulative_change_amount': sum(
                applied_orders.mapped('change_amount')),
        }

    def _dashboard_defect_summary(self):
        """缺失改善摘要：缺失總數量、已改善數量、未改善數量"""
        if 'supervision.defect' not in self.env:
            return None

        Defect = self.env['supervision.defect']
        domain = [('project_id', '=', self.id)]

        total_count = Defect.search_count(domain)

        # 已改善（verified + closed）
        improved_count = Defect.search_count(
            domain + [('state', 'in', ('verified', 'closed'))])

        # 未改善（open, investigating, action_taken）
        unimproved_count = Defect.search_count(
            domain + [('state', 'not in', ('verified', 'closed'))])

        return {
            'total_count': total_count,
            'improved_count': improved_count,
            'unimproved_count': unimproved_count,
        }

    def _dashboard_test_summary(self):
        """檢試驗摘要：待檢驗量、未處理預警數、未達標工項數"""
        if 'supervision.test.record' not in self.env:
            return None

        TestRecord = self.env['supervision.test.record']
        domain = [('project_id', '=', self.id)]

        # 待檢驗（尚未檢驗）
        pending_count = TestRecord.search_count(
            domain + [('processing_status', '=', 'not_started')])

        # 未達標工項數（從工項檢試驗統計，合格次數 < 需檢驗合格次數）
        # is_qualified 為 Python computed，需用 search + filtered 計算
        fail_count = 0
        if 'supervision.test.task.statistics' in self.env:
            stats = self.env['supervision.test.task.statistics'].search(
                [('project_id', '=', self.id)])
            fail_count = len(stats.filtered(lambda r: not r.is_qualified))

        # 未處理預警數
        pending_warning_count = 0
        if 'supervision.test.warning' in self.env:
            pending_warning_count = self.env['supervision.test.warning'].search_count(
                [('project_id', '=', self.id), ('state', '=', 'pending')])

        return {
            'pending_count': pending_count,
            'pending_warning_count': pending_warning_count,
            'fail_count': fail_count,
        }

    def _dashboard_review_summary(self):
        """送審管制摘要"""
        if 'supervision.review.application' not in self.env:
            return None

        Review = self.env['supervision.review.application']
        domain = [('project_id', '=', self.id)]

        # 待送審（草稿且有預定日期）
        pending_count = Review.search_count(
            domain + [
                ('state', '=', 'draft'),
                ('expected_review_date', '!=', False),
            ])

        # 逾期未送（有預定日期但延遲 > 0 且尚未完成）
        overdue_count = Review.search_count(
            domain + [
                ('state', '=', 'draft'),
                ('review_delay_days', '>', 0),
            ])

        # 已完成
        done_count = Review.search_count(
            domain + [('state', '=', 'done')])

        return {
            'pending_count': pending_count,
            'overdue_count': overdue_count,
            'done_count': done_count,
        }
