# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class NotificationAcceptance(models.Model):
    """
    通報單驗收單

    設計特點:
    - 狀態機制: draft -> accept -> cancel
    - 數量追蹤與驗證
    - 驗收後自動更新通報單狀態
    """
    _name = 'notification.acceptance'
    _description = '通報單驗收單'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'acceptance_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='驗收單號', required=True, copy=False, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('notification.acceptance') or '/')

    slip_id = fields.Many2one(
        'reservation.notification.slip', string='通報單',
        required=True, index=True,
        domain=[('state', 'in', ['approved', 'in_progress'])],
        tracking=True)

    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        related='slip_id.project_id', store=True)

    company_id = fields.Many2one(
        'res.company', string='公司',
        related='slip_id.company_id', store=True)

    currency_id = fields.Many2one(
        'res.currency', string='幣別',
        related='slip_id.currency_id', store=True)

    # === 驗收資訊 ===
    acceptance_date = fields.Date(
        string='驗收日期', required=True,
        default=fields.Date.today,
        tracking=True)

    acceptance_type = fields.Selection([
        ('preliminary', '初驗'),
        ('partial', '部分驗收'),
        ('final', '正驗'),
    ], string='驗收類型', required=True, default='final',
       tracking=True)

    acceptance_no = fields.Integer(
        string='驗收次數',
        help='本通報單的第幾次驗收',
        compute='_compute_acceptance_no', store=True)

    # === 驗收人員 ===
    acceptor_id = fields.Many2one(
        'res.users', string='驗收人員',
        default=lambda self: self.env.uid,
        tracking=True)

    witness_ids = fields.Many2many(
        'res.users', 'notification_acceptance_witness_rel',
        'acceptance_id', 'user_id',
        string='會同人員')

    # === 驗收明細 ===
    line_ids = fields.One2many(
        'notification.acceptance.line', 'acceptance_id',
        string='驗收明細')

    line_count = fields.Integer(
        string='明細數量',
        compute='_compute_line_count')

    # === 金額彙總 ===
    total_qty_accepted = fields.Float(
        string='驗收總數量',
        compute='_compute_totals', store=True,
        digits=(16, 4))

    total_accepted_amount = fields.Monetary(
        string='驗收總金額',
        currency_field='currency_id',
        compute='_compute_totals', store=True)

    # === 驗收結果 ===
    has_defect = fields.Boolean(
        string='是否有缺失', default=False)

    defect_description = fields.Text(
        string='缺失說明')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment', 'notification_acceptance_attachment_rel',
        'acceptance_id', 'attachment_id',
        string='驗收資料')

    photo_ids = fields.Many2many(
        'ir.attachment', 'notification_acceptance_photo_rel',
        'acceptance_id', 'attachment_id',
        string='驗收照片')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('accept', '已驗收'),
        ('cancel', '取消'),
    ], string='狀態', default='draft', tracking=True, index=True,
       help='驗收單狀態: draft -> accept | cancel')

    # === 備註 ===
    notes = fields.Text(string='備註')

    # === 計算方法 ===
    @api.depends('slip_id', 'slip_id.acceptance_ids')
    def _compute_acceptance_no(self):
        for rec in self:
            if rec.slip_id:
                # 計算本次是第幾次驗收
                previous = rec.slip_id.acceptance_ids.filtered(
                    lambda a: a.id < rec.id or (a.id == rec.id)
                ).sorted('id')
                rec.acceptance_no = len(previous)
            else:
                rec.acceptance_no = 0

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('line_ids.qty_accepted', 'line_ids.accepted_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_qty_accepted = sum(rec.line_ids.mapped('qty_accepted'))
            rec.total_accepted_amount = sum(rec.line_ids.mapped('accepted_amount'))

    # === onchange 方法 ===
    @api.onchange('slip_id')
    def _onchange_slip_id(self):
        """當選擇通報單時，自動帶入待驗收項目"""
        if self.slip_id:
            lines = []
            for slip_line in self.slip_id.detail_line_ids:
                if slip_line.qty_remaining > 0:
                    lines.append(Command.create({
                        'slip_line_id': slip_line.id,
                        'qty_accepted': slip_line.qty_remaining,
                    }))
            self.line_ids = lines

    # === 動作方法 ===
    def action_accept(self):
        """確認驗收"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('只有草稿狀態可以確認驗收')
            if not rec.line_ids:
                raise ValidationError('請先填寫驗收明細')

            # 驗證所有明細
            for line in rec.line_ids:
                if line.qty_accepted <= 0:
                    raise ValidationError(
                        f'項目 {line.item_no}: 驗收數量必須大於 0'
                    )
                if line.qty_accepted > line.qty_to_accept:
                    raise ValidationError(
                        f'項目 {line.item_no}: 驗收數量 ({line.qty_accepted}) '
                        f'不得超過待驗收數量 ({line.qty_to_accept})'
                    )

            # 更新通報單明細的 qty_accepted
            for line in rec.line_ids:
                if line.slip_line_id:
                    line.slip_line_id.qty_accepted += line.qty_accepted

            # 檢查通報單是否全部驗收完成
            slip = rec.slip_id
            all_accepted = all(
                sl.qty_remaining <= 0 for sl in slip.detail_line_ids
            )

            if all_accepted:
                # 更新通報單狀態為已完成
                slip.write({
                    'state': 'completed',
                    'acceptance_id': rec.id,
                })
            elif slip.state == 'approved':
                # 如果是第一次驗收，更新為執行中
                slip.write({'state': 'in_progress'})

            rec.write({'state': 'accept'})

    def action_cancel(self):
        """取消驗收"""
        for rec in self:
            if rec.state == 'accept':
                # 回退 qty_accepted
                for line in rec.line_ids:
                    if line.slip_line_id:
                        new_qty = line.slip_line_id.qty_accepted - line.qty_accepted
                        line.slip_line_id.qty_accepted = max(0, new_qty)

                # 如果通報單因此驗收而標記完成，則回退狀態
                slip = rec.slip_id
                if slip.acceptance_id == rec:
                    slip.write({
                        'state': 'in_progress',
                        'acceptance_id': False,
                    })

            rec.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """重設為草稿"""
        for rec in self:
            if rec.state != 'cancel':
                raise UserError('只有取消狀態可以重設為草稿')
            rec.write({'state': 'draft'})

    # === 其他方法 ===
    def action_load_pending_lines(self):
        """載入待驗收項目"""
        self.ensure_one()
        if not self.slip_id:
            raise UserError('請先選擇通報單')

        existing_line_ids = self.line_ids.mapped('slip_line_id').ids
        new_lines = []

        for slip_line in self.slip_id.detail_line_ids:
            if slip_line.qty_remaining > 0 and slip_line.id not in existing_line_ids:
                new_lines.append(Command.create({
                    'slip_line_id': slip_line.id,
                    'qty_accepted': slip_line.qty_remaining,
                }))

        if new_lines:
            self.write({'line_ids': new_lines})
        else:
            raise UserError('沒有新的待驗收項目')

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'notification.acceptance') or '/'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state == 'accept':
                raise UserError('已驗收的單據無法刪除，請先取消')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': self.env['ir.sequence'].next_by_code('notification.acceptance') or '/',
            'state': 'draft',
            'acceptance_date': fields.Date.today(),
        })
        return super().copy(default)
