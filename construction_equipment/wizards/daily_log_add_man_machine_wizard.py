# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError


class DailyLogAddManMachineWizardLine(models.TransientModel):
    """批次新增人機使用精靈明細（數量與時數）"""
    _name = 'daily.log.add.man.machine.wizard.line'
    _description = '批次新增人機使用精靈明細'
    _order = 'record_type, sequence, id'

    wizard_id = fields.Many2one(
        'daily.log.add.man.machine.wizard',
        required=True,
        ondelete='cascade')

    personnel_type_id = fields.Many2one(
        'personnel.type',
        string='人員/機具',
        required=True)

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

    selected_type_ids = fields.Many2many(
        'personnel.type',
        'dl_mm_wiz_type_rel',
        'wizard_id',
        'type_id',
        string='選擇人員/機具',
    )

    line_ids = fields.One2many(
        'daily.log.add.man.machine.wizard.line',
        'wizard_id',
        string='數量與時數明細',
    )

    @api.onchange('selected_type_ids')
    def _onchange_selected_type_ids(self):
        """同步 selected_type_ids → line_ids，保留已編輯的 qty/hours"""
        existing = {
            line.personnel_type_id.id: line
            for line in self.line_ids
            if line.personnel_type_id
        }
        new_lines = self.env['daily.log.add.man.machine.wizard.line']
        for pt in self.selected_type_ids:
            if pt.id in existing:
                new_lines |= existing[pt.id]
            else:
                new_lines |= self.env['daily.log.add.man.machine.wizard.line'].new({
                    'personnel_type_id': pt.id,
                    'quantity': 1.0,
                    'hours': 8.0,
                })
        self.line_ids = new_lines

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
        """新增已選取項目並關閉 wizard（父表單自動刷新）"""
        self.ensure_one()
        if not self.selected_type_ids:
            raise UserError('請至少選取一個人員/機具！')
        # selected_type_ids 已確實存入 M2M junction，是可靠的 personnel_type_id 來源
        # line_ids 用來取使用者在 Tab2 調整過的 qty/hours（若存在）
        line_overrides = {
            line.personnel_type_id.id: (line.quantity, line.hours)
            for line in self.line_ids
            if line.personnel_type_id
        }
        vals_list = [
            {
                'daily_log_id': self.sheet_id.id,
                'personnel_type_id': pt.id,
                'quantity': line_overrides.get(pt.id, (1.0, 8.0))[0],
                'hours': line_overrides.get(pt.id, (1.0, 8.0))[1],
            }
            for pt in self.selected_type_ids
        ]
        self.env['daily.log.man.machine.detail'].create(vals_list)
        return {'type': 'ir.actions.act_window_close'}
