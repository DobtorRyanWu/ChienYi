# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from datetime import date, datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .progress_calc import ProgressCalc, effective_date, line_key

_logger = logging.getLogger(__name__)

# 進度差異超過這個百分點判定超前／落後（與 progress.schedule.line._compute_variance 相同）
VARIANCE_TOLERANCE = 1.0
VARIANCE_STATUS_LABELS = {
    'ahead': '超前',
    'on_track': '正常',
    'delayed': '落後',
}


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
        today = local_today()
        DailyLogSheet = self.env['daily.log.sheet']
        
        for project in self:
            if not project.active_schedule_id:
                project.daily_planned_progress = 0.0
                project.daily_actual_progress = 0.0
                continue
            
            # 找到今日所在的進度區間（交界日取照日期排前面的那一段）
            current_line = project.active_schedule_id.line_ids.filtered(
                lambda l: l.date_start and l.date_end and
                         l.date_start <= today <= l.date_end
            ).sorted(line_key)

            if current_line:
                line = current_line[0]

                # 本日預定進度（當日份額）＝這一段的預定 ÷ 這一段自己的日子（跟累計同一套，progress_calc）
                days = line._owned_day_count()
                project.daily_planned_progress = line.planned_progress / days if days else 0.0

                # 今日的施工日誌（2026-11-24 起草稿也算，跟累計實際進度同一套）
                today_log = DailyLogSheet.search([
                    ('supervision_project_id', '=', project.id),
                    ('log_date', '=', today),
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

    # =========================================================================
    # 開工前改契約日期 → 草稿進度表、空白日誌跟著同步
    # （開工後的日期鎖在 construction_supervision_base 的 write()）
    # =========================================================================

    def write(self, vals):
        from odoo.addons.construction_supervision_base.models.supervision_project import (
            CONTRACT_DATES_SYSTEM_WRITE,
        )
        if self.env.context.get(CONTRACT_DATES_SYSTEM_WRITE):
            return super().write(vals)
        draft_changed = self._contract_date_changes(vals).filtered(lambda p: p.state == 'draft')
        drop_logs = self.env['daily.log.sheet']
        for project in draft_changed:
            drop_logs |= project._prepare_contract_date_change(vals)
        res = super().write(vals)
        if draft_changed:
            if 'contract_end_date' in vals:
                # 草稿進度表建立時抄下的「原完工日」改成新的預定契約完工日；開工日本來就
                # related 到工程、自動跟著變。進度區間不重排，啟用時檢查區間。
                draft_changed.schedule_ids.filtered(lambda s: s.state == 'draft').write(
                    {'original_end_date': fields.Date.to_date(vals['contract_end_date'])})
            if drop_logs:
                _logger.info('開工前改契約日期：刪除新範圍外從沒填過的空白日誌 %d 張（工程 %s）',
                             len(drop_logs), ', '.join(draft_changed.mapped('code')))
                drop_logs.sudo().unlink()
        return res

    def _prepare_contract_date_change(self, vals):
        """開工前改日期的前置檢查，回傳要刪掉的空白日誌。

        - 所有進度表都要是草稿（使用中、已歸檔的要先退回草稿）。
        - 新範圍外的日誌：從沒填過的刪掉；有填過的就擋下並列出日期。
        """
        self.ensure_one()
        not_draft = self.schedule_ids.filtered(lambda s: s.state != 'draft')
        if not_draft:
            raise UserError(
                '工程「%s」還有不是草稿的進度表（%s），要改契約開工日或預定契約完工日，'
                '請先把進度表退回草稿。' % (
                    self.display_name,
                    '、'.join('第%s版（%s）' % (s.version, dict(s._fields['state'].selection).get(s.state))
                             for s in not_draft.sorted('version'))))
        new_start = fields.Date.to_date(vals['contract_start_date']) \
            if 'contract_start_date' in vals else self.contract_start_date
        new_end = fields.Date.to_date(vals['contract_end_date']) \
            if 'contract_end_date' in vals else self.contract_end_date
        Sheet = self.env['daily.log.sheet'].sudo()
        domain = [('supervision_project_id', '=', self.id)]
        outside = Sheet.search(domain).filtered(
            lambda s: (new_start and s.log_date < new_start) or (new_end and s.log_date > new_end))
        filled = outside.filtered(lambda s: not s._is_untouched_blank())
        if filled:
            raise UserError(
                '工程「%s」新的契約日期範圍（%s ～ %s）外面有已經填過內容的施工日誌，不能改：\n%s\n'
                '請先處理這些日誌（確認內容不要了就刪掉）再改日期。' % (
                    self.display_name, new_start or '-', new_end or '-',
                    '\n'.join('- %s' % d for d in sorted(filled.mapped('log_date')))))
        return outside

    @api.depends('active_schedule_id', 'active_schedule_id.current_cumulative_planned',
                 'active_schedule_id.current_cumulative_actual',
                 'active_schedule_id.current_variance')
    def _compute_schedule_progress(self):
        """首頁的累計預定／實際＝到今天（台灣日期，含當天）、共用算法（progress_calc）。不存，讀的時候現算。

        2026-11-24 以前讀使用中進度表存的「今天所在那一段的累計」：預定是那一段結束時的值、
        過了一天不會重算。"""
        today = local_today()
        for project in self:
            if project.active_schedule_id:
                planned, actual = project._progress_cumulative_on(today)
                project.schedule_cumulative_planned = planned or 0.0
                project.schedule_cumulative_actual = actual or 0.0
                project.schedule_variance = round(actual or 0.0, 2) - round(planned or 0.0, 2)
            else:
                project.schedule_cumulative_planned = 0.0
                project.schedule_cumulative_actual = 0.0
                project.schedule_variance = 0.0

    def _progress_cumulative_on(self, day, before=False, calc=None):
        """到 day（含）的 (累計預定, 累計實際)，所有地方共用（progress_calc；沒有資料的一邊是 None）。

        :param before: 契約變更當天要「變更前」的數字（只有進度曲線用）
        """
        self.ensure_one()
        calc = calc or ProgressCalc(self)
        return calc.planned(day, before=before), calc.actual(day, before=before)

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

    def get_progress_chart_data(self):
        """
        跨版本進度圖表數據：每一天都照共用算法（progress_calc）算，跟首頁、進度報告、印出來的日報是同一個數字。

        返回格式：{
            'dates': ['2024-01-01', ...],      # 每一天一個點；契約變更（新版生效）那一天兩個點：變更前、變更後
            'planned': [10, 20, ...],          # 累計預定
            'actual': [8, 18, ..., None],      # 累計實際；今天之後是 None（還沒發生，圖上不畫）
            'versions': [1, 1, 2, ...],        # 每個點用哪一版進度表（變更那一天：變更前的點＝舊版、變更後＝新版）
            'point_types': ['key', 'normal', ...],
            'today': '2024-01-15',
            'version_changes': [...],
            'actual_points': [8, None, ..., 18],  # 畫線用：只有累計實際有變的日子有值，其他 None（點跟點連直線）
            'axis_start': '2024-01-01', 'axis_end': '2024-06-30',  # 時間軸範圍
            'show_today': True,                # 畫不畫「今日」線
        }

        2026-11-27（使用者定）：
        - 實際進度線只把累計真的有變的日子當點、點跟點連直線（以前每一天一個點、沿用最後一個 → 階梯）。
          只改圖：首頁、日報、報告照舊沿用最後一個（'actual' 每一天的值不變，提示框照它顯示）。
          填了 0 的日子累計沒變 → 不當點；契約變更那天變更前、變更後不同 → 兩個點都留（垂直線）；
          最後一個有值的點照舊（畫到今天或完工日）。
        - 時間軸不再一律畫到今天（以前「今日」線會把軸撐開）：已完工（有實際完工日）畫到預定完工日與
          實際完工日較晚的那天、不畫今日線；沒完工畫到預定完工日與今天較晚的那天、照樣畫今日線。

        2026-11-24 以前段內用直線內插：實際進度不是照日誌（今天 11% 畫成 7.44%）、交界日的日誌在發生前一天
        就畫出來、預定少算一天。契約變更那一天照舊畫兩個點（使用者：那一天要看到一條垂直線，同一天看得到
        變更前與變更後的百分比）。
        """
        self.ensure_one()
        # 「今天」＝台灣日期（公司儀表板合約 §1-6、§5.3）
        today = local_today()
        empty = {
            'dates': [],
            'planned': [],
            'actual': [],
            'versions': [],
            'point_types': [],
            'today': today.isoformat(),
            'version_changes': [],
            'actual_points': [],
            'axis_start': None,
            'axis_end': None,
            'show_today': False,
        }
        # 草稿版本還沒啟用，不進圖表；已歸檔版本是歷史基準，照舊保留
        schedules = self.schedule_ids.filtered(lambda s: s.state != 'draft' and s.line_ids).sorted('version')
        if not schedules:
            return empty

        calc = ProgressCalc(self)
        lines = schedules.mapped('line_ids').filtered(lambda l: l.date_start and l.date_end)
        if not lines:
            return empty
        # 圖表範圍：第一版的開工日（區間可以早於開工日、晚於完工日：照區間延伸）到最後一版的完工日
        starts = [d for d in [schedules[0].start_date] + lines.mapped('date_start') if d]
        ends = [d for d in [schedules[-1].adjusted_end_date] + lines.mapped('date_end') if d]
        start_date, end_date = min(starts), max(ends)

        version_changes = []
        change_days = set()
        for schedule in schedules[1:]:
            boundary = effective_date(schedule)
            version_changes.append({
                'date': boundary.isoformat() if boundary else None,
                'version': schedule.version,
                'reason': schedule.change_reason or f'進度表版本 v{schedule.version}',
                'change_orders': self._progress_readable_change_order_names(schedule),
            })
            if boundary:
                change_days.add(boundary)

        key_dates = {start_date, end_date, today} | change_days
        dates, planned, actual, versions, point_types = [], [], [], [], []

        def add(day, before):
            day_planned, day_actual = self._progress_cumulative_on(day, before=before, calc=calc)
            governing = calc.governing(day, before=before)
            dates.append(day.isoformat())
            planned.append(round(day_planned or 0.0, 2))
            actual.append(None if day > today else round(day_actual or 0.0, 2))
            versions.append(governing.version if governing else None)
            point_types.append('key' if day in key_dates else 'normal')

        day = start_date
        while day <= end_date:
            if day in change_days:
                add(day, before=True)      # 變更前
            add(day, before=False)
            day += timedelta(days=1)

        # 時間軸範圍（2026-11-27）
        completed = self.actual_end_date
        axis_end = max(end_date, completed) if completed else max(end_date, today)
        show_today = not completed and start_date <= today <= axis_end

        return {
            'dates': dates,
            'planned': planned,
            'actual': actual,
            'versions': versions,
            'point_types': point_types,
            'today': today.isoformat(),
            'version_changes': version_changes,
            'actual_points': self._progress_chart_actual_points(dates, actual),
            'axis_start': start_date.isoformat(),
            'axis_end': axis_end.isoformat(),
            'show_today': show_today,
        }

    @api.model
    def _progress_chart_actual_points(self, dates, actual):
        """進度圖實際進度線要畫的點（2026-11-27）：累計跟前一個點不同的日子才當點，其他 None（圖上點跟點連直線）。
        第一個、最後一個有值的點一定留；同一天兩個點（契約變更的變更前／變更後）不同 → 兩個都留（垂直線）。"""
        points = [None] * len(actual)
        filled = [i for i, value in enumerate(actual) if value is not None]
        if not filled:
            return points
        first, last = filled[0], filled[-1]
        for i in filled:
            value = actual[i]
            prev = actual[i - 1] if i > 0 else None
            if i in (first, last) or prev is None or abs(value - prev) >= 0.005:
                points[i] = value
                if i > 0 and prev is not None and dates[i - 1] == dates[i]:
                    points[i - 1] = prev
        return points

    def _progress_readable_change_order_names(self, schedule):
        """進度表對應的變更單名稱，只列看的人讀得到的（公司儀表板合約 §5.3）。

        Many2many 讀取只套記錄規則、不查 ACL，而且快取不分 sudo：同一個交易先以 sudo 讀過，
        本人讀到的就是 sudo 的值。所以讀名稱之前一定要以本人身分過一次讀取權，
        看不到的不帶名稱（也不報 AccessError）。
        """
        orders = schedule.related_change_order_ids
        if not orders:
            return []
        return [order.name for order in orders._filtered_access('read')]

    @api.model
    def _progress_values_on(self, chart_data, day):
        """從 get_progress_chart_data() 的結果取某一天的累計預定／實際進度（跨版拼接後的同一份數字）。

        取「日期 ≤ day」的最後一點（版本更迭那天取新版）；day 在第一點之前 → 0（還沒開始）；
        沒有任何點（沒建進度表或只有草稿）→ None。
        回傳 {'planned', 'actual', 'variance', 'variance_status', 'version'}。
        """
        dates = chart_data.get('dates') or []
        if not dates:
            return None
        day_iso = day.isoformat()
        versions = chart_data.get('versions') or [None] * len(dates)
        index = None
        for i, point_date in enumerate(dates):
            if point_date <= day_iso:
                index = i
            else:
                break
        if index is None:
            planned = actual = 0.0
            version = versions[0]
        else:
            planned = chart_data['planned'][index] or 0.0
            actual = chart_data['actual'][index] or 0.0
            version = versions[index]
        variance = round(actual - planned, 2)
        if variance > VARIANCE_TOLERANCE:
            status = 'ahead'
        elif variance < -VARIANCE_TOLERANCE:
            status = 'delayed'
        else:
            status = 'on_track'
        return {
            'planned': planned,
            'actual': actual,
            'variance': variance,
            'variance_status': status,
            'version': version,
        }

    # =========================================================================
    # 儀表板 API
    # =========================================================================

    def _dashboard_blocks(self):
        """單一案件儀表板的區塊清單 [(key, 方法)]，依序執行。

        其他模組要加、減、換區塊時覆寫這個方法（例：公司儀表板 construction_company_dashboard 在後面
        加今日照片、今日日誌、估驗三塊，並改寫錯誤處理），不要另外複製一份清單（公司儀表板合約 §0b-18）。
        """
        self.ensure_one()
        return [
            ('basic_info', self._dashboard_basic_info),
            ('duration_info', self._dashboard_duration_info),
            ('progress_summary', self._dashboard_progress_summary),
            ('change_order_summary', self._dashboard_change_order_summary),
            ('defect_summary', self._dashboard_defect_summary),
            ('test_summary', self._dashboard_test_summary),
            ('review_summary', self._dashboard_review_summary),
        ]

    def get_project_dashboard_data(self):
        """取得單一案件的儀表板統合資料（各區塊獨立錯誤隔離）"""
        self.ensure_one()
        result = {}
        for key, method in self._dashboard_blocks():
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
        """進度摘要：與圖表、公司儀表板卡片同一份數字（get_progress_chart_data() 跨版拼接的今天值）。

        不再呼叫會寫入的 schedule._compute_current_progress()，也不讀已存的 current_* 值
        （只在明細被改時重算、會過時；公司儀表板合約 §5.3）。
        """
        values = self._progress_values_on(self.get_progress_chart_data(), local_today())
        if values is None:
            return None
        return {
            'cumulative_planned': values['planned'],
            'cumulative_actual': values['actual'],
            'variance': values['variance'],
            'variance_status': values['variance_status'],
            'variance_status_label': VARIANCE_STATUS_LABELS.get(values['variance_status'], ''),
            'schedule_version': values['version'],
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
        # 依工程類型選模型，與前台缺失列表一致
        defect_model = ('reservation.defect.improvement'
                        if self.project_type == 'reservation'
                        else 'general.defect.improvement')
        if defect_model not in self.env:
            return None

        Defect = self.env[defect_model]
        domain = [('project_id', '=', self.id)]

        total_count = Defect.search_count(domain)

        # 已改善（verified + closed）
        improved_count = Defect.search_count(
            domain + [('state', 'in', ('verified', 'closed'))])

        # 未改善（draft, notified, improving, improved）：與公司儀表板「待改缺失」同一個條件
        unimproved_count = Defect.search_count(domain + Defect._dash_open_domain())

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
