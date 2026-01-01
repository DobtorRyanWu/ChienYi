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
            defect.access_url = f'/my/construction/defect/{defect.id}'

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

    def portal_submit_improvement(self, improvement_text, partner, after_photos=None):
        """
        Portal 用戶提交改善說明

        Args:
            improvement_text: 改善說明文字
            partner: Portal 用戶的 partner
            after_photos: 改善後照片附件 IDs
        """
        self.ensure_one()

        vals = {
            'portal_improver_id': partner.id,
            'portal_improvement_note': improvement_text,
            'portal_updated_date': fields.Datetime.now(),
            'improvement_description': improvement_text,
        }

        if after_photos:
            vals['after_photo_ids'] = [(6, 0, after_photos)]

        self.sudo().write(vals)

        # 發送通知給監造人員
        self.message_post(
            body=f'承包廠商已提交改善說明：\n{improvement_text}',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True
