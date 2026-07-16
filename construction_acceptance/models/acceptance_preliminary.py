# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class AcceptancePreliminary(models.Model):
    """
    初驗紀錄

    設計說明：
    - 工程竣工後的初次驗收
    - 記錄驗收人員、日期、項目與結果
    - 發現缺失時設定改善期限
    - 支援部分合格、不合格等多種結果
    - 完成後可進行正驗
    """
    _name = 'acceptance.preliminary'
    _description = '初驗紀錄'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'acceptance_date desc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='初驗單號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('acceptance.preliminary') or '/',
        index=True)

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
        readonly=True,
        domain="[('state', '=', 'completion')]")

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    contractor_company_id = fields.Many2one(
        'res.company',
        string='施工廠商',
        domain="[('company_type', '=', 'contractor')]",
        tracking=True,
        help='被驗收的施工廠商')

    authority_name = fields.Char(
        string='業主/主辦機關',
        related='project_id.authority_name',
        store=True)

    # === 驗收日期與期間 ===
    acceptance_date = fields.Date(
        string='初驗日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    scheduled_date = fields.Date(
        string='預定初驗日',
        tracking=True,
        help='原定初驗日期')

    completion_date = fields.Date(
        string='竣工日期',
        related='project_id.actual_end_date',
        store=True)

    days_from_completion = fields.Integer(
        string='竣工後天數',
        compute='_compute_days_from_completion',
        store=True,
        help='從竣工到初驗的天數')

    @api.depends('acceptance_date', 'completion_date')
    def _compute_days_from_completion(self):
        for record in self:
            if record.acceptance_date and record.completion_date:
                record.days_from_completion = (record.acceptance_date - record.completion_date).days
            else:
                record.days_from_completion = 0

    # === 驗收人員 ===
    chairman_id = fields.Many2one(
        'res.partner',
        string='驗收主席',
        tracking=True,
        help='主辦機關指派的驗收主席')

    committee_ids = fields.Many2many(
        'res.partner',
        'preliminary_acceptance_committee_rel',
        'acceptance_id', 'partner_id',
        string='驗收委員',
        help='驗收委員會成員')

    supervision_representative_id = fields.Many2one(
        'res.users',
        string='監造代表',
        default=lambda self: self.env.uid,
        tracking=True,
        help='監造單位代表')

    contractor_representative_id = fields.Many2one(
        'res.partner',
        string='廠商代表',
        tracking=True,
        help='施工廠商代表')

    # === 驗收項目明細 ===
    line_ids = fields.One2many(
        'acceptance.preliminary.line',
        'acceptance_id',
        string='驗收項目',
        copy=True)

    # === 驗收結果 ===
    result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '有條件合格'),
        ('partial', '部分合格'),
        ('fail', '不合格'),
    ], string='驗收結果', tracking=True,
       help='合格：全部通過；有條件合格：有輕微缺失但可接受；部分合格：部分項目不合格；不合格：多項不合格')

    # === 缺失統計 ===
    defect_ids = fields.One2many(
        'acceptance.defect',
        'preliminary_acceptance_id',
        string='驗收缺失')

    defect_count = fields.Integer(
        string='缺失數量',
        compute='_compute_defect_statistics',
        store=True)

    unresolved_defect_count = fields.Integer(
        string='未解決缺失',
        compute='_compute_defect_statistics',
        store=True)

    has_unresolved_defect = fields.Boolean(
        string='有未解決缺失',
        compute='_compute_defect_statistics',
        store=True)

    @api.depends('defect_ids', 'defect_ids.state')
    def _compute_defect_statistics(self):
        for record in self:
            defects = record.defect_ids
            record.defect_count = len(defects)
            unresolved = defects.filtered(lambda d: d.state not in ('resolved', 'closed'))
            record.unresolved_defect_count = len(unresolved)
            record.has_unresolved_defect = record.unresolved_defect_count > 0

    # === 改善期限 ===
    improvement_deadline = fields.Date(
        string='改善期限',
        tracking=True,
        help='缺失改善的最後期限')

    extension_deadline = fields.Date(
        string='展延後期限',
        tracking=True,
        help='經核准展延後的改善期限')

    effective_deadline = fields.Date(
        string='有效期限',
        compute='_compute_effective_deadline',
        store=True)

    @api.depends('improvement_deadline', 'extension_deadline')
    def _compute_effective_deadline(self):
        for record in self:
            record.effective_deadline = record.extension_deadline or record.improvement_deadline

    # === 相關文件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'preliminary_acceptance_attachment_rel',
        'acceptance_id', 'attachment_id',
        string='驗收附件',
        help='驗收紀錄、會議記錄等')

    minutes = fields.Html(
        string='驗收會議紀錄',
        help='初驗會議記錄內容')

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

    # === 備註 ===
    note = fields.Text(
        string='備註')

    # === 狀態 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('scheduled', '已排定'),
        ('in_progress', '驗收中'),
        ('pending_improvement', '待改善'),
        ('improvement_done', '改善完成'),
        ('reviewed', '已審核'),
        ('closed', '已結案'),
        ('cancelled', '已取消'),
    ], string='狀態', default='draft', tracking=True, index=True,
       help='草稿 -> 已排定 -> 驗收中 -> 待改善/已審核 -> 改善完成 -> 已審核 -> 已結案')

    # === 關聯正驗 ===
    final_acceptance_id = fields.Many2one(
        'acceptance.final',
        string='關聯正驗',
        readonly=True,
        help='基於此初驗產生的正驗')

    can_create_final = fields.Boolean(
        string='可建立正驗',
        compute='_compute_can_create_final')

    @api.depends('state', 'has_unresolved_defect', 'result')
    def _compute_can_create_final(self):
        for record in self:
            # 初驗已審核、無未解決缺失、結果為合格或有條件合格
            record.can_create_final = (
                record.state in ('reviewed', 'improvement_done') and
                not record.has_unresolved_defect and
                record.result in ('pass', 'conditional', 'partial')
            )

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '初驗單號必須唯一！'),
    ]

    # === 動作方法 ===
    def action_schedule(self):
        """排定驗收"""
        for record in self:
            if record.state != 'draft':
                raise UserError('只有草稿狀態可以排定驗收')
            if not record.scheduled_date:
                raise ValidationError('請先設定預定初驗日')
            record.state = 'scheduled'

    def action_start(self):
        """開始驗收"""
        for record in self:
            if record.state not in ('draft', 'scheduled'):
                raise UserError('只有草稿或已排定狀態可以開始驗收')
            record.state = 'in_progress'

    def action_complete_with_defects(self):
        """完成驗收（有缺失）"""
        for record in self:
            if record.state != 'in_progress':
                raise UserError('只有驗收中狀態可以完成驗收')
            if not record.result:
                raise ValidationError('請先選擇驗收結果')
            if not record.improvement_deadline:
                raise ValidationError('有缺失時必須設定改善期限')
            record.state = 'pending_improvement'
            # 更新工程狀態為驗收中
            record.project_id.write({'state': 'acceptance'})

    def action_complete_pass(self):
        """完成驗收（合格）"""
        for record in self:
            if record.state != 'in_progress':
                raise UserError('只有驗收中狀態可以完成驗收')
            if record.defect_count > 0:
                raise UserError('有缺失記錄，請使用「有缺失」按鈕完成驗收')
            record.write({
                'result': 'pass',
                'state': 'reviewed',
            })
            # 更新工程狀態為驗收中
            record.project_id.write({'state': 'acceptance'})

    def action_confirm_improvement(self):
        """確認改善完成"""
        for record in self:
            if record.state != 'pending_improvement':
                raise UserError('只有待改善狀態可以確認改善完成')
            if record.has_unresolved_defect:
                raise UserError(f'尚有 {record.unresolved_defect_count} 項缺失未解決')
            record.state = 'improvement_done'

    def action_review(self):
        """審核通過"""
        for record in self:
            if record.state not in ('in_progress', 'improvement_done'):
                raise UserError('只有驗收中或改善完成狀態可以審核')
            record.write({
                'state': 'reviewed',
                'reviewer_id': self.env.uid,
                'review_date': fields.Datetime.now(),
            })

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'reviewed':
                raise UserError('只有已審核狀態可以結案')
            record.state = 'closed'

    def action_cancel(self):
        """取消"""
        for record in self:
            if record.state in ('closed',):
                raise UserError('已結案的初驗不可取消')
            record.state = 'cancelled'

    def action_reset_draft(self):
        """重設為草稿"""
        for record in self:
            if record.state not in ('scheduled', 'cancelled'):
                raise UserError('只有已排定或已取消狀態可以重設為草稿')
            record.state = 'draft'

    # === 建立正驗 ===
    def action_create_final_acceptance(self):
        """建立正驗"""
        self.ensure_one()
        if not self.can_create_final:
            raise UserError('目前狀態無法建立正驗，請確認缺失已解決且初驗已審核')

        if self.final_acceptance_id:
            return {
                'type': 'ir.actions.act_window',
                'name': '正驗紀錄',
                'res_model': 'acceptance.final',
                'view_mode': 'form',
                'res_id': self.final_acceptance_id.id,
            }

        return {
            'type': 'ir.actions.act_window',
            'name': '建立正驗',
            'res_model': 'acceptance.final',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.project_id.id,
                'default_preliminary_acceptance_id': self.id,
                'default_contractor_company_id': self.contractor_company_id.id,
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
                'default_preliminary_acceptance_id': self.id,
                'default_source': 'preliminary',
                'default_deadline': self.effective_deadline,
                'default_responsible_company_id': self.contractor_company_id.id,
            },
            'target': 'current',
        }

    # === 查看缺失 ===
    def action_view_defects(self):
        """查看驗收缺失"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '驗收缺失',
            'res_model': 'acceptance.defect',
            'view_mode': 'list,form',
            'domain': [('preliminary_acceptance_id', '=', self.id)],
            'context': {
                'default_project_id': self.project_id.id,
                'default_preliminary_acceptance_id': self.id,
                'default_source': 'preliminary',
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('acceptance.preliminary') or '/'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'cancelled'):
                raise UserError('只有草稿或已取消的初驗可以刪除')
        return super().unlink()

    # === 約束 ===
    @api.constrains('acceptance_date', 'completion_date')
    def _check_dates(self):
        for record in self:
            if record.acceptance_date and record.completion_date:
                if record.acceptance_date < record.completion_date:
                    raise ValidationError('初驗日期不得早於竣工日期')

    @api.constrains('improvement_deadline', 'acceptance_date')
    def _check_improvement_deadline(self):
        for record in self:
            if record.improvement_deadline and record.acceptance_date:
                if record.improvement_deadline < record.acceptance_date:
                    raise ValidationError('改善期限不得早於初驗日期')


class AcceptancePreliminaryLine(models.Model):
    """初驗項目明細"""
    _name = 'acceptance.preliminary.line'
    _description = '初驗項目明細'
    _order = 'sequence, id'

    # === 關聯 ===
    acceptance_id = fields.Many2one(
        'acceptance.preliminary',
        string='初驗單',
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
        ('other', '其他'),
    ], string='項目類別', required=True, default='quality')

    name = fields.Char(
        string='驗收項目',
        required=True)

    description = fields.Text(
        string='項目說明')

    # === 關聯工項 ===
    task_id = fields.Many2one(
        'project.task',
        string='關聯工項',
        help='對應的契約工項')

    # === 驗收結果 ===
    result = fields.Selection([
        ('pass', '合格'),
        ('conditional', '有條件合格'),
        ('fail', '不合格'),
        ('na', '不適用'),
    ], string='驗收結果', default='pass', required=True)

    defect_description = fields.Text(
        string='缺失說明',
        help='不合格或有條件合格時的缺失說明')

    # === 備註 ===
    note = fields.Text(
        string='備註')

    # === 約束 ===
    @api.constrains('result', 'defect_description')
    def _check_defect_description(self):
        for line in self:
            if line.result in ('conditional', 'fail') and not line.defect_description:
                raise ValidationError(
                    f'項目「{line.name}」為有條件合格或不合格，請填寫缺失說明')
