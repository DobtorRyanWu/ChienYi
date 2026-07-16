# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class ConstructionWeeklySchedule(models.Model):
    """施工排程（周排程）"""
    _name = 'construction.weekly.schedule'
    _description = '施工排程'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'week_start asc'

    # === 基本資訊 ===
    supervision_project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='原生專案',
        related='supervision_project_id',
        store=True,
        readonly=True,
    )

    # === 周次 ===
    week_start = fields.Date(
        string='周起始日',
        required=True,
        index=True,
    )
    week_end = fields.Date(
        string='周結束日',
        compute='_compute_week_end',
        store=True,
    )
    week_display = fields.Char(
        string='周次',
        compute='_compute_week_display',
        store=True,
    )
    week_mode = fields.Selection([
        ('iso', 'ISO 周次'),
        ('project', '專案周次'),
    ], string='周次模式', default='project')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已確認'),
    ], string='狀態', default='draft', tracking=True)

    # === 明細 ===
    line_ids = fields.One2many(
        'construction.weekly.schedule.line',
        'schedule_id',
        string='排程明細',
    )

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='supervision_project_id.company_id',
        store=True,
    )

    # =========================================================================
    # 計算方法
    # =========================================================================

    @api.depends('week_start')
    def _compute_week_end(self):
        for rec in self:
            if rec.week_start:
                rec.week_end = rec.week_start + timedelta(days=6)
            else:
                rec.week_end = False

    @api.depends('week_start', 'week_mode', 'supervision_project_id.contract_start_date')
    def _compute_week_display(self):
        for rec in self:
            if not rec.week_start:
                rec.week_display = ''
                continue

            start_str = rec.week_start.strftime('%m/%d')
            end_date = rec.week_start + timedelta(days=6)
            end_str = end_date.strftime('%m/%d')

            if rec.week_mode == 'iso':
                iso_week = rec.week_start.isocalendar()[1]
                rec.week_display = f'ISO W{iso_week} ({start_str}~{end_str})'
            else:
                contract_start = rec.supervision_project_id.contract_start_date
                if contract_start:
                    project_week = (rec.week_start - contract_start).days // 7 + 1
                    rec.week_display = f'專案第{project_week}周 ({start_str}~{end_str})'
                else:
                    rec.week_display = f'{start_str}~{end_str}'

    @api.depends('week_display')
    def _compute_display_name(self):
        for rec in self:
            project_name = rec.supervision_project_id.name or ''
            rec.display_name = f'{project_name} - {rec.week_display}' if rec.week_display else f'排程 #{rec.id}'

    # =========================================================================
    # 動作方法
    # =========================================================================

    def action_confirm(self):
        """確認排程"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('請至少新增一筆排程明細')
            rec.state = 'confirmed'
            rec._create_inspection_activities()

    def _create_inspection_activities(self):
        """對需要自主檢查的工項建立活動提醒"""
        self.ensure_one()
        inspection_lines = self.line_ids.filtered(lambda l: l.need_inspection)
        if not inspection_lines:
            return

        # 取得指派對象
        user = self.supervision_project_id._get_activity_user('inspection')

        # 組合活動 note：列出所有需檢查的工項
        note_lines = []
        for line in inspection_lines:
            item_no = line.item_no or ''
            task_name = line.task_name or ''
            type_names = self._get_inspection_type_names(line.task_id)
            type_info = f'（檢查類型：{type_names}）' if type_names else ''
            note_lines.append(f'[{item_no}] {task_name} {type_info}')

        items_html = ''.join(f'<li>{nl}</li>' for nl in note_lines)
        note = (
            f'<p><strong>{self.week_display}</strong> 排程中，'
            f'以下工項需安排自主檢查：</p>'
            f'<ul>{items_html}</ul>'
        )

        # 建立活動
        self.activity_schedule(
            act_type_xmlid='construction_daily_log.activity_type_inspection_schedule',
            summary=f'自主檢查排程提醒 - {self.week_display}',
            note=note,
            user_id=user.id,
            date_deadline=self.week_start,
        )

        # 同步發送收件匣通知
        self.message_post(
            body=note,
            subject=f'自主檢查排程提醒 - {self.week_display}',
            partner_ids=user.partner_id.ids,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    def _get_inspection_type_names(self, task):
        """取得工項關聯的自主檢查類型名稱"""
        if 'self.inspection.type' not in self.env:
            return ''
        types = self.env['self.inspection.type'].search([
            ('task_ids', 'in', task.id),
        ])
        return '、'.join(types.mapped('name')) if types else ''

    def action_reset_draft(self):
        """退回草稿"""
        for rec in self:
            rec.state = 'draft'

    def action_prev_week(self):
        """上一周"""
        self.ensure_one()
        prev_start = self.week_start - timedelta(days=7)
        prev_schedule = self.search([
            ('supervision_project_id', '=', self.supervision_project_id.id),
            ('week_start', '=', prev_start),
        ], limit=1)
        if prev_schedule:
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': prev_schedule.id,
                'view_mode': 'form',
                'target': 'current',
            }
        raise UserError('上一周的排程不存在')

    def action_next_week(self):
        """下一周"""
        self.ensure_one()
        next_start = self.week_start + timedelta(days=7)
        next_schedule = self.search([
            ('supervision_project_id', '=', self.supervision_project_id.id),
            ('week_start', '=', next_start),
        ], limit=1)
        if next_schedule:
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': next_schedule.id,
                'view_mode': 'form',
                'target': 'current',
            }
        raise UserError('下一周的排程不存在')

    def action_add_items_wizard(self):
        """開啟新增工項精靈"""
        self.ensure_one()
        # 先建立 wizard（觸發 create 中的自動填充邏輯）
        wizard = self.env['weekly.schedule.add.items.wizard'].create({
            'schedule_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': '新增施工項目',
            'res_model': 'weekly.schedule.add.items.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }
