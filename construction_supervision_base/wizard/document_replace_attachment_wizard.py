# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class DocumentReplaceAttachmentWizard(models.TransientModel):
    """
    替換附件精靈
    
    將當前附件標記為歷史，上傳新的附件作為當前版本
    """
    _name = 'document.replace.attachment.wizard'
    _description = '替換附件精靈'
    
    document_id = fields.Many2one(
        'supervision.document',
        string='文件',
        required=True,
        readonly=True)
    
    current_attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_current_attachments',
        string='目前的附件',
        readonly=True)
    
    @api.depends('document_id')
    def _compute_current_attachments(self):
        """計算當前附件"""
        for wizard in self:
            if wizard.document_id:
                wizard.current_attachment_ids = wizard.document_id.current_attachment_ids
            else:
                wizard.current_attachment_ids = False
    
    new_attachment_ids = fields.Many2many(
        'ir.attachment',
        'replace_wizard_attachment_rel',
        'wizard_id', 'attachment_id',
        string='新的附件',
        help='上傳新的附件檔案')
    
    version_note = fields.Char(
        string='版本說明',
        help='說明此次更新的內容')
    
    keep_old_attachments = fields.Boolean(
        string='保留舊附件為歷史',
        default=True,
        help='勾選後舊附件會移至歷史記錄；取消勾選則直接刪除')
    
    def action_replace(self):
        """執行替換"""
        self.ensure_one()
        
        if not self.new_attachment_ids:
            raise UserError('請上傳至少一個新的附件檔案')
        
        # 取得當前附件
        current_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'supervision.document'),
            ('res_id', '=', self.document_id.id),
            ('is_current_version', '=', True),
        ])
        
        # 處理舊附件
        if self.keep_old_attachments:
            # 移至歷史
            current_attachments.write({
                'is_current_version': False,
                'replaced_date': fields.Datetime.now(),
                'replaced_by_id': self.env.uid,
                'version_note': self.version_note or '被新版本替換',
            })
        else:
            # 直接刪除
            current_attachments.unlink()
        
        # 設定新附件
        self.new_attachment_ids.write({
            'res_model': 'supervision.document',
            'res_id': self.document_id.id,
            'is_current_version': True,
            'version_note': self.version_note or '新版本',
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '替換成功',
                'message': f'已替換 {len(current_attachments)} 個附件',
                'type': 'success',
                'sticky': False,
            }
        }
