# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class ReservationDefectImprovement(models.Model):
    """
    預約式缺失改善 (通報單內)

    設計說明：
    - 綁定於通報單的缺失改善記錄
    - 用於預約式工程的缺失追蹤與改善
    - 與 reservation.notification.slip 關聯
    - 支援驗收缺失關聯
    """
    _name = 'reservation.defect.improvement'
    _description = '預約式缺失改善 (通報單內)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'notification_date desc, id desc'

    # === 通報單關聯 ===
    slip_id = fields.Many2one(
        'reservation.notification.slip',
        string='所屬通報單',
        required=True,
        ondelete='cascade',
        tracking=True)

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        related='slip_id.project_id',
        store=True)

    company_id = fields.Many2one(
        'res.company',
        string='公司',
        related='project_id.company_id',
        store=True)

    # === 驗收關聯 ===
    acceptance_id = fields.Many2one(
        'notification.acceptance',
        string='關聯驗收單',
        help='若為驗收時發現的缺失')

    # === 基本資料 ===
    record_no = fields.Char(
        string='紀錄表編號',
        required=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('reservation.defect.improvement') or '/')

    # === 檢查類型 ===
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety_env', '安衛及環境清潔檢查'),
    ], string='檢查類型', required=True, default='construction', tracking=True)

    # === 單位資訊 ===
    discovery_unit = fields.Char(
        string='發現單位',
        help='發現缺失的單位名稱')

    improvement_unit = fields.Char(
        string='執行改善單位',
        help='負責改善的單位名稱')

    # === 日期 ===
    notification_date = fields.Date(
        string='通知改善日期',
        default=fields.Date.today,
        tracking=True)

    deadline = fields.Date(
        string='限定完成改善日期',
        tracking=True)

    closure_date = fields.Date(
        string='結案日期',
        tracking=True)

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue',
        store=True)

    @api.depends('deadline', 'state', 'closure_date')
    def _compute_overdue(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ('conform', 'corrected'):
                # 已結案，不算逾期
                record.is_overdue = False
                record.overdue_days = 0
            elif record.deadline:
                if record.closure_date:
                    # 已結案，檢查是否逾期結案
                    record.is_overdue = record.closure_date > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (record.closure_date - record.deadline).days
                    else:
                        record.overdue_days = 0
                else:
                    # 未結案
                    record.is_overdue = today > record.deadline
                    if record.is_overdue:
                        record.overdue_days = (today - record.deadline).days
                    else:
                        record.overdue_days = 0
            else:
                record.is_overdue = False
                record.overdue_days = 0

    # === 缺失內容 ===
    defect_description = fields.Text(
        string='缺失具體情形',
        required=True,
        tracking=True)

    defect_location = fields.Char(
        string='缺失位置')

    defect_cause = fields.Text(
        string='缺失發生原因')

    improvement_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    prevention_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

    # === 照片 ===
    defect_photo_ids = fields.Many2many(
        'ir.attachment',
        'reservation_defect_photo_rel',
        'defect_id', 'attachment_id',
        string='缺失照片')

    improvement_photo_ids = fields.Many2many(
        'ir.attachment',
        'reservation_improvement_photo_rel',
        'defect_id', 'attachment_id',
        string='改善後照片')

    # === 確認資訊 ===
    confirmer_id = fields.Many2one(
        'res.users',
        string='確認人',
        tracking=True)

    confirm_date = fields.Date(
        string='確認日期')

    confirm_comment = fields.Text(
        string='確認意見')

    # === 編號前綴設定 ===
    supervision_prefix = fields.Char(
        string='監造編號前綴',
        help='監造單位使用的編號前綴')

    contractor_prefix = fields.Char(
        string='營造編號前綴',
        help='營造廠商使用的編號前綴')

    # === 狀態 (監造視角) ===
    state = fields.Selection([
        ('conform', '符合要求'),
        ('corrected', '已矯正'),
        ('uncorrected', '未矯正'),
        ('overdue', '逾時未矯正'),
        ('other', '其他'),
    ], string='缺失狀態', default='uncorrected', tracking=True)

    # === 動作方法 ===
    def action_mark_corrected(self):
        """標記已矯正"""
        for record in self:
            if record.state not in ('uncorrected', 'overdue'):
                raise UserError('只有未矯正或逾時未矯正狀態可以標記為已矯正')
            if not record.improvement_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'corrected',
                'closure_date': fields.Date.today(),
                'confirmer_id': self.env.uid,
                'confirm_date': fields.Date.today(),
            })

    def action_mark_conform(self):
        """標記符合要求"""
        for record in self:
            record.write({
                'state': 'conform',
                'closure_date': fields.Date.today(),
                'confirmer_id': self.env.uid,
                'confirm_date': fields.Date.today(),
            })

    def action_mark_overdue(self):
        """標記逾時未矯正"""
        for record in self:
            if record.state != 'uncorrected':
                raise UserError('只有未矯正狀態可以標記為逾時')
            record.state = 'overdue'

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('corrected', 'conform'):
                raise UserError('只有已矯正或符合要求狀態可以重新開啟')
            record.write({
                'state': 'uncorrected',
                'closure_date': False,
            })

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失"""
        today = fields.Date.today()
        overdue_records = self.search([
            ('state', '=', 'uncorrected'),
            ('deadline', '<', today),
        ])
        for record in overdue_records:
            record.state = 'overdue'

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('record_no') or vals.get('record_no') == '/':
                vals['record_no'] = self.env['ir.sequence'].next_by_code('reservation.defect.improvement') or '/'
        return super().create(vals_list)

    # === 約束 ===
    @api.constrains('deadline', 'notification_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.notification_date:
                if record.deadline < record.notification_date:
                    raise ValidationError('限定完成改善日期不得早於通知改善日期')
