# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .progress_calc import SKIP_CHANGE_DAY, line_key, owned_days


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
        string='計畫校正過渡明細（舊）',
        default=False,
        copy=True,
        help='舊的標記：以前只有這種明細可以填負數。2026-11-20 起每一段都可以是負數，'
             '2026-11-24「計畫倒退校正」改成「變更日進度」後，這一欄不影響任何計算（匯入工具還會寫）。',
    )
    is_change_day_row = fields.Boolean(
        string='變更日那一列',
        compute='_compute_is_change_day_row',
        help='系統在這一版的變更日切出來的那一列一天：預定進度由「變更日進度」的兩格算出來，不能直接改。',
    )
    # 系統切出變更日那一列時記下的（畫面不顯示）：改變更日期時才併得回原本那一段（2026-11-24，1.15.1）
    split_row = fields.Boolean(
        string='變更日切出來的一列',
        copy=False,
        readonly=True,
    )
    split_share = fields.Float(
        string='切出來時這一天本來的預定',
        copy=False,
        readonly=True,
        digits=(5, 2),
        help='這一天在原本那一段裡分到的預定進度：匯入、手動建的版本「變更後累計預定進度」空白就照它；'
             '改變更日期時把它加回原本那一段。',
    )
    split_origin_id = fields.Many2one(
        'progress.schedule.line',
        string='從哪一段切出來',
        copy=False,
        readonly=True,
        ondelete='set null',
    )

    @api.depends('date_start', 'date_end', 'split_row', 'schedule_id.change_date', 'schedule_id.version',
                 'schedule_id.line_ids.date_start')
    def _compute_is_change_day_row(self):
        for line in self:
            schedule = line.schedule_id
            line.is_change_day_row = bool(
                schedule and line.split_row and line.date_start
                and line.date_start == line.date_end == schedule.change_date
                and schedule._change_day_applicable())

    @api.depends('schedule_id.line_ids.planned_progress', 'schedule_id.line_ids.date_start',
                 'schedule_id.line_ids.date_end', 'schedule_id.line_ids.sequence',
                 'sequence', 'planned_progress', 'date_start', 'date_end')
    def _compute_cumulative_planned(self):
        """累計預定進度＝照日期排在自己前面（含自己）的各段預定相加。

        2026-11-24 起照日期排（progress_calc.line_key），以前照序號「小於等於」——兩段序號一樣時會互相多算、
        序號跟日期順序不一致時累計錯段。"""
        for line in self:
            if not line.schedule_id:
                line.cumulative_planned = 0.0
                continue
            key = line_key(line)
            prev_lines = line.schedule_id.line_ids.filtered(lambda l: line_key(l) <= key)
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
    actual_correction_target = fields.Float(
        string='變更後累計實際進度 (%)',
        digits=(5, 2),
        default=0.0,
        copy=True,   # 跟著新版本複製：之前那次契約變更的調整，下一版照樣算進去
        readonly=True,
        help='只有變更日那一列會有（由進度表「變更日進度」的「變更後累計實際進度」帶入）：'
             '這一列的實際進度由系統算，讓到這一天（含）的累計實際進度剛好等於這個數字。0＝照施工日誌加總。',
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

    @api.depends('schedule_id.line_ids.actual_progress', 'schedule_id.line_ids.date_start',
                 'schedule_id.line_ids.date_end', 'schedule_id.line_ids.sequence',
                 'sequence', 'actual_progress', 'date_start', 'date_end')
    def _compute_cumulative_actual(self):
        """累計實際進度＝照日期排在自己前面（含自己）的各段實際進度相加
        （各段實際進度由 progress.schedule._sync_actual_all_lines 照共用算法寫，相加剛好是到這一段結束日的累計）。"""
        for line in self:
            if not line.schedule_id:
                line.cumulative_actual = 0.0
                continue
            key = line_key(line)
            prev_lines = line.schedule_id.line_ids.filtered(lambda l: line_key(l) <= key)
            line.cumulative_actual = sum(prev_lines.mapped('actual_progress'))

    @api.onchange('actual_progress')
    def _onchange_actual_progress(self):
        """當實際進度改變時，重新計算自己和後續行的累計值"""
        if self.schedule_id and self.schedule_id.line_ids:
            # 強制重新計算所有行（會觸發連鎖更新）
            self.schedule_id.line_ids._compute_cumulative_actual()

    def _order_key(self):
        """區間在同一張進度表裡的先後（progress_calc.line_key：開始日 → 結束日 → 序號 → id）"""
        self.ensure_one()
        return line_key(self)

    def _owned_day_count(self):
        """這一段自己的日子有幾天（交界日算在排前面的那一段；progress_calc.owned_days）"""
        self.ensure_one()
        if not self.date_start or not self.date_end:
            return 0
        siblings = self.schedule_id.line_ids if self.schedule_id else self
        return len(owned_days(siblings).get(self.id) or [])

    def _daily_logs(self):
        """這一段日期範圍內（兩頭都含）的施工日誌（任何狀態）"""
        self.ensure_one()
        return self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.schedule_id.project_id.id),
            ('log_date', '>=', self.date_start),
            ('log_date', '<=', self.date_end),
        ])

    def _sync_actual_from_daily_logs(self):
        """從施工日誌重算實際進度（日誌儲存、進度表啟用時自動觸發）：整張進度表照共用算法重算
        （progress.schedule._sync_actual_all_lines）。"""
        self.mapped('schedule_id')._sync_actual_all_lines()

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
    # 交界日同一天時算在照日期排前面的那一段：日誌的「本日所屬區間」、本日預定份額、累計預定與累計實際都一樣
    # （2026-11-24 起共用 progress_calc；以前實際進度兩段各算一次）。
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
        """從施工日誌同步實際進度（「從日誌同步進度」按鈕）：跟自動同步同一套（整張進度表重算）。
        回傳這幾段範圍內有沒有日誌（有校正後累計實際進度的那一小段也算有）。"""
        lines = self.filtered(lambda l: l.date_start and l.date_end and l.schedule_id.project_id)
        if not lines:
            return False
        lines._sync_actual_from_daily_logs()
        return bool(lines.filtered(lambda l: l.actual_correction_target or l._daily_logs()))

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
        # copy_from_previous_version / 變更日切分 皆已 gate state=='draft'，
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
        records = super().create(vals_list)
        records._refresh_schedule_change_day()
        return records

    def _refresh_schedule_change_day(self, schedules=None):
        """明細改了（新增、改預定或日期、刪除）→ 變更日那一列照兩格重算（只算數字，不切分；2026-11-24）。
        2026-11-27 起使用中那一版也算（使用中可以直接改每一期的預定）。"""
        if self.env.context.get(SKIP_CHANGE_DAY):
            return
        schedules = (schedules if schedules is not None else self.mapped('schedule_id')).exists()
        schedules.filtered(lambda s: s.state in ('draft', 'active'))._refresh_change_day_line(split=False)

    def _period_label(self):
        """活動紀錄用：「第 15 期 11/30～12/06」（期數照日期排；跨年寫年份）"""
        self.ensure_one()
        lines = self.schedule_id.line_ids.filtered(lambda l: l.date_start and l.date_end).sorted(line_key)
        number = (list(lines).index(self) + 1) if self in lines else 0
        if self.date_start and self.date_end:
            fmt = '%Y/%m/%d' if self.date_start.year != self.date_end.year else '%m/%d'
            period = f'{self.date_start.strftime(fmt)}～{self.date_end.strftime(fmt)}'
        else:
            period = ''
        return (f'第 {number} 期 ' if number else '') + period

    def write(self, vals):
        """寫入時檢查狀態。

        2026-11-27（使用者定，照舊系統「改在用的那一張」）：使用中那一版可以直接改每一期的預定進度，存檔就生效；
        變更日那一列除外（那一列照「變更日進度」的「變更後累計預定進度」算）。每一期的日期、新增、刪除照舊只有草稿能改；
        已歸檔的不能改。使用中改了預定 → 進度表的活動紀錄寫一筆（例：第 15 期 11/30～12/06 預定 19.75 → 18.00）。"""
        # 禁止直接修改 actual_progress
        if 'actual_progress' in vals and not self.env.context.get('allow_sync_progress'):
            raise UserError('實際進度只能透過「從日誌同步進度」功能更新，不可手動修改。')

        # 如果是修改進度資料，檢查進度表狀態
        progress_fields = {'planned_progress', 'date_start', 'date_end'}
        internal = self.env.context.get(SKIP_CHANGE_DAY)
        logs = []
        if progress_fields & set(vals.keys()):
            for line in self:
                if line.schedule_state == 'archived':
                    raise UserError('已歸檔的進度表不可修改')
                if line.schedule_state != 'active':
                    continue
                if {'date_start', 'date_end'} & set(vals):
                    raise UserError('使用中的進度表不可修改區間日期（要改日期請先「重設草稿」）')
                if 'planned_progress' in vals and not internal:
                    if line.is_change_day_row:
                        raise UserError(
                            '變更日那一列的預定進度由「變更日進度」頁籤的「變更後累計預定進度」算出來，'
                            '要改請改那一格。')
                    old = round(line.planned_progress or 0.0, 2)
                    new = round(vals['planned_progress'] or 0.0, 2)
                    if abs(old - new) >= 0.005:
                        logs.append((line, f'{line._period_label()} 預定 {old:.2f} → {new:.2f}'))

        res = super().write(vals)
        if progress_fields & set(vals.keys()):
            self._refresh_schedule_change_day()
        by_schedule = {}
        for line, text in logs:
            by_schedule.setdefault(line.schedule_id, []).append(text)
        for schedule, texts in by_schedule.items():
            schedule.message_post(
                body=Markup('<br/>').join(['使用中改了預定進度：'] + texts),
                message_type='notification',
            )
        return res

    def unlink(self):
        """刪除時檢查狀態"""
        for line in self:
            if line.schedule_state != 'draft':
                raise UserError('只有草稿狀態的進度表明細可以刪除')
        schedules = self.mapped('schedule_id')
        res = super().unlink()
        self._refresh_schedule_change_day(schedules)
        return res
