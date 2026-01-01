# -*- coding: utf-8 -*-

from odoo import models, fields


class ProjectTask(models.Model):
    """
    契約工項 - 契約變更關聯擴展 (v5.2)

    擴展 project.task 支援：
    - 關聯契約變更單
    - 追蹤工項由哪次變更新增/修改
    """
    _inherit = 'project.task'

    # === 契約變更關聯 ===
    change_order_id = fields.Many2one(
        'contract.change.order',
        string='契約變更單',
        index=True,
        help='此工項由哪次契約變更新增/修改')

    change_order_name = fields.Char(
        string='變更單編號',
        related='change_order_id.name',
        store=True)

    is_change_item = fields.Boolean(
        string='變更項目',
        compute='_compute_is_change_item',
        store=True,
        help='此工項是否為變更新增/修改的項目')

    change_type = fields.Selection([
        ('original', '原契約'),
        ('added', '變更新增'),
        ('modified', '變更修改'),
    ], string='工項來源',
       compute='_compute_change_type',
       store=True,
       help='標示工項來源：原契約/變更新增/變更修改')

    # === 計算欄位 ===
    def _compute_is_change_item(self):
        for task in self:
            task.is_change_item = bool(task.change_order_id)

    def _compute_change_type(self):
        for task in self:
            if not task.change_order_id:
                task.change_type = 'original'
            else:
                # 檢查是否為變更單中的新增項目
                ChangeOrderLine = self.env['contract.change.order.line']
                add_line = ChangeOrderLine.search([
                    ('change_order_id', '=', task.change_order_id.id),
                    ('change_type', '=', 'add'),
                    ('item_no', '=', task.item_no),
                ], limit=1)
                if add_line:
                    task.change_type = 'added'
                else:
                    task.change_type = 'modified'
