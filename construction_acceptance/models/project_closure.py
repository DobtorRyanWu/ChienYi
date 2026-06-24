# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta


class ProjectClosure(models.Model):
    """
    結案處理

    設計說明：
    - 驗收合格後的工程結案程序
    - 保固期設定與管理
    - 結案文件檢核
    - 保留款退還追蹤
    - 工程績效總結
    """
    _name = 'project.closure'
    _description = '結案處理'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'closure_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='結案單號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('project.closure') or '/',
        index=True)

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
        readonly=True,
        domain="[('state', '=', 'acceptance')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    authority_name = fields.Char(
        string='業主/主辦機關',
        related='project_id.authority_name',
        store=True)

    # === 關聯正驗 ===
    final_acceptance_id = fields.Many2one(
        'acceptance.final',
        string='關聯正驗',
        required=True,
        tracking=True,
        domain="[('project_id', '=', project_id), ('is_pass', '=', True), ('state', 'in', ['approved', 'closed'])]",
        readonly=True)

    acceptance_date = fields.Date(
        related='final_acceptance_id.acceptance_date',
        string='驗收合格日',
        store=True)

    certificate_no = fields.Char(
        related='final_acceptance_id.certificate_no',
        string='驗收合格證明編號',
        store=True)

    # === 結案日期 ===
    closure_date = fields.Date(
        string='結案日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    # === 契約資訊摘要 ===
    contract_amount = fields.Monetary(
        string='契約金額',
        related='project_id.contract_amount',
        store=True,
        currency_field='currency_id')

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id)

    contract_start_date = fields.Date(
        string='契約開工日',
        related='project_id.contract_start_date',
        store=True)

    contract_end_date = fields.Date(
        string='契約完工日',
        related='project_id.contract_end_date',
        store=True)

    actual_start_date = fields.Date(
        string='實際開工日',
        related='project_id.actual_start_date',
        store=True)

    actual_end_date = fields.Date(
        string='實際完工日',
        related='project_id.actual_end_date',
        store=True)

    # === 工期統計 ===
    contract_duration = fields.Integer(
        string='契約工期(日)',
        related='project_id.contract_duration',
        store=True)

    actual_duration = fields.Integer(
        string='實際工期(日)',
        related='project_id.actual_duration',
        store=True)

    duration_variance = fields.Integer(
        string='工期差異(日)',
        compute='_compute_duration_variance',
        store=True,
        help='正值為延遲，負值為提前')

    is_delayed = fields.Boolean(
        string='是否逾期',
        compute='_compute_duration_variance',
        store=True)

    @api.depends('contract_duration', 'actual_duration')
    def _compute_duration_variance(self):
        for record in self:
            record.duration_variance = record.actual_duration - record.contract_duration
            record.is_delayed = record.duration_variance > 0

    # === 結算金額 ===
    final_amount = fields.Monetary(
        string='結算金額',
        currency_field='currency_id',
        tracking=True,
        help='最終結算工程總金額')

    amount_variance = fields.Monetary(
        string='金額差異',
        compute='_compute_amount_variance',
        store=True,
        currency_field='currency_id',
        help='結算金額與契約金額差異')

    amount_variance_rate = fields.Float(
        string='金額差異率(%)',
        compute='_compute_amount_variance',
        store=True,
        digits=(5, 2))

    @api.depends('final_amount', 'contract_amount')
    def _compute_amount_variance(self):
        for record in self:
            record.amount_variance = (record.final_amount or 0) - (record.contract_amount or 0)
            if record.contract_amount:
                record.amount_variance_rate = (record.amount_variance / record.contract_amount) * 100
            else:
                record.amount_variance_rate = 0

    # === 保固管理 ===
    warranty_start_date = fields.Date(
        string='保固起始日',
        tracking=True)

    warranty_period_months = fields.Integer(
        string='保固期(月)',
        default=12,
        tracking=True)

    warranty_end_date = fields.Date(
        string='保固截止日',
        compute='_compute_warranty_end_date',
        store=True,
        tracking=True)

    @api.depends('warranty_start_date', 'warranty_period_months')
    def _compute_warranty_end_date(self):
        for record in self:
            if record.warranty_start_date and record.warranty_period_months:
                record.warranty_end_date = (
                    record.warranty_start_date +
                    relativedelta(months=record.warranty_period_months)
                )
            else:
                record.warranty_end_date = False

    warranty_status = fields.Selection([
        ('active', '保固中'),
        ('expired', '已到期'),
    ], string='保固狀態',
       compute='_compute_warranty_status',
       store=True)

    days_to_warranty_end = fields.Integer(
        string='距保固到期(日)',
        compute='_compute_days_to_warranty_end')

    @api.depends('warranty_end_date')
    def _compute_warranty_status(self):
        """計算保固狀態 (stored)"""
        today = fields.Date.today()
        for record in self:
            if record.warranty_end_date:
                if today <= record.warranty_end_date:
                    record.warranty_status = 'active'
                else:
                    record.warranty_status = 'expired'
            else:
                record.warranty_status = False

    @api.depends('warranty_end_date')
    def _compute_days_to_warranty_end(self):
        """計算距保固到期天數 (non-stored)"""
        today = fields.Date.today()
        for record in self:
            if record.warranty_end_date and today <= record.warranty_end_date:
                record.days_to_warranty_end = (record.warranty_end_date - today).days
            else:
                record.days_to_warranty_end = 0

    # === 保留款管理 ===
    warranty_bond_amount = fields.Monetary(
        string='保固保證金',
        currency_field='currency_id',
        tracking=True)

    retention_amount = fields.Monetary(
        string='保留款金額',
        currency_field='currency_id',
        tracking=True)

    retention_release_date = fields.Date(
        string='保留款退還日',
        tracking=True)

    retention_released = fields.Boolean(
        string='保留款已退還',
        default=False,
        tracking=True)

    retention_release_amount = fields.Monetary(
        string='實際退還金額',
        currency_field='currency_id',
        tracking=True)

    retention_note = fields.Text(
        string='保留款說明')

    # === 結案文件檢核 ===
    document_checklist_ids = fields.One2many(
        'project.closure.document',
        'closure_id',
        string='文件檢核清單')

    document_complete = fields.Boolean(
        string='文件齊全',
        compute='_compute_document_complete',
        store=True)

    document_complete_rate = fields.Float(
        string='文件完成率(%)',
        compute='_compute_document_complete',
        store=True,
        digits=(5, 2))

    @api.depends('document_checklist_ids', 'document_checklist_ids.is_received')
    def _compute_document_complete(self):
        for record in self:
            docs = record.document_checklist_ids.filtered(lambda d: d.is_required)
            if docs:
                received = docs.filtered(lambda d: d.is_received)
                record.document_complete_rate = (len(received) / len(docs)) * 100
                record.document_complete = len(received) == len(docs)
            else:
                record.document_complete_rate = 100
                record.document_complete = True

    # === 工程績效 ===
    performance_summary = fields.Html(
        string='績效總結')

    performance_score = fields.Float(
        string='績效評分',
        digits=(3, 1),
        help='0-100 分')

    lessons_learned = fields.Html(
        string='經驗教訓',
        help='記錄此工程的經驗教訓供未來參考')

    # === 相關文件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'project_closure_attachment_rel',
        'closure_id', 'attachment_id',
        string='結案附件')

    # === 審核資訊 ===
    reviewer_id = fields.Many2one(
        'res.users',
        string='審核者',
        readonly=True)

    review_date = fields.Datetime(
        string='審核時間',
        readonly=True)

    approver_id = fields.Many2one(
        'res.users',
        string='核定者',
        readonly=True)

    approve_date = fields.Datetime(
        string='核定時間',
        readonly=True)

    # === 備註 ===
    note = fields.Text(
        string='備註')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('pending_document', '待文件'),
        ('pending_review', '待審核'),
        ('reviewed', '已審核'),
        ('approved', '已核定'),
        ('closed', '已結案'),
        ('cancelled', '已取消'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '結案單號必須唯一！'),
        ('project_unique', 'UNIQUE(project_id)', '每個工程只能有一筆結案記錄！'),
    ]

    # === onchange ===
    @api.onchange('final_acceptance_id')
    def _onchange_final_acceptance(self):
        """從正驗帶入資訊"""
        if self.final_acceptance_id:
            final = self.final_acceptance_id
            self.project_id = final.project_id
            self.warranty_start_date = final.warranty_start_date
            self.warranty_period_months = final.warranty_period_months
            self.warranty_bond_amount = final.warranty_bond_amount

    # === 動作方法 ===
    def action_start_document_check(self):
        """開始文件檢核"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以開始文件檢核')
            # 自動產生標準文件清單
            record._create_standard_document_checklist()
            record.state = 'pending_document'

    def _create_standard_document_checklist(self):
        """產生標準結案文件清單"""
        self.ensure_one()
        standard_docs = [
            ('contract', '契約正本', True),
            ('completion_report', '竣工報告', True),
            ('acceptance_record', '驗收紀錄', True),
            ('certificate', '驗收合格證明', True),
            ('as_built', '竣工圖', True),
            ('warranty_bond', '保固保證金', True),
            ('payment_record', '付款記錄', True),
            ('quality_record', '品質紀錄', False),
            ('photo_record', '施工照片', False),
            ('test_report', '試驗報告', False),
            ('manual', '操作維護手冊', False),
        ]

        for doc_type, doc_name, is_required in standard_docs:
            self.env['project.closure.document'].create({
                'closure_id': self.id,
                'document_type': doc_type,
                'name': doc_name,
                'is_required': is_required,
            })

    def action_submit_review(self):
        """提交審核"""
        for record in self:
            if record.state != 'pending_document':
                raise UserError('只有待文件狀態可以提交審核')
            if not record.document_complete:
                raise UserError(
                    f'必要文件尚未齊全（完成率：{record.document_complete_rate:.1f}%），'
                    '請完成文件收集後再提交審核'
                )
            if not record.final_amount:
                raise ValidationError('請填寫結算金額')
            record.state = 'pending_review'

    def action_review(self):
        """審核通過"""
        for record in self:
            if record.state != 'pending_review':
                raise UserError('只有待審核狀態可以審核')
            record.write({
                'state': 'reviewed',
                'reviewer_id': self.env.uid,
                'review_date': fields.Datetime.now(),
            })

    def action_approve(self):
        """核定"""
        for record in self:
            if record.state != 'reviewed':
                raise UserError('只有已審核狀態可以核定')
            record.write({
                'state': 'approved',
                'approver_id': self.env.uid,
                'approve_date': fields.Datetime.now(),
            })
            # 回寫正驗關聯
            record.final_acceptance_id.write({
                'closure_id': record.id,
            })

    def action_close(self):
        """完成結案"""
        for record in self:
            if record.state != 'approved':
                raise UserError('只有已核定狀態可以完成結案')
            record.state = 'closed'
            # 更新工程狀態為已結案
            record.project_id.write({'state': 'closed'})

    def action_return_revision(self):
        """退回修正"""
        for record in self:
            if record.state not in ('pending_review', 'reviewed'):
                raise UserError('只有待審核或已審核狀態可以退回修正')
            record.state = 'pending_document'

    def action_cancel(self):
        """取消"""
        for record in self:
            if record.state in ('approved', 'closed'):
                raise UserError('已核定或已結案的記錄不可取消')
            record.state = 'cancelled'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('pending_document', 'cancelled'):
                raise UserError('只有待文件或已取消狀態可以重設為草稿')
            # 清除文件清單
            record.document_checklist_ids.unlink()
            record.state = 'draft'

    # === 保留款退還 ===
    def action_release_retention(self):
        """退還保留款"""
        self.ensure_one()
        if self.retention_released:
            raise UserError('保留款已退還')
        if self.warranty_status != 'expired':
            raise UserError('保固期尚未到期，無法退還保留款')

        self.write({
            'retention_released': True,
            'retention_release_date': fields.Date.today(),
            'retention_release_amount': self.retention_amount,
        })
        self.message_post(
            body=f'保留款已退還，金額：{self.retention_amount}',
            message_type='notification',
        )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('project.closure') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'cancelled'):
                raise UserError('只有草稿或已取消的結案記錄可以刪除')
        return super().unlink()


class ProjectClosureDocument(models.Model):
    """結案文件檢核"""
    _name = 'project.closure.document'
    _description = '結案文件檢核'
    _order = 'sequence, id'

    # === 關聯 ===
    closure_id = fields.Many2one(
        'project.closure',
        string='結案單',
        required=True,
        ondelete='cascade',
        index=True)

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 文件資訊 ===
    document_type = fields.Selection([
        ('contract', '契約'),
        ('completion_report', '竣工報告'),
        ('acceptance_record', '驗收紀錄'),
        ('certificate', '驗收合格證明'),
        ('as_built', '竣工圖'),
        ('warranty_bond', '保固保證金'),
        ('payment_record', '付款記錄'),
        ('quality_record', '品質紀錄'),
        ('photo_record', '施工照片'),
        ('test_report', '試驗報告'),
        ('manual', '操作維護手冊'),
        ('other', '其他'),
    ], string='文件類型', required=True, default='other')

    name = fields.Char(
        string='文件名稱',
        required=True)

    description = fields.Text(
        string='文件說明')

    is_required = fields.Boolean(
        string='必要文件',
        default=True)

    # === 收件狀態 ===
    is_received = fields.Boolean(
        string='已收到',
        default=False)

    received_date = fields.Date(
        string='收件日期')

    receiver_id = fields.Many2one(
        'res.users',
        string='收件人')

    # === 附件 ===
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='電子檔')

    # === 備註 ===
    note = fields.Text(
        string='備註')

    # === onchange ===
    @api.onchange('is_received')
    def _onchange_is_received(self):
        if self.is_received and not self.received_date:
            self.received_date = fields.Date.today()
            self.receiver_id = self.env.uid
