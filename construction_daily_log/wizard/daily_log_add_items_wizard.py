# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError


class DailyLogAddItemsWizard(models.TransientModel):
    """新增施工項目精靈"""
    _name = 'daily.log.add.items.wizard'
    _description = '新增施工項目'

    sheet_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌',
        required=True,
        readonly=True,
    )

    project_id = fields.Many2one(
        related='sheet_id.project_id',
        string='工程案件',
        readonly=True,
    )

    log_date = fields.Date(
        related='sheet_id.log_date',
        string='日誌日期',
        readonly=True,
    )

    selected_task_ids = fields.Many2many(
        'project.task',
        'dl_add_items_wiz_task_rel',
        'wizard_id',
        'task_id',
        string='選擇施工項目',
    )

    existing_line_ids = fields.One2many(
        related='sheet_id.line_ids',
        string='已有工項',
        readonly=False,
    )

    # 分頁二：自填項目（純文字，不登記為契約工項）
    extra_line_ids = fields.One2many(
        'daily.log.add.items.wizard.extra',
        'wizard_id',
        string='自填項目',
    )

    def _reopen_wizard(self, existing_tab=False):
        """建立新 wizard 並重新開啟"""
        new_wizard = self.env['daily.log.add.items.wizard'].create({
            'sheet_id': self.sheet_id.id,
        })
        view_id = False
        if existing_tab:
            view = self.env.ref(
                'construction_daily_log.daily_log_add_items_wizard_form_existing',
                raise_if_not_found=False,
            )
            view_id = view.id if view else False
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.log.add.items.wizard',
            'view_mode': 'form',
            'res_id': new_wizard.id,
            'target': 'new',
        }
        if view_id:
            action['view_id'] = view_id
        return action

    def _create_daily_log_lines(self, tasks):
        """從 project.task recordset 建立 daily.log.line 記錄（跳過已存在的）"""
        sheet = self.sheet_id
        existing_items = sheet.line_ids.mapped('work_item_id')
        new_tasks = tasks - existing_items

        if not new_tasks:
            return

        existing_sequences = sheet.line_ids.mapped('sequence')
        max_seq = max(existing_sequences) if existing_sequences else 0

        lines_vals = [
            {
                'sheet_id': sheet.id,
                'work_item_id': item.id,
                'project_id': sheet.project_id.id,
                'employee_id': sheet.employee_id.id,
                'name': f'施工記錄 - {item.name}',
                'date': sheet.log_date,
                'daily_qty': 0.0,
                'sequence': max_seq + (idx * 10),
            }
            for idx, item in enumerate(new_tasks, start=1)
        ]
        self.env['daily.log.line'].create(lines_vals)

    def _create_extra_lines(self, extra_lines):
        """從自填項目建立 daily.log.line（entry_type='extra'，純文字不碰契約工項）"""
        sheet = self.sheet_id
        existing_sequences = sheet.line_ids.mapped('sequence')
        max_seq = max(existing_sequences) if existing_sequences else 0

        lines_vals = [
            {
                'sheet_id': sheet.id,
                'entry_type': 'extra',
                'custom_name': ex.name,
                'name': f'施工記錄 - {ex.name}',
                'location': ex.location or False,
                'work_description': ex.work_description or False,
                'project_id': sheet.project_id.id,
                'employee_id': sheet.employee_id.id,
                'date': sheet.log_date,
                'daily_qty': 0.0,
                'sequence': max_seq + (idx * 10),
            }
            for idx, ex in enumerate(extra_lines, start=1)
        ]
        self.env['daily.log.line'].create(lines_vals)

    def action_add_selected(self):
        """新增兩分頁的項目並關閉 wizard（父表單自動刷新）。
        排序由 daily.log.line 的 type_order 決定（契約恆在自填之前），與此處建立先後無關。"""
        self.ensure_one()
        if not self.selected_task_ids and not self.extra_line_ids:
            raise UserError('請至少選取一個契約工項，或填寫一個自填項目！')
        # 1) 先建契約工項
        if self.selected_task_ids:
            self._create_daily_log_lines(self.selected_task_ids)
        # 2) 再建自填項目
        if self.extra_line_ids:
            self._create_extra_lines(self.extra_line_ids)
        return {'type': 'ir.actions.act_window_close'}
