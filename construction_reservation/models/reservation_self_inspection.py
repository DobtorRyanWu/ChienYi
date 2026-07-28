# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ReservationSelfInspectionReservation(models.Model):
    """
    預約式自主檢查擴展

    擴展說明：
    - 增強與通報單的互動
    - 提供從缺失項目建立缺失改善記錄的功能
    - 增加工期驗證
    """
    _inherit = 'reservation.self.inspection'

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

    # === 缺失改善關聯 ===
    defect_improvement_ids = fields.One2many(
        'reservation.defect.improvement',
        compute='_compute_defect_improvement_ids',
        string='關聯缺失改善')

    defect_improvement_count = fields.Integer(
        string='缺失改善數',
        compute='_compute_defect_improvement_ids')

    # === 計算方法 ===
    @api.depends('checklist_ids.defect_improvement_id')
    def _compute_defect_improvement_ids(self):
        for record in self:
            improvements = record.checklist_ids.mapped('defect_improvement_id')
            record.defect_improvement_ids = improvements
            record.defect_improvement_count = len(improvements)

    # === 動作方法 ===
    def action_view_defect_improvements(self):
        """查看關聯的缺失改善記錄"""
        self.ensure_one()
        improvement_ids = self.checklist_ids.mapped('defect_improvement_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': '缺失改善記錄',
            'res_model': 'reservation.defect.improvement',
            'view_mode': 'list,form',
            'domain': [('id', 'in', improvement_ids)],
        }

    def action_create_defect_improvements(self):
        """開啟建立缺失改善 Wizard（選監造/營造），整張檢查的未建立缺失項"""
        self.ensure_one()

        defect_items = self.checklist_ids.filtered(
            lambda x: x.check_result == 'defect' and not x.defect_improvement_id
        )
        if not defect_items:
            raise UserError('沒有需要建立缺失改善記錄的檢查項目')

        return {
            'type': 'ir.actions.act_window',
            'name': '建立缺失改善',
            'res_model': 'create.reservation.defect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_inspection_id': self.id},
        }

    # === 約束驗證 ===
    @api.constrains('inspection_date', 'slip_id')
    def _check_inspection_date_in_slip_period(self):
        """驗證檢查日期在通報單工期內"""
        for record in self:
            if record.slip_id and record.inspection_date:
                slip = record.slip_id
                # 檢查是否在預定工期內
                if slip.planned_start_date and record.inspection_date < slip.planned_start_date:
                    raise ValidationError(
                        f'檢查日期 ({record.inspection_date}) 不得早於'
                        f'通報單預定開工日 ({slip.planned_start_date})')

    @api.constrains('slip_id')
    def _check_slip_state(self):
        """驗證通報單狀態：草稿階段的通報單不得建立自主檢查。

        注意：通報單的狀態流程是 draft → not_started → in_progress → closed
        （construction_notification_slip/models/notification_slip.py:128-134），
        沒有 approved / completed 這兩個值。
        """
        for record in self:
            if record.slip_id and record.slip_id.state not in (
                    'not_started', 'in_progress', 'closed'):
                raise ValidationError(
                    '草稿狀態的通報單不得建立自主檢查，請先確認通報單')


class ReservationSelfInspectionItemReservation(models.Model):
    """
    預約式自主檢查項目擴展

    擴展說明：
    - 新增缺失改善關聯欄位
    """
    _inherit = 'reservation.self.inspection.item'

    # === 缺失改善關聯 ===
    defect_improvement_id = fields.Many2one(
        'reservation.defect.improvement',
        string='關聯缺失改善',
        ondelete='set null',
        help='若此項目有缺失，關聯的缺失改善單')

    has_improvement = fields.Boolean(
        string='已建立改善',
        compute='_compute_has_improvement',
        store=True)

    improvement_state = fields.Selection(
        related='defect_improvement_id.state',
        string='改善狀態',
        store=True)

    @api.depends('defect_improvement_id')
    def _compute_has_improvement(self):
        for record in self:
            record.has_improvement = bool(record.defect_improvement_id)

    def action_view_improvement(self):
        """查看缺失改善記錄"""
        self.ensure_one()
        if not self.defect_improvement_id:
            raise UserError('尚未建立缺失改善記錄')

        return {
            'type': 'ir.actions.act_window',
            'name': '缺失改善記錄',
            'res_model': 'reservation.defect.improvement',
            'view_mode': 'form',
            'res_id': self.defect_improvement_id.id,
        }

    def action_create_improvement(self):
        """逐行建立缺失改善：開啟 wizard（選監造/營造），僅針對本項目"""
        self.ensure_one()
        if self.check_result != 'defect':
            raise UserError('只有缺失項目可以建立缺失改善記錄')
        if self.defect_improvement_id:
            raise UserError('已建立缺失改善記錄')

        return {
            'type': 'ir.actions.act_window',
            'name': '建立缺失改善',
            'res_model': 'create.reservation.defect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_inspection_id': self.inspection_id.id,
                'default_item_ids': [(6, 0, [self.id])],
            },
        }
