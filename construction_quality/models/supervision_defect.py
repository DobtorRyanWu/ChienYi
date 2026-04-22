# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionDefect(models.Model):
    """
    缺失管理 (NCR - Non-Conformance Report)

    設計說明：
    - 一般式工程專用的缺失管理
    - 完整的 NCR 狀態流程：open -> investigating -> action_taken -> verified -> closed
    - 支援缺失來源追溯與改善追蹤
    - 逾期自動檢測與警示
    """
    _name = 'supervision.defect'
    _description = '缺失管理 (NCR)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'found_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='缺失編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('supervision.defect') or '/')

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        tracking=True,
        index=True)

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

    # === 缺失來源 ===
    source = fields.Selection([
        ('inspection', '抽查發現'),
        ('daily_check', '日常檢查'),
        ('self_inspection', '自主檢查'),
        ('preliminary_acceptance', '初驗'),
        ('final_acceptance', '正驗'),
        ('authority_audit', '機關查核'),
        ('other', '其他'),
    ], string='缺失來源', required=True, default='daily_check', tracking=True)

    source_reference = fields.Reference(
        selection=[
            ('general.self.inspection', '自主檢查'),
            ('work.acceptance', '驗收紀錄'),
        ],
        string='來源單據',
        help='關聯的來源記錄')

    source_description = fields.Char(
        string='來源說明',
        help='來源補充說明')

    # === 缺失分類 ===
    defect_type = fields.Selection([
        ('quality', '品質缺失'),
        ('safety', '安全缺失'),
        ('environmental', '環境缺失'),
        ('schedule', '進度缺失'),
        ('documentation', '文件缺失'),
    ], string='缺失類型', required=True, default='quality', tracking=True)

    # === 缺失內容 ===
    description = fields.Text(
        string='缺失說明',
        required=True,
        tracking=True)

    location = fields.Char(
        string='發生位置',
        help='具體發生位置')

    found_date = fields.Date(
        string='發現日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    # === 責任歸屬 ===
    responsible_party = fields.Selection([
        ('contractor', '施工廠商'),
        ('subcontractor', '分包商'),
        ('supplier', '供應商'),
        ('design', '設計單位'),
        ('other', '其他'),
    ], string='責任方', tracking=True)

    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]")

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True)

    deadline = fields.Date(
        string='改善期限',
        tracking=True)

    # === 開立資訊 ===
    issuer_id = fields.Many2one(
        'res.users',
        string='開立者',
        default=lambda self: self.env.uid,
        tracking=True)

    issue_date = fields.Datetime(
        string='開立時間',
        default=fields.Datetime.now)

    # === 調查資訊 ===
    investigator_id = fields.Many2one(
        'res.users',
        string='調查人',
        tracking=True)

    investigation_date = fields.Datetime(
        string='調查時間')

    root_cause = fields.Text(
        string='根本原因分析',
        help='5 Whys 或其他根因分析')

    # === 改善資訊 ===
    improvement_description = fields.Text(
        string='改善說明',
        tracking=True)

    corrective_action = fields.Text(
        string='矯正措施',
        help='針對缺失的改善行動')

    preventive_action = fields.Text(
        string='預防措施',
        help='避免再次發生的預防措施')

    improvement_date = fields.Datetime(
        string='改善完成時間',
        tracking=True)

    improver_id = fields.Many2one(
        'res.users',
        string='改善執行者',
        tracking=True)

    # === 驗證資訊 ===
    verifier_id = fields.Many2one(
        'res.users',
        string='驗證者',
        tracking=True)

    verify_date = fields.Datetime(
        string='驗證時間')

    verify_result = fields.Selection([
        ('pass', '驗證通過'),
        ('fail', '驗證不通過'),
        ('reopen', '需重新改善'),
    ], string='驗證結果', tracking=True)

    verify_comment = fields.Text(
        string='驗證意見')

    # === 結案資訊 ===
    closer_id = fields.Many2one(
        'res.users',
        string='結案者',
        tracking=True)

    close_date = fields.Datetime(
        string='結案時間')

    close_comment = fields.Text(
        string='結案說明')

    # === 照片附件 ===
    before_photo_ids = fields.Many2many(
        'ir.attachment',
        'defect_before_photo_rel',
        'defect_id', 'attachment_id',
        string='改善前照片')

    after_photo_ids = fields.Many2many(
        'ir.attachment',
        'defect_after_photo_rel',
        'defect_id', 'attachment_id',
        string='改善後照片')

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'defect_attachment_rel',
        'defect_id', 'attachment_id',
        string='相關附件')

    # === 狀態 (NCR 流程) ===
    state = fields.Selection([
        ('open', '開立'),
        ('investigating', '調查中'),
        ('action_taken', '已採取措施'),
        ('verified', '已驗證'),
        ('closed', '結案'),
    ], string='狀態', default='open', tracking=True, index=True,
       help='NCR 狀態流程：open -> investigating -> action_taken -> verified -> closed')

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue',
        store=True)

    days_open = fields.Integer(
        string='開立天數',
        compute='_compute_days_open')

    @api.depends('deadline', 'state')
    def _compute_overdue(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ('verified', 'closed'):
                # 已結案不算逾期
                record.is_overdue = False
                record.overdue_days = 0
            elif record.deadline:
                record.is_overdue = today > record.deadline
                if record.is_overdue:
                    record.overdue_days = (today - record.deadline).days
                else:
                    record.overdue_days = 0
            else:
                record.is_overdue = False
                record.overdue_days = 0

    @api.depends('found_date', 'close_date')
    def _compute_days_open(self):
        today = fields.Date.today()
        for record in self:
            if record.found_date:
                if record.close_date:
                    end_date = record.close_date.date()
                else:
                    end_date = today
                record.days_open = (end_date - record.found_date).days
            else:
                record.days_open = 0

    # === 動作方法 (NCR 狀態流程) ===
    def action_start_investigation(self):
        """開始調查"""
        for record in self:
            if record.state != 'open':
                raise UserError('只有開立狀態可以開始調查')
            record.write({
                'state': 'investigating',
                'investigator_id': self.env.uid,
                'investigation_date': fields.Datetime.now(),
            })

    def action_take_action(self):
        """採取改善措施"""
        for record in self:
            if record.state != 'investigating':
                raise UserError('只有調查中狀態可以採取改善措施')
            if not record.corrective_action:
                raise UserError('請先填寫矯正措施')
            record.write({
                'state': 'action_taken',
                'improvement_date': fields.Datetime.now(),
                'improver_id': self.env.uid,
            })

    def action_verify(self):
        """驗證改善結果"""
        for record in self:
            if record.state != 'action_taken':
                raise UserError('只有已採取措施狀態可以驗證')
            record.write({
                'state': 'verified',
                'verifier_id': self.env.uid,
                'verify_date': fields.Datetime.now(),
                'verify_result': 'pass',
            })

    def action_verify_fail(self):
        """驗證不通過，重新調查"""
        for record in self:
            if record.state != 'action_taken':
                raise UserError('只有已採取措施狀態可以驗證')
            record.write({
                'state': 'investigating',
                'verifier_id': self.env.uid,
                'verify_date': fields.Datetime.now(),
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
                'close_date': fields.Datetime.now(),
            })

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state != 'closed':
                raise UserError('只有結案狀態可以重新開啟')
            record.write({
                'state': 'open',
                'close_date': False,
                'closer_id': False,
            })

    def action_reset_draft(self):
        """重設為開立狀態"""
        for record in self:
            if record.state not in ('investigating', 'action_taken'):
                raise UserError('只有調查中或已採取措施狀態可以重設')
            record.write({
                'state': 'open',
                'investigator_id': False,
                'investigation_date': False,
            })

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期更新逾期狀態"""
        # 重新計算所有未結案缺失的逾期狀態
        open_defects = self.search([
            ('state', 'not in', ('verified', 'closed')),
            ('deadline', '!=', False),
        ])
        for defect in open_defects:
            defect._compute_overdue()

    @api.model
    def _cron_send_overdue_notification(self):
        """發送逾期通知"""
        overdue_defects = self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ('verified', 'closed')),
        ])
        for defect in overdue_defects:
            # 發送訊息通知負責人
            if defect.responsible_user_id:
                defect.message_post(
                    body=f'缺失 {defect.name} 已逾期 {defect.overdue_days} 天，請儘速處理！',
                    partner_ids=defect.responsible_user_id.partner_id.ids,
                    message_type='notification',
                )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('supervision.defect') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('open',):
                raise UserError('只有開立狀態的缺失可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('deadline', 'found_date')
    def _check_dates(self):
        for record in self:
            if record.deadline and record.found_date:
                if record.deadline < record.found_date:
                    raise ValidationError('改善期限不得早於發現日期')

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)',
         '缺失編號必須唯一！'),
    ]
