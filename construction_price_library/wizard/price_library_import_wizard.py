# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class PriceLibraryImportWizard(models.TransientModel):
    """
    價格庫匯入精靈

    將價格庫項目匯入契約工項 (project.task)

    使用場景：
    1. 建立新專案時，從價格庫快速匯入標準工項
    2. 新增工項時，參考價格庫的標準單價
    """
    _name = 'price.library.import.wizard'
    _description = '價格庫匯入精靈'

    # === 目標工程 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='目標工程',
        required=True,
        help='將價格項目匯入此工程案件')

    # === 篩選條件 ===
    category_id = fields.Many2one(
        'price.library.category',
        string='分類篩選',
        help='只顯示此分類下的項目')

    # === 選擇項目 ===
    item_ids = fields.Many2many(
        'price.library.item',
        'price_library_import_wizard_item_rel',
        'wizard_id',
        'item_id',
        string='選擇項目',
        help='選擇要匯入的價格庫項目')

    # === 匯入選項 ===
    import_qty = fields.Boolean(
        string='設定預設數量',
        default=False,
        help='勾選後可設定預設數量，否則數量為 0')

    default_qty = fields.Float(
        string='預設數量',
        default=1.0,
        digits=(16, 4),
        help='匯入時的預設數量')

    # === 計數資訊 ===
    selected_count = fields.Integer(
        string='已選擇項目數',
        compute='_compute_selected_count',
        help='已選擇的項目數量')

    total_amount = fields.Float(
        string='預估總金額',
        compute='_compute_total_amount',
        digits=(16, 2),
        help='選擇項目的預估總金額（依預設數量計算）')

    @api.depends('item_ids')
    def _compute_selected_count(self):
        """計算已選擇的項目數量"""
        for wizard in self:
            wizard.selected_count = len(wizard.item_ids)

    @api.depends('item_ids', 'import_qty', 'default_qty')
    def _compute_total_amount(self):
        """計算預估總金額"""
        for wizard in self:
            qty = wizard.default_qty if wizard.import_qty else 0
            wizard.total_amount = sum(
                item.unit_price * qty for item in wizard.item_ids
            )

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """當分類變更時，更新項目的 domain"""
        if self.category_id:
            return {
                'domain': {
                    'item_ids': [('category_id', '=', self.category_id.id)]
                }
            }
        return {
            'domain': {
                'item_ids': []
            }
        }

    # === 匯入動作 ===
    def action_import(self):
        """
        執行匯入

        將選擇的價格庫項目建立為契約工項 (project.task)
        """
        self.ensure_one()

        if not self.item_ids:
            raise UserError('請至少選擇一個價格項目')

        if not self.project_id.project_id:
            raise UserError('工程案件未關聯專案，無法建立工項')

        # 取得數量
        qty = self.default_qty if self.import_qty else 0

        # 準備工項資料
        task_vals_list = []
        for item in self.item_ids:
            task_vals_list.append({
                'project_id': self.project_id.project_id.id,
                'name': item.name,
                'item_no': item.item_no or '',
                'unit': item.unit,
                'unit_price': item.unit_price,
                'planned_qty': qty,
                'specification': item.specification or '',
                'construction_notes': item.description or '',
            })

        # 批次建立工項
        created_tasks = self.env['project.task'].create(task_vals_list)

        # 返回已建立的工項清單
        return {
            'type': 'ir.actions.act_window',
            'name': '已匯入的工項',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_tasks.ids)],
            'context': {
                'default_project_id': self.project_id.project_id.id,
            },
            'target': 'current',
        }

    def action_select_all(self):
        """選擇所有項目（依目前篩選條件）"""
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.category_id:
            domain.append(('category_id', '=', self.category_id.id))

        items = self.env['price.library.item'].search(domain)
        self.item_ids = [Command.set(items.ids)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'price.library.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_clear_selection(self):
        """清除選擇"""
        self.ensure_one()
        self.item_ids = [Command.clear()]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'price.library.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
