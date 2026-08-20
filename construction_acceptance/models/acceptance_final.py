# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class AcceptanceFinal(models.Model):
    """
    正驗紀錄

    設計說明：
    - 初驗缺失改善後的正式驗收
    - 必須基於初驗結果
    - 最終驗收結果判定
    - 通過後產生驗收合格證明
    - 通過後可進入結案程序
    """
    _name = 'acceptance.final'
    _description = '正驗紀錄'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'supervision.attachment.mixin']
    _order = 'acceptance_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='正驗單號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('acceptance.final') or '/',
        index=True)

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
        readonly=True)

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    contractor_company_id = fields.Many2one(
        'res.company',
        string='施工廠商',
        domain="[('company_type', '=', 'contractor')]",
        tracking=True)

    authority_name = fields.Char(
        string='業主/主辦機關',
        related='project_id.authority_name',
        store=True)

    # === 關聯初驗 ===
    preliminary_acceptance_id = fields.Many2one(
        'acceptance.preliminary',
        string='關聯初驗',
        required=True,
        tracking=True,
        domain="[('project_id', '=', project_id), ('state', 'in', ['reviewed', 'improvement_done', 'closed'])]",
        readonly=True)

    preliminary_result = fields.Selection(
        related='preliminary_acceptance_id.result',
        string='初驗結果',
        store=True)

    preliminary_defect_count = fields.Integer(
        related='preliminary_acceptance_id.defect_count',
        string='初驗缺失數')

    # === 驗收日期 ===
    acceptance_date = fields.Date(
        string='正驗日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    scheduled_date = fields.Date(
        string='預定正驗日',
        tracking=True)

    days_from_preliminary = fields.Integer(
        string='距初驗天數',
        compute='_compute_days_from_preliminary',
        store=True)

    @api.depends('acceptance_date', 'preliminary_acceptance_id.acceptance_date')
    def _compute_days_from_preliminary(self):
        for record in self:
            if record.acceptance_date and record.preliminary_acceptance_id.acceptance_date:
                record.days_from_preliminary = (
                    record.acceptance_date - record.preliminary_acceptance_id.acceptance_date
                ).days
            else:
                record.days_from_preliminary = 0

    # === 驗收人員 ===
    chairman_id = fields.Many2one(
        'res.partner',
        string='驗收主席',
        tracking=True)

    committee_ids = fields.Many2many(
        'res.partner',
        'final_acceptance_committee_rel',
        'acceptance_id', 'partner_id',
        string='驗收委員')

    supervision_representative_id = fields.Many2one(
        'res.users',
        string='監造代表',
        default=lambda self: self.env.uid,
        tracking=True)

    contractor_representative_id = fields.Many2one(
        'res.partner',
        string='廠商代表',
        tracking=True)

    # === 驗收項目明細 ===
    line_ids = fields.One2many(
        'acceptance.final.line',
        'acceptance_id',
        string='驗收項目',
        copy=True)

    # === 驗收結果 ===
    result = fields.Selection([
        ('pass', '驗收合格'),
        ('conditional', '有條件合格'),
        ('fail', '驗收不合格'),
    ], string='驗收結果', tracking=True)

    is_pass = fields.Boolean(
        string='驗收通過',
        compute='_compute_is_pass',
        store=True)

    @api.depends('result')
    def _compute_is_pass(self):
        for record in self:
            record.is_pass = record.result in ('pass', 'conditional')

    # === 缺失統計（正驗發現的新缺失）===
    defect_ids = fields.One2many(
        'acceptance.defect',
        'final_acceptance_id',
        string='正驗缺失')

    defect_count = fields.Integer(
        string='正驗缺失數',
        compute='_compute_defect_count',
        store=True)

    @api.depends('defect_ids')
    def _compute_defect_count(self):
        for record in self:
            record.defect_count = len(record.defect_ids)

    # === 驗收合格證明 ===
    certificate_no = fields.Char(
        string='驗收合格證明編號',
        copy=False,
        tracking=True)

    certificate_date = fields.Date(
        string='發證日期',
        tracking=True)

    certificate_attachment_id = fields.Many2one(
        'ir.attachment',
        string='驗收合格證明',
        help='驗收合格證明書掃描檔')

    # === 保固資訊 ===
    warranty_start_date = fields.Date(
        string='保固起始日',
        tracking=True,
        help='通常為驗收合格日')

    warranty_period_months = fields.Integer(
        string='保固期(月)',
        default=12,
        tracking=True)

    warranty_end_date = fields.Date(
        string='保固截止日',
        compute='_compute_warranty_end_date',
        store=True)

    @api.depends('warranty_start_date', 'warranty_period_months')
    def _compute_warranty_end_date(self):
        for record in self:
            if record.warranty_start_date and record.warranty_period_months:
                from dateutil.relativedelta import relativedelta
                record.warranty_end_date = (
                    record.warranty_start_date +
                    relativedelta(months=record.warranty_period_months)
                )
            else:
                record.warranty_end_date = False

    warranty_bond_amount = fields.Monetary(
        string='保固保證金',
        currency_field='currency_id',
        tracking=True)

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id)

    # === 相關文件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'final_acceptance_attachment_rel',
        'acceptance_id', 'attachment_id',
        string='驗收附件')

    def _attachment_default_category(self):
        """正驗附件 → 17-結案驗收 / 驗收資料"""
        return self.env.ref(
            'construction_supervision_base.cat_17_02',
            raise_if_not_found=False) or super()._attachment_default_category()

    def _attachment_default_folder(self):
        """正驗附件 → 17-結案驗收 / 02-驗收資料 / <這張正驗單>

        路徑由分類的祖先鏈推出，不寫死中文字串（分類改名會自動跟著改）。
        """
        return self._attachment_category_folder()

    minutes = fields.Html(
        string='驗收會議紀錄')

    # === 審核資訊 ===
    reviewer_id = fields.Many2one(
        'res.users',
        string='審核者',
        readonly=True)

    review_date = fields.Datetime(
        string='審核時間',
        readonly=True)

    review_comment = fields.Text(
        string='審核意見')

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
        ('scheduled', '已排定'),
        ('in_progress', '驗收中'),
        ('pending_review', '待審核'),
        ('reviewed', '已審核'),
        ('approved', '已核定'),
        ('closed', '已結案'),
        ('cancelled', '已取消'),
    ], string='狀態', default='draft', tracking=True, index=True)

    # === 關聯結案 ===
    closure_id = fields.Many2one(
        'project.closure',
        string='關聯結案',
        readonly=True)

    can_create_closure = fields.Boolean(
        string='可建立結案',
        compute='_compute_can_create_closure')

    @api.depends('state', 'is_pass')
    def _compute_can_create_closure(self):
        for record in self:
            record.can_create_closure = (
                record.state in ('approved', 'closed') and
                record.is_pass
            )

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '正驗單號必須唯一！'),
    ]

    # === onchange ===
    @api.onchange('preliminary_acceptance_id')
    def _onchange_preliminary_acceptance(self):
        """從初驗帶入資訊"""
        if self.preliminary_acceptance_id:
            prelim = self.preliminary_acceptance_id
            self.project_id = prelim.project_id
            self.contractor_company_id = prelim.contractor_company_id
            self.chairman_id = prelim.chairman_id
            self.committee_ids = [Command.set(prelim.committee_ids.ids)]

    @api.onchange('result', 'acceptance_date')
    def _onchange_result(self):
        """驗收通過時設定保固起始日"""
        if self.result in ('pass', 'conditional') and self.acceptance_date:
            if not self.warranty_start_date:
                self.warranty_start_date = self.acceptance_date

    # === 動作方法 ===
    def action_schedule(self):
        """排定驗收"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以排定驗收')
            if not record.scheduled_date:
                raise ValidationError('請先設定預定正驗日')
            record.state = 'scheduled'

    def action_start(self):
        """開始驗收"""
        for record in self:
            if record.state not in ('draft', 'scheduled'):
                raise UserError('只有草稿或已排定狀態可以開始驗收')
            record.state = 'in_progress'

    def action_submit_review(self):
        """提交審核"""
        for record in self:
            if record.state != 'in_progress':
                raise UserError('只有驗收中狀態可以提交審核')
            if not record.result:
                raise ValidationError('請先選擇驗收結果')
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
            if record.is_pass and not record.certificate_no:
                raise ValidationError('驗收合格時必須填寫驗收合格證明編號')
            record.write({
                'state': 'approved',
                'approver_id': self.env.uid,
                'approve_date': fields.Datetime.now(),
            })
            # 回寫初驗關聯
            record.preliminary_acceptance_id.write({
                'final_acceptance_id': record.id,
            })

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'approved':
                raise UserError('只有已核定狀態可以結案')
            record.state = 'closed'

    def action_return_revision(self):
        """退回修正"""
        for record in self:
            if record.state not in ('pending_review', 'reviewed'):
                raise UserError('只有待審核或已審核狀態可以退回修正')
            record.state = 'in_progress'

    def action_cancel(self):
        """取消"""
        for record in self:
            if record.state in ('approved', 'closed'):
                raise UserError('已核定或已結案的正驗不可取消')
            record.state = 'cancelled'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('scheduled', 'cancelled'):
                raise UserError('只有已排定或已取消狀態可以重設為草稿')
            record.state = 'draft'

    # === 建立結案 ===
    def action_create_closure(self):
        """建立結案"""
        self.ensure_one()
        if not self.can_create_closure:
            raise UserError('目前狀態無法建立結案，請確認正驗已核定且驗收通過')

        if self.closure_id:
            return {
                'type': 'ir.actions.act_window',
                'name': '結案處理',
                'res_model': 'project.closure',
                'view_mode': 'form',
                'res_id': self.closure_id.id,
            }

        return {
            'type': 'ir.actions.act_window',
            'name': '建立結案',
            'res_model': 'project.closure',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.project_id.id,
                'default_final_acceptance_id': self.id,
                'default_warranty_start_date': self.warranty_start_date,
                'default_warranty_end_date': self.warranty_end_date,
                'default_warranty_period_months': self.warranty_period_months,
                'default_warranty_bond_amount': self.warranty_bond_amount,
            },
            'target': 'current',
        }

    # === 建立缺失 ===
    def action_create_defect(self):
        """建立驗收缺失"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '建立驗收缺失',
            'res_model': 'acceptance.defect',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.project_id.id,
                'default_final_acceptance_id': self.id,
                'default_source': 'final',
                'default_responsible_company_id': self.contractor_company_id.id,
            },
            'target': 'current',
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('acceptance.final') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'cancelled'):
                raise UserError('只有草稿或已取消的正驗可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('acceptance_date', 'preliminary_acceptance_id')
    def _check_dates(self):
        for record in self:
            if record.acceptance_date and record.preliminary_acceptance_id.acceptance_date:
                if record.acceptance_date < record.preliminary_acceptance_id.acceptance_date:
                    raise ValidationError('正驗日期不得早於初驗日期')


class AcceptanceFinalLine(models.Model):
    """正驗項目明細"""
    _name = 'acceptance.final.line'
    _description = '正驗項目明細'
    _order = 'sequence, id'

    # === 關聯 ===
    acceptance_id = fields.Many2one(
        'acceptance.final',
        string='正驗單',
        required=True,
        ondelete='cascade',
        index=True)

    sequence = fields.Integer(
        string='序號',
        default=10)

    # === 驗收項目 ===
    category = fields.Selection([
        ('quality', '品質'),
        ('quantity', '數量'),
        ('function', '功能'),
        ('safety', '安全'),
        ('document', '文件'),
        ('improvement', '缺失改善'),
        ('other', '其他'),
    ], string='項目類別', required=True, default='quality')

    name = fields.Char(
        string='驗收項目',
        required=True)

    description = fields.Text(
        string='項目說明')

    # === 關聯初驗缺失 ===
    preliminary_defect_id = fields.Many2one(
        'acceptance.defect',
        string='原初驗缺失',
        domain="[('preliminary_acceptance_id', '=', parent.preliminary_acceptance_id)]",
        help='對應的初驗缺失項目')

    # === 驗收結果 ===
    result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '有條件合格'),
        ('fail', '不合格'),
        ('na', '不適用'),
    ], string='驗收結果', default='pass', required=True)

    defect_description = fields.Text(
        string='缺失說明')

    # === 備註 ===
    note = fields.Text(
        string='備註')
