# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class GeneralDefectImprovement(models.Model):
    """
    一般式缺失改善

    設計說明：
    - 獨立於通報單的缺失改善記錄
    - 用於一般式工程的缺失追蹤與改善
    - 可從自主檢查或日常巡查開立
    - 完整的改善追蹤流程
    """
    _name = 'general.defect.improvement'
    _description = '一般式缺失改善'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'notification_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='缺失編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('general.defect.improvement') or '/')

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        tracking=True,
        index=True,
        domain="[('project_type', '=', 'general')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    task_id = fields.Many2one(
        'project.task',
        string='關聯工項',
        domain="[('project_id', '=', project_id)]",
        help='此缺失關聯的契約工項')

    # === 來源關聯 ===
    source_type = fields.Selection([
        ('self_inspection', '自主檢查'),
        ('daily_check', '日常巡查'),
        ('supervision', '監造抽查'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ], string='缺失來源', required=True, default='daily_check', tracking=True)

    self_inspection_id = fields.Many2one(
        'general.self.inspection',
        string='來源自主檢查',
        domain="[('project_id', '=', project_id)]",
        help='若從自主檢查開立的缺失')

    self_inspection_item_id = fields.Many2one(
        'general.self.inspection.item',
        string='來源檢查項目',
        domain="[('inspection_id', '=', self_inspection_id)]",
        help='自主檢查中的具體缺失項目')

    ncr_id = fields.Many2one(
        'supervision.defect',
        string='關聯 NCR',
        domain="[('project_id', '=', project_id)]",
        help='若需關聯 NCR 缺失單')

    # === 檢查類型 ===
    check_type = fields.Selection([
        ('construction', '施工檢查'),
        ('safety', '安全檢查'),
        ('environment', '環境檢查'),
        ('quality', '品質檢查'),
    ], string='檢查類型', required=True, default='construction', tracking=True)

    # === 缺失分類 ===
    defect_category = fields.Selection([
        ('quality', '品質缺失'),
        ('safety', '安全缺失'),
        ('environmental', '環境缺失'),
        ('documentation', '文件缺失'),
        ('other', '其他'),
    ], string='缺失類別', required=True, default='quality', tracking=True)

    severity = fields.Selection([
        ('minor', '輕微'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ], string='嚴重程度', required=True, default='minor', tracking=True)

    # === 單位資訊 ===
    discovery_unit = fields.Char(
        string='發現單位',
        help='發現缺失的單位名稱')

    discovery_user_id = fields.Many2one(
        'res.users',
        string='發現人',
        default=lambda self: self.env.uid,
        tracking=True)

    improvement_unit = fields.Char(
        string='執行改善單位',
        help='負責改善的單位名稱')

    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]",
        help='負責改善的施工廠商')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True,
        help='負責執行改善的人員')

    # === 日期 ===
    found_date = fields.Date(
        string='發現日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    notification_date = fields.Date(
        string='通知改善日期',
        default=fields.Date.today,
        tracking=True)

    deadline = fields.Date(
        string='改善期限',
        tracking=True)

    improvement_date = fields.Date(
        string='實際改善日期',
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
            if record.state in ('improved', 'verified', 'closed'):
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
    defect_location = fields.Char(
        string='缺失位置',
        help='發生缺失的具體位置')

    defect_description = fields.Text(
        string='缺失說明',
        required=True,
        tracking=True)

    defect_cause = fields.Text(
        string='缺失發生原因',
        help='分析缺失發生的根本原因')

    # === 改善資訊 ===
    improvement_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    prevention_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

    improvement_result = fields.Text(
        string='改善結果說明',
        help='改善完成後的結果說明')

    # === 照片 ===
    defect_photo_ids = fields.Many2many(
        'ir.attachment',
        'general_defect_photo_rel',
        'defect_id', 'attachment_id',
        string='缺失照片')

    improvement_photo_ids = fields.Many2many(
        'ir.attachment',
        'general_improvement_photo_rel',
        'defect_id', 'attachment_id',
        string='改善後照片')

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'general_defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關附件')

    # === 驗證資訊 ===
    verifier_id = fields.Many2one(
        'res.users',
        string='驗證人',
        tracking=True)

    verify_date = fields.Date(
        string='驗證日期')

    verify_result = fields.Selection([
        ('pass', '驗證通過'),
        ('fail', '驗證不通過'),
    ], string='驗證結果', tracking=True)

    verify_comment = fields.Text(
        string='驗證意見')

    # === 結案資訊 ===
    closer_id = fields.Many2one(
        'res.users',
        string='結案人',
        tracking=True)

    close_comment = fields.Text(
        string='結案說明')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('notified', '已通知'),
        ('improving', '改善中'),
        ('improved', '已改善'),
        ('verified', '已驗證'),
        ('closed', '結案'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 備註 ===
    note = fields.Text(string='備註說明')

    # === 動作方法 ===
    def action_notify(self):
        """通知改善"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以通知改善')
            if not record.deadline:
                raise ValidationError('請先設定改善期限')
            record.write({
                'state': 'notified',
                'notification_date': fields.Date.today(),
            })

    def action_start_improvement(self):
        """開始改善"""
        for record in self:
            if record.state != 'notified':
                raise UserError('只有已通知狀態可以開始改善')
            record.state = 'improving'

    def action_complete_improvement(self):
        """完成改善"""
        for record in self:
            if record.state != 'improving':
                raise UserError('只有改善中狀態可以標記完成')
            if not record.improvement_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'improved',
                'improvement_date': fields.Date.today(),
            })

    def action_verify_pass(self):
        """驗證通過"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            record.write({
                'state': 'verified',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'pass',
            })

    def action_verify_fail(self):
        """驗證不通過"""
        for record in self:
            if record.state != 'improved':
                raise UserError('只有已改善狀態可以驗證')
            record.write({
                'state': 'improving',
                'verifier_id': self.env.uid,
                'verify_date': fields.Date.today(),
                'verify_result': 'fail',
            })

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'verified':
                raise UserError('只有已驗證狀態可以結案')
            record.write({
                'state': 'closed',
                'closer_id': self.env.uid,
                'closure_date': fields.Date.today(),
            })

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('verified', 'closed'):
                raise UserError('只有已驗證或結案狀態可以重新開啟')
            record.write({
                'state': 'improving',
                'closure_date': False,
                'closer_id': False,
                'verify_result': False,
            })

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('draft', 'notified'):
                raise UserError('只有草稿或已通知狀態可以重設')
            record.state = 'draft'

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失"""
        today = fields.Date.today()
        # 更新所有未結案且逾期的記錄
        overdue_records = self.search([
            ('state', 'not in', ('improved', 'verified', 'closed')),
            ('deadline', '<', today),
            ('is_overdue', '=', False),
        ])
        # 觸發重新計算
        for record in overdue_records:
            record._compute_overdue()

    @api.model
    def _cron_send_overdue_notification(self):
        """發送逾期通知"""
        overdue_records = self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ('improved', 'verified', 'closed')),
        ])
        for record in overdue_records:
            # 發送訊息通知負責人
            if record.responsible_user_id:
                record.message_post(
                    body=f'缺失 {record.name} 已逾期 {record.overdue_days} 天，請儘速處理！',
                    partner_ids=record.responsible_user_id.partner_id.ids,
                    message_type='notification',
                )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('general.defect.improvement') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft',):
                raise UserError('只有草稿狀態的缺失可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('deadline', 'found_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.found_date:
                if record.deadline < record.found_date:
                    raise ValidationError('改善期限不得早於發現日期')

    @api.constrains('notification_date', 'found_date')
    def _check_notification_date(self):
        for record in self:
            if record.notification_date and record.found_date:
                if record.notification_date < record.found_date:
                    raise ValidationError('通知改善日期不得早於發現日期')

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)',
         '缺失編號必須唯一！'),
    ]
