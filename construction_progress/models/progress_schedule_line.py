# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ProgressScheduleLine(models.Model):
    """
    進度表明細

    每一行代表一個時間區間的進度規劃與執行狀況
    業務說明：
    - 時間區間可自動產生或手動設定
    - 預定進度由使用者填寫
    - 實際進度可從施工日誌自動帶入
    - 累計進度與差異由系統自動計算
    """
    _name = 'progress.schedule.line'
    _description = '進度表明細'
    _order = 'schedule_id, sequence, date_start'

    # === 關聯欄位 ===
    schedule_id = fields.Many2one(
        'progress.schedule',
        string='進度表',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        related='schedule_id.project_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='schedule_id.company_id',
        store=True,
        readonly=True,
    )
    schedule_state = fields.Selection(
        related='schedule_id.state',
        string='進度表狀態',
        store=True,
        readonly=True,
    )
    schedule_is_latest = fields.Boolean(
        string='所屬進度表是最新版本',
        related='schedule_id.is_latest_version',
        store=True,
        help='該明細所屬的進度表是否為該工程的最新版本',
    )

    # === 序號 ===
    sequence = fields.Integer(
        string='序號',
        default=10,
        index=True,
    )

    # === 時間區間 ===
    date_start = fields.Date(
        string='開始日期',
        required=True,
    )
    date_end = fields.Date(
        string='結束日期',
        required=True,
    )
    period_display = fields.Char(
        string='期間',
        compute='_compute_period_display',
        store=True,
    )
    period_days = fields.Integer(
        string='區間天數',
        compute='_compute_period_days',
        store=True,
    )

    @api.depends('date_start', 'date_end')
    def _compute_period_display(self):
        """計算期間顯示文字"""
        for line in self:
            if line.date_start and line.date_end:
                start_str = line.date_start.strftime('%m/%d')
                end_str = line.date_end.strftime('%m/%d')
                if line.date_start.year != line.date_end.year:
                    # 跨年度顯示完整日期
                    start_str = line.date_start.strftime('%Y/%m/%d')
                    end_str = line.date_end.strftime('%Y/%m/%d')
                line.period_display = f"{start_str} - {end_str}"
            else:
                line.period_display = ''

    @api.depends('date_start', 'date_end')
    def _compute_period_days(self):
        """計算區間天數"""
        for line in self:
            if line.date_start and line.date_end:
                line.period_days = (line.date_end - line.date_start).days + 1
            else:
                line.period_days = 0

    # === 預定進度 ===
    planned_progress = fields.Float(
        string='預定進度 (%)',
        digits=(5, 2),
        default=0.0,
        help='本區間預定完成進度百分比',
    )
    cumulative_planned = fields.Float(
        string='累計預定進度 (%)',
        compute='_compute_cumulative_planned',
        store=True,
        digits=(5, 2),
    )
    from_plan_correction = fields.Boolean(
        string='計畫校正過渡明細',
        default=False,
        copy=True,   # 跨版本複製時保留，使歷史校正負值永遠合法
        help='標記此明細由「套用計畫基準校正」產生；其負值預定進度視為合法歷史，'
             '不受後續新版本另設校正視窗影響',
    )

    @api.depends('schedule_id.line_ids.planned_progress', 'sequence', 'planned_progress')
    def _compute_cumulative_planned(self):
        """計算累計預定進度"""
        for line in self:
            if not line.schedule_id:
                line.cumulative_planned = 0.0
                continue
            # 取得序號小於等於自己的所有明細
            prev_lines = line.schedule_id.line_ids.filtered(
                lambda l: l.sequence <= line.sequence
            )
            line.cumulative_planned = sum(prev_lines.mapped('planned_progress'))

    @api.onchange('planned_progress')
    def _onchange_planned_progress(self):
        """當預定進度改變時，重新計算自己和後續行的累計值"""
        if self.schedule_id and self.schedule_id.line_ids:
            # 強制重新計算所有行（會觸發連鎖更新）
            self.schedule_id.line_ids._compute_cumulative_planned()

    # === 實際進度 ===
    actual_progress = fields.Float(
        string='實際進度 (%)',
        digits=(5, 2),
        default=0.0,
        help='本區間實際完成進度百分比（可手動填寫或從施工日誌帶入）',
    )
    cumulative_actual = fields.Float(
        string='累計實際進度 (%)',
        compute='_compute_cumulative_actual',
        store=True,
        digits=(5, 2),
    )
    synced_from_log = fields.Boolean(
        string='已從日誌同步',
        default=False,
        readonly=True,
        help='標記此進度是否從施工日誌同步',
    )
    last_sync_date = fields.Datetime(
        string='最後同步時間',
        readonly=True,
    )

    @api.depends('schedule_id.line_ids.actual_progress', 'sequence', 'actual_progress')
    def _compute_cumulative_actual(self):
        """計算累計實際進度"""
        for line in self:
            if not line.schedule_id:
                line.cumulative_actual = 0.0
                continue
            # 取得序號小於等於自己的所有明細
            prev_lines = line.schedule_id.line_ids.filtered(
                lambda l: l.sequence <= line.sequence
            )
            line.cumulative_actual = sum(prev_lines.mapped('actual_progress'))

    @api.onchange('actual_progress')
    def _onchange_actual_progress(self):
        """當實際進度改變時，重新計算自己和後續行的累計值"""
        if self.schedule_id and self.schedule_id.line_ids:
            # 強制重新計算所有行（會觸發連鎖更新）
            self.schedule_id.line_ids._compute_cumulative_actual()

    def _sync_actual_from_daily_logs(self):
        """從施工日誌重算並同步實際進度（供日誌儲存時自動觸發）"""
        for line in self:
            logs = self.env['daily.log.sheet'].search([
                ('supervision_project_id', '=', line.schedule_id.project_id.id),
                ('log_date', '>=', line.date_start),
                ('log_date', '<=', line.date_end),
                ('state', 'in', ('filled', 'auto_locked', 'locked')),
            ])
            total = sum(logs.mapped('daily_actual_progress'))
            line.with_context(allow_sync_progress=True).write({
                'actual_progress': total,
                'synced_from_log': True,
                'last_sync_date': fields.Datetime.now(),
            })

    # === 差異分析 ===
    variance = fields.Float(
        string='超前(+)/落後(-)',
        compute='_compute_variance',
        store=True,
        digits=(5, 2),
        help='正值表示超前，負值表示落後',
    )
    variance_status = fields.Selection([
        ('ahead', '超前'),
        ('on_track', '正常'),
        ('delayed', '落後'),
    ], string='進度狀態', compute='_compute_variance', store=True)

    @api.depends('cumulative_planned', 'cumulative_actual')
    def _compute_variance(self):
        """計算進度差異與狀態"""
        for line in self:
            line.variance = line.cumulative_actual - line.cumulative_planned

            # 差異超過 1% 判定為超前或落後
            if line.variance > 1:
                line.variance_status = 'ahead'
            elif line.variance < -1:
                line.variance_status = 'delayed'
            else:
                line.variance_status = 'on_track'

    # === 備註 ===
    notes = fields.Text(
        string='備註',
        help='本區間進度備註說明',
    )

    # === SQL 約束 ===
    _sql_constraints = [
        ('date_check', 'CHECK(date_end >= date_start)',
         '結束日期必須晚於或等於開始日期'),
        # planned_progress 的下限由 Python 約束處理（允許計畫倒退校正使用負值）
        ('planned_progress_max', 'CHECK(planned_progress <= 100)',
         '預定進度不可超過 100%'),
        ('actual_progress_range', 'CHECK(actual_progress >= 0 AND actual_progress <= 100)',
         '實際進度必須在 0 到 100 之間'),
    ]

    # =========================================================================
    # 約束驗證
    # =========================================================================

    @api.constrains('planned_progress')
    def _check_planned_progress(self):
        """預定進度負值僅限：(a) 校正過渡明細(歷史) 或 (b) 當前校正視窗內"""
        for line in self:
            if line.planned_progress < 0:
                # (a) 由套用校正產生的過渡明細，永久視為合法（支援跨版本多次校正）
                if line.from_plan_correction:
                    continue
                # (b) 保留舊行為：當前校正視窗內允許負值
                sched = line.schedule_id
                if not (
                    sched.needs_plan_correction
                    and sched.correction_period_start
                    and sched.correction_period_end
                    and sched.correction_period_start <= line.date_start
                    and line.date_end <= sched.correction_period_end
                ):
                    raise ValidationError(
                        f'預定進度不可為負數（{line.planned_progress:.2f}%）。\n'
                        f'若需要修正計畫倒退，請在進度表上啟用「需要計畫基準校正」並套用校正。'
                    )

    @api.constrains('date_start', 'date_end', 'schedule_id')
    def _check_date_in_project_range(self):
        """驗證日期在工程期間內"""
        for line in self:
            if not line.schedule_id or not line.date_start or not line.date_end:
                continue

            schedule = line.schedule_id
            if schedule.start_date and line.date_start < schedule.start_date:
                raise ValidationError(
                    f'區間開始日期 ({line.date_start}) 不可早於工程開工日 ({schedule.start_date})'
                )
            if schedule.adjusted_end_date and line.date_end > schedule.adjusted_end_date:
                raise ValidationError(
                    f'區間結束日期 ({line.date_end}) 不可晚於調整後完工日 ({schedule.adjusted_end_date})'
                )

    @api.constrains('date_start', 'date_end', 'schedule_id')
    def _check_no_overlap(self):
        """驗證區間不重疊"""
        for line in self:
            if not line.schedule_id or not line.date_start or not line.date_end:
                continue

            overlapping = self.search([
                ('schedule_id', '=', line.schedule_id.id),
                ('id', '!=', line.id),
                ('date_start', '<=', line.date_end),
                ('date_end', '>=', line.date_start),
            ], limit=1)

            if overlapping:
                raise ValidationError(
                    f'區間日期 ({line.period_display}) 與其他區間 ({overlapping.period_display}) 重疊'
                )

    # =========================================================================
    # 動作方法
    # =========================================================================

    def action_sync_from_daily_log(self):
        """從施工日誌同步實際進度（累加該區間所有日誌）"""
        synced = False
        for line in self:
            if not line.date_start or not line.date_end:
                continue
            if not line.schedule_id.project_id:
                continue
            
            # 查找該區間內已填寫或已鎖定的日誌（排除草稿）
            DailyLogSheet = self.env['daily.log.sheet']
            logs = DailyLogSheet.search([
                ('supervision_project_id', '=', line.schedule_id.project_id.id),
                ('log_date', '>=', line.date_start),
                ('log_date', '<=', line.date_end),
                ('state', 'in', ('filled', 'auto_locked', 'locked')),
            ])
            
            if logs:
                # 累加該區間所有日誌的進度增量
                total_progress = sum(logs.mapped('daily_actual_progress'))
                
                # 使用 context 允許更新
                line.with_context(allow_sync_progress=True).write({
                    'actual_progress': total_progress,
                    'synced_from_log': True,
                    'last_sync_date': fields.Datetime.now(),
                })
                synced = True
        
        return synced

    def action_clear_actual_progress(self):
        """清除實際進度"""
        for line in self:
            if line.schedule_state != 'draft':
                raise UserError('只有草稿狀態的進度表可以清除實際進度')
            line.write({
                'actual_progress': 0.0,
                'synced_from_log': False,
                'last_sync_date': False,
            })
        return True

    # =========================================================================
    # CRUD 覆寫
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """建立時自動計算序號"""
        for vals in vals_list:
            if 'sequence' not in vals or vals.get('sequence', 0) <= 0:
                schedule_id = vals.get('schedule_id')
                if schedule_id:
                    existing_lines = self.search([
                        ('schedule_id', '=', schedule_id)
                    ])
                    vals['sequence'] = (len(existing_lines) + 1) * 10
        return super().create(vals_list)

    def write(self, vals):
        """寫入時檢查狀態"""
        # 禁止直接修改 actual_progress
        if 'actual_progress' in vals and not self.env.context.get('allow_sync_progress'):
            raise UserError('實際進度只能透過「從日誌同步進度」功能更新，不可手動修改。')
        
        # 如果是修改進度資料，檢查進度表狀態
        progress_fields = {'planned_progress', 'date_start', 'date_end'}
        if progress_fields & set(vals.keys()):
            for line in self:
                # 使用中的進度表不能修改預定進度和日期
                if line.schedule_state == 'active':
                    raise UserError('使用中的進度表不可修改預定進度和日期')
                elif line.schedule_state == 'archived':
                    raise UserError('已歸檔的進度表不可修改')

        return super().write(vals)

    def unlink(self):
        """刪除時檢查狀態"""
        for line in self:
            if line.schedule_state != 'draft':
                raise UserError('只有草稿狀態的進度表明細可以刪除')
        return super().unlink()
