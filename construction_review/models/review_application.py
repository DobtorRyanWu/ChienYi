# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionReviewApplication(models.Model):
    """
    送審管制

    對應舊系統: reviewApplication
    業務說明:
    - 管理工程材料送審流程
    - 追蹤型錄、樣品、測試報告、協力廠商資料的送審進度
    - 記錄審查結果、廠驗、取樣試驗等資訊
    """
    _name = 'supervision.review.application'
    _description = '送審管制'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expected_review_date asc, id desc'
    _rec_name = 'display_name'

    # === 基本資料 ===
    name = fields.Char(
        string='材料名稱',
        required=True,
        tracking=True,
        help='舊系統欄位: name')

    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True)

    sequence_code = fields.Char(
        string='送審編號',
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: '/')

    project_id = fields.Many2one(
        'supervision.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        domain="[('state', 'not in', ['closed', 'terminated'])]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True,
        readonly=True)

    # === 契約資訊 (舊系統欄位) ===
    no = fields.Char(
        string='契約詳細表項次',
        tracking=True,
        help='舊系統欄位: no')

    number = fields.Float(
        string='契約數量',
        digits='Product Unit of Measure',
        help='舊系統欄位: number')

    amount = fields.Monetary(
        string='金額',
        currency_field='currency_id',
        help='舊系統欄位: amount')

    currency_id = fields.Many2one(
        'res.currency',
        string='幣別',
        related='project_id.currency_id',
        store=True,
        readonly=True)

    # === 送審日期 (舊系統欄位) ===
    expected_review_date = fields.Date(
        string='送審-預定日期',
        tracking=True,
        help='舊系統欄位: expectedReviewDate')

    final_review_date = fields.Date(
        string='送審-實際日期',
        tracking=True,
        help='舊系統欄位: finalReviewDate')

    review_delay_days = fields.Integer(
        string='送審延遲天數',
        compute='_compute_review_delay_days',
        store=True,
        help='實際送審日期與預定日期的差異天數，正數表示延遲')

    @api.depends('expected_review_date', 'final_review_date')
    def _compute_review_delay_days(self):
        for record in self:
            if record.expected_review_date and record.final_review_date:
                delta = record.final_review_date - record.expected_review_date
                record.review_delay_days = delta.days
            else:
                record.review_delay_days = 0

    # === 送審資料 (舊系統欄位) ===
    has_catalog = fields.Boolean(
        string='型錄',
        default=False,
        tracking=True,
        help='舊系統欄位: hasCatalog')

    has_demo = fields.Boolean(
        string='樣品',
        default=False,
        tracking=True,
        help='舊系統欄位: hasDemo')

    has_related_test_report = fields.Boolean(
        string='相關測試報告',
        default=False,
        tracking=True,
        help='舊系統欄位: hasRelatedTestReport')

    has_subcontractor = fields.Boolean(
        string='協力廠商資料',
        default=False,
        tracking=True,
        help='舊系統欄位: hasSubcontractor')

    others = fields.Text(
        string='其他送審資料',
        help='舊系統欄位: others')

    # === 送審資料摘要 ===
    review_materials_summary = fields.Char(
        string='送審資料摘要',
        compute='_compute_review_materials_summary',
        store=True)

    @api.depends('has_catalog', 'has_demo', 'has_related_test_report', 'has_subcontractor', 'others')
    def _compute_review_materials_summary(self):
        for record in self:
            materials = []
            if record.has_catalog:
                materials.append('型錄')
            if record.has_demo:
                materials.append('樣品')
            if record.has_related_test_report:
                materials.append('測試報告')
            if record.has_subcontractor:
                materials.append('協力廠商')
            if record.others:
                materials.append('其他')
            record.review_materials_summary = ', '.join(materials) if materials else '-'

    # === 審查 (舊系統欄位) ===
    review_date = fields.Date(
        string='審查日期',
        tracking=True,
        help='舊系統欄位: reviewDate')

    final_review_result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '條件式通過'),
        ('fail', '不合格'),
    ], string='審查結果',
       tracking=True,
       help='舊系統欄位: finalReviewResult')

    review_comment = fields.Text(
        string='審查意見',
        help='審查人員的意見與備註')

    reviewer_id = fields.Many2one(
        'res.users',
        string='審查人員',
        tracking=True,
        domain="[('company_id', '=', company_id)]")

    # === 廠驗 (舊系統欄位) ===
    is_factory_inspection = fields.Boolean(
        string='是否廠驗',
        default=False,
        tracking=True,
        help='舊系統欄位: isFactoryInspection')

    factory_inspection_date = fields.Date(
        string='廠驗日期',
        tracking=True,
        help='舊系統欄位: factoryInspectionDate')

    factory_inspection_result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
        ('pending', '待定'),
    ], string='廠驗結果',
       tracking=True)

    factory_inspection_note = fields.Text(
        string='廠驗備註')

    # === 取樣試驗 (舊系統欄位) ===
    is_test = fields.Boolean(
        string='是否取樣試驗',
        default=False,
        tracking=True,
        help='舊系統欄位: isTest')

    test_unit = fields.Char(
        string='預定試驗單位',
        tracking=True,
        help='舊系統欄位: testUnit')

    test_date = fields.Date(
        string='試驗日期',
        tracking=True)

    test_result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
        ('pending', '待定'),
    ], string='試驗結果',
       tracking=True)

    test_report_no = fields.Char(
        string='試驗報告編號')

    # === 歸檔 (舊系統欄位) ===
    archive_number = fields.Char(
        string='歸檔編號',
        tracking=True,
        help='舊系統欄位: archiveNumber')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已送審'),
        ('reviewing', '審查中'),
        ('approved', '已核定'),
        ('rejected', '退件'),
    ], string='狀態',
       default='draft',
       required=True,
       tracking=True,
       index=True)

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'review_application_attachment_rel',
        'review_id',
        'attachment_id',
        string='送審文件')

    attachment_count = fields.Integer(
        string='附件數',
        compute='_compute_attachment_count')

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.attachment_ids)

    # === 追蹤欄位 ===
    submitted_date = fields.Datetime(
        string='送審時間',
        readonly=True)

    submitted_by = fields.Many2one(
        'res.users',
        string='送審人',
        readonly=True)

    approved_date = fields.Datetime(
        string='核定時間',
        readonly=True)

    approved_by = fields.Many2one(
        'res.users',
        string='核定人',
        readonly=True)

    # === 計算欄位 ===
    @api.depends('sequence_code', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.sequence_code and record.sequence_code != '/':
                record.display_name = f'[{record.sequence_code}] {record.name}'
            else:
                record.display_name = record.name or ''

    # === 約束 ===
    @api.constrains('expected_review_date', 'final_review_date')
    def _check_review_dates(self):
        for record in self:
            if record.expected_review_date and record.final_review_date:
                if record.final_review_date < record.expected_review_date:
                    # 允許提前送審，只做提醒
                    pass

    @api.constrains('has_catalog', 'has_demo', 'has_related_test_report', 'has_subcontractor', 'others')
    def _check_review_materials(self):
        """確保至少選擇一項送審資料"""
        for record in self:
            if record.state not in ('draft',):
                if not any([
                    record.has_catalog,
                    record.has_demo,
                    record.has_related_test_report,
                    record.has_subcontractor,
                    record.others
                ]):
                    raise ValidationError('請至少選擇一項送審資料類型')

    # === 狀態動作 ===
    def action_submit(self):
        """送審"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以送審')

            # 驗證必要欄位
            if not record.expected_review_date:
                raise ValidationError('請填寫預定送審日期')

            if not any([
                record.has_catalog,
                record.has_demo,
                record.has_related_test_report,
                record.has_subcontractor,
                record.others
            ]):
                raise ValidationError('請至少選擇一項送審資料類型')

            # 產生送審編號
            if record.sequence_code == '/':
                record.sequence_code = self.env['ir.sequence'].next_by_code(
                    'supervision.review.application') or '/'

            record.write({
                'state': 'submitted',
                'submitted_date': fields.Datetime.now(),
                'submitted_by': self.env.uid,
                'final_review_date': fields.Date.today(),
            })

    def action_start_review(self):
        """開始審查"""
        for record in self:
            if record.state != 'submitted':
                raise UserError('只有已送審狀態可以開始審查')
            record.state = 'reviewing'

    def action_approve(self):
        """核定"""
        for record in self:
            if record.state != 'reviewing':
                raise UserError('只有審查中狀態可以核定')

            if not record.final_review_result:
                raise ValidationError('請選擇審查結果')

            record.write({
                'state': 'approved',
                'review_date': fields.Date.today(),
                'approved_date': fields.Datetime.now(),
                'approved_by': self.env.uid,
                'reviewer_id': self.env.uid,
            })

    def action_reject(self):
        """退件"""
        for record in self:
            if record.state != 'reviewing':
                raise UserError('只有審查中狀態可以退件')

            if not record.review_comment:
                raise ValidationError('退件時請填寫審查意見')

            record.write({
                'state': 'rejected',
                'final_review_result': 'fail',
                'review_date': fields.Date.today(),
                'reviewer_id': self.env.uid,
            })

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('submitted', 'rejected'):
                raise UserError('只有已送審或退件狀態可以重設為草稿')
            record.write({
                'state': 'draft',
                'submitted_date': False,
                'submitted_by': False,
            })

    def action_resubmit(self):
        """重新送審 (退件後)"""
        for record in self:
            if record.state != 'rejected':
                raise UserError('只有退件狀態可以重新送審')
            record.write({
                'state': 'submitted',
                'submitted_date': fields.Datetime.now(),
                'submitted_by': self.env.uid,
                'final_review_date': fields.Date.today(),
                'final_review_result': False,
                'review_comment': False,
            })

    # === 檢視動作 ===
    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '送審文件',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('sequence_code', '/') == '/':
                # 送審編號在送審時產生，建立時先保持 /
                pass
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'rejected'):
                raise UserError('只有草稿或退件狀態的送審記錄可以刪除')
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'sequence_code': '/',
            'state': 'draft',
            'submitted_date': False,
            'submitted_by': False,
            'approved_date': False,
            'approved_by': False,
            'final_review_date': False,
            'review_date': False,
            'final_review_result': False,
            'review_comment': False,
            'reviewer_id': False,
        })
        return super().copy(default)

    # === 名稱搜尋 ===
    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                '|', '|',
                ('sequence_code', operator, name),
                ('name', operator, name),
                ('no', operator, name)
            ] + domain
        return self._search(domain, limit=limit, order=order)
