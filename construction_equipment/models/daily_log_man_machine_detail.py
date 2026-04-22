# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class DailyLogManMachineDetail(models.Model):
    """
    施工日誌人機使用明細

    使用者在施工日誌中直接選擇人員機具種類並登記當日使用量。
    儲存時系統自動 find-or-create 工程層級的彙整記錄（daily.log.man.machine），
    確保只有實際被使用的種類才會出現在統計中。
    """
    _name = 'daily.log.man.machine.detail'
    _description = '施工日誌人機使用明細'
    _order = 'daily_log_id, sequence'

    # === 關聯欄位 ===
    sequence = fields.Integer('排序', default=10)

    daily_log_id = fields.Many2one(
        'daily.log.sheet',
        string='施工日誌',
        required=True,
        ondelete='cascade',
        index=True)

    # 使用者直接選種類（不再選工程層級彙整記錄）
    personnel_type_id = fields.Many2one(
        'personnel.type',
        string='人員機具種類',
        required=True,
        domain="[('active', '=', True)]",
        ondelete='restrict',
    )

    # 彙整記錄由 create() 自動 find-or-create，不需使用者操作
    man_machine_id = fields.Many2one(
        'daily.log.man.machine',
        string='人機彙整記錄',
        ondelete='restrict',
        index=True,
    )

    project_id = fields.Many2one(
        related='daily_log_id.project_id',
        string='所屬工程',
        store=True)

    date = fields.Date(
        related='daily_log_id.log_date',
        string='日期',
        store=True)

    # === 類型資訊（自動帶入） ===
    record_type = fields.Selection(
        related='personnel_type_id.record_type',
        string='記錄類型',
        store=True)

    # === 使用量記錄 ===
    quantity = fields.Float(
        string='數量/人數',
        default=1.0,
        help='當日使用數量或人數')

    hours = fields.Float(
        string='使用時數',
        required=True,
        help='當日使用時數')

    # === 額外資訊（選填） ===
    employee_name = fields.Char(
        string='人員',
        help='如需記錄具體人員可填寫')

    specific_equipment_name = fields.Char(
        string='具體設備',
        help='如需記錄具體設備可填寫')

    note = fields.Text('備註')

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """建立明細時，自動 find-or-create 對應的工程層級彙整記錄"""
        ManMachine = self.env['daily.log.man.machine']
        PersonnelType = self.env['personnel.type']
        for vals in vals_list:
            pt_id = vals.get('personnel_type_id')
            if pt_id and not vals.get('man_machine_id'):
                log = self.env['daily.log.sheet'].browse(vals.get('daily_log_id'))
                # supervision_project_id 是 supervision.project，與 man_machine 的 project_id 一致
                sup_project_id = log.supervision_project_id.id if log and log.supervision_project_id else False
                if sup_project_id:
                    mm = ManMachine.search([
                        ('project_id', '=', sup_project_id),
                        ('personnel_type_id', '=', pt_id),
                    ], limit=1)
                    if not mm:
                        pt = PersonnelType.browse(pt_id)
                        mm = ManMachine.with_context(
                            tracking_disable=True,
                            mail_create_nolog=True,
                        ).create({
                            'project_id': sup_project_id,
                            'record_type': pt.record_type,
                            'personnel_type_id': pt_id,
                            'unit': 'hour',
                        })
                    vals['man_machine_id'] = mm.id
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Name Methods
    # -------------------------------------------------------------------------

    @api.depends('personnel_type_id', 'hours')
    def _compute_display_name(self):
        """Odoo 18 使用 _compute_display_name"""
        for record in self:
            name = record.personnel_type_id.display_name if record.personnel_type_id else '使用明細'
            record.display_name = f'{name} - {record.hours}小時'
