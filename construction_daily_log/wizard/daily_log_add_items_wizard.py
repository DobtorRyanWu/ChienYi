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

    # 工項明細（One2many，直接顯示可勾選列表）
    line_ids = fields.One2many(
        'daily.log.add.items.wizard.line',
        'wizard_id',
        string='可選工項',
    )

    search_keyword = fields.Char(
        string='搜尋工項',
        help='輸入工項名稱或編號關鍵字，按「搜尋」過濾列表')

    available_item_count = fields.Integer(
        string='可選工項數',
        compute='_compute_available_item_count',
    )

    # 已有工項（可操作）
    existing_line_ids = fields.One2many(
        related='sheet_id.line_ids',
        string='已有工項',
        readonly=False,
    )

    @api.depends('line_ids')
    def _compute_available_item_count(self):
        for wizard in self:
            wizard.available_item_count = len(wizard.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            # 如果建立時沒帶 line_ids，自動產生可選工項
            if not wizard.line_ids and wizard.sheet_id:
                sheet = wizard.sheet_id
                existing_items = sheet.line_ids.mapped('work_item_id')
                all_leaf_items = self.env['project.task'].search([
                    ('project_id', '=', sheet.project_id.id),
                    ('is_summary_item', '=', False),
                    ('active', '=', True),
                ])
                available = all_leaf_items - existing_items
                line_vals = [
                    {'wizard_id': wizard.id, 'task_id': task.id}
                    for task in available
                ]
                if line_vals:
                    self.env['daily.log.add.items.wizard.line'].create(line_vals)
        return wizards

    def _reopen_wizard(self):
        """建立新 wizard 並重新開啟"""
        new_wizard = self.env['daily.log.add.items.wizard'].create({
            'sheet_id': self.sheet_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.log.add.items.wizard',
            'view_mode': 'form',
            'res_id': new_wizard.id,
            'target': 'new',
        }

    def _create_daily_log_lines(self, wiz_lines):
        """從 wizard lines 建立 daily.log.line 記錄"""
        sheet = self.sheet_id
        existing_sequences = sheet.line_ids.mapped('sequence')
        max_seq = max(existing_sequences) if existing_sequences else 0

        lines_vals = []
        for idx, wiz_line in enumerate(wiz_lines, start=1):
            item = wiz_line.task_id
            lines_vals.append({
                'sheet_id': sheet.id,
                'work_item_id': item.id,
                'task_id': item.id,
                'project_id': sheet.project_id.id,
                'employee_id': sheet.employee_id.id,
                'name': f'施工記錄 - {item.name}',
                'date': sheet.log_date,
                'unit_amount': 0.0,
                'daily_qty': 0.0,
                'sequence': max_seq + (idx * 10),
            })

        return self.env['daily.log.line'].create(lines_vals)

    def action_search(self):
        """依關鍵字過濾工項列表，保留已勾選狀態"""
        self.ensure_one()

        # 記錄目前已勾選的工項 id
        selected_task_ids = set(
            self.line_ids.filtered('selected').mapped('task_id').ids
        )

        # 取得所有可選工項
        sheet = self.sheet_id
        existing_items = sheet.line_ids.mapped('work_item_id')
        all_leaf_items = self.env['project.task'].search([
            ('project_id', '=', sheet.project_id.id),
            ('is_summary_item', '=', False),
            ('active', '=', True),
        ])
        available = all_leaf_items - existing_items

        # 套用關鍵字過濾（空白則顯示全部）
        kw = (self.search_keyword or '').strip().lower()
        if kw:
            available = available.filtered(
                lambda t: kw in (t.name or '').lower()
                       or kw in (t.item_no or '').lower()
            )

        # 重建列表，還原勾選狀態
        self.line_ids.unlink()
        if available:
            self.env['daily.log.add.items.wizard.line'].create([
                {
                    'wizard_id': self.id,
                    'task_id': task.id,
                    'selected': task.id in selected_task_ids,
                }
                for task in available
            ])

        # 重新開啟同一 wizard，顯示過濾結果
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.log.add.items.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_add_selected(self):
        """新增勾選的工項，刷新列表讓 wizard 停留"""
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.selected)
        if not selected:
            raise UserError('請至少勾選一個工項！')
        self._create_daily_log_lines(selected)
        return self.action_search()

    def action_add_all(self):
        """全部新增（所有可選工項），刷新列表讓 wizard 停留"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError('沒有可選的工項！')
        self._create_daily_log_lines(self.line_ids)
        return self.action_search()
