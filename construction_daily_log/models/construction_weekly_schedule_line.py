# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ConstructionWeeklyScheduleLine(models.Model):
    """施工排程明細"""
    _name = 'construction.weekly.schedule.line'
    _description = '施工排程明細'
    _order = 'sequence, id'

    schedule_id = fields.Many2one(
        'construction.weekly.schedule',
        string='排程',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='排序', default=10)

    # === 工項 ===
    task_id = fields.Many2one(
        'project.task',
        string='施工項目',
        required=True,
        ondelete='cascade',
    )

    # === Related 欄位（唯讀） ===
    task_name = fields.Char(related='task_id.name', string='施工項目名稱')
    parent_id = fields.Many2one(related='task_id.parent_id', string='父工項')
    parent_item_path = fields.Char(related='task_id.parent_id.full_item_path', string='父工項路徑')
    item_no = fields.Char(related='task_id.item_no', string='完整項次')
    display_item_no = fields.Char(related='task_id.display_item_no', string='項次')
    unit = fields.Char(related='task_id.unit', string='單位')
    planned_qty = fields.Float(related='task_id.planned_qty', string='契約數量')
    actual_qty = fields.Float(
        related='task_id.actual_qty',
        string='累計完成數量',
        digits=(16, 4),
    )

    # === 排程欄位（可編輯） ===
    need_inspection = fields.Boolean(
        string='本周安排自主檢查',
        default=False,
    )

    # === Computed ===
    has_inspection_type = fields.Boolean(
        string='自主檢查工項',
        compute='_compute_has_inspection_type',
        help='此工項是否有對應的自主檢查表類型',
    )

    company_id = fields.Many2one(
        related='schedule_id.company_id',
        store=True,
    )

    @api.constrains('need_inspection')
    def _check_need_inspection(self):
        for line in self:
            if line.need_inspection and not line.has_inspection_type:
                task_name = line.task_id.name if line.task_id else ''
                raise ValidationError(
                    f'工項「{task_name}」尚未設定自主檢查類型，無法勾選「本周安排自主檢查」。\n'
                    '請先至自主檢查類型設定頁面建立對應的檢查類型。'
                )

    @api.depends('task_id')
    def _compute_has_inspection_type(self):
        """檢查工項是否有對應的自主檢查表類型"""
        for line in self:
            if line.task_id:
                # 搜尋是否有關聯此工項的 inspection type
                # 搜尋 self.inspection.type 中關聯此工項的類型
                count = self.env['self.inspection.type'].search_count([
                    ('task_ids', 'in', line.task_id.id),
                ]) if 'self.inspection.type' in self.env else 0
                line.has_inspection_type = count > 0
            else:
                line.has_inspection_type = False
