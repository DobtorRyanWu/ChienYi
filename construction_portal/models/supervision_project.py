# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionProjectPortal(models.Model):
    """
    工程案件 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可透過關聯的承包廠商查看工程案件
    """
    # 原生 project.project 已含 portal.mixin，此處明列以保留本模組對 mixin hook 的覆寫。
    # list 形式 _inherit 混入 mixin 時，必須顯式指定 _name，否則 Odoo 會用類別名當新 model
    _name = 'project.project'
    _inherit = ['project.project', 'portal.mixin']

    # === Portal 安全規則輔助欄位 ===
    # 因為 Many2many 欄位遍歷在 ir.rule domain 中無法正確運作
    # 所以新增此欄位儲存承包廠商的 partner IDs
    contractor_partner_ids = fields.Many2many(
        'res.partner',
        'supervision_project_contractor_partner_rel',
        'project_id', 'partner_id',
        string='承包廠商聯絡人',
        compute='_compute_contractor_partner_ids',
        store=True,
        help='承包廠商公司對應的聯絡人，用於 Portal 安全規則')

    @api.depends('contractor_company_ids', 'contractor_company_ids.partner_id')
    def _compute_contractor_partner_ids(self):
        """計算承包廠商的 partner IDs"""
        for project in self:
            project.contractor_partner_ids = project.contractor_company_ids.mapped('partner_id')

    def _compute_access_url(self):
        super()._compute_access_url()
        for project in self:
            project.access_url = f'/construction/{project.id}'

    def _get_portal_return_action(self):
        """Portal 返回動作"""
        self.ensure_one()
        return self.env.ref('construction_portal.portal_my_construction_projects')

    @api.model
    def _get_portal_projects_domain(self, partner):
        """
        取得 Portal 用戶可存取的工程案件 domain

        邏輯：
        - 內部用戶（監造工程師等）：顯示所屬公司管理的案件，
          或自己為監造工程師的案件。僅排除「終止」狀態。
        - Portal 用戶（承包廠商）：顯示公司為承包廠商的案件，
          排除「未開始」和「終止」狀態。
        """
        user = self.env.user

        # 系統管理者：與後台 Rule 143「管理者: 工程案件完整存取」對齊，
        # 不做公司過濾，只排除「終止」狀態（必須先於 group_user 判斷，
        # 因為 group_system 是 group_user 的超集）
        if user.has_group('base.group_system'):
            return [('state', '!=', 'terminated')]

        # 內部用戶：監造單位人員
        # 注意：company_id 用 env.companies.ids（跟隨 Odoo 右上角多公司切換器），
        # 不用 user.company_id.id（那個只會拿到使用者的主要公司,無法跨公司切換）
        if user.has_group('base.group_user'):
            return [
                '|',
                ('supervision_engineer_id', '=', user.id),
                ('company_id', 'in', self.env.companies.ids),
                ('state', '!=', 'terminated'),
            ]

        # Portal 用戶：依角色分流（與 ir.rule 對齊）
        # - 老闆 group_portal_boss：公司承包的所有專案
        # - 主管/現場/閱覽：只看被指派為「參與成員」的專案
        company_partner = partner.commercial_partner_id or partner

        if user.has_group('construction_supervision_base.group_portal_boss'):
            return [
                ('contractor_partner_ids', 'in', [company_partner.id]),
                ('state', 'not in', ['draft', 'terminated']),
            ]

        return [
            ('member_user_ids', 'in', [user.id]),
            ('state', 'not in', ['draft', 'terminated']),
        ]

    # === 進度欄位（供 Portal 模板使用）===
    actual_progress = fields.Float(
        string='實際進度(%)',
        compute='_compute_actual_progress',
        digits=(5, 2),
        help='從使用中進度表取得累計實際進度')

    def _compute_actual_progress(self):
        """從 construction_progress 的累計實際進度取得"""
        for project in self:
            if 'schedule_cumulative_actual' in project._fields:
                project.actual_progress = project.schedule_cumulative_actual
            else:
                project.actual_progress = 0.0

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
