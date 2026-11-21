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

    @api.depends('schedule_id.name', 'period_display')
    def _compute_display_name(self):
        """進度表名稱加區間日期；新建未填時以描述代替，避免露出 NewId"""
        for line in self:
            if line.schedule_id.name and line.period_display:
                line.display_name = f'{line.schedule_id.name} {line.period_display}'
            else:
                line.display_name = line.schedule_id.name or line._description

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
        copy=False,   # 新版本的實際進度從 0 開始；非零值複製會被 create 守衛擋下
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
        copy=False,   # 隨實際進度一起歸零
        help='標記此進度是否從施工日誌同步',
    )
    last_sync_date = fields.Datetime(
        string='最後同步時間',
        readonly=True,
        copy=False,
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

    # === 輸入值檢查 ===
    # 2026-11-20 回復原版（1118 會議）：這裡原本有五條檢查，當時全部拿掉——舊系統儲存進度表只檢查
    # 「變更時間有填、預定進度不能全部是 0」（views/PC/Schedule.vue addSchedule），其餘不比對。
    # 2026-11-22 使用者對照鈺鈞的意見表逐條決定後，現況是：
    #   加回    date_check（結束日不早於開始日，清單 PG-07）：舊資料 50 個版本只擋到打錯與測試的 4 個
    #   放寬加回 _check_no_overlap（區間不重疊，清單 PG-06）：上一段結束日＝下一段開始日不算重疊
    #   維持拿掉 planned_progress_max（單一區間不超過 100%）、_check_planned_progress（預定進度不可為負）、
    #           _check_date_in_project_range（區間不可早於開工日、晚於調整後完工日）
    # 交界日同一天時，日誌的「本日所屬區間」取第一筆符合的（daily_log_sheet._compute_progress_line 的 limit=1）。
    # actual_progress 一直沒有界限：它是施工日誌 daily_actual_progress 的加總，只能經同步寫入
    # （見 create() 與 write() 的 allow_sync_progress 閘門）。
    _sql_constraints = [
        ('date_check', 'CHECK(date_end >= date_start)',
         '結束日期必須晚於或等於開始日期'),
    ]

    @api.constrains('date_start', 'date_end', 'schedule_id')
    def _check_no_overlap(self):
        """同一張進度表的區間不可重疊。

        只共用一個交界日（上一段結束日＝下一段開始日）不算重疊：舊系統 2021 年的工程每月一段都這樣填，
        原本的判定（含交界日）會把它們擋掉，所以兩邊都用嚴格的大於／小於。"""
        for line in self:
            if not line.schedule_id or not line.date_start or not line.date_end:
                continue

            overlapping = self.search([
                ('schedule_id', '=', line.schedule_id.id),
                ('id', '!=', line.id),
                ('date_start', '<', line.date_end),
                ('date_end', '>', line.date_start),
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
        """建立時自動計算序號，並比照 write/unlink 擋非草稿進度表新增明細。"""
        allow_sync = self.env.context.get('allow_sync_progress')
        # 明細只能在「草稿」進度表新增：action_generate_lines / extend / add /
        # copy_from_previous_version / apply_correction 皆已 gate state=='draft'，
        # 合法路徑不受影響；此守衛堵住繞過那些 action 的程式化／匯入裸 create，在
        # 「使用中／已歸檔」進度表灌明細（髒值原本的入口，且事後因 write 被擋還得繞
        # SQL 才能修）。遷移／回填等刻意在 active 表補列的合法批次帶
        # allow_line_on_active_schedule 旗標放行，避免擋死自家工具。
        allow_on_active = self.env.context.get('allow_line_on_active_schedule')
        for vals in vals_list:
            # 實際進度是施工日誌的衍生加總，只能經同步寫入。擋掉非同步管道
            # （獨立表單、CSV 匯入、程式化 create）帶入的非零實際進度，避免 -50/250
            # 這類非法值繞過 write() 閘門靜默落庫。0.0（如複製版本時的初始化）放行。
            if not allow_sync and vals.get('actual_progress'):
                raise UserError('實際進度只能透過「從日誌同步進度」功能更新，不可手動修改。')
            # 狀態守衛：非草稿進度表不得新增明細（與 write/unlink 一致）
            if not allow_on_active:
                schedule_id = vals.get('schedule_id')
                if schedule_id:
                    schedule = self.env['progress.schedule'].browse(schedule_id)
                    if schedule.state and schedule.state != 'draft':
                        raise UserError(
                            '只有草稿狀態的進度表可以新增明細。'
                            '使用中的進度表如需調整，請先「重設為草稿」。')
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
