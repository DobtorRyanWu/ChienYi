# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError


class DailyLogAddManMachineWizardLine(models.TransientModel):
    """批次新增人機使用精靈明細"""
    _name = 'daily.log.add.man.machine.wizard.line'
    _description = '批次新增人機使用精靈明細'
    _order = 'record_type, sequence, id'

    wizard_id = fields.Many2one(
        'daily.log.add.man.machine.wizard',
        required=True,
        ondelete='cascade')

    selected = fields.Boolean(string='勾選', default=False)

    personnel_type_id = fields.Many2one(
        'personnel.type',
        string='人員/機具',
        required=True,
        readonly=True)

    record_type = fields.Selection(
        related='personnel_type_id.record_type',
        string='類型',
        store=True,
        readonly=True)

    sequence = fields.Integer(
        related='personnel_type_id.sequence',
        string='排序',
        store=True,
        readonly=True)

    quantity = fields.Float(string='數量', default=1.0)
    hours = fields.Float(string='時數', default=8.0)


class DailyLogAddManMachineWizard(models.TransientModel):
    """批次新增人機使用精靈"""
    _name = 'daily.log.add.man.machine.wizard'
    _description = '批次新增人機使用'

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

    line_ids = fields.One2many(
        'daily.log.add.man.machine.wizard.line',
        'wizard_id',
        string='可選人員/機具',
    )

    search_keyword = fields.Char(
        string='搜尋',
        help='輸入名稱關鍵字過濾列表')

    available_type_count = fields.Integer(
        string='可選項數',
        compute='_compute_available_type_count',
    )

    @api.depends('line_ids')
    def _compute_available_type_count(self):
        for wizard in self:
            wizard.available_type_count = len(wizard.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            if not wizard.line_ids:
                all_types = self.env['personnel.type'].search(
                    [('active', '=', True)],
                    order='record_type, sequence, name',
                )
                if all_types:
                    self.env['daily.log.add.man.machine.wizard.line'].create([
                        {
                            'wizard_id': wizard.id,
                            'personnel_type_id': pt.id,
                            'quantity': 1.0,
                            'hours': 8.0,
                        }
                        for pt in all_types
                    ])
        return wizards

    def action_search(self):
        """依關鍵字過濾列表，保留已勾選狀態"""
        self.ensure_one()

        # 記錄目前已勾選的 personnel_type
        selected_ids = set(
            self.line_ids.filtered('selected').mapped('personnel_type_id').ids
        )

        # 搜尋符合條件的 personnel.type
        domain = [('active', '=', True)]
        kw = (self.search_keyword or '').strip()
        if kw:
            domain += [('name', 'ilike', kw)]

        all_types = self.env['personnel.type'].search(
            domain, order='record_type, sequence, name'
        )

        # 重建列表，還原勾選狀態
        self.line_ids.unlink()
        if all_types:
            self.env['daily.log.add.man.machine.wizard.line'].create([
                {
                    'wizard_id': self.id,
                    'personnel_type_id': pt.id,
                    'selected': pt.id in selected_ids,
                    'quantity': 1.0,
                    'hours': 8.0,
                }
                for pt in all_types
            ])

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.log.add.man.machine.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _create_man_machine_details(self, wiz_lines):
        """從 wizard lines 建立 daily.log.man.machine.detail 記錄"""
        sheet = self.sheet_id
        vals_list = [
            {
                'daily_log_id': sheet.id,
                'personnel_type_id': line.personnel_type_id.id,
                'quantity': line.quantity or 1.0,
                'hours': line.hours or 0.0,
            }
            for line in wiz_lines
        ]
        if vals_list:
            self.env['daily.log.man.machine.detail'].create(vals_list)

    def action_add_selected(self):
        """新增勾選的項目，刷新列表讓 wizard 停留"""
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.selected)
        if not selected:
            raise UserError('請至少勾選一個項目！')
        self._create_man_machine_details(selected)
        self.line_ids.write({'selected': False})
        return self.action_search()

    def action_add_all(self):
        """全部新增，刷新列表讓 wizard 停留"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError('沒有可選的項目！')
        self._create_man_machine_details(self.line_ids)
        self.line_ids.write({'selected': False})
        return self.action_search()
