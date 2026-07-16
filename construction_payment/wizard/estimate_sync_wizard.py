# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EstimateSyncWizard(models.TransientModel):
    """
    同步估驗計價工項精靈

    在契約變更單套用後，將指定日期之後（草稿/待核定狀態）的估驗計價單
    工項清單與「變更後核定數量」同步至最新的契約內容：
    1. 更新現有明細行的 approved_qty → task.planned_qty
    2. 新增缺少的工項明細行（estimate_qty = 0）
    已核定或已歸檔的估驗單不受影響。
    """
    _name = 'estimate.sync.wizard'
    _description = '同步估驗計價工項'

    change_order_id = fields.Many2one(
        'contract.change.order',
        '來源契約變更單',
        readonly=True,
        required=True,
    )
    project_id = fields.Many2one(
        'project.project',
        '所屬工程',
        related='change_order_id.project_id',
        readonly=True,
    )
    sync_from_date = fields.Date(
        '同步基準日期',
        required=True,
        help='估驗日期（含）大於或等於此日期的草稿/待核定估驗計價單才會被更新',
    )
    affected_estimate_count = fields.Integer(
        '預計受影響的估驗單數',
        compute='_compute_affected_estimate_count',
        readonly=True,
    )

    @api.depends('project_id', 'sync_from_date')
    def _compute_affected_estimate_count(self):
        for wiz in self:
            if not wiz.project_id or not wiz.sync_from_date:
                wiz.affected_estimate_count = 0
                continue
            count = self.env['payment.estimate'].search_count([
                ('project_id', '=', wiz.project_id.id),
                ('state', 'in', ('draft', 'pending_approval')),
                ('estimate_date', '>=', wiz.sync_from_date),
            ])
            wiz.affected_estimate_count = count

    def action_sync(self):
        """執行同步：更新工項清單與核定數量"""
        self.ensure_one()
        if not self.project_id:
            raise UserError('找不到所屬工程')

        # 取得需要同步的估驗計價單（草稿/待核定，且估驗日期 >= 基準日）
        estimates = self.env['payment.estimate'].search([
            ('project_id', '=', self.project_id.id),
            ('state', 'in', ('draft', 'pending_approval')),
            ('estimate_date', '>=', self.sync_from_date),
        ])

        if not estimates:
            raise UserError('找不到符合條件的估驗計價單（草稿/待核定，且建立日期 >= 基準日期）')

        # 取得工程目前有效的全部工項（含彙總項，彙總列以「一式」呈現）
        current_tasks = self.env['project.task'].search([
            ('supervision_project_id', '=', self.project_id.id),
            ('active', '=', True),
        ], order='sequence, id')
        current_task_ids = set(current_tasks.ids)

        EstimateLine = self.env['payment.estimate.line'].with_context(
            tracking_disable=True,
        )

        synced_count = 0
        for estimate in estimates:
            existing_task_ids = set(estimate.line_ids.mapped('task_id').ids)

            # 1. 更新現有行的 approved_qty（彙總列正規化為 1）
            for line in estimate.line_ids:
                if line.task_id and line.task_id.id in current_task_ids:
                    if line.is_summary_item:
                        line.approved_qty = 1.0
                    else:
                        line.approved_qty = line.task_id.planned_qty

            # 2. 新增缺少的工項行（彙總列「一式」qty=1）
            missing_tasks = current_tasks.filtered(
                lambda t: t.id not in existing_task_ids
            )
            if missing_tasks:
                line_vals = []
                for task in missing_tasks:
                    vals = EstimateLine._prepare_line_vals(task, task.sequence or 10)
                    vals['estimate_id'] = estimate.id
                    line_vals.append(vals)
                EstimateLine.create(line_vals)

            synced_count += 1

        _logger.info(
            '同步完成：共更新 %d 筆估驗計價單（工程=%s）',
            synced_count,
            self.project_id.code,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '同步完成',
                'message': f'已更新 {synced_count} 筆估驗計價單的工項清單與核定數量。',
                'type': 'success',
                'sticky': False,
            },
        }
