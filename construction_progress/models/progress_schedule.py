# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError

from odoo.addons.construction_supervision_base.models.supervision_project import (
    CONTRACT_DATES_SYSTEM_WRITE,
)
from odoo.addons.construction_supervision_base.utils.local_date import local_today

from .progress_calc import SKIP_CHANGE_DAY, ProgressCalc, line_key, owned_days

# 「工程僅存的進度表不能刪」的例外：整個工程要刪掉的維護腳本才帶（畫面、前台都不會帶）
ALLOW_DELETE_LAST_SCHEDULE = 'allow_delete_last_progress_schedule'


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
        'project.project',
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
                 'line_ids.date_start', 'line_ids.date_end', 'line_ids.planned_progress',
                 'line_ids.actual_progress', 'line_ids.actual_correction_target')
    def _compute_current_progress(self):
        """這一版進度表到今天（台灣日期，含當天）的累計預定／實際（共用算法 progress_calc）。

        2026-11-24 以前取「今天所在那一段」的累計＝那一段結束時的預定（段落中間一定看起來落後）。
        這幾個欄位要存（清單的超前／落後篩選、分組要用），日期一過就舊了 → 每天排程重算使用中的進度表
        （_cron_refresh_current_progress）。"""
        today = local_today()
        for rec in self:
            if not rec.project_id or not rec.line_ids:
                rec.current_cumulative_planned = 0.0
                rec.current_cumulative_actual = 0.0
                rec.current_variance = 0.0
                rec.current_variance_status = 'on_track'
                continue
            calc = ProgressCalc(rec.project_id, max_version=rec.version, include_schedule=rec)
            planned = calc.planned_in(rec, today) or 0.0
            actual = calc.actual(today) or 0.0
            variance = round(actual, 2) - round(planned, 2)
            rec.current_cumulative_planned = planned
            rec.current_cumulative_actual = actual
            rec.current_variance = variance
            rec.current_variance_status = (
                'ahead' if variance > 1 else 'delayed' if variance < -1 else 'on_track')

    @api.model
    def _cron_refresh_current_progress(self):
        """每天重算使用中進度表「到今天」的累計（存起來的值過了一天就舊了）"""
        schedules = self.sudo().search([('state', '=', 'active')])
        schedules._compute_current_progress()
        return True

    # === 版本資訊 ===
    is_latest_version = fields.Boolean(
        string='是最新版本',
        compute='_compute_is_latest_version',
        store=True,
        help='是否為該工程的最新版本進度表（不論狀態）',
    )

    @api.depends('project_id', 'version')
    def _compute_is_latest_version(self):
        """計算是否為最新版本。

        ⚠ @api.depends 只能列自己的 project_id/version——當同工程新增（或搬入、刪除）
        另一張版本更高的進度表時，ORM 不會觸發「舊那張」重算，於是 is_latest_version=True
        會 stale 地留在舊版上。所以 create/write/unlink 必須顯式呼叫
        `_recompute_latest_for_projects` 重算兄弟記錄（見下）。
        """
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

    # === 變更日進度（2026-11-24 改；原「計畫倒退校正」） ===
    # 照舊系統（EAGLE 進度表的一天區間＋日誌的「變更後進度」）：進度表一換版，變更日那一天在明細裡獨立成一列
    # （開始日＝結束日＝變更日，不跟前後段共用那一天），這一列放「變更後累計預定／實際進度」。兩格都可以不填：
    #   預定空白 → 當天照變更前的值（不往下掉、曲線沒有垂直線）；實際空白 → 照施工日誌加總。
    # 拿掉的：「需要計畫基準校正」開關（原本用途＝只在校正區間准許負數，2026-11-20 起每一段都可以負數）、
    #   「校正基準日」（直接用變更日；以前兩個日期的說明互相矛盾）、「套用校正」按鈕（現在填了就馬上算）。
    # 自動切分＋變更日以後歸零只在「建立新版本」「改變更日期」（與「從前一版本複製」）做；匯入、手動建的版本
    #   （沒有 copied_from_id）不會被自動切分、歸零，只有填了兩格才會切出變更日那一列。
    # 內部欄位名稱不改（correction_target_*），只改畫面上的名字。
    copied_from_id = fields.Many2one(
        'progress.schedule',
        string='從哪一版建立',
        copy=False,
        readonly=True,
        ondelete='set null',
        help='用「建立新版本」或「從前一版本複製」建的版本才有：改變更日期時照新日期從這一版重新切分。'
             '沒有的版本（匯入、手動建的）不會自動切分、歸零。',
    )
    correction_pre_cumulative = fields.Float(
        string='變更前累計預定進度 (%)',
        compute='_compute_change_before',
        digits=(5, 2),
        help='前面幾版進度表到變更日當天（含）的累計預定進度。「變更後累計預定進度」空白就照這個數字。',
    )
    change_pre_actual = fields.Float(
        string='變更前累計實際進度 (%)',
        compute='_compute_change_before',
        digits=(5, 2),
        help='到變更日當天（含）的累計實際進度（照施工日誌加總、不算這一版的調整）。',
    )
    correction_target_cumulative = fields.Float(
        # 內部名稱沿用「校正」；畫面上叫「變更後累計預定進度」
        string='變更後累計預定進度 (%)',
        copy=False,
        digits=(5, 2),
        help='變更日當天（含）照新計畫的累計預定進度。可以不填：空白＝當天照原本的值（不往下掉）——'
             '「建立新版本」建的照前一版那一天的值（變更前的值）；匯入、手動建的照這一版自己那一天的份額。'
             '變更日那一列的預定進度由系統算＝這個數字 − 前一天的累計。',
    )
    correction_target_actual = fields.Float(
        string='變更後累計實際進度 (%)',
        copy=False,
        digits=(5, 2),
        help='契約金額改了、已完成的比例要重新換算時填：變更日當天（含）的累計實際進度應該是多少。'
             '系統在變更日那一列放一筆調整，讓累計剛好等於這個數字；施工日誌一筆都不改，舊版保留原本的數字。'
             '可以不填：0 或空白＝不調整，照施工日誌加總（展延、契約金額沒變時就是這樣）。',
    )
    change_day_applicable = fields.Boolean(
        string='有變更日那一列',
        compute='_compute_change_day_applicable',
        help='第 1 版、或變更日不晚於第一段開始日（還沒開工就改版、整張重排）→ 不切分、沒有變更日那一列。',
    )
    effective_change_date = fields.Date(
        string='實際生效日',
        compute='_compute_effective_change_date',
        store=True,
        readonly=True,
        help='＝變更時間（2026-11-24 起；以前有計畫倒退校正時是校正基準日）。'
             '供施工日誌以此為界切換舊版/新版進度值。',
    )

    @api.depends('change_date')
    def _compute_effective_change_date(self):
        for rec in self:
            rec.effective_change_date = rec.change_date

    @api.depends('version', 'change_date', 'line_ids.date_start')
    def _compute_change_day_applicable(self):
        for rec in self:
            rec.change_day_applicable = rec._change_day_applicable()

    def _change_day_applicable(self):
        """第 2 版以後、變更日晚於第一段開始日 → 變更日在明細裡獨立成一列。"""
        self.ensure_one()
        starts = [d for d in self.line_ids.mapped('date_start') if d]
        return bool((self.version or 0) > 1 and self.change_date and starts and self.change_date > min(starts))

    @api.depends('project_id', 'version', 'change_date')
    def _compute_change_before(self):
        for rec in self:
            planned = actual = 0.0
            if rec.project_id and rec.change_date and (rec.version or 0) > 1:
                calc = ProgressCalc(rec.project_id, max_version=rec.version - 1)
                planned = calc.planned(rec.change_date) or 0.0
                actual = calc.actual(rec.change_date) or 0.0
            rec.correction_pre_cumulative = planned
            rec.change_pre_actual = actual

    def _change_day_line(self, day=None):
        """變更日那一列：系統切出來的那一列一天（開始日＝結束日＝變更日，split_row）。"""
        self.ensure_one()
        day = day or self.change_date
        if not day:
            return self.env['progress.schedule.line']
        return self.line_ids.filtered(lambda l: l.split_row and l.date_start == day and l.date_end == day)[:1]

    def _wants_change_day(self):
        """啟用、填兩格時要不要切出變更日那一列：「建立新版本」建的，或填了兩格之一。
        匯入、手動建、兩格都空、也沒改過變更日期 → 不動明細。"""
        self.ensure_one()
        return bool(self.copied_from_id or self.correction_target_cumulative or self.correction_target_actual)

    def _split_at_change_day(self, zero_after=False):
        """變更日在明細裡獨立成一列：包含變更日的段切成「變更日以前／變更日那一列／變更日以後」。
        兩段共用變更日（上一段結束日＝下一段開始日＝變更日）兩段都切；變更日落在兩段中間的空檔 → 放一列在空檔。
        預定照這一段自己的日子（交界日算前一段）比例分，照累計四捨五入（切開前後到每一天的累計都不變）；
        那一列記下這一天本來的份額（split_share）與從哪一段切出來（split_origin_id），之後改日期才併得回去。
        zero_after＝True（建立新版本、改變更日期、從前一版本複製）→ 變更日以後各段歸零、日期分段留著，照新計畫重填。
        切完各段的實際進度照日誌重算（以前要等到啟用或有日誌存檔，表上的實際進度才會對）。"""
        self.ensure_one()
        if self.state != 'draft' or not self._change_day_applicable():
            return
        me = self.with_context(**{SKIP_CHANGE_DAY: True})
        Line = me.env['progress.schedule.line']
        d = self.change_date
        one = timedelta(days=1)
        lines = me.line_ids.filtered(lambda l: l.date_start and l.date_end)
        row = me._change_day_line()
        owned = owned_days(lines)
        day_share = 0.0
        origin = Line
        for line in lines.sorted(line_key):
            if line == row or not (line.date_start <= d <= line.date_end):
                continue
            days = owned.get(line.id) or []
            amount = line.planned_progress or 0.0
            n = len(days)
            if n:
                before_amt = round(amount * sum(1 for x in days if x < d) / n, 2)
                upto = round(amount * sum(1 for x in days if x <= d) / n, 2)
                share = round(upto - before_amt, 2)
                after_amt = round(amount - upto, 2)
            else:
                before_amt, share, after_amt = 0.0, 0.0, amount
            day_share += share
            line_end = line.date_end
            if line.date_start < d:
                line.write({'date_end': d - one, 'planned_progress': before_amt})
                if line_end > d:
                    Line.create({'schedule_id': self.id, 'date_start': d + one, 'date_end': line_end,
                                 'planned_progress': after_amt, 'notes': line.notes})
                if d in days:
                    origin = line
            elif line_end > d:
                line.write({'date_start': d + one, 'planned_progress': after_amt})
                if d in days:
                    origin = line
            else:
                # 變更日本來就有一條單日列（例：一天一段的進度表）：併進變更日那一列
                day_share += after_amt
                line.unlink()
        if not row:
            day_share = round(day_share, 2)
            row = Line.create({'schedule_id': self.id, 'date_start': d, 'date_end': d,
                               'planned_progress': day_share, 'split_row': True, 'split_share': day_share,
                               'split_origin_id': origin.id if origin else False})
        if zero_after:
            me.line_ids.filtered(lambda l: l.date_start and l.date_start > d).write({'planned_progress': 0.0})
        me._resequence_lines()
        self._sync_actual_all_lines()

    def _unsplit_change_day(self, day):
        """把某一天切出來的那一列併回去（匯入、手動建的版本改變更日期時用）：這一天本來的份額加回它是從哪一段
        切出來的那一段（那一段不在了 → 前一天結束的那一段、再不然隔天開始的那一段）；那一列填過的調整不留。"""
        self.ensure_one()
        row = self._change_day_line(day)
        if not row:
            return False
        me = self.with_context(**{SKIP_CHANGE_DAY: True})
        one = timedelta(days=1)
        share = round(row.split_share or 0.0, 2)
        lines = me.line_ids - row
        origin = row.split_origin_id
        if not (origin and origin in lines and (origin.date_end == day - one or origin.date_start == day + one)):
            origin = (lines.filtered(lambda l: l.date_end == day - one)[:1]
                      or lines.filtered(lambda l: l.date_start == day + one)[:1])
        row.with_context(**{SKIP_CHANGE_DAY: True}).unlink()
        if origin:
            vals = {'planned_progress': round((origin.planned_progress or 0.0) + share, 2)}
            vals['date_end' if origin.date_end == day - one else 'date_start'] = day
            origin.write(vals)
        elif share:
            me.env['progress.schedule.line'].create({
                'schedule_id': self.id, 'date_start': day, 'date_end': day, 'planned_progress': share})
        self._sync_actual_all_lines()
        return True

    def _refresh_change_day_line(self, split=True):
        """變更日那一列的數字照兩格重算。
        預定：填了＝這個數字 − 前一天的累計；空白＝當天照原本的值 ——「建立新版本」建的照前一版的值（變更前的值）、
        匯入或手動建的照這一版自己這一天本來的份額（不替它補平，它自己的明細就是新的計畫）。
        實際：變更後累計實際進度（空白＝0＝照日誌加總）。預定與切分只動草稿，實際草稿與使用中都會。"""
        for rec in self:
            if rec.state not in ('draft', 'active') or not rec._change_day_applicable():
                continue
            draft = rec.state == 'draft'
            row = rec._change_day_line()
            if split and draft and (row or rec._wants_change_day()):
                rec._split_at_change_day()
                row = rec._change_day_line()
            if not row:
                continue
            d = rec.change_date
            vals = {}
            if draft:
                calc = ProgressCalc(rec.project_id, max_version=rec.version - 1)
                before = calc.planned_in(rec, d - timedelta(days=1)) or 0.0
                amount = None
                if rec.correction_target_cumulative:
                    amount = round(rec.correction_target_cumulative - before, 2)
                elif rec.copied_from_id:
                    prev = calc.planned(d)
                    if prev is not None:
                        amount = round(prev - before, 2)
                if amount is None:
                    amount = round(row.split_share or 0.0, 2)
                if abs((row.planned_progress or 0.0) - amount) >= 0.005:
                    vals['planned_progress'] = amount
            actual = rec.correction_target_actual or 0.0
            if abs((row.actual_correction_target or 0.0) - actual) >= 0.005:
                vals['actual_correction_target'] = actual
            if vals:
                row.with_context(**{SKIP_CHANGE_DAY: True}).write(vals)
                if 'actual_correction_target' in vals:
                    rec._sync_actual_all_lines()

    def _rebuild_from_source(self):
        """改了變更日期（「建立新版本」建的）：照新日期從建立這一版的那一版重新切分（變更日以後歸零）。"""
        self.ensure_one()
        src = self.copied_from_id
        if not src or not src.line_ids:
            return
        me = self.with_context(**{SKIP_CHANGE_DAY: True})
        me.line_ids.unlink()
        for line in src.line_ids:
            line.with_context(**{SKIP_CHANGE_DAY: True}).copy({'schedule_id': self.id})
        self.invalidate_recordset(['line_ids'])
        self._split_at_change_day(zero_after=True)
        self.message_post(
            body=f'變更日期改成 {self.change_date}：已照第 {src.version} 版重新切分進度明細，'
                 f'變更日以後的預定進度已清成 0，請照新計畫重填。',
            message_type='notification',
        )

    @api.onchange('change_date')
    def _onchange_change_date_resplit(self):
        origin = self._origin
        if (self.copied_from_id and self.state == 'draft' and origin and origin.id and origin.change_date
                and self.change_date and self.change_date != origin.change_date):
            return {'warning': {
                'title': '改變更日期',
                'message': '儲存後會照新的變更日期，從第 %s 版重新切分進度明細；'
                           '變更日以後已經填的預定進度會清成 0，要重填。' % self.copied_from_id.version,
            }}

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

    # 2026-11-22 加回（使用者決定，清單 PG-12）：11-20 曾照 1118 會議拿掉；舊系統 36 個填了展延天數的工程
    # 沒有一個是負數，留著當防呆。
    @api.constrains('current_extension', 'base_extension_duration')
    def _check_extension_not_below_contract(self):
        """累計工期展延不可為負（不可短於原合約工期）；
        本次核准展延允許為負，用於跨版本修正前一版的過度展延。"""
        for rec in self:
            if rec.duration_extension < 0:
                raise ValidationError(
                    f'累計工期展延（{rec.duration_extension} 天）不可為負數，'
                    f'工期不可短於原合約工期。'
                )

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
        
        # 複製明細（只複製預定進度，實際進度從 0 開始；之前那幾次變更日的實際調整照樣帶過來）
        Line = self.env['progress.schedule.line'].with_context(**{SKIP_CHANGE_DAY: True})
        for line in previous_schedule.line_ids:
            Line.create({
                'schedule_id': self.id,
                'sequence': line.sequence,
                'date_start': line.date_start,
                'date_end': line.date_end,
                'planned_progress': line.planned_progress,
                'actual_progress': 0.0,  # 實際進度重新開始
                'actual_correction_target': line.actual_correction_target,
                'notes': line.notes,
            })
        
        # 失效快取並重新載入
        self.invalidate_recordset(['line_ids', 'line_count'])
        # 2026-11-24：跟「建立新版本」一樣，變更日獨立成一列、變更日以後歸零
        self.with_context(**{SKIP_CHANGE_DAY: True}).write({'copied_from_id': previous_schedule.id})
        self._split_at_change_day(zero_after=True)
        self._refresh_change_day_line(split=False)
        
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
        # 2026-11-20 回復原版（1118 會議）：拿掉「預定進度總和不可超過 100%」——舊系統只檢查不能全部是 0

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
        # 變更日那一列照最新的兩格、明細重算一次（2026-11-24；匯入、手動建、兩格都空的版本不動）
        self._refresh_change_day_line()

        # 2026-11-20 回復原版（1118 會議）：啟用時不再檢查「進度區間要從開工日排到調整後完工日、中間不能有空檔、
        # 不能超出」（_check_lines_cover_period，已刪）——舊系統儲存進度表只檢查「變更時間有填、預定進度不能全部是 0」。
        # 2026-11-22 加回（使用者決定，清單 PG-12）：累計工期展延不可為負數。
        current_project_extension = self.project_id.extension_duration or 0
        if self.duration_extension < 0:
            raise UserError(
                f'無法啟用：本進度表的累計工期展延（{self.duration_extension} 天）為負數，'
                f'工期不可短於原合約工期。'
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
        # 第一次啟用時記下「進度表啟用過」
        if not self.project_id.progress_ever_activated:
            update_vals['progress_ever_activated'] = True
        if update_vals:
            # 展延寫回完工日是正規路徑，開工後的契約日期鎖放行
            self.project_id.with_context(**{CONTRACT_DATES_SYSTEM_WRITE: True}).write(update_vals)

        # 在 Chatter 中記錄
        self.message_post(
            body='✅ 進度表已設為使用中',
            message_type='notification',
        )

        # ── 觸發相關施工日誌重算 ──────────────────────────────────────────
        # 以 effective_change_date（＝change_date，2026-11-24 起）為觸發起點
        effective_date = self.effective_change_date or self.change_date

        # 1. effective_date 當天的日誌：重算進度變更標記（本日預定仍用舊版）
        # 生效日當天及之後的日誌一律重算衍生進度欄位（含已鎖定的歷史日誌）——這些是依
        # 核定計畫推導的衍生值，更新它們不算竄改使用者輸入；鎖定守門已放行衍生欄位寫入。
        logs_on_effective = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('log_date', '=', effective_date),
        ])
        if logs_on_effective:
            logs_on_effective._compute_active_progress_schedule()
            logs_on_effective._compute_has_progress_change()
            logs_on_effective._compute_changed_planned_progress()
            # base_progress_schedule_id 在 effective_date 當天仍返回舊版，不需重算
            # （effective_change_date < log_date 嚴格小於，v2 不符合當天）

        # 2. effective_date 之後的日誌：切換到新版進度表，並重算所有進度欄位
        logs_after_effective = self.env['daily.log.sheet'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('log_date', '>', effective_date),
        ])
        if logs_after_effective:
            logs_after_effective._compute_active_progress_schedule()
            logs_after_effective._compute_base_progress_schedule()
            logs_after_effective._compute_progress_line()
            logs_after_effective._compute_daily_planned_progress()
            logs_after_effective._compute_has_progress_change()
            logs_after_effective._compute_changed_planned_progress()

        # 3. 這一版每一段的實際進度從施工日誌重算（2026-11-24）。
        #    新版是從舊版複製的，實際進度從 0 開始（copy=False）；以前啟用時不重算，
        #    只有之後有日誌存檔的那幾段會同步 → 前台首頁的工程進度掉成只算部分段（實測 60% 掉到 25%），
        #    要有人按「同步所有明細」才回來。
        self._sync_actual_all_lines()
        self._compute_current_progress()

    def _resequence_lines(self):
        """切割前整理：依開始日排序後以 10 為步長重設 sequence，確保有足夠間距插入新行。

        2026-11-24：開始日一樣（交界日上的單日列與從交界日開始的那一段）再照結束日、原本的序號排，
        單日列排前面，結果才固定。"""
        for idx, line in enumerate(self.line_ids.sorted(
                lambda l: (l.date_start or fields.Date.today(), l.date_end or fields.Date.today(),
                           l.sequence, l.id))):
            line.sequence = (idx + 1) * 10

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
            # 開始施工後只有使用中（最新）那一版能退回草稿；舊版要改請「建立新版本」
            if rec.state == 'archived' and rec.project_id.state != 'draft':
                raise UserError(
                    '工程已開始施工，已歸檔的舊版進度表（第%s版）不能退回草稿。\n'
                    '要拿舊版內容修改，請在這一版按「建立新版本」複製一份。' % rec.version)
            rec.write({'state': 'draft'})
        return True

    def action_create_new_version(self):
        """建立新版本：先跳視窗問變更日期（一定要填，不預設今天；2026-11-24）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '建立新版本',
            'res_model': 'progress.new.version.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_schedule_id': self.id},
        }

    def _create_new_version(self, change_date, change_reason=False):
        """從這一版複製出新版本：變更日在明細裡獨立成一列、變更日以後各段歸零（日期分段留著）。回傳新版本。"""
        self.ensure_one()
        if not change_date:
            raise UserError('請填變更日期')
        max_version = max(self.search([
            ('project_id', '=', self.project_id.id)
        ]).mapped('version') or [0])
        new = self.with_context(**{SKIP_CHANGE_DAY: True}).copy({
            'version': max_version + 1,
            'change_date': change_date,
            'state': 'draft',
            'change_reason': change_reason or False,
            'copied_from_id': self.id,
        })
        new = self.env['progress.schedule'].browse(new.id)
        new._split_at_change_day(zero_after=True)
        new._refresh_change_day_line(split=False)
        return new

    def action_sync_all_lines_from_daily_log(self):
        """同步所有明細的實際進度（從施工日誌；整張一次重算，共用算法）"""
        self.ensure_one()
        self._sync_actual_all_lines()
        self._compute_current_progress()
        synced_count = len(self.line_ids.filtered(
            lambda l: l.date_start and l.date_end and (l.actual_correction_target or l._daily_logs())))

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

    def _recompute_latest_for_projects(self, project_ids):
        """強制重算指定工程所有進度表的 is_latest_version。

        修 stale stored compute（見 _compute_is_latest_version 的說明）：同工程新增或
        刪除版本後，舊版的 is_latest_version 不會自動重算。這裡顯式標記同工程所有
        兄弟記錄的 version 欄位為已變動，觸發 ORM 重算 stored compute。
        """
        project_ids = [p for p in set(project_ids) if p]
        if not project_ids:
            return
        siblings = self.sudo().search([('project_id', 'in', project_ids)])
        if siblings:
            siblings.modified(['version'])

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
                project = self.env['project.project'].browse(vals['project_id'])
                vals['base_extension_duration'] = project.extension_duration or 0
                # 快照此刻的 contract_end_date 作為「前一版完工日」基準
                if 'original_end_date' not in vals:
                    vals['original_end_date'] = project.contract_end_date
        records = super().create(vals_list)
        # 新增版本後，同工程舊版的 is_latest_version 已 stale，重算兄弟記錄
        records._recompute_latest_for_projects(records.mapped('project_id').ids)
        return records

    def write(self, vals):
        old_dates = {rec.id: rec.change_date for rec in self} if 'change_date' in vals else {}
        res = super().write(vals)
        # 改動 version 或 project_id 會影響同工程誰是最新版，重算兄弟記錄
        if 'version' in vals or 'project_id' in vals:
            self._recompute_latest_for_projects(self.mapped('project_id').ids)
        if self.env.context.get(SKIP_CHANGE_DAY):
            return res
        # 改了變更日期（草稿）：新的變更日馬上獨立成一列（2026-11-24 使用者：不要等填了兩格才獨立）。
        # 「建立新版本」建的 → 照新日期從原本那一版重新切分（變更日以後歸零）；
        # 匯入、手動建的（1.15.0 以前建的新版本也是）→ 舊日期那一列併回原本那一段、在新日期切一列，其他明細不動
        if 'change_date' in vals:
            for rec in self:
                old = old_dates.get(rec.id)
                if rec.state != 'draft' or not old or old == rec.change_date:
                    continue
                if rec.copied_from_id:
                    rec._rebuild_from_source()
                else:
                    rec._unsplit_change_day(old)
                    rec._split_at_change_day()
        # 填了、改了、清空了兩格（或改了變更日期）→ 變更日那一列馬上照新的數字算
        if {'change_date', 'correction_target_cumulative', 'correction_target_actual'} & set(vals):
            if 'correction_target_actual' in vals:
                for rec in self:
                    if (rec.state == 'active' and rec.correction_target_actual and rec._change_day_applicable()
                            and not rec._change_day_line()):
                        raise UserError(
                            '這一版的進度明細沒有變更日（%s）那一列（匯入或手動建的），'
                            '請先「重設草稿」再填，系統才會切出那一列。' % rec.change_date)
            self._refresh_change_day_line()
        return res

    def _sync_actual_all_lines(self):
        """整張進度表的實際進度照共用算法重算（progress_calc）。

        每一段的累計實際＝到這一段結束日（含）的累計實際（照日期加總所有日誌、草稿也算；基準點＝變更後累計
        實際進度、舊系統匯入的累計值）；每一段的實際進度＝自己的累計 − 前一段的累計（照日期排），所以：
        - 交界日只算在前一段、空檔日子的日誌算進下一段、開工前的日誌算進第一段；
        - 變更日那一列自然是負的調整（例：20 − 37.5 ＝ −17.5），累計剛好等於填的「變更後累計實際進度」；
        - 只用這一版（含）以前的進度表的調整——舊版自己的數字不受之後變更的調整影響。
        先四捨五入到小數兩位再相減，各段相加才會剛好等於累計。"""
        now = fields.Datetime.now()
        for schedule in self:
            if not schedule.project_id:
                continue
            calc = ProgressCalc(schedule.project_id, max_version=schedule.version, include_schedule=schedule)
            prev = 0.0
            for line in schedule.line_ids.filtered(lambda l: l.date_start and l.date_end).sorted(line_key):
                cum = round(calc.actual(line.date_end) or 0.0, 2)
                value = round(cum - prev, 2)
                prev = cum
                if line.synced_from_log and abs((line.actual_progress or 0.0) - value) < 0.005:
                    continue
                line.with_context(allow_sync_progress=True).write({
                    'actual_progress': value,
                    'synced_from_log': True,
                    'last_sync_date': now,
                })

    def unlink(self):
        """只允許刪除草稿狀態的進度表"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態的進度表可以刪除')
        # 工程僅存的那一張不能刪（不論有沒有日誌）；開工前要改日期退回草稿就好。
        # ALLOW_DELETE_LAST_SCHEDULE 只給整個工程要刪掉的維護腳本用，畫面不會帶。
        if not self.env.context.get(ALLOW_DELETE_LAST_SCHEDULE):
            for project in self.mapped('project_id'):
                remaining = self.search_count([('project_id', '=', project.id), ('id', 'not in', self.ids)])
                if not remaining:
                    raise UserError(
                        '進度表是工程「%s」僅存的一張，不能刪除。\n'
                        '要改內容請直接修改這一張（使用中的先退回草稿）。' % project.display_name)
        # 記下受影響工程，刪除後重算剩餘兄弟（刪掉最高版時最新版會換人）
        affected = self.mapped('project_id').ids
        res = super().unlink()
        self._recompute_latest_for_projects(affected)
        return res

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
