# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api
from odoo.exceptions import UserError


class ManMachineCopyWizard(models.TransientModel):
    """
    人機項目複製精靈
    
    允許將選中的人機項目批次複製到其他工程，並可逐項調整單價
    """
    _name = 'daily.log.man.machine.copy.wizard'
    _description = '人機項目複製精靈'

    # === 目標工程 ===
    target_project_id = fields.Many2one(
        'supervision.project',
        string='目標工程',
        required=True,
        help='選擇要複製到的目標工程')

    # === 明細清單 ===
    line_ids = fields.One2many(
        'daily.log.man.machine.copy.wizard.line',
        'wizard_id',
        string='複製項目明細')

    # === 摘要資訊 ===
    source_count = fields.Integer(
        string='記錄數量',
        compute='_compute_source_count')

    @api.depends('line_ids')
    def _compute_source_count(self):
        """計算記錄數量"""
        for wizard in self:
            wizard.source_count = len(wizard.line_ids)

    @api.model
    def default_get(self, fields_list):
        """初始化精靈時，自動建立明細行"""
        res = super().default_get(fields_list)
        
        # 取得選中的記錄
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            return res
            
        source_records = self.env['daily.log.man.machine'].browse(active_ids)
        
        # 為每個選中記錄建立明細行
        lines = []
        for record in source_records:
            lines.append((0, 0, {
                'source_id': record.id,
                'source_name': record.name_get()[0][1],
                'original_price': record.unit_price,
                'new_price': record.unit_price,
                'adjust_mode': 'keep',
            }))
        
        res['line_ids'] = lines
        return res

    def action_copy(self):
        """執行複製"""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError('沒有要複製的項目')
        
        if not self.target_project_id:
            raise UserError('請選擇目標工程')
        
        # 執行複製
        copied_count = 0
        for line in self.line_ids:
            source = line.source_id
            
            # 準備複製的值
            vals = {
                'project_id': self.target_project_id.id,
                'record_type': source.record_type,
                'personnel_type_id': source.personnel_type_id.id if source.personnel_type_id else False,
                'equipment_name': source.equipment_name,
                'equipment_number': source.equipment_number,
                'unit': source.unit,
                'unit_price': line.new_price,
                'note': source.note,
            }
            
            # 創建新記錄
            self.env['daily.log.man.machine'].create(vals)
            copied_count += 1
        
        # 返回成功通知
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '複製成功',
                'message': f'已成功複製 {copied_count} 筆記錄到「{self.target_project_id.name}」',
                'type': 'success',
                'sticky': False,
            }
        }


class ManMachineCopyWizardLine(models.TransientModel):
    """
    人機項目複製精靈明細
    
    每一筆要複製的記錄都會有一個明細行，可以獨立調整單價
    """
    _name = 'daily.log.man.machine.copy.wizard.line'
    _description = '人機項目複製精靈明細'
    _order = 'sequence, id'

    sequence = fields.Integer(string='排序', default=10)

    wizard_id = fields.Many2one(
        'daily.log.man.machine.copy.wizard',
        string='精靈',
        required=True,
        ondelete='cascade')

    source_id = fields.Many2one(
        'daily.log.man.machine',
        string='來源記錄',
        required=True,
        readonly=True)

    source_name = fields.Char(
        string='項目名稱',
        readonly=True)

    original_price = fields.Float(
        string='原單價',
        readonly=True,
        digits='Product Price')

    # === 調整方式 ===
    adjust_mode = fields.Selection([
        ('keep', '保持不變'),
        ('fixed', '固定金額調整'),
        ('percentage', '百分比調整'),
    ], string='調整方式', default='keep', required=True)

    adjust_value = fields.Float(
        string='調整值',
        help='固定調整：+100 或 -50 表示增減金額；百分比：+10 或 -15 表示增減百分比')

    new_price = fields.Float(
        string='新單價',
        compute='_compute_new_price',
        store=True,
        readonly=False,
        digits='Product Price')

    # -------------------------------------------------------------------------
    # Compute Methods
    # -------------------------------------------------------------------------

    @api.depends('original_price', 'adjust_mode', 'adjust_value')
    def _compute_new_price(self):
        """根據調整方式計算新單價"""
        for line in self:
            if line.adjust_mode == 'keep':
                line.new_price = line.original_price
            elif line.adjust_mode == 'fixed':
                line.new_price = line.original_price + line.adjust_value
            elif line.adjust_mode == 'percentage':
                line.new_price = line.original_price * (1 + line.adjust_value / 100)
            else:
                line.new_price = line.original_price

    # -------------------------------------------------------------------------
    # Onchange Methods
    # -------------------------------------------------------------------------

    @api.onchange('adjust_mode')
    def _onchange_adjust_mode(self):
        """切換調整方式時，重置調整值"""
        if self.adjust_mode == 'keep':
            self.adjust_value = 0
