# -*- coding: utf-8 -*-

from odoo import models, fields, api


class GeneralSelfInspectionPortal(models.Model):
    """
    一般式自主檢查 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可建立與查看自主檢查
    """
    _inherit = ['general.self.inspection', 'portal.mixin']
    _name = 'general.self.inspection'

    def _compute_access_url(self):
        super()._compute_access_url()
        for inspection in self:
            inspection.access_url = f'/my/construction/inspection/{inspection.id}'

    # === Portal 專用欄位 ===
    portal_creator_id = fields.Many2one(
        'res.partner',
        string='Portal 填表人',
        help='由 Portal 用戶建立時記錄的聯絡人')

    is_portal_created = fields.Boolean(
        string='Portal 建立',
        default=False,
        help='是否由 Portal 用戶建立')

    @api.model
    def _get_portal_inspections_domain(self, partner, project_ids=None):
        """
        取得 Portal 用戶可存取的自主檢查 domain
        """
        domain = []
        if project_ids:
            domain.append(('project_id', 'in', project_ids))

        # Portal 用戶可以看到:
        # 1. 自己建立的
        # 2. 所屬工程的所有檢查
        return domain

    @api.model
    def create_from_portal(self, vals, partner):
        """
        從 Portal 建立自主檢查

        Args:
            vals: 表單資料
            partner: Portal 用戶的 partner

        Returns:
            新建立的自主檢查記錄
        """
        vals.update({
            'portal_creator_id': partner.id,
            'is_portal_created': True,
        })
        return self.sudo().create(vals)
