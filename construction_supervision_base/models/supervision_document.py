# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionDocument(models.Model):
    """
    工程文件管理

    設計特點：
    - 完整的文件分類體系
    - 版本控制機制
    - 審核流程 (提送 -> 審查 -> 核定)
    - 關聯 ir.attachment 儲存實際檔案
    """
    _name = 'supervision.document'
    _description = '工程文件'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='文件名稱', required=True, tracking=True)

    project_id = fields.Many2one(
        'supervision.project', string='所屬工程',
        required=True, ondelete='cascade', index=True)

    # === 文件分類 ===
    document_type = fields.Selection([
        # 開工文件
        ('personnel_list', '工地人員名冊'),
        ('schedule', '工程預定進度表'),
        ('waste_plan', '剩餘資源處理計畫書'),
        ('construction_plan', '施工計畫書'),
        ('quality_plan', '品質計畫書'),
        ('safety_plan', '職業安全衛生管理計畫書'),
        ('insurance', '工程保險'),
        ('material_approval', '材料設備送審'),
        # 施工文件
        ('daily_log', '施工日誌'),
        ('supervision_report', '監造報表'),
        ('test_report', '試驗報告'),
        ('inspection_record', '檢驗紀錄'),
        ('photo', '工程照片'),
        ('meeting_minutes', '會議紀錄'),
        # 竣工文件
        ('completion_drawing', '竣工圖'),
        ('completion_settlement', '竣工結算'),
        ('supervision_final_report', '監造報告書'),
        ('quality_certificate', '品質證明'),
        ('warranty_certificate', '保固書'),
        # 其他
        ('correspondence', '往來函文'),
        ('change_order', '變更設計'),
        ('other', '其他'),
    ], string='文件類型', required=True, index=True, tracking=True)

    document_category = fields.Selection([
        ('pre_construction', '施工前'),
        ('construction', '施工中'),
        ('completion', '竣工'),
        ('acceptance', '驗收'),
        ('other', '其他'),
    ], string='文件類別',
       compute='_compute_document_category', store=True)

    @api.depends('document_type')
    def _compute_document_category(self):
        pre_construction_types = [
            'personnel_list', 'schedule', 'waste_plan', 'construction_plan',
            'quality_plan', 'safety_plan', 'insurance', 'material_approval'
        ]
        construction_types = [
            'daily_log', 'supervision_report', 'test_report',
            'inspection_record', 'photo', 'meeting_minutes'
        ]
        completion_types = [
            'completion_drawing', 'completion_settlement',
            'supervision_final_report', 'quality_certificate', 'warranty_certificate'
        ]

        for doc in self:
            if doc.document_type in pre_construction_types:
                doc.document_category = 'pre_construction'
            elif doc.document_type in construction_types:
                doc.document_category = 'construction'
            elif doc.document_type in completion_types:
                doc.document_category = 'completion'
            else:
                doc.document_category = 'other'

    # === 文件編號 ===
    document_no = fields.Char(
        string='文件編號', copy=False, index=True,
        help='系統自動產生的文件編號')

    # === 版本控制 ===
    version = fields.Integer(string='版本', default=1)

    parent_id = fields.Many2one(
        'supervision.document', string='前一版本',
        help='此文件的前一個版本')

    child_ids = fields.One2many(
        'supervision.document', 'parent_id', string='後續版本')

    is_current = fields.Boolean(
        string='當前版本', default=True,
        help='標記此版本為當前有效版本')

    # === 附件檔案 ===
    attachment_ids = fields.Many2many(
        'ir.attachment', 'supervision_document_attachment_rel',
        'document_id', 'attachment_id',
        string='附件檔案')

    attachment_count = fields.Integer(
        string='附件數', compute='_compute_attachment_count')

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for doc in self:
            doc.attachment_count = len(doc.attachment_ids)

    # === 公司關聯 ===
    company_id = fields.Many2one(
        'res.company', string='提送公司',
        default=lambda self: self.env.company,
        help='提送此文件的公司')

    # === 簽核資訊 ===
    submitter_id = fields.Many2one(
        'res.users', string='提送者', tracking=True)

    submit_date = fields.Datetime(string='提送時間')

    reviewer_id = fields.Many2one(
        'res.users', string='審查者', tracking=True)

    review_date = fields.Datetime(string='審查時間')

    approver_id = fields.Many2one(
        'res.users', string='核定者', tracking=True)

    approve_date = fields.Datetime(string='核定時間')

    # === 審查意見 ===
    review_comment_ids = fields.One2many(
        'supervision.review.comment', 'document_id', string='審查意見')

    review_result = fields.Selection([
        ('pass', '符合'),
        ('revision', '需補正'),
        ('reject', '不符合'),
    ], string='審查結果', tracking=True)

    # === 狀態管理 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提送'),
        ('reviewing', '審查中'),
        ('revision', '補正中'),
        ('recommended', '建議核定'),
        ('approved', '已核定'),
        ('rejected', '退件'),
    ], string='狀態', default='draft', tracking=True, index=True)

    is_locked = fields.Boolean(
        string='已鎖定', default=False,
        help='鎖定後無法修改')

    # === 到期日 ===
    due_date = fields.Date(
        string='應提送日期',
        help='文件應提送的日期')

    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_is_overdue', store=True)

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for doc in self:
            if doc.due_date and doc.state in ('draft', 'revision'):
                doc.is_overdue = today > doc.due_date
            else:
                doc.is_overdue = False

    # === 備註 ===
    notes = fields.Text(string='備註說明')
    rejection_reason = fields.Text(string='退件原因')

    # === 狀態動作 ===
    def action_submit(self):
        """提送文件"""
        for doc in self:
            if doc.state != 'draft' and doc.state != 'revision':
                raise UserError('只有草稿或補正中狀態可以提送')
            if not doc.attachment_ids:
                raise ValidationError('請至少上傳一個附件檔案')
            doc.write({
                'state': 'submitted',
                'submitter_id': self.env.uid,
                'submit_date': fields.Datetime.now(),
            })

    def action_start_review(self):
        """開始審查"""
        for doc in self:
            if doc.state != 'submitted':
                raise UserError('只有已提送狀態可以開始審查')
            doc.write({
                'state': 'reviewing',
                'reviewer_id': self.env.uid,
            })

    def action_request_revision(self):
        """退回補正"""
        for doc in self:
            if doc.state != 'reviewing':
                raise UserError('只有審查中狀態可以退回補正')

            # 建立新版本
            new_version = doc.copy({
                'version': doc.version + 1,
                'parent_id': doc.id,
                'state': 'draft',
                'is_current': True,
                'submitter_id': False,
                'submit_date': False,
                'reviewer_id': False,
                'review_date': False,
                'approver_id': False,
                'approve_date': False,
                'review_result': False,
            })

            doc.write({
                'state': 'revision',
                'is_current': False,
                'review_result': 'revision',
                'review_date': fields.Datetime.now(),
            })

            return {
                'type': 'ir.actions.act_window',
                'name': '新版本文件',
                'res_model': 'supervision.document',
                'res_id': new_version.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_recommend(self):
        """建議核定"""
        for doc in self:
            if doc.state != 'reviewing':
                raise UserError('只有審查中狀態可以建議核定')
            doc.write({
                'state': 'recommended',
                'review_result': 'pass',
                'review_date': fields.Datetime.now(),
            })

    def action_approve(self):
        """核定"""
        for doc in self:
            if doc.state not in ('reviewing', 'recommended'):
                raise UserError('只有審查中或建議核定狀態可以核定')
            doc.write({
                'state': 'approved',
                'approver_id': self.env.uid,
                'approve_date': fields.Datetime.now(),
                'is_locked': True,
            })

    def action_reject(self):
        """退件"""
        for doc in self:
            if doc.state not in ('submitted', 'reviewing'):
                raise UserError('只有已提送或審查中狀態可以退件')
            doc.write({
                'state': 'rejected',
                'review_result': 'reject',
                'review_date': fields.Datetime.now(),
            })

    def action_reset_draft(self):
        """重設為草稿"""
        for doc in self:
            if doc.state not in ('submitted', 'rejected'):
                raise UserError('只有已提送或退件狀態可以重設為草稿')
            if doc.is_locked:
                raise UserError('已鎖定的文件無法重設')
            doc.write({
                'state': 'draft',
                'submitter_id': False,
                'submit_date': False,
            })

    # === 檢視動作 ===
    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '附件檔案',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
        }

    def action_view_history(self):
        """查看版本歷史"""
        self.ensure_one()

        # 找出所有相關版本
        all_versions = self
        parent = self.parent_id
        while parent:
            all_versions |= parent
            parent = parent.parent_id

        all_versions |= self.child_ids
        for child in self.child_ids:
            all_versions |= child.child_ids

        return {
            'type': 'ir.actions.act_window',
            'name': '版本歷史',
            'res_model': 'supervision.document',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', all_versions.ids)],
            'context': {'create': False},
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('document_no'):
                vals['document_no'] = self.env['ir.sequence'].next_by_code(
                    'supervision.document') or '/'
        return super().create(vals_list)

    def write(self, vals):
        for doc in self:
            if doc.is_locked and not self.env.user.has_group('base.group_system'):
                allowed_fields = {'message_follower_ids', 'message_ids', 'activity_ids'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError('已鎖定的文件無法修改')
        return super().write(vals)

    def unlink(self):
        for doc in self:
            if doc.state not in ('draft', 'rejected'):
                raise UserError('只有草稿或退件狀態的文件可以刪除')
            if doc.is_locked:
                raise UserError('已鎖定的文件無法刪除')
        return super().unlink()

    def name_get(self):
        result = []
        for doc in self:
            name = f'[{doc.document_no}] {doc.name}'
            if doc.version > 1:
                name += f' (v{doc.version})'
            result.append((doc.id, name))
        return result


class SupervisionReviewComment(models.Model):
    """
    審查意見

    記錄文件審查過程中的意見與回覆
    """
    _name = 'supervision.review.comment'
    _description = '審查意見'
    _order = 'item_no, id'

    document_id = fields.Many2one(
        'supervision.document', string='文件',
        required=True, ondelete='cascade')

    item_no = fields.Integer(string='審查項次', default=1)

    review_item = fields.Char(string='審查項目')

    review_result = fields.Selection([
        ('pass', '符合'),
        ('revision', '補正'),
        ('reject', '不符合'),
    ], string='審查結果', required=True)

    comment = fields.Text(string='審查意見')

    reviewer_id = fields.Many2one(
        'res.users', string='審查人',
        default=lambda self: self.env.uid)

    review_date = fields.Datetime(
        string='審查時間',
        default=fields.Datetime.now)

    # === 回覆資訊 ===
    reply = fields.Text(string='回覆說明')

    reply_user_id = fields.Many2one(
        'res.users', string='回覆人')

    reply_date = fields.Datetime(string='回覆時間')

    reply_attachment_ids = fields.Many2many(
        'ir.attachment', 'review_comment_attachment_rel',
        'comment_id', 'attachment_id',
        string='回覆附件')

    def action_reply(self):
        """回覆審查意見"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '回覆審查意見',
            'res_model': 'supervision.review.comment',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
