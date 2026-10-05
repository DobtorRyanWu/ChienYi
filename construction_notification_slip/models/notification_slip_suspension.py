# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ReservationNotificationSlipSuspension(models.Model):
    """通報單停工紀錄（一次停工一列，可多次停工）。

    停工天數＝復工日 − 停工日（不含復工當天）。實例：北搶 111-19 第 12 通
    6/21 停工、7/18 復工 → 27 天，監造管理表的預定竣工日正好由 7/7 順延到 8/3。

    為什麼獨立一張表而不是在通報單上放「累計停工天數」：天數由日期算出來才能驗算，
    事後更正某一次的日期會自動重算；手動累加的天數改錯了系統無從發現。
    """
    _name = 'reservation.notification.slip.suspension'
    _description = '通報單停工紀錄'
    _order = 'suspend_date, id'

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, ondelete='cascade', index=True)

    suspend_date = fields.Date(string='停工日', required=True)

    resume_date = fields.Date(
        string='復工日',
        help='空白＝仍在停工中')

    reason = fields.Text(string='停工原因', required=True)

    note = fields.Char(string='備註')

    days = fields.Integer(
        string='停工天數',
        compute='_compute_days', store=True,
        help='復工日 − 停工日；仍在停工中為 0（復工後才計入）')

    @api.depends('suspend_date', 'resume_date')
    def _compute_days(self):
        for rec in self:
            if rec.suspend_date and rec.resume_date:
                rec.days = max(0, (rec.resume_date - rec.suspend_date).days)
            else:
                rec.days = 0

    @api.constrains('suspend_date', 'resume_date', 'slip_id')
    def _check_dates(self):
        for rec in self:
            slip = rec.slip_id
            if rec.resume_date and rec.resume_date < rec.suspend_date:
                raise ValidationError(
                    f'復工日（{rec.resume_date}）不可早於停工日（{rec.suspend_date}）')
            if slip.actual_start_date and rec.suspend_date < slip.actual_start_date:
                raise ValidationError(
                    f'停工日（{rec.suspend_date}）不可早於實際開工日（{slip.actual_start_date}）')
            # 依停工日排序後，每一段都要在前一段復工之後才開始
            periods = slip.suspension_ids.sorted(lambda s: (s.suspend_date, s.id))
            for prev, nxt in zip(periods, periods[1:]):
                if not prev.resume_date or nxt.suspend_date < prev.resume_date:
                    raise ValidationError(
                        f'{slip.name}：停工期間重疊（{prev.suspend_date}～'
                        f'{prev.resume_date or "未復工"} 與 {nxt.suspend_date} 起）')
            slip._check_suspension_consistency()

    @api.model_create_multi
    def create(self, vals_list):
        slips = self.env['reservation.notification.slip'].browse(
            [v.get('slip_id') for v in vals_list if v.get('slip_id')])
        slips._check_not_cancelled_for_children('停工紀錄')
        return super().create(vals_list)

    def write(self, vals):
        self.mapped('slip_id')._check_not_cancelled_for_children('停工紀錄')
        return super().write(vals)

    def unlink(self):
        slips = self.mapped('slip_id')
        slips._check_not_cancelled_for_children('停工紀錄')
        if any(s.state == 'suspended' for s in slips):
            open_lines = self.filtered(lambda s: not s.resume_date)
            if open_lines:
                raise UserError('停工中的通報單不能刪除未復工的那一筆停工紀錄，請用「復工」')
        return super().unlink()
