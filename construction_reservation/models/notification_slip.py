# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ReservationNotificationSlipReservation(models.Model):
    """
    通報單擴展 - 預約式工程專用

    擴展說明：
    - 整合自主檢查關聯
    - 整合缺失改善關聯
    - 提供統計資訊
    - 提供快速建立功能
    """
    _inherit = 'reservation.notification.slip'

    # === 自主檢查關聯 ===
    self_inspection_ids = fields.One2many(
        'reservation.self.inspection',
        'slip_id',
        string='自主檢查記錄')

    self_inspection_count = fields.Integer(
        string='自主檢查數',
        compute='_compute_self_inspection_stats',
        store=True)

    self_inspection_defect_count = fields.Integer(
        string='檢查缺失數',
        compute='_compute_self_inspection_stats',
        store=True,
        help='自主檢查中發現的缺失項目數量')

    self_inspection_confirmed_count = fields.Integer(
        string='已確認檢查數',
        compute='_compute_self_inspection_stats',
        store=True)

    # === 缺失改善關聯 ===
    defect_improvement_ids = fields.One2many(
        'reservation.defect.improvement',
        'slip_id',
        string='缺失改善記錄')

    defect_improvement_count = fields.Integer(
        string='缺失改善數',
        compute='_compute_defect_improvement_stats',
        store=True)

    defect_uncorrected_count = fields.Integer(
        string='未矯正數',
        compute='_compute_defect_improvement_stats',
        store=True,
        help='狀態為未矯正或逾時未矯正的缺失數量')

    defect_corrected_count = fields.Integer(
        string='已矯正數',
        compute='_compute_defect_improvement_stats',
        store=True)

    defect_overdue_count = fields.Integer(
        string='逾期缺失數',
        compute='_compute_defect_improvement_stats',
        store=True,
        help='已逾期的缺失數量')

    # === 品質指標 ===
    quality_pass_rate = fields.Float(
        string='品質合格率 (%)',
        compute='_compute_quality_metrics',
        store=True,
        digits=(5, 2),
        help='(無缺失項目數 / 總檢查項目數) x 100')

    defect_closure_rate = fields.Float(
        string='缺失結案率 (%)',
        compute='_compute_quality_metrics',
        store=True,
        digits=(5, 2),
        help='(已矯正+符合要求) / 總缺失數 x 100')

    # === 計算方法 ===
    @api.depends('self_inspection_ids', 'self_inspection_ids.state',
                 'self_inspection_ids.has_defect', 'self_inspection_ids.defect_count')
    def _compute_self_inspection_stats(self):
        for slip in self:
            inspections = slip.self_inspection_ids
            slip.self_inspection_count = len(inspections)
            slip.self_inspection_confirmed_count = len(
                inspections.filtered(lambda r: r.state == 'confirmed'))
            slip.self_inspection_defect_count = sum(
                inspections.mapped('defect_count'))

    @api.depends('defect_improvement_ids', 'defect_improvement_ids.state',
                 'defect_improvement_ids.is_overdue')
    def _compute_defect_improvement_stats(self):
        for slip in self:
            defects = slip.defect_improvement_ids
            slip.defect_improvement_count = len(defects)
            slip.defect_uncorrected_count = len(
                defects.filtered(lambda r: r.state in ('uncorrected', 'overdue')))
            slip.defect_corrected_count = len(
                defects.filtered(lambda r: r.state in ('corrected', 'conform')))
            slip.defect_overdue_count = len(
                defects.filtered(lambda r: r.is_overdue))

    @api.depends('self_inspection_ids.checklist_ids.check_result',
                 'defect_improvement_ids', 'defect_improvement_ids.state')
    def _compute_quality_metrics(self):
        for slip in self:
            # 計算品質合格率
            all_items = slip.self_inspection_ids.mapped('checklist_ids')
            total_items = len(all_items.filtered(lambda x: x.check_result != 'na'))
            pass_items = len(all_items.filtered(lambda x: x.check_result == 'pass'))
            if total_items > 0:
                slip.quality_pass_rate = (pass_items / total_items) * 100
            else:
                slip.quality_pass_rate = 0.0

            # 計算缺失結案率
            total_defects = len(slip.defect_improvement_ids)
            closed_defects = len(
                slip.defect_improvement_ids.filtered(
                    lambda r: r.state in ('corrected', 'conform')))
            if total_defects > 0:
                slip.defect_closure_rate = (closed_defects / total_defects) * 100
            else:
                slip.defect_closure_rate = 100.0

    # === 動作方法 ===
    def action_view_self_inspections(self):
        """查看自主檢查記錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '自主檢查記錄',
            'res_model': 'reservation.self.inspection',
            'view_mode': 'list,form',
            'domain': [('slip_id', '=', self.id)],
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_view_defect_improvements(self):
        """查看缺失改善記錄"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '缺失改善記錄',
            'res_model': 'reservation.defect.improvement',
            'view_mode': 'list,kanban,form',
            'domain': [('slip_id', '=', self.id)],
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_view_uncorrected_defects(self):
        """查看未矯正缺失"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '未矯正缺失',
            'res_model': 'reservation.defect.improvement',
            'view_mode': 'list,kanban,form',
            'domain': [
                ('slip_id', '=', self.id),
                ('state', 'in', ('uncorrected', 'overdue'))
            ],
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_create_self_inspection(self):
        """建立自主檢查"""
        self.ensure_one()
        if self.state not in ('approved', 'in_progress'):
            raise UserError('只有已核准或執行中的通報單可以建立自主檢查')

        return {
            'type': 'ir.actions.act_window',
            'name': '新增自主檢查',
            'res_model': 'reservation.self.inspection',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_create_defect_improvement(self):
        """建立缺失改善記錄"""
        self.ensure_one()
        if self.state not in ('approved', 'in_progress'):
            raise UserError('只有已核准或執行中的通報單可以建立缺失改善')

        return {
            'type': 'ir.actions.act_window',
            'name': '新增缺失改善',
            'res_model': 'reservation.defect.improvement',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_slip_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_create_defect_from_inspection(self):
        """從自主檢查缺失項目建立缺失改善記錄"""
        self.ensure_one()

        # 找出有缺失但尚未建立改善記錄的檢查項目
        defect_items = self.self_inspection_ids.mapped('checklist_ids').filtered(
            lambda x: x.check_result == 'defect' and not x.defect_improvement_id
        )

        if not defect_items:
            raise UserError('沒有需要建立缺失改善記錄的檢查項目')

        created_count = 0
        for item in defect_items:
            inspection = item.inspection_id
            vals = {
                'slip_id': self.id,
                'check_type': 'construction',
                'defect_description': f'[{inspection.inspection_no}] {item.check_item}\n實際情形: {item.actual_result or ""}',
                'defect_location': inspection.inspection_location or self.location,
                'notification_date': fields.Date.today(),
            }
            defect = self.env['reservation.defect.improvement'].create(vals)
            item.defect_improvement_id = defect.id
            created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '建立成功',
                'message': f'已建立 {created_count} 筆缺失改善記錄',
                'type': 'success',
                'sticky': False,
            }
        }

    # === 完成驗證擴展 ===
    def action_complete(self):
        """完成通報單 - 擴展驗證"""
        for rec in self:
            # 檢查未結案的缺失
            uncorrected = rec.defect_improvement_ids.filtered(
                lambda r: r.state in ('uncorrected', 'overdue'))
            if uncorrected:
                raise ValidationError(
                    f'尚有 {len(uncorrected)} 筆未矯正的缺失改善記錄，'
                    '請先處理後再完成通報單')

        return super().action_complete()
