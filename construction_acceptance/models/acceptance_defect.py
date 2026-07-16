# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class AcceptanceDefect(models.Model):
    """
    驗收缺失

    設計說明：
    - 獨立於 NCR (supervision.defect) 的驗收缺失模型
    - 專門追蹤初驗/正驗發現的缺失
    - 完整的改善追蹤與覆驗流程
    - 支援逾期自動警示
    """
    _name = 'acceptance.defect'
    _description = '驗收缺失'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'deadline asc, id desc'

    # === 基本資料 ===
    name = fields.Char(
        string='缺失編號',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('acceptance.defect') or '/',
        index=True)

    # === 工程關聯 ===
    project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True)

    company_id = fields.Many2one(
        'res.company',
        string='管理公司',
        related='project_id.company_id',
        store=True)

    # === 驗收關聯 ===
    preliminary_acceptance_id = fields.Many2one(
        'acceptance.preliminary',
        string='初驗來源',
        tracking=True,
        index=True,
        help='此缺失來自的初驗')

    final_acceptance_id = fields.Many2one(
        'acceptance.final',
        string='正驗來源',
        tracking=True,
        index=True,
        help='此缺失來自的正驗')

    source = fields.Selection([
        ('preliminary', '初驗'),
        ('final', '正驗'),
    ], string='缺失來源', required=True, default='preliminary', tracking=True)

    source_display = fields.Char(
        string='來源單據',
        compute='_compute_source_display')

    @api.depends('source', 'preliminary_acceptance_id', 'final_acceptance_id')
    def _compute_source_display(self):
        for record in self:
            if record.source == 'preliminary' and record.preliminary_acceptance_id:
                record.source_display = record.preliminary_acceptance_id.name
            elif record.source == 'final' and record.final_acceptance_id:
                record.source_display = record.final_acceptance_id.name
            else:
                record.source_display = ''

    # === 缺失分類 ===
    category = fields.Selection([
        ('quality', '品質缺失'),
        ('quantity', '數量不符'),
        ('function', '功能缺失'),
        ('safety', '安全缺失'),
        ('document', '文件缺失'),
        ('appearance', '外觀缺失'),
        ('other', '其他'),
    ], string='缺失類別', required=True, default='quality', tracking=True)

    severity = fields.Selection([
        ('minor', '輕微'),
        ('major', '重大'),
        ('critical', '嚴重'),
    ], string='嚴重程度', required=True, default='minor', tracking=True)

    # === 缺失內容 ===
    description = fields.Text(
        string='缺失說明',
        required=True,
        tracking=True)

    location = fields.Char(
        string='發生位置',
        help='具體位置或工項編號')

    task_id = fields.Many2one(
        'project.task',
        string='關聯工項',
        help='與此缺失相關的契約工項')

    found_date = fields.Date(
        string='發現日期',
        required=True,
        default=fields.Date.today,
        tracking=True)

    # === 責任歸屬 ===
    responsible_company_id = fields.Many2one(
        'res.company',
        string='責任廠商',
        domain="[('company_type', '=', 'contractor')]",
        tracking=True)

    responsible_user_id = fields.Many2one(
        'res.users',
        string='負責人',
        tracking=True)

    discovery_user_id = fields.Many2one(
        'res.users',
        string='發現人',
        default=lambda self: self.env.uid,
        tracking=True,
        help='實際發現此驗收缺失的人員')

    # === 改善期限 ===
    deadline = fields.Date(
        string='改善期限',
        required=True,
        tracking=True)

    extension_count = fields.Integer(
        string='展延次數',
        default=0)

    extension_deadline = fields.Date(
        string='展延後期限',
        tracking=True)

    effective_deadline = fields.Date(
        string='有效期限',
        compute='_compute_effective_deadline',
        store=True)

    @api.depends('deadline', 'extension_deadline')
    def _compute_effective_deadline(self):
        for record in self:
            record.effective_deadline = record.extension_deadline or record.deadline

    # === 改善資訊 ===
    improvement_description = fields.Text(
        string='改善說明',
        tracking=True)

    improvement_date = fields.Date(
        string='改善完成日',
        tracking=True)

    improver_id = fields.Many2one(
        'res.users',
        string='改善執行者',
        tracking=True)

    # === 照片證據 ===
    before_photo_ids = fields.Many2many(
        'ir.attachment',
        'acceptance_defect_before_photo_rel',
        'defect_id', 'attachment_id',
        string='改善前照片')

    after_photo_ids = fields.Many2many(
        'ir.attachment',
        'acceptance_defect_after_photo_rel',
        'defect_id', 'attachment_id',
        string='改善後照片')

    # === 覆驗資訊 ===
    recheck_date = fields.Date(
        string='覆驗日期',
        tracking=True)

    recheck_user_id = fields.Many2one(
        'res.users',
        string='覆驗人員',
        tracking=True)

    recheck_result = fields.Selection([
        ('pass', '合格'),
        ('fail', '不合格'),
        ('partial', '部分合格'),
    ], string='覆驗結果', tracking=True)

    recheck_comment = fields.Text(
        string='覆驗意見')

    recheck_count = fields.Integer(
        string='覆驗次數',
        default=0)

    # === 結案資訊 ===
    close_date = fields.Datetime(
        string='結案時間',
        readonly=True)

    closer_id = fields.Many2one(
        'res.users',
        string='結案者',
        readonly=True)

    close_comment = fields.Text(
        string='結案說明')

    # === 狀態 ===
    state = fields.Selection([
        ('open', '開立'),
        ('improving', '改善中'),
        ('submitted', '已提交'),
        ('rechecking', '覆驗中'),
        ('resolved', '已解決'),
        ('closed', '已結案'),
    ], string='狀態', default='open', tracking=True, index=True,
       help='開立 -> 改善中 -> 已提交 -> 覆驗中 -> 已解決/改善中(不合格) -> 已結案')

    # === 逾期計算 ===
    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_overdue',
        store=True)

    overdue_days = fields.Integer(
        string='逾期天數',
        compute='_compute_overdue',
        store=True)

    days_remaining = fields.Integer(
        string='剩餘天數',
        compute='_compute_days_remaining')

    @api.depends('effective_deadline', 'state')
    def _compute_overdue(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ('resolved', 'closed'):
                record.is_overdue = False
                record.overdue_days = 0
            elif record.effective_deadline:
                record.is_overdue = today > record.effective_deadline
                if record.is_overdue:
                    record.overdue_days = (today - record.effective_deadline).days
                else:
                    record.overdue_days = 0
            else:
                record.is_overdue = False
                record.overdue_days = 0

    @api.depends('effective_deadline', 'state')
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ('resolved', 'closed'):
                record.days_remaining = 0
            elif record.effective_deadline:
                record.days_remaining = (record.effective_deadline - today).days
            else:
                record.days_remaining = 0

    # === SQL 約束 ===
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '缺失編號必須唯一！'),
    ]

    # === 動作方法 ===
    def action_start_improvement(self):
        """開始改善"""
        for record in self:
            if record.state != 'open':
                raise UserError('只有開立狀態可以開始改善')
            record.state = 'improving'

    def write(self, vals):
        """覆寫 write：responsible_user_id 首次設定時發送通知"""
        needs_notify = {}
        if 'responsible_user_id' in vals and vals['responsible_user_id']:
            for record in self:
                if not record.responsible_user_id:
                    needs_notify[record.id] = vals['responsible_user_id']
        result = super().write(vals)
        for record in self:
            if record.id in needs_notify:
                partner = record.responsible_user_id.partner_id
                record.message_subscribe(partner_ids=partner.ids)
                record.message_post(
                    body=(
                        f'驗收缺失 <b>{record.name}</b> 已指派給您處理，'
                        f'請於 <b>{record.effective_deadline}</b> 前完成改善。<br/>'
                        f'缺失說明：{record.description or "（無）"}'
                    ),
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )
        return result

    def action_submit_improvement(self):
        """提交改善結果"""
        for record in self:
            if record.state != 'improving':
                raise UserError('只有改善中狀態可以提交')
            if not record.improvement_description:
                raise ValidationError('請填寫改善說明')
            record.write({
                'state': 'submitted',
                'improvement_date': fields.Date.today(),
                'improver_id': self.env.uid,
            })
            notify_user = record.discovery_user_id
            if notify_user:
                partner = notify_user.partner_id
                record.message_post(
                    body=f'驗收缺失 <b>{record.name}</b> 已完成改善，請複查。',
                    partner_ids=partner.ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                )

    def action_start_recheck(self):
        """開始覆驗"""
        for record in self:
            if record.state != 'submitted':
                raise UserError('只有已提交狀態可以開始覆驗')
            record.write({
                'state': 'rechecking',
                'recheck_date': fields.Date.today(),
                'recheck_user_id': self.env.uid,
            })

    def action_recheck_pass(self):
        """覆驗通過"""
        for record in self:
            if record.state != 'rechecking':
                raise UserError('只有覆驗中狀態可以完成覆驗')
            record.write({
                'state': 'resolved',
                'recheck_result': 'pass',
                'recheck_count': record.recheck_count + 1,
            })

    def action_recheck_fail(self):
        """覆驗不通過"""
        for record in self:
            if record.state != 'rechecking':
                raise UserError('只有覆驗中狀態可以完成覆驗')
            record.write({
                'state': 'improving',
                'recheck_result': 'fail',
                'recheck_count': record.recheck_count + 1,
            })
            record.message_post(
                body=f'覆驗不通過，需要重新改善。覆驗意見：{record.recheck_comment or "無"}',
                message_type='notification',
            )

    def action_close(self):
        """結案"""
        for record in self:
            if record.state != 'resolved':
                raise UserError('只有已解決狀態可以結案')
            record.write({
                'state': 'closed',
                'close_date': fields.Datetime.now(),
                'closer_id': self.env.uid,
            })

    def action_reopen(self):
        """重新開啟"""
        for record in self:
            if record.state not in ('resolved', 'closed'):
                raise UserError('只有已解決或已結案狀態可以重新開啟')
            record.write({
                'state': 'open',
                'close_date': False,
                'closer_id': False,
                'recheck_result': False,
            })

    def action_extend_deadline(self):
        """展延期限"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '展延期限',
            'res_model': 'acceptance.defect.extend.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_defect_id': self.id,
                'default_current_deadline': self.effective_deadline,
            },
        }

    # === 排程任務 ===
    @api.model
    def _cron_check_overdue(self):
        """定期檢查逾期缺失"""
        overdue_defects = self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ('resolved', 'closed')),
        ])
        for defect in overdue_defects:
            # 發送通知
            if defect.responsible_user_id:
                defect.message_post(
                    body=f'驗收缺失 {defect.name} 已逾期 {defect.overdue_days} 天，請儘速處理！',
                    partner_ids=defect.responsible_user_id.partner_id.ids,
                    message_type='notification',
                )

    @api.model
    def _cron_send_deadline_reminder(self):
        """發送期限提醒（到期前3天）"""
        today = fields.Date.today()
        from datetime import timedelta
        reminder_date = today + timedelta(days=3)

        upcoming_defects = self.search([
            ('effective_deadline', '=', reminder_date),
            ('state', 'not in', ('resolved', 'closed')),
        ])
        for defect in upcoming_defects:
            if defect.responsible_user_id:
                defect.message_post(
                    body=f'驗收缺失 {defect.name} 將於 3 天後到期，請儘速完成改善！',
                    partner_ids=defect.responsible_user_id.partner_id.ids,
                    message_type='notification',
                )

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('acceptance.defect') or '/'
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

    @api.constrains('source', 'preliminary_acceptance_id', 'final_acceptance_id')
    def _check_source(self):
        for record in self:
            if record.source == 'preliminary' and not record.preliminary_acceptance_id:
                raise ValidationError('缺失來源為初驗時，必須選擇初驗來源')
            if record.source == 'final' and not record.final_acceptance_id:
                raise ValidationError('缺失來源為正驗時，必須選擇正驗來源')


class AcceptanceDefectExtendWizard(models.TransientModel):
    """展延期限精靈"""
    _name = 'acceptance.defect.extend.wizard'
    _description = '展延期限精靈'

    defect_id = fields.Many2one(
        'acceptance.defect',
        string='驗收缺失',
        required=True)

    current_deadline = fields.Date(
        string='目前期限',
        readonly=True)

    new_deadline = fields.Date(
        string='新期限',
        required=True)

    reason = fields.Text(
        string='展延原因',
        required=True)

    @api.constrains('new_deadline', 'current_deadline')
    def _check_new_deadline(self):
        for wizard in self:
            if wizard.new_deadline and wizard.current_deadline:
                if wizard.new_deadline <= wizard.current_deadline:
                    raise ValidationError('新期限必須晚於目前期限')

    def action_confirm(self):
        """確認展延"""
        self.ensure_one()
        self.defect_id.write({
            'extension_deadline': self.new_deadline,
            'extension_count': self.defect_id.extension_count + 1,
        })
        self.defect_id.message_post(
            body=f'期限已展延至 {self.new_deadline}（第 {self.defect_id.extension_count} 次展延）\n'
                 f'展延原因：{self.reason}',
            message_type='notification',
        )
        return {'type': 'ir.actions.act_window_close'}
