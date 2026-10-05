# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ReservationNotificationSlipStateWizard(models.TransientModel):
    """停工／復工／退單共用一個精靈（一張暫存表，不是三張）。

    精靈只負責收輸入；真正的狀態轉換在通報單的 action_suspend／action_resume／
    action_cancel_slip，匯入工具以 RPC 直接呼叫同一組方法。
    """
    _name = 'reservation.notification.slip.state.wizard'
    _description = '通報單停工／復工／退單'

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單', required=True)
    project_id = fields.Many2one(related='slip_id.project_id')
    mode = fields.Selection([
        ('suspend', '停工'),
        ('resume', '復工'),
        ('cancel', '退單'),
    ], required=True)

    # 停工／復工
    suspend_date = fields.Date(string='停工日', default=fields.Date.context_today)
    suspend_reason = fields.Text(string='停工原因')
    open_suspend_date = fields.Date(string='本次停工日', compute='_compute_open_suspension')
    open_suspend_reason = fields.Text(string='本次停工原因', compute='_compute_open_suspension')
    resume_date = fields.Date(string='復工日', default=fields.Date.context_today)

    # 退單
    cancel_reason = fields.Selection([
        ('return', '退單'),
        ('merge', '合併'),
        ('other', '其他'),
    ], string='退單原因', default='return')
    cancel_date = fields.Date(string='退單日期', default=fields.Date.context_today)
    cancel_note = fields.Text(string='說明')
    merged_into_slip_id = fields.Many2one(
        'reservation.notification.slip', string='併入的通報單',
        domain="[('project_id', '=', project_id), ('id', '!=', slip_id), ('state', '!=', 'cancelled')]")
    linked_summary = fields.Text(string='仍掛在本單的資料', compute='_compute_linked_summary')

    @api.depends('slip_id')
    def _compute_open_suspension(self):
        for wiz in self:
            line = wiz.slip_id.suspension_ids.filtered(lambda s: not s.resume_date)[:1]
            wiz.open_suspend_date = line.suspend_date
            wiz.open_suspend_reason = line.reason

    @api.depends('slip_id')
    def _compute_linked_summary(self):
        """退單不擋「已經掛在本單上的紀錄」，但要讓人在按下去之前看到。

        西區 111-16 第 7 通就是停工、查驗之後才退單，真的會有檢查紀錄；
        這些紀錄維持掛在本單（歷史），要不要搬到別一通由人決定。
        """
        for wiz in self:
            slip = wiz.slip_id
            parts = []
            counts = [
                ('自主檢查', 'reservation.self.inspection', 'slip_id'),
                ('缺失改善', 'reservation.defect.improvement', 'slip_id'),
                ('施工日誌', 'daily.log.sheet', 'notification_slip_id'),
            ]
            for label, model, field in counts:
                if slip and model in self.env and field in self.env[model]._fields:
                    n = self.env[model].search_count([(field, '=', slip.id)])
                    if n:
                        parts.append(f'{label} {n} 筆')
            if slip.related_photo_count:
                parts.append(f'照片 {slip.related_photo_count} 張')
            if slip.merged_slip_ids:
                parts.append('併入本單的通報單 ' + '、'.join(slip.merged_slip_ids.mapped('name')))
            wiz.linked_summary = '、'.join(parts)

    def action_confirm(self):
        self.ensure_one()
        slip = self.slip_id
        if self.mode == 'suspend':
            slip.action_suspend(self.suspend_date, self.suspend_reason)
        elif self.mode == 'resume':
            slip.action_resume(self.resume_date)
        else:
            slip.action_cancel_slip(
                cancel_reason=self.cancel_reason,
                cancel_date=self.cancel_date,
                cancel_note=self.cancel_note,
                merged_into_slip_id=self.merged_into_slip_id.id)
        return {'type': 'ir.actions.act_window_close'}
