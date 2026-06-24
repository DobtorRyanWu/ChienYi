# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError


class SupervisionDocument(models.Model):
    """
    工程文件管理（輕量版）

    設計特點：
    - 簡潔的文件分類體系
    - 附件歷史記錄（自動保留所有版本）
    - 簡化的狀態流程（草稿/已上傳/已封存）
    """
    _name = 'supervision.document'
    _description = '工程文件'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    active = fields.Boolean(string='啟用', default=True)

    name = fields.Char(
        string='文件名稱', required=True, tracking=True)

    project_id = fields.Many2one(
        'supervision.project', string='所屬工程',
        required=True, ondelete='cascade', index=True, tracking=True)

    # === 文件分類 ===
    document_category_id = fields.Many2one(
        'supervision.document.category',
        string='文件分類',
        required=True,
        index=True,
        tracking=True,
        help='選擇此文件所屬的分類')

    # 向下相容：保留舊欄位作為關聯欄位
    document_type = fields.Char(
        string='舊文件類型代碼',
        related='document_category_id.code',
        store=False,
        readonly=True,
        help='僅供系統內部使用')

    # === 文件編號 ===
    document_no = fields.Char(
        string='文件編號', copy=False, index=True,
        help='系統自動產生的文件編號')

    # === 附件管理（支援歷史記錄） ===
    # 上傳新附件的可寫欄位
    upload_attachment_ids = fields.Many2many(
        'ir.attachment',
        'supervision_document_upload_attachment_rel',
        'document_id', 'attachment_id',
        string='上傳附件',
        help='點擊此處上傳新的文件附件')
    
    attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='所有附件',
        help='包含當前附件與歷史附件')

    current_attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='當前附件',
        help='目前有效的附件檔案')

    history_attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='歷史附件',
        help='已被替換的舊版本附件')

    attachment_count = fields.Integer(
        string='當前附件數', compute='_compute_attachments', store=True)

    history_count = fields.Integer(
        string='歷史附件數', compute='_compute_attachments', store=True)

    def _compute_attachments(self):
        """計算附件相關欄位"""
        Attachment = self.env['ir.attachment']
        for doc in self:
            if doc.id:
                # 取得所有附件
                all_attachments = Attachment.search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', doc.id)
                ])
                
                # 分類當前和歷史附件
                current = all_attachments.filtered(lambda a: a.is_current_version)
                history = all_attachments - current
                
                doc.attachment_ids = all_attachments
                doc.current_attachment_ids = current
                doc.history_attachment_ids = history
                doc.attachment_count = len(current)
                doc.history_count = len(history)
            else:
                doc.attachment_ids = False
                doc.current_attachment_ids = False
                doc.history_attachment_ids = False
                doc.attachment_count = 0
                doc.history_count = 0

    # === 公司關聯 ===
    company_id = fields.Many2one(
        'res.company', string='所屬公司',
        default=lambda self: self.env.company,
        tracking=True,
        help='此文件所屬的公司')

    # === 上傳資訊 ===
    uploader_id = fields.Many2one(
        'res.users', string='上傳者',
        default=lambda self: self.env.uid,
        tracking=True,
        readonly=True)

    upload_date = fields.Datetime(
        string='上傳時間',
        default=fields.Datetime.now,
        tracking=True,
        readonly=True)

    # === 狀態管理（簡化版） ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('uploaded', '已上傳'),
        ('archived', '已封存'),
    ], string='狀態', default='draft', tracking=True, index=True,
       help='草稿：尚未上傳附件；已上傳：已有附件可用；已封存：不再使用')

    # === 到期日提醒 ===
    due_date = fields.Date(
        string='應上傳日期',
        tracking=True,
        help='文件應上傳的期限日期')

    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_is_overdue', store=True)

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for doc in self:
            if doc.due_date and doc.state == 'draft':
                doc.is_overdue = today > doc.due_date
            else:
                doc.is_overdue = False

    # === 備註 ===
    notes = fields.Html(string='備註說明', tracking=True)

    # === 計算欄位：最後更新資訊 ===
    last_update_date = fields.Datetime(
        string='最後更新',
        compute='_compute_last_update')

    last_update_user_id = fields.Many2one(
        'res.users', string='最後更新者',
        compute='_compute_last_update')

    def _compute_last_update(self):
        """計算最後更新資訊"""
        Attachment = self.env['ir.attachment']
        for doc in self:
            if doc.id:
                # 取得最新的附件
                latest = Attachment.search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', doc.id),
                    ('is_current_version', '=', True),
                ], order='create_date desc', limit=1)
                
                if latest:
                    doc.last_update_date = latest.create_date
                    doc.last_update_user_id = latest.create_uid
                else:
                    doc.last_update_date = doc.create_date
                    doc.last_update_user_id = doc.create_uid
            else:
                doc.last_update_date = False
                doc.last_update_user_id = False

    # === 狀態動作 ===
    def action_upload(self):
        """標記為已上傳"""
        for doc in self:
            if not doc.current_attachment_ids:
                raise ValidationError('請先上傳至少一個附件檔案')
            doc.state = 'uploaded'

    def action_archive(self):
        """封存文件"""
        for doc in self:
            doc.state = 'archived'
            doc.active = False

    def action_unarchive(self):
        """取消封存"""
        for doc in self:
            doc.state = 'uploaded' if doc.current_attachment_ids else 'draft'
            doc.active = True

    def action_reset_draft(self):
        """重設為草稿"""
        for doc in self:
            doc.state = 'draft'

    # === 附件管理動作 ===
    def action_view_current_attachments(self):
        """查看當前附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '當前附件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.current_attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
                'default_is_current_version': True,
            },
        }

    def action_view_history_attachments(self):
        """查看歷史附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '歷史附件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.history_attachment_ids.ids)],
            'context': {'create': False},
        }

    def action_replace_attachment(self):
        """替換附件（將當前附件移至歷史）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '替換附件',
            'res_model': 'document.replace.attachment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
            },
        }

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # 自動產生文件編號
            if not vals.get('document_no'):
                vals['document_no'] = self.env['ir.sequence'].next_by_code(
                    'supervision.document') or '/'
            
            # 設定上傳者和上傳時間
            if not vals.get('uploader_id'):
                vals['uploader_id'] = self.env.uid
            if not vals.get('upload_date'):
                vals['upload_date'] = fields.Datetime.now()
        
        return super().create(vals_list)

    def write(self, vals):
        # 處理附件上傳
        if 'upload_attachment_ids' in vals and vals['upload_attachment_ids']:
            # 解析 Many2many 命令
            upload_commands = vals['upload_attachment_ids']
            new_attachment_ids = []
            
            for command in upload_commands:
                if command[0] == 6:  # (6, 0, [ids])
                    new_attachment_ids.extend(command[2])
                elif command[0] == 4:  # (4, id)
                    new_attachment_ids.append(command[1])
            
            if new_attachment_ids:
                # 更新附件的 res_model 和 res_id
                attachments = self.env['ir.attachment'].browse(new_attachment_ids)
                for attachment in attachments:
                    attachment.write({
                        'res_model': self._name,
                        'res_id': self.id,
                        'is_current_version': True,
                    })
            
            # 移除 upload_attachment_ids ，避免寫入資料庫
            vals.pop('upload_attachment_ids')
        
        result = super().write(vals)
        
        # 當附件被上傳且狀態是草稿時，自動改為已上傳
        for doc in self:
            if doc.state == 'draft' and doc.current_attachment_ids:
                doc.state = 'uploaded'
        
        return result

    def unlink(self):
        for doc in self:
            if doc.state == 'uploaded':
                raise UserError('已上傳的文件無法刪除，請先封存')
        return super().unlink()

    def name_get(self):
        result = []
        for doc in self:
            name = f'[{doc.document_no}] {doc.name}'
            result.append((doc.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', ('document_no', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)


class IrAttachment(models.Model):
    """
    擴展附件模型，支援版本標記
    """
    _inherit = 'ir.attachment'

    is_current_version = fields.Boolean(
        string='當前版本',
        default=True,
        help='標記此附件是否為當前有效版本')

    replaced_date = fields.Datetime(
        string='替換時間',
        help='此附件被替換為歷史版本的時間')

    replaced_by_id = fields.Many2one(
        'res.users', string='替換者',
        help='將此附件替換的使用者')

    version_note = fields.Char(
        string='版本備註',
        help='此版本的說明或變更記錄')

    def action_restore_as_current(self):
        """將歷史附件恢復為當前版本"""
        for attachment in self:
            if attachment.is_current_version:
                raise UserError('此附件已經是當前版本')
            
            # 將目前的當前版本改為歷史
            current_attachments = self.search([
                ('res_model', '=', attachment.res_model),
                ('res_id', '=', attachment.res_id),
                ('is_current_version', '=', True),
            ])
            current_attachments.write({
                'is_current_version': False,
                'replaced_date': fields.Datetime.now(),
                'replaced_by_id': self.env.uid,
            })
            
            # 恢復此附件為當前版本
            attachment.write({
                'is_current_version': True,
                'replaced_date': False,
                'replaced_by_id': False,
            })
    
    @api.model_create_multi
    def create(self, vals_list):
        """創建附件後觸發 supervision.document 的計數更新"""
        attachments = super().create(vals_list)
        self._trigger_document_recompute(attachments)
        return attachments
    
    def write(self, vals):
        """更新附件後觸發 supervision.document 的計數更新"""
        result = super().write(vals)
        # 如果更新了 is_current_version 欄位，觸發重新計算
        if 'is_current_version' in vals:
            self._trigger_document_recompute(self)
        return result
    
    def unlink(self):
        """刪除附件前記錄關聯的文件，以便觸發重新計算"""
        # 記錄關聯的 supervision.document
        doc_ids = set()
        for attachment in self:
            if attachment.res_model == 'supervision.document' and attachment.res_id:
                doc_ids.add(attachment.res_id)
        
        result = super().unlink()
        
        # 觸發重新計算
        if doc_ids:
            docs = self.env['supervision.document'].browse(list(doc_ids))
            docs._compute_attachments()
        
        return result
    
    def _trigger_document_recompute(self, attachments):
        """觸發 supervision.document 的附件計數重新計算"""
        doc_ids = set()
        for attachment in attachments:
            if attachment.res_model == 'supervision.document' and attachment.res_id:
                doc_ids.add(attachment.res_id)
        
        if doc_ids:
            docs = self.env['supervision.document'].browse(list(doc_ids))
            docs._compute_attachments()
