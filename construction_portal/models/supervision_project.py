# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionProjectPortal(models.Model):
    """
    工程案件 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可透過關聯的承包廠商查看工程案件
    """
    _inherit = ['supervision.project', 'portal.mixin']
    _name = 'supervision.project'

    def _compute_access_url(self):
        super()._compute_access_url()
        for project in self:
            project.access_url = f'/my/construction/{project.id}'

    def _get_portal_return_action(self):
        """Portal 返回動作"""
        self.ensure_one()
        return self.env.ref('construction_portal.portal_my_construction_projects')

    @api.model
    def _get_portal_projects_domain(self, partner):
        """
        取得 Portal 用戶可存取的工程案件 domain

        邏輯：
        1. 找出 partner 所屬的公司 (透過 parent_id 或 commercial_partner_id)
        2. 找出該公司作為承包廠商的工程案件
        """
        # 取得 partner 的公司 (parent or self)
        company_partner = partner.commercial_partner_id or partner

        # 找出以此公司為承包廠商的工程案件
        # 承包廠商是 res.company，需要找到對應的 company
        companies = self.env['res.company'].sudo().search([
            ('partner_id', '=', company_partner.id)
        ])

        if companies:
            return [
                ('contractor_company_ids', 'in', companies.ids),
                ('state', 'not in', ['draft', 'terminated']),
            ]
        return [('id', '=', False)]  # 沒有符合的公司，返回空結果

    # === Portal 統計欄位 ===
    inspection_count = fields.Integer(
        string='自主檢查數',
        compute='_compute_portal_counts')

    defect_count = fields.Integer(
        string='缺失數',
        compute='_compute_portal_counts')

    photo_count = fields.Integer(
        string='照片數',
        compute='_compute_portal_counts')

    open_defect_count = fields.Integer(
        string='待處理缺失',
        compute='_compute_portal_counts')

    def _compute_portal_counts(self):
        for project in self:
            # 自主檢查數
            project.inspection_count = self.env['general.self.inspection'].search_count([
                ('project_id', '=', project.id)
            ])
            # 缺失數
            project.defect_count = self.env['supervision.defect'].search_count([
                ('project_id', '=', project.id)
            ])
            # 待處理缺失
            project.open_defect_count = self.env['supervision.defect'].search_count([
                ('project_id', '=', project.id),
                ('state', 'not in', ['verified', 'closed'])
            ])
            # 照片數
            project.photo_count = self.env['supervision.photo'].search_count([
                ('project_id', '=', project.id)
            ])
