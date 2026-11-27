# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api

from .progress_calc import ProgressCalc, line_key


class DailyLogSheet(models.Model):
    """
    施工日誌表單擴展 - 進度整合
    
    設計說明：
    - 在 progress 模組中擴展 daily.log.sheet
    - 避免循環依賴（progress 已依賴 daily_log）
    - 實現雙向整合：從進度表讀取 → 回饋至進度表
    """
    _inherit = 'daily.log.sheet'

    # 開工前改契約日期時，判斷「從沒填過的空白日誌」用。
    # 不列欄位清單（列了會漏新加的欄）：凡是使用者能填的欄位（存資料庫、不是計算、不是關聯到
    # 工程／填表人／公司這些系統帶的值）跟新建一張空白日誌的預設值比，子表一列都不能有。
    _BLANK_SYSTEM_FIELDS = frozenset({
        'supervision_project_id', 'employee_id', 'company_id', 'log_date', 'state',
        'user_id', 'project_id', 'department_id',
    })

    def _is_untouched_blank(self):
        """這張日誌是不是「進度表啟用時建好、之後從沒填過」的空白日誌"""
        self.ensure_one()
        if self.state != 'draft':
            return False
        defaults = None
        for name, field in self._fields.items():
            if (not field.store or field.compute or field.related or field.automatic
                    or name in models.MAGIC_COLUMNS or name in self._BLANK_SYSTEM_FIELDS
                    or name.startswith(('message_', 'activity_', 'rating_', 'website_message'))):
                continue
            value = self[name]
            if field.type in ('one2many', 'many2many'):
                if value:
                    return False
                continue
            if defaults is None:
                defaults = self.default_get(list(self._fields))
            default = defaults.get(name, False)
            if field.type == 'many2one':
                if value.id != (default or False):
                    return False
            elif (value or False) != (default or False):
                return False
        return True

    # === 進度狀況欄位 ===
    
    # 本日預定進度（從進度表自動計算）
    daily_planned_progress = fields.Float(
        string='本日預定進度(%)',
        compute='_compute_daily_planned_progress',
        store=True,
        digits=(5, 2),
        help='今日應完成的進度（當日份額）',
    )
    
    # 當日進度（使用者手動填寫）
    daily_actual_progress = fields.Float(
        string='當日進度(%)',
        digits=(5, 2),
        tracking=True,
        help='手動填寫本日實際完成進度（該區間內的進度增量）',
    )
    
    # 當前使用的進度表（永遠指向目前 active 版本，供過時警告等用途）
    active_progress_schedule_id = fields.Many2one(
        'progress.schedule',
        string='目前進度表',
        compute='_compute_active_progress_schedule',
        store=True,
        help='該工程目前使用中的進度表版本',
    )

    # 計算本日預定進度用的進度表（日期感知版）
    # 語意：log_date 當天「生效」的進度表版本
    # - 若當天有新版啟用（進度表變更日 = log_date），仍使用「舊版」
    #   → 保留舊版數值在 daily_planned_progress，新版數值在 changed_planned_progress
    # - 若當天無新版啟用，使用當天能找到的最新版
    base_progress_schedule_id = fields.Many2one(
        'progress.schedule',
        string='基礎進度表（本日預定用）',
        compute='_compute_base_progress_schedule',
        store=True,
        help='計算 daily_planned_progress 的進度表；變更當天使用舊版，隔天起才切換新版',
    )

    # 對應的進度區間
    progress_line_id = fields.Many2one(
        'progress.schedule.line',
        string='對應進度區間',
        compute='_compute_progress_line',
        store=True,
        help='本日所屬的進度區間',
    )
    
    # 有無進度變更（覆寫 construction_daily_log 的定義，改為 compute+store）
    # 語意：這一天是不是某一版進度表的「變更日期」（第 1 版不算、草稿不算），與 daily_actual_progress 無關。
    # 2026-11-27（使用者定）：不能手動勾 —— 以前可以手動改，勾錯天只改那張日誌、進度表與圖都不變，頁面跟圖對不上；
    # 第 1 版的變更日期＝開工日，以前也會被勾。由進度表啟用、重設草稿、改變更日期時重算（progress.schedule）。
    has_progress_change = fields.Boolean(
        string='有進度變更',
        compute='_compute_has_progress_change',
        store=True,
        help='自動勾，代表這一天是某一版進度表的「變更日期」（第 1 版不算），不能手動改。',
    )

    # 變更後本日預定進度（只留資料，畫面不顯示；2026-11-27 起變更那天改顯示「變更後累計預定／實際進度」）
    changed_planned_progress = fields.Float(
        string='變更後本日預定進度(%)',
        compute='_compute_changed_planned_progress',
        store=True,
        digits=(5, 2),
        help='新版進度表對應當天的預定進度（每日份額）',
    )

    # 變更那天顯示的兩格累計（不存資料庫；跟進度圖、首頁同一套算法 progress_calc，2026-11-27）
    change_cumulative_planned = fields.Float(
        string='變更後累計預定進度(%)',
        compute='_compute_change_cumulative',
        digits=(5, 2),
        help='換版後，累計到這一天應該完成多少。要改請到那一版進度表的「變更日進度」頁籤'
             '（使用中那一版可以直接改，已歸檔的不能改）。',
    )
    change_cumulative_actual = fields.Float(
        string='變更後累計實際進度(%)',
        compute='_compute_change_cumulative',
        digits=(5, 2),
        help='換版後，累計到這一天實際完成多少。要改的地方同上。',
    )

    # 本日進度參考值（由施工明細推算）
    daily_progress_reference = fields.Float(
        string='參考值 (%)',
        compute='_compute_daily_progress_reference',
        store=False,
        digits=(10, 4),
        help='= Σ(本日完成數量 × 施工項目單價) ÷ 契約總金額 × 100',
    )

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('supervision_project_id')
    def _compute_active_progress_schedule(self):
        """找到該工程目前使用中的進度表（供過時警告等用途）"""
        for sheet in self:
            if not sheet.supervision_project_id:
                sheet.active_progress_schedule_id = False
                continue

            # 找使用中的進度表
            schedule = self.env['progress.schedule'].search([
                ('project_id', '=', sheet.supervision_project_id.id),
                ('state', '=', 'active'),
            ], limit=1)

            sheet.active_progress_schedule_id = schedule

    @api.depends('supervision_project_id', 'log_date')
    def _compute_base_progress_schedule(self):
        """
        找到 log_date 當天「生效」的進度表（日期感知版）

        使用 effective_change_date（實際生效日）作為邊界：2026-11-24 起＝change_date
        （以前有計畫倒退校正時是校正基準日，那個日期已經拿掉）

        規則：
        - 優先找 effective_change_date < log_date（嚴格小於）的最新版
          → 確保在 effective_change_date 當天仍使用舊版（「本日預定進度」顯示舊值）
        - 若無（工程第一天），退後找 effective_change_date = log_date 的最舊版

        範例（v2 變更日 5/22）：
          5/21 以前 → v1
          5/22      → v1（v2.effective = 5/22，不滿足嚴格小於；「變更後本日預定」另外從 v2 取）
          5/23 以後 → v2（v2.effective = 5/22 < 5/23）
        """
        for sheet in self:
            if not sheet.supervision_project_id or not sheet.log_date:
                sheet.base_progress_schedule_id = False
                continue

            # 主查詢：effective_change_date 嚴格小於 log_date，取最高版本
            schedule = self.env['progress.schedule'].search([
                ('project_id', '=', sheet.supervision_project_id.id),
                ('state', 'in', ('active', 'archived')),
                ('effective_change_date', '<', sheet.log_date),
            ], order='version desc', limit=1)

            if not schedule:
                # 退後：找 effective_change_date = log_date 的最舊版（工程第一天）
                schedule = self.env['progress.schedule'].search([
                    ('project_id', '=', sheet.supervision_project_id.id),
                    ('state', 'in', ('active', 'archived')),
                    ('effective_change_date', '=', sheet.log_date),
                ], order='version asc', limit=1)

            sheet.base_progress_schedule_id = schedule

    @api.depends('base_progress_schedule_id', 'log_date')
    def _compute_progress_line(self):
        """找到本日對應的進度區間（使用 base_progress_schedule_id）"""
        for sheet in self:
            if not sheet.base_progress_schedule_id or not sheet.log_date:
                sheet.progress_line_id = False
                continue

            # 找包含本日的區間；兩段共用交界日時取照日期排前面的那一段（2026-11-24 起照日期，
            # 跟累計的算法 progress_calc 同一段；以前照序號）
            line = self.env['progress.schedule.line'].search([
                ('schedule_id', '=', sheet.base_progress_schedule_id.id),
                ('date_start', '<=', sheet.log_date),
                ('date_end', '>=', sheet.log_date),
            ], order='date_start, date_end, sequence, id', limit=1)

            sheet.progress_line_id = line

    @api.depends('progress_line_id', 'progress_line_id.planned_progress',
                 'progress_line_id.date_start', 'progress_line_id.date_end',
                 'progress_line_id.schedule_id.line_ids.date_start',
                 'progress_line_id.schedule_id.line_ids.date_end')
    def _compute_daily_planned_progress(self):
        """本日預定進度（當日份額）＝這一段的預定 ÷ 這一段自己的日子
        （交界日算在前一段，後一段分到它剩下的日子；2026-11-24 起跟累計同一套）"""
        for sheet in self:
            if not sheet.progress_line_id:
                sheet.daily_planned_progress = 0.0
                continue
            line = sheet.progress_line_id
            days = line._owned_day_count()
            sheet.daily_planned_progress = line.planned_progress / days if days > 0 else 0.0

    def _change_schedules_by_project(self):
        """{工程 id: 那個工程的「換版」進度表（使用中、已歸檔，照版本排，不含第一版）}"""
        result = {}
        Schedule = self.env['progress.schedule'].sudo()
        for project in self.mapped('supervision_project_id'):
            schedules = Schedule.search([
                ('project_id', '=', project.id),
                ('state', 'in', ('active', 'archived')),
            ], order='version asc')
            result[project.id] = schedules[1:]
        return result

    def _change_day_schedule(self):
        """這一天換上的那一版進度表（這一天是它的變更日期；第 1 版、草稿不算）。沒有回空的。"""
        self.ensure_one()
        Schedule = self.env['progress.schedule']
        if not self.supervision_project_id or not self.log_date:
            return Schedule
        changes = self._change_schedules_by_project().get(self.supervision_project_id.id) or Schedule
        hit = changes.filtered(lambda s: (s.effective_change_date or s.change_date) == self.log_date)
        return hit.sorted('version')[-1:] if hit else Schedule

    @api.depends('supervision_project_id', 'log_date')
    def _compute_has_progress_change(self):
        """這一天是不是某一版進度表的變更日期（使用中、已歸檔；第 1 版不算 —— 它的變更日期＝開工日，不是換版）。
        跟進度圖的換版日（progress_calc.change_days，也是不含第一版）同一套。"""
        changes = self._change_schedules_by_project()
        for sheet in self:
            if not sheet.supervision_project_id or not sheet.log_date:
                sheet.has_progress_change = False
                continue
            days = {s.effective_change_date or s.change_date
                    for s in changes.get(sheet.supervision_project_id.id) or []}
            sheet.has_progress_change = sheet.log_date in days

    @api.depends('supervision_project_id', 'log_date', 'has_progress_change')
    def _compute_change_cumulative(self):
        """變更那天：換版後到這一天（含）的累計預定／實際（跟進度圖「變更後」那個點同一個數字）。一般日子 0、不顯示。"""
        calcs = {}
        for sheet in self:
            planned = actual = 0.0
            project = sheet.supervision_project_id
            if sheet.has_progress_change and project and sheet.log_date:
                calc = calcs.get(project.id)
                if calc is None:
                    calc = calcs[project.id] = ProgressCalc(project)
                planned = calc.planned(sheet.log_date) or 0.0
                actual = calc.actual(sheet.log_date) or 0.0
            sheet.change_cumulative_planned = planned
            sheet.change_cumulative_actual = actual

    @api.depends('supervision_project_id', 'log_date', 'has_progress_change')
    def _compute_changed_planned_progress(self):
        """從新版進度表計算「變更後的預定進度」（使用 effective_change_date 定位新版）"""
        for sheet in self:
            if not sheet.has_progress_change or not sheet.log_date:
                sheet.changed_planned_progress = 0.0
                continue
            # 以 effective_change_date = log_date 找到當天生效的新版進度表
            new_schedule = self.env['progress.schedule'].search([
                ('project_id', '=', sheet.supervision_project_id.id),
                ('effective_change_date', '=', sheet.log_date),
                ('state', 'in', ('active', 'archived')),
            ], limit=1, order='version desc')
            if not new_schedule:
                sheet.changed_planned_progress = 0.0
                continue
            # 找包含當天的進度區間（變更日在新版是獨立的一天）；交界日取照日期排前面的那一段
            line = new_schedule.line_ids.filtered(
                lambda l: l.date_start and l.date_end
                          and l.date_start <= sheet.log_date <= l.date_end
            ).sorted(line_key)
            if line:
                l = line[0]
                days = l._owned_day_count()
                sheet.changed_planned_progress = l.planned_progress / days if days > 0 else 0.0
            else:
                sheet.changed_planned_progress = 0.0

    @api.depends('line_ids.daily_qty', 'line_ids.work_item_id.unit_price',
                 'supervision_project_id.contract_amount')
    def _compute_daily_progress_reference(self):
        """計算本日進度參考值：Σ(本日完成數量 × 施工項目單價) ÷ 契約總金額 × 100"""
        for sheet in self:
            contract_amount = sheet.supervision_project_id.contract_amount
            if not contract_amount:
                sheet.daily_progress_reference = 0.0
                continue
            total = sum(
                line.daily_qty * (line.work_item_id.unit_price or 0.0)
                for line in sheet.line_ids
            )
            sheet.daily_progress_reference = (total / contract_amount) * 100.0

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    # 2026-11-20 回復原版（1118 會議 A2）：拿掉「建立日誌前必須先有使用中的進度表」。
    # 開口合約（預約式）沒有預定進度表；沒有進度表時本日預定進度算 0、同步實際進度那段會直接略過。

    # -------------------------------------------------------------------------
    # Write Method - Feedback to Progress Module
    # -------------------------------------------------------------------------

    # 改了會影響累計實際進度的欄位：本日進度、舊系統匯入的累計值、日期（2026-11-24 起草稿也算，
    # 狀態不再影響數字，但照舊觸發一次同步）
    _PROGRESS_SYNC_FIELDS = ('daily_actual_progress', 'actual_progress', 'state', 'log_date')

    def _progress_schedules_to_sync(self, extra_lines=None):
        """要重算的進度表：這幾張日誌所屬工程的每一版（使用中、已歸檔、草稿）。

        每一版的明細都照日期加總所有日誌（progress_calc，只差用到哪幾版的調整），所以任何一篇日誌改了，
        每一版的數字都可能變。2026-11-24（1.15.2）以前只重算「這一天所屬那一版」＋使用中那一版 →
        三版以上時夾在中間的舊版、變更日之後的日子（屬於新版）對舊版、還沒啟用的草稿，明細都停在舊數字。"""
        Schedule = self.env['progress.schedule'].sudo()
        schedules = Schedule
        if extra_lines:
            schedules |= extra_lines.sudo().mapped('schedule_id')
        projects = self.mapped('supervision_project_id')
        if projects:
            schedules |= Schedule.search([('project_id', 'in', projects.ids)])
        return schedules

    @api.model_create_multi
    def create(self, vals_list):
        sheets = super().create(vals_list)
        changed = sheets.filtered(lambda s: s.daily_actual_progress or s.actual_progress)
        if changed:
            changed._progress_schedules_to_sync(changed.mapped('progress_line_id'))._sync_actual_all_lines()
        return sheets

    def write(self, vals):
        """本日進度、狀態或日期真的改變時，自動同步到進度表（新舊兩個區間都重算）。

        2026-10-28 以前只看本日進度：前台的正常流程是「新增（草稿）→ 標記已填寫（只改狀態）→ 14 天自動鎖定
        （只改狀態）」，而同步只算已填寫／鎖定的日誌——被填的那張永遠不在它自己觸發的同步裡，進度表、首頁進度 %、
        進度報告都不會動（r1 審查 F3／RT2-3；jt 10-28 實查 5,679 張日誌全是自動鎖定）。
        """
        watch = any(f in vals for f in self._PROGRESS_SYNC_FIELDS)
        if watch:
            def snapshot(s):
                return (s.daily_actual_progress, s.actual_progress, s.state, s.progress_line_id, s.log_date)
            before = {s.id: snapshot(s) for s in self}

        res = super().write(vals)

        if watch:
            changed = self.filtered(lambda s: snapshot(s) != before[s.id])
            if changed:
                lines = self.env['progress.schedule.line']
                for sheet in changed:
                    lines |= before[sheet.id][3] | sheet.progress_line_id
                changed._progress_schedules_to_sync(lines)._sync_actual_all_lines()

        return res

    def unlink(self):
        """刪掉有填進度的日誌 → 這個工程每一版進度表的實際進度重算（2026-11-24 以前刪日誌哪一版都不重算）。"""
        had = self.filtered(lambda s: s.daily_actual_progress or s.actual_progress)
        projects = had.mapped('supervision_project_id')
        res = super().unlink()
        if projects:
            self.env['progress.schedule'].sudo().search(
                [('project_id', 'in', projects.ids)])._sync_actual_all_lines()
        return res
    
    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    
    def action_view_progress_schedule(self):
        """查看對應的進度表：變更那天開那一天換上的那一版（2026-11-27），其他日子開使用中那一版。"""
        self.ensure_one()
        schedule = (self._change_day_schedule() if self.has_progress_change else False) \
            or self.active_progress_schedule_id
        if not schedule:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '提示',
                    'message': '該工程尚未建立進度表',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': '進度表',
            'res_model': 'progress.schedule',
            'res_id': schedule.id,
            'view_mode': 'form',
            'target': 'current',
        }
