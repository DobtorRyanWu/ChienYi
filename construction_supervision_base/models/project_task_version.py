# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectTaskVersion(models.Model):
    """
    工項版本紀錄

    每次契約變更套用後，新增一筆版本記錄，完整保存歷次數量/單價。
    v1 在工項建立時自動建立（由 project.task.create override 處理）。
    """
    _name = 'project.task.version'
    _description = '工項版本紀錄'
    _order = 'task_id, version'
    _rec_name = 'version'

    task_id = fields.Many2one(
        'project.task', string='工項',
        required=True, ondelete='cascade', index=True)

    version = fields.Integer(
        string='版本號', required=True, default=1)

    planned_qty = fields.Float(
        string='數量', digits=(16, 4), required=True)

    unit_price = fields.Float(
        string='單價', digits=(16, 2), required=True)

    planned_amount = fields.Float(
        string='複價', compute='_compute_amount', store=True)

    change_date = fields.Date(
        string='生效日期', required=True)

    change_reason = fields.Char(
        string='變更原因')

    change_order_id = fields.Many2one(
        'contract.change.order', string='所屬變更單',
        ondelete='set null', index=True)

    _sql_constraints = [
        ('task_version_unique', 'UNIQUE(task_id, version)',
         '同一工項的版本號碼不得重複'),
    ]

    @api.depends('planned_qty', 'unit_price')
    def _compute_amount(self):
        for v in self:
            v.planned_amount = v.planned_qty * v.unit_price
