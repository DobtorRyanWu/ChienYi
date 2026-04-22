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
    
    # 當前使用的進度表
    active_progress_schedule_id = fields.Many2one(
        'progress.schedule',
        string='目前進度表',
        compute='_compute_active_progress_schedule',
        store=True,
        help='該工程目前使用中的進度表版本',
    )
    
    # 對應的進度區間
    progress_line_id = fields.Many2one(
        'progress.schedule.line',
        string='對應進度區間',
        compute='_compute_progress_line',
        store=True,
        help='本日所屬的進度區間',
    )
    
    # 進度表過時檢查
    has_outdated_schedule = fields.Boolean(
        string='進度表過時',
        compute='_compute_has_outdated_schedule',
        help='契約變更已核准但進度表尚未更新',
    )
    outdated_warning_message = fields.Html(
        string='警告訊息',
        compute='_compute_has_outdated_schedule',
    )
    
    # 變更後預定進度（契約變更時使用）
    changed_planned_progress = fields.Float(
        string='變更後本日預定進度(%)',
        digits=(5, 2),
        help='契約變更後的預定進度（暫時手動填寫）',
    )

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('supervision_project_id')
    def _compute_active_progress_schedule(self):
        """找到該工程目前使用中的進度表"""
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

    @api.depends('active_progress_schedule_id', 'log_date')
    def _compute_progress_line(self):
        """找到本日對應的進度區間"""
        for sheet in self:
            if not sheet.active_progress_schedule_id or not sheet.log_date:
                sheet.progress_line_id = False
                continue
            
            # 找包含本日的區間
            line = self.env['progress.schedule.line'].search([
                ('schedule_id', '=', sheet.active_progress_schedule_id.id),
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

    @api.depends('supervision_project_id', 'active_progress_schedule_id')
    def _compute_has_outdated_schedule(self):
        """檢查進度表是否過時"""
        ContractChange = self.env['contract.change.order']
        
        for sheet in self:
            if not sheet.supervision_project_id or not sheet.active_progress_schedule_id:
                sheet.has_outdated_schedule = False
                sheet.outdated_warning_message = ''
                continue
            
            # 查找所有契約變更單
            all_changes = ContractChange.search([
                ('project_id', '=', sheet.supervision_project_id.id),
            ])
            
            # 排除已被進度表關聯的變更單
            schedule = sheet.active_progress_schedule_id
            unhandled_changes = all_changes - schedule.related_change_order_ids
            
            if unhandled_changes:
                sheet.has_outdated_schedule = True
                
                # 分類顯示
                draft_changes = unhandled_changes.filtered(lambda c: c.state == 'draft')
                other_changes = unhandled_changes - draft_changes
                
                warning_parts = []
                
                if draft_changes:
                    draft_list = '<ul>' + ''.join([
                        f'<li>{c.name} (草稿)</li>' for c in draft_changes
                    ]) + '</ul>'
                    warning_parts.append(f'''
                        <p><strong>草稿中的契約變更：</strong></p>
                        {draft_list}
                        <p class="text-warning">
                            這些變更單尚在草擬中，但可能影響工程進度規劃。
                        </p>
                    ''')
                
                if other_changes:
                    # 取得 state 的顯示名稱
                    state_selection = dict(self.env['contract.change.order']._fields['state'].selection)
                    other_list = '<ul>' + ''.join([
                        f'<li>{c.name} ({state_selection.get(c.state, c.state)})</li>'
                        for c in other_changes
                    ]) + '</ul>'
                    warning_parts.append(f'''
                        <p><strong>已提交/審查/核准的契約變更：</strong></p>
                        {other_list}
                        <p class="text-danger">
                            這些變更單已進入正式流程，建議儘速更新進度表！
                        </p>
                    ''')
                
                alert_class = 'warning' if not other_changes else 'danger'
                need_text = '可能需要' if draft_changes and not other_changes else '需要'
                
                sheet.outdated_warning_message = f'''
                    <div class="alert alert-{alert_class}">
                        <h4><i class="fa fa-exclamation-triangle"></i> 
                            {need_text}更新進度表
                        </h4>
                        {''.join(warning_parts)}
                        <p>
                            <strong>目前進度表：</strong>v{schedule.version} 
                            (變更日期: {schedule.change_date})
                        </p>
                    </div>
                '''
            else:
                sheet.has_outdated_schedule = False
                sheet.outdated_warning_message = ''

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
        """當填寫實際進度時，標記為有進度變更"""
        res = super().write(vals)
        
        # 如果修改了 daily_actual_progress
        if 'daily_actual_progress' in vals:
            for sheet in self:
                if sheet.daily_actual_progress > 0:
                    # 標記有進度變更（供 progress 模組同步使用）
                    # 這個欄位原本就在 daily_log_sheet 中
                    if hasattr(sheet, 'has_progress_change'):
                        sheet.has_progress_change = True
        
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
