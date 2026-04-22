# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectTask(models.Model):
    """
    契約工項 - 契約變更關聯擴展 (v5.2)

    擴展 project.task 支援：
    - 關聯契約變更單
    - 追蹤工項由哪次變更新增/修改
    - 支援多次變更記錄
    """
    _inherit = 'project.task'

    # === 契約變更關聯 ===
    change_order_id = fields.Many2one(
        'contract.change.order',
        string='最後變更單',
        index=True,
        help='最後一次影響此工項的契約變更單（向下相容）')
    
    change_order_ids = fields.Many2many(
        'contract.change.order',
        'task_change_order_rel',
        'task_id',
        'change_order_id',
        string='歷次契約變更',
        help='所有影響此工項的契約變更單')

    change_order_name = fields.Char(
        string='變更單編號',
        related='change_order_id.name',
        store=True)
    
    change_history_display = fields.Char(
        string='變更紀錄',
        compute='_compute_change_history_display',
        store=True,
        help='格式：第N次契約變更(欄位)；第M次契約變更(欄位)')

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

    # === 原始契約數量（供估驗計價使用）===
    original_planned_qty = fields.Float(
        string='原始契約數量',
        digits=(16, 4),
        help='契約變更前的原始數量，首次變更時自動凍結')

    # === 計算欄位 ===
    @api.depends('change_order_ids', 'change_order_ids.state')
    def _compute_change_history_display(self):
        """計算變更紀錄顯示文字"""
        for task in self:
            if not task.change_order_ids:
                task.change_history_display = False
                continue
            
            # 只顯示已套用的變更單
            applied_orders = task.change_order_ids.filtered(
                lambda o: o.state == 'applied'
            ).sorted(key=lambda o: o.sequence)
            
            if not applied_orders:
                task.change_history_display = False
                continue
            
            # 組合變更紀錄
            change_records = []
            
            for order in applied_orders:
                # 找出此變更單中與此工項相關的明細
                lines = order.line_ids.filtered(
                    lambda l: l.task_id == task or 
                    (l.change_type == 'add' and l.item_no == task.item_no)
                )
                
                if lines:
                    # 收集被變更的欄位
                    changed_fields = set()
                    for line in lines:
                        if line.change_type == 'add':
                            changed_fields.add('新增')
                        elif line.change_type == 'delete':
                            changed_fields.add('刪除')
                        else:  # modify
                            if line.qty_change != 0:
                                changed_fields.add('數量')
                            if line.price_change != 0:
                                changed_fields.add('單價')
                    
                    if changed_fields:
                        fields_str = '、'.join(sorted(changed_fields))
                        change_records.append(
                            f'第{order.sequence}次契約變更({fields_str})'
                        )
            
            task.change_history_display = '；'.join(change_records) if change_records else False
    
    @api.depends('change_order_id')
    def _compute_is_change_item(self):
        for task in self:
            task.is_change_item = bool(task.change_order_id)

    @api.depends('change_order_id')
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
