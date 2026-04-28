# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionDefectPortal(models.Model):
    """
    缺失管理 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可查看並填寫改善說明
    """
    _inherit = ['supervision.defect', 'portal.mixin']
    _name = 'supervision.defect'

    def _compute_access_url(self):
        super()._compute_access_url()
        for defect in self:
            defect.access_url = f'/construction/defect/{defect.id}'

    # === Portal 專用欄位 ===
    portal_improver_id = fields.Many2one(
        'res.partner',
        string='Portal 改善人',
        help='由 Portal 用戶填寫改善說明時記錄')

    portal_improvement_note = fields.Text(
        string='Portal 改善說明',
        help='Portal 用戶填寫的改善說明')

    portal_updated_date = fields.Datetime(
        string='Portal 更新時間',
        help='Portal 用戶最後更新時間')

    @api.model
    def _get_portal_defects_domain(self, partner, project_ids=None):
        """
        取得 Portal 用戶可存取的缺失 domain
        """
        domain = []
        if project_ids:
            domain.append(('project_id', 'in', project_ids))
        return domain

    def portal_submit_improvement(self, improvement_text, partner,
                                   after_photos=None,
                                   corrective_action=None,
                                   preventive_action=None):
        """
        Portal 用戶提交改善說明

        Args:
            improvement_text: 改善說明文字
            partner: Portal 用戶的 partner
            after_photos: 改善後照片附件 IDs
            corrective_action: 矯正措施
            preventive_action: 預防措施
        """
        self.ensure_one()

        vals = {
            'portal_improver_id': partner.id,
            'portal_improvement_note': improvement_text,
            'portal_updated_date': fields.Datetime.now(),
            'improvement_description': improvement_text,
        }

        if corrective_action:
            vals['corrective_action'] = corrective_action
        if preventive_action:
            vals['preventive_action'] = preventive_action
        if after_photos:
            vals['after_photo_ids'] = [(4, pid) for pid in after_photos]

        self.sudo().write(vals)

        # 組訊息正文（含有填的欄位都一併通知）
        body_lines = [f'承包廠商 {partner.name} 已提交改善：']
        body_lines.append(f'【改善說明】\n{improvement_text or "(未填)"}')
        if corrective_action:
            body_lines.append(f'【矯正措施】\n{corrective_action}')
        if preventive_action:
            body_lines.append(f'【預防措施】\n{preventive_action}')
        if after_photos:
            body_lines.append(f'【改善後照片】已上傳 {len(after_photos)} 張')

        self.sudo().message_post(
            body='\n\n'.join(body_lines).replace('\n', '<br/>'),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=list(after_photos) if after_photos else None,
        )

        return True
