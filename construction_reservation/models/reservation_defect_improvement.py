# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ReservationDefectImprovementReservation(models.Model):
    """
    預約式缺失改善擴展

    擴展說明：
    - 增強與通報單的互動
    - 增強與自主檢查的關聯
    - 提供從驗收缺失建立改善記錄的功能
    """
    _inherit = 'reservation.defect.improvement'

    # === 通報單資訊擴展 ===
    slip_state = fields.Selection(
        related='slip_id.state',
        string='通報單狀態',
        store=True)

    slip_work_status = fields.Selection(
        related='slip_id.state',
        string='施作狀態',
        store=True)

    slip_location = fields.Char(
        related='slip_id.location',
        string='通報單地點',
        store=True)

    slip_number = fields.Char(
        related='slip_id.slip_number',
        string='通報單編號',
        store=True)

    # === 自主檢查來源 ===
    source_inspection_item_ids = fields.One2many(
        'reservation.self.inspection.item',
        'defect_improvement_id',
        string='來源檢查項目')

    source_inspection_count = fields.Integer(
        string='來源檢查項目數',
        compute='_compute_source_inspection_count')

    is_from_inspection = fields.Boolean(
        string='來自自主檢查',
        compute='_compute_is_from_inspection',
        store=True)

    # 單一來源（供「關聯與備註」頁籤以與一般式相同的三欄格式呈現）
    source_inspection_id = fields.Many2one(
        'reservation.self.inspection',
        string='來源自主檢查',
        compute='_compute_single_source')
    source_inspection_item_id = fields.Many2one(
        'reservation.self.inspection.item',
        string='來源檢查項目',
        compute='_compute_single_source')
    source_inspection_no = fields.Char(
        string='檢查編號',
        compute='_compute_single_source')

    @api.depends('source_inspection_item_ids')
    def _compute_single_source(self):
        for record in self:
            item = record.source_inspection_item_ids[:1]
            record.source_inspection_item_id = item
            record.source_inspection_id = item.inspection_id
            record.source_inspection_no = item.inspection_id.inspection_no

    # === 計算方法 ===
    @api.depends('source_inspection_item_ids')
    def _compute_source_inspection_count(self):
        for record in self:
            record.source_inspection_count = len(record.source_inspection_item_ids)

    @api.depends('source_inspection_item_ids')
    def _compute_is_from_inspection(self):
        for record in self:
            record.is_from_inspection = len(record.source_inspection_item_ids) > 0

    # === 動作方法 ===
    def action_view_source_inspections(self):
        """查看來源自主檢查"""
        self.ensure_one()
        inspection_ids = self.source_inspection_item_ids.mapped('inspection_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': '來源自主檢查',
            'res_model': 'reservation.self.inspection',
            'view_mode': 'list,form',
            'domain': [('id', 'in', inspection_ids)],
        }

    def action_reopen(self):
        """重新開啟 - 擴展"""
        for record in self:
            # 清除複查資訊
            record.write({
                'recheck_date': False,
                'recheck_result': False,
                'recheck_note': False,
                'improvement_progress': 0,
            })
        return super().action_reopen()

    # === 約束驗證 ===
    # 2026-11-20 回復原版（1118 會議）：拿掉「改善進度必須在 0-100 之間」——舊系統沒有範圍檢查

    @api.constrains('slip_id')
    def _check_slip_not_cancelled(self):
        """退單（作廢）的通報單不得再掛缺失改善（只在改掛通報單時檢查）。"""
        for record in self:
            if record.slip_id.state == 'cancelled':
                raise ValidationError(f'{record.slip_id.name} 已退單，不得掛缺失改善')

    # 2026-11-20 回復原版（1118 會議）：拿掉「通知改善日期不得早於通報單的最早起算日」——舊系統沒有日期先後檢查

    # === 建立方法擴展 ===
    @api.model
    def create_from_acceptance_defect(self, slip_id, defect_description, defect_location=False):
        """從通報單建立缺失改善記錄"""
        vals = {
            'slip_id': slip_id,
            'check_type': 'construction',
            'defect_description': defect_description,
            'defect_location': defect_location or '',
            'notification_date': fields.Date.today(),
        }
        return self.create(vals)
