# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DailyLogSheet(models.Model):
    """
    施工日誌表單擴展 - 進度整合
    
    設計說明：
    - 在 progress 模組中擴展 daily.log.sheet
    - 避免循環依賴（progress 已依賴 daily_log）
    - 實現雙向整合：從進度表讀取 → 回饋至進度表
    """
    _inherit = 'daily.log.sheet'

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
    # 語意：當天是否有新版進度表被啟用，與 daily_actual_progress 無關
    has_progress_change = fields.Boolean(
        string='有進度變更',
        compute='_compute_has_progress_change',
        store=True,
        readonly=False,  # 允許使用者手動覆寫
        help='當天有新版進度表被啟用時自動為 True',
    )

    # 變更後預定進度（覆寫，改為 compute+store，自動從新版進度表取得）
    changed_planned_progress = fields.Float(
        string='變更後本日預定進度(%)',
        compute='_compute_changed_planned_progress',
        store=True,
        readonly=False,  # 允許使用者手動覆寫
        digits=(5, 2),
        help='新版進度表對應當天的預定進度（每日份額）',
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

        使用 effective_change_date（實際生效日）作為邊界：
        - 無校正版本：effective_change_date = change_date
        - 有校正版本：effective_change_date = correction_date

        規則：
        - 優先找 effective_change_date < log_date（嚴格小於）的最新版
          → 確保在 effective_change_date 當天仍使用舊版（「本日預定進度」顯示舊值）
        - 若無（工程第一天），退後找 effective_change_date = log_date 的最舊版

        範例（v2 有校正，change_date=5/15，correction_date=5/22）：
          5/21 以前 → v1（v2.effective = 5/22，不滿足 < 5/21）
          5/22      → v1（v2.effective = 5/22，不滿足嚴格小於）
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

            # 找包含本日的區間
            line = self.env['progress.schedule.line'].search([
                ('schedule_id', '=', sheet.base_progress_schedule_id.id),
                ('date_start', '<=', sheet.log_date),
                ('date_end', '>=', sheet.log_date),
            ], limit=1)

            sheet.progress_line_id = line

    @api.depends('progress_line_id', 'progress_line_id.planned_progress',
                 'progress_line_id.date_start', 'progress_line_id.date_end')
    def _compute_daily_planned_progress(self):
        """計算本日預定進度（當日份額）"""
        for sheet in self:
            if not sheet.progress_line_id:
                sheet.daily_planned_progress = 0.0
                continue

            line = sheet.progress_line_id
            total_days = (line.date_end - line.date_start).days + 1
            sheet.daily_planned_progress = line.planned_progress / total_days if total_days > 0 else 0.0

    @api.depends('supervision_project_id', 'log_date')
    def _compute_has_progress_change(self):
        """偵測當天是否有新版進度表在此日生效（使用 effective_change_date 統一判斷）"""
        for sheet in self:
            if not sheet.supervision_project_id or not sheet.log_date:
                sheet.has_progress_change = False
                continue
            changed = self.env['progress.schedule'].search_count([
                ('project_id', '=', sheet.supervision_project_id.id),
                ('effective_change_date', '=', sheet.log_date),
                ('state', 'in', ('active', 'archived')),
            ])
            sheet.has_progress_change = bool(changed)

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
            # 找包含當天的進度區間（校正切割後 Part2 是單天區間，total_days=1）
            line = new_schedule.line_ids.filtered(
                lambda l: l.date_start and l.date_end
                          and l.date_start <= sheet.log_date <= l.date_end
            )
            if line:
                l = line[0]
                total_days = (l.date_end - l.date_start).days + 1
                sheet.changed_planned_progress = (
                    l.planned_progress / total_days if total_days > 0 else 0.0
                )
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

    @api.constrains('supervision_project_id', 'log_date')
    def _check_progress_schedule_exists(self):
        """約束：建立日誌前必須先有進度表"""
        for sheet in self:
            # 只在新建且有專案時檢查
            if sheet.supervision_project_id and sheet.log_date and not sheet.active_progress_schedule_id:
                raise ValidationError(
                    f'工程案件「{sheet.supervision_project_id.name}」尚未建立進度表！\n\n'
                    f'請先至「進度管理 > 進度表」建立並啟用該工程的進度表，'
                    f'才能填寫施工日誌。'
                )

    # -------------------------------------------------------------------------
    # Write Method - Feedback to Progress Module
    # -------------------------------------------------------------------------

    def write(self, vals):
        """當 daily_actual_progress 實際改變時，自動同步到進度表"""
        # 在寫入前記錄舊值，供後續比較
        if 'daily_actual_progress' in vals:
            old_values = {sheet.id: sheet.daily_actual_progress for sheet in self}

        res = super().write(vals)

        # 只有值真正改變時才觸發同步，避免每次儲存都重算
        if 'daily_actual_progress' in vals:
            new_value = vals['daily_actual_progress']
            for sheet in self:
                old_value = old_values.get(sheet.id, 0.0)
                if new_value != old_value and sheet.progress_line_id:
                    sheet.progress_line_id._sync_actual_from_daily_logs()

        return res
    
    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    
    def action_view_progress_schedule(self):
        """查看對應的進度表"""
        self.ensure_one()
        if not self.active_progress_schedule_id:
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
            'res_id': self.active_progress_schedule_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
