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

    def action_schedule_recheck(self):
        """安排複查"""
        self.ensure_one()
        if self.state not in ('notified', 'improving'):
            raise UserError('只有已通知或改善中狀態可以安排複查')
        self.write({
            'recheck_date': fields.Date.today(),
            'recheck_result': 'pending',
        })
        return True

    def action_recheck_pass(self):
        """複查通過 → 標記為已改善"""
        self.ensure_one()
        if not self.recheck_date:
            raise UserError('請先設定複查日期')
        self.write({
            'recheck_result': 'pass',
            'state': 'improved',
            'improvement_date': fields.Date.today(),
            'verifier_id': self.env.uid,
            'verify_date': fields.Date.today(),
            'improvement_progress': 100,
        })
        return True

    def action_recheck_fail(self):
        """複查不通過"""
        self.ensure_one()
        if not self.recheck_date:
            raise UserError('請先設定複查日期')
        self.write({
            'recheck_result': 'fail',
            'recheck_date': False,
        })
        return True

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
    @api.constrains('improvement_progress')
    def _check_improvement_progress(self):
        """驗證改善進度"""
        for record in self:
            if record.improvement_progress < 0 or record.improvement_progress > 100:
                raise ValidationError('改善進度必須在 0-100 之間')

    @api.constrains('slip_id', 'notification_date')
    def _check_notification_date(self):
        """驗證通知日期在通報單工期內"""
        for record in self:
            if record.slip_id and record.notification_date:
                slip = record.slip_id
                if slip.planned_start_date and record.notification_date < slip.planned_start_date:
                    raise ValidationError(
                        f'通知改善日期 ({record.notification_date}) 不得早於'
                        f'通報單預定開工日 ({slip.planned_start_date})')

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
