# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectTaskVersion(models.Model):
    """擴展工項版本：新增變更次序欄位（需 contract.change.order 已載入）"""
    _inherit = 'project.task.version'

    change_sequence = fields.Integer(
        string='第幾次變更',
        compute='_compute_change_sequence')

    # 註：change_order_id 於 base 模組定義（跨模組前向參照 contract.change.order），
    #     故 depends 不traverse .change_no（避免註冊期 _unknown 解析失敗）；
    #     僅依賴 change_order_id，body 於執行期讀取 .change_no。
    @api.depends('change_order_id')
    def _compute_change_sequence(self):
        for v in self:
            # 用「本專案第幾次變更」(change_no)，不可用排序欄位 sequence(default=10)
            v.change_sequence = v.change_order_id.change_no if v.change_order_id else 0


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
    @api.depends('version_ids', 'version_ids.change_order_id',
                 'version_ids.planned_qty', 'version_ids.unit_price',
                 'change_order_ids.change_no')
    def _compute_change_history_display(self):
        """計算變更紀錄顯示文字（從 version_ids 計算，比較相鄰版本差異）"""
        for task in self:
            versions = task.version_ids.sorted(key=lambda v: v.version)
            if not versions:
                task.change_history_display = False
                continue

            records = []
            prev_qty = None
            prev_price = None

            for v in versions:
                if prev_qty is None:
                    # 第一個版本：判斷是否為變更單新增的工項
                    if v.change_order_id:
                        seq = v.change_order_id.change_no or '?'
                        records.append(f'第{seq}次契約變更(新增)')
                    # 原始契約工項（無變更單）不列入顯示
                    prev_qty = v.planned_qty
                    prev_price = v.unit_price
                    continue

                # 比較與上一版本的差異
                if v.change_order_id:
                    parts = []
                    if v.planned_qty != prev_qty:
                        parts.append('數量')
                    if v.unit_price != prev_price:
                        parts.append('單價')
                    if parts:
                        seq = v.change_order_id.change_no or '?'
                        records.append(f'第{seq}次契約變更({" ".join(parts)})')

                prev_qty = v.planned_qty
                prev_price = v.unit_price

            task.change_history_display = '；'.join(records) if records else False
    
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
