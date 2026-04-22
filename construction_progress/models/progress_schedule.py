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
        group_operator='max',
    )
    change_date = fields.Date(
        string='變更時間',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    change_reason = fields.Text(
        string='變更原因',
        help='記錄本版本進度表變更的原因（如：契約變更、設計變更、施工方法調整、業主要求、天候因素等）',
    )

    # === 多公司架構 ===
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True,
        readonly=True,
    )

    # === 契約變更關聯（可選功能）===
    related_change_order_ids = fields.Many2many(
        'contract.change.order',
        'progress_schedule_change_order_rel',
        'schedule_id', 'change_order_id',
        string='對應的契約變更單',
        help='【可選功能】此版本進度表對應處理的契約變更單。'
             '注意：進度表變更不一定是因為契約變更，也可能是其他原因（設計變更、施工調整等）。'
             '需要 construction_contract_change 模組。',
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
        readonly=True,
        store=True,
        help='建立/複製本版進度表時快照的 contract_end_date（前一版啟用後的完工日）',
    )

    # 建立/複製時快照工程案件的累計展延天數，不隨工程案件的後續變動
    base_extension_duration = fields.Integer(
        string='展延基準值',
        default=0,
        readonly=True,
        help='建立本版進度表時的累計展延天數（系統自動記錄，不可修改）',
    )

    # 使用者在此版本新增的核准展延天數
    current_extension = fields.Integer(
        string='本次核准展延工期(日)',
        default=0,
        help='本版本新增的核准展延天數；系統將自動累加至「累計工期展延」',
    )

    # 累計展延 = 基準 + 本次，啟用時寫回工程案件
    duration_extension = fields.Integer(
        string='累計工期展延(日)',
        compute='_compute_duration_extension',
        store=True,
        readonly=True,
        help='展延基準值 + 本次核准展延工期（啟用時寫回工程案件）',
    )

    adjusted_end_date = fields.Date(
        string='調整後完工日期',
        compute='_compute_adjusted_end_date',
        store=True,
    )
    approved_duration = fields.Integer(
        string='核定工期',
        related='project_id.original_duration',
        readonly=True,
    )
    total_duration = fields.Integer(
        string='總工期(含展延)',
        compute='_compute_total_duration',
        store=True,
    )

    # 補充進度區間按鈕的顯示控制
    lines_cover_adjusted_end = fields.Boolean(
        string='區間已涵蓋完工日',
        compute='_compute_lines_cover_adjusted_end',
        help='當最後一筆區間的結束日 >= 調整後完工日期時為 True',
    )

    @api.depends('line_ids.date_end', 'adjusted_end_date')
    def _compute_lines_cover_adjusted_end(self):
        """判斷現有區間是否已涵蓋調整後完工日，用於控制「補充進度區間」按鈕顯示"""
        for rec in self:
            if not rec.line_ids or not rec.adjusted_end_date:
                rec.lines_cover_adjusted_end = False
                continue
            last_end = max(
                (l.date_end for l in rec.line_ids if l.date_end),
                default=None,
            )
            rec.lines_cover_adjusted_end = bool(last_end and last_end >= rec.adjusted_end_date)

    @api.depends('base_extension_duration', 'current_extension')
    def _compute_duration_extension(self):
        """累計工期展延 = 建立時基準 + 本次核准展延"""
        for rec in self:
            rec.duration_extension = (rec.base_extension_duration or 0) + (rec.current_extension or 0)

    @api.depends('original_end_date', 'current_extension')
    def _compute_adjusted_end_date(self):
        """計算調整後完工日期：前一版完工日 + 本次核准展延"""
        for rec in self:
            if rec.original_end_date:
                rec.adjusted_end_date = rec.original_end_date + timedelta(
                    days=rec.current_extension or 0)
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

    week_alignment_mode = fields.Selection([
        ('project_start', '工期起算制'),
        ('calendar', '日曆周制'),
    ], string='周期對齊方式', default='project_start',
       help=(
           '工期起算制：以開工日為基準，每 7（或 14）天為一組，不對齊日曆周。\n'
           '例：開工日 3/5（週三）→ 3/5–3/11、3/12–3/18…\n\n'
           '日曆周制：首個區間自動截斷至當週週日，後續區間對齊週一至週日。\n'
           '例：開工日 3/5（週三）→ 3/5–3/9（5天）、3/10–3/16、3/17–3/23…'
       ))

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

    # === 本周進度資訊（從當前區間取得）===
    current_week_period = fields.Char(
        string='本周日期',
        compute='_compute_current_week_info',
        store=True,
        help='今日所在的進度區間日期範圍',
    )
    current_week_planned = fields.Float(
        string='本周預定進度(%)',
        compute='_compute_current_week_info',
        store=True,
        digits=(5, 2),
        help='今日所在區間的預定進度（非累計）',
    )
    current_week_actual = fields.Float(
        string='本周實際進度(%)',
        compute='_compute_current_week_info',
        store=True,
        digits=(5, 2),
        help='今日所在區間的實際進度（非累計）',
    )

    @api.depends('line_ids.date_start', 'line_ids.date_end',
                 'line_ids.planned_progress', 'line_ids.actual_progress')
    def _compute_current_week_info(self):
        """計算本周（今日所在區間）的進度資訊"""
        today = fields.Date.today()
        
        for rec in self:
            # 找到包含今日的區間
            current_line = rec.line_ids.filtered(
                lambda l: l.date_start and l.date_end and 
                         l.date_start <= today <= l.date_end
            )
            
            if current_line:
                line = current_line[0]
                rec.current_week_period = line.period_display
                rec.current_week_planned = line.planned_progress  # 非累計
                rec.current_week_actual = line.actual_progress    # 非累計
            else:
                # 如果今日不在任何區間內，找最近的區間
                past_line = rec.line_ids.filtered(
                    lambda l: l.date_end and l.date_end < today
                ).sorted('date_end', reverse=True)
                
                if past_line:
                    line = past_line[0]
                    rec.current_week_period = f'已過期 ({line.period_display})'
                    rec.current_week_planned = line.planned_progress
                    rec.current_week_actual = line.actual_progress
                else:
                    rec.current_week_period = '-'
                    rec.current_week_planned = 0.0
                    rec.current_week_actual = 0.0

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
                 'line_ids.date_start', 'line_ids.date_end')
    def _compute_current_progress(self):
        """計算目前進度（含進行中區間）"""
        today = fields.Date.today()
        for rec in self:
            # 優先：找今日所在的進行中區間
            current_period = rec.line_ids.filtered(
                lambda l: l.date_start and l.date_end and
                          l.date_start <= today <= l.date_end
            )
            if current_period:
                line = current_period[0]
                rec.current_cumulative_planned = line.cumulative_planned
                rec.current_cumulative_actual = line.cumulative_actual
                rec.current_variance = line.variance
                rec.current_variance_status = line.variance_status
            else:
                # 退回：找最接近今日且已完成的區間
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

    # === 版本資訊 ===
    is_latest_version = fields.Boolean(
        string='是最新版本',
        compute='_compute_is_latest_version',
        store=True,
        help='是否為該工程的最新版本進度表（不論狀態）',
    )

    @api.depends('project_id', 'version')
    def _compute_is_latest_version(self):
        """計算是否為最新版本"""
        for schedule in self:
            if not schedule.project_id:
                schedule.is_latest_version = False
                continue
            
            # 找到同工程的最高版本號
            max_version_schedule = self.search([
                ('project_id', '=', schedule.project_id.id)
            ], order='version desc', limit=1)
            
            schedule.is_latest_version = (schedule.id == max_version_schedule.id)

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
        # duration_extension 已改為 computed stored，由 Python constraint 驗證
        ('unique_project_version', 'UNIQUE(project_id, version)',
         '同一工程的進度表版本號不可重複'),
    ]

    @api.constrains('current_extension')
    def _check_current_extension_non_negative(self):
        """本次核准展延工期不可為負數"""
        for rec in self:
            if (rec.current_extension or 0) < 0:
                raise ValidationError('本次核准展延工期不可為負數')

    # =========================================================================
    # Onchange 方法
    # =========================================================================

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """當選擇工程案件時，檢查是否有前一個版本"""
        if self.project_id and not self.line_ids and not self.id:
            # 找到前一個版本
            previous_schedule = self.search([
                ('project_id', '=', self.project_id.id)
            ], order='version desc', limit=1)
            
            if previous_schedule and previous_schedule.line_ids:
                return {
                    'warning': {
                        'title': '發現前一個版本',
                        'message': (
                            f'該工程已有 v{previous_schedule.version} 版本的進度表，'
                            f'共 {len(previous_schedule.line_ids)} 筆進度明細。\n\n'
                            f'儲存後，您可以使用「從前一版本複製」按鈕來繼承明細。'
                        )
                    }
                }

    # =========================================================================
    # 動作方法
    # =========================================================================

    def _calc_calendar_period_end(self, start_date, interval_weeks):
        """計算日曆周制的期末日期（對齊至週日）

        以 start_date 所在週的週一為基準，往後算 interval_weeks 週，
        結果為該週的週日（Python weekday：週一=0，週日=6）。
        """
        days_to_monday = start_date.weekday()  # Mon=0, Sun=6
        monday = start_date - timedelta(days=days_to_monday)
        return monday + timedelta(weeks=interval_weeks) - timedelta(days=1)

    def action_generate_lines(self):
        """根據計算模式自動產生進度區間（全部清除重建）"""
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

        # 決定間隔週數
        interval_weeks = 1 if self.calculation_mode == 'weekly' else 2

        lines = []
        current_date = self.start_date
        sequence = 1

        while current_date <= self.adjusted_end_date:
            if self.week_alignment_mode == 'calendar':
                end_date = self._calc_calendar_period_end(current_date, interval_weeks)
            else:
                end_date = current_date + timedelta(days=(interval_weeks * 7) - 1)

            end_date = min(end_date, self.adjusted_end_date)
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
            self.invalidate_recordset(['line_ids', 'line_count'])
            self.message_post(
                body=f'✅ 已自動產生 {len(lines)} 個進度區間',
                message_type='notification',
            )

        # 返回重新開啟當前記錄
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context),
        }

    def action_extend_lines(self):
        """補充進度區間（保留現有紀錄，只添加缺少部分）"""
        self.ensure_one()

        # 前置驗證
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以補充進度區間')
        if not self.adjusted_end_date:
            raise ValidationError('請先設定工期展延天數')
        if self.calculation_mode == 'custom':
            raise UserError('自訂模式請手動新增進度區間')

        interval_weeks = 1 if self.calculation_mode == 'weekly' else 2
        interval_days = interval_weeks * 7

        existing_lines = self.line_ids.sorted('date_start')
        preserved_count = len(existing_lines)

        if not existing_lines:
            # 無現有資料，直接重新產生
            return self.action_generate_lines()

        last_line = existing_lines[-1]

        # --- 處理最後一筆截斷的不完整區間 ---
        if last_line.period_days < interval_days:
            # 計算這個區間「完整」應結束到哪一天
            if self.week_alignment_mode == 'calendar':
                full_end = self._calc_calendar_period_end(last_line.date_start, interval_weeks)
            else:
                full_end = last_line.date_start + timedelta(days=interval_days - 1)

            if full_end < self.adjusted_end_date:
                # 補全最後一筆至完整區間結束，再繼續往後新增
                if self.state != 'draft':
                    raise UserError('狀態已變更，無法修改區間')
                last_line.write({'date_end': full_end})
                next_start = full_end + timedelta(days=1)
            elif full_end == self.adjusted_end_date:
                # 最後一筆剛好補到完工日，不需再新增
                if self.state != 'draft':
                    raise UserError('狀態已變更，無法修改區間')
                last_line.write({'date_end': full_end})
                self.invalidate_recordset(['line_ids', 'line_count'])
                self.message_post(
                    body=f'✅ 已保留舊有 {preserved_count} 筆，補全最後一個區間至完工日（新增 0 筆）',
                    message_type='notification',
                )
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'context': dict(self.env.context),
                }
            else:
                # 新完工日在最後一筆的完整區間之內，只更新結束日即可
                if self.state != 'draft':
                    raise UserError('狀態已變更，無法修改區間')
                last_line.write({'date_end': self.adjusted_end_date})
                self.invalidate_recordset(['line_ids', 'line_count'])
                self.message_post(
                    body=f'✅ 已保留舊有 {preserved_count} 筆，更新最後一個區間的結束日期（新增 0 筆）',
                    message_type='notification',
                )
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'context': dict(self.env.context),
                }
        else:
            # 最後一筆是完整區間，嚴格從其後一天開始
            next_start = last_line.date_end + timedelta(days=1)

        # --- 嚴格判斷：next_start 必須 <= adjusted_end_date 才建立 ---
        if next_start > self.adjusted_end_date:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '無需補充',
                    'message': f'現有 {preserved_count} 筆區間已涵蓋完工日期，無需補充。',
                    'type': 'info',
                    'sticky': False,
                }
            }

        # --- 建立缺少的區間 ---
        lines = []
        current_date = next_start
        sequence = max(self.line_ids.mapped('sequence') or [0])

        while current_date <= self.adjusted_end_date:
            if self.week_alignment_mode == 'calendar':
                end_date = self._calc_calendar_period_end(current_date, interval_weeks)
            else:
                end_date = current_date + timedelta(days=interval_days - 1)

            end_date = min(end_date, self.adjusted_end_date)
            sequence += 1
            lines.append({
                'schedule_id': self.id,
                'sequence': sequence,
                'date_start': current_date,
                'date_end': end_date,
                'planned_progress': 0.0,
            })
            current_date = end_date + timedelta(days=1)

        added_count = len(lines)
        if lines:
            self.env['progress.schedule.line'].create(lines)

        self.invalidate_recordset(['line_ids', 'line_count'])
        self.message_post(
            body=f'✅ 已保留舊有 {preserved_count} 筆，新增 {added_count} 筆區間',
            message_type='notification',
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context),
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

    def action_copy_from_previous_version(self):
        """從前一個版本複製進度明細"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError('只有草稿狀態可以複製明細')
        
        if self.line_ids:
            raise UserError('已有進度明細，無法複製。\n請先清空現有明細或使用「產生進度區間」功能。')
        
        # 找到前一個版本
        previous_schedule = self.search([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
        ], order='version desc', limit=1)
        
        if not previous_schedule:
            raise UserError('找不到前一個版本的進度表')
        
        if not previous_schedule.line_ids:
            raise UserError(f'v{previous_schedule.version} 版本沒有進度明細')
        
        # 複製明細（只複製預定進度，實際進度從 0 開始）
        for line in previous_schedule.line_ids:
            self.env['progress.schedule.line'].create({
                'schedule_id': self.id,
                'sequence': line.sequence,
                'date_start': line.date_start,
                'date_end': line.date_end,
                'planned_progress': line.planned_progress,
                'actual_progress': 0.0,  # 實際進度重新開始
                'notes': line.notes,
            })
        
        # 失效快取並重新載入
        self.invalidate_recordset(['line_ids', 'line_count'])
        
        # 記錄操作
        self.message_post(
            body=f'✅ 已從 v{previous_schedule.version} 複製 {len(previous_schedule.line_ids)} 筆進度明細',
            message_type='notification',
        )
        
        # 返回重新開啟表單
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context),
        }

    def action_activate(self):
        """開啟啟用精靈（啟用並批量建立日誌）"""
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

        return {
            'type': 'ir.actions.act_window',
            'name': '啟用進度表',
            'res_model': 'progress.activate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_schedule_id': self.id,
            },
        }

    def _do_activate(self):
        """實際執行啟用（由 wizard 呼叫）"""
        self.ensure_one()

        # 【安全防護】展延天數不可逆向減少
        current_project_extension = self.project_id.extension_duration or 0
        if self.duration_extension < current_project_extension:
            raise UserError(
                f'無法啟用：本進度表的累計工期展延（{self.duration_extension} 天）'
                f'小於工程案件目前的展延天數（{current_project_extension} 天）。\n'
                f'展延天數只能增加，不可逆向減少。'
            )

        # 將同專案其他進度表歸檔
        other_schedules = self.search([
            ('project_id', '=', self.project_id.id),
            ('id', '!=', self.id),
            ('state', '=', 'active'),
        ])
        if other_schedules:
            other_schedules.write({'state': 'archived'})

        self.write({'state': 'active'})

        # 寫回工程案件：累計展延天數 + 最新預定完工日
        update_vals = {}
        if self.duration_extension != current_project_extension:
            update_vals['extension_duration'] = self.duration_extension
        if self.adjusted_end_date and self.adjusted_end_date != self.project_id.contract_end_date:
            update_vals['contract_end_date'] = self.adjusted_end_date
        if update_vals:
            self.project_id.write(update_vals)

        # 在 Chatter 中記錄
        self.message_post(
            body='✅ 進度表已設為使用中',
            message_type='notification',
        )

        # ── 觸發相關施工日誌重算 ──────────────────────────────────────────
        # change_date 為新版進度表的生效日（通常 = 今天）
        change_date = self.change_date

        # 1. change_date 當天的日誌：重算 has_progress_change / changed_planned_progress
        #    以及 active_progress_schedule_id（過時警告用）
        logs_on_change = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('log_date', '=', change_date),
        ])
        if logs_on_change:
            logs_on_change._compute_active_progress_schedule()
            logs_on_change._compute_has_progress_change()
            logs_on_change._compute_changed_planned_progress()
            # base_progress_schedule_id 在變更當天仍返回舊版，不需重算
            # （change_date < log_date 嚴格小於，v2 不符合）

        # 2. change_date 之後的日誌：切換到新版進度表
        logs_after_change = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('log_date', '>', change_date),
        ])
        if logs_after_change:
            logs_after_change._compute_active_progress_schedule()
            logs_after_change._compute_base_progress_schedule()
            logs_after_change._compute_progress_line()
            logs_after_change._compute_daily_planned_progress()

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
        """建立進度表時自動計算版本號，並快照 base_extension_duration"""
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
            # 快照當下工程案件的累計展延天數，作為本版基準
            if 'project_id' in vals and 'base_extension_duration' not in vals:
                project = self.env['supervision.project'].browse(vals['project_id'])
                vals['base_extension_duration'] = project.extension_duration or 0
                # 快照此刻的 contract_end_date 作為「前一版完工日」基準
                if 'original_end_date' not in vals:
                    vals['original_end_date'] = project.contract_end_date
        return super().create(vals_list)

    def unlink(self):
        """只允許刪除草稿狀態的進度表"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態的進度表可以刪除')
        return super().unlink()

    def copy(self, default=None):
        """複製時重設狀態與展延欄位"""
        default = dict(default or {})
        default.setdefault('state', 'draft')
        default.setdefault('change_date', fields.Date.today())
        # 複製時重設展延欄位：以工程案件目前的累計值為新基準，本次從 0 開始
        default['current_extension'] = 0
        if self.project_id:
            default['base_extension_duration'] = self.project_id.extension_duration or 0
            # 快照此刻 contract_end_date，作為新版「前一版完工日」基準
            default.setdefault('original_end_date', self.project_id.contract_end_date)
        return super().copy(default)
