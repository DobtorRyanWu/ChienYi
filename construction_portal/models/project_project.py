# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectProjectPortal(models.Model):
    """
    project.project Portal 擴展

    新增反向關聯欄位和輔助欄位，用於 Portal 安全規則
    讓承包廠商可以不需要成為關注者就能存取工程專案
    """
    _inherit = 'project.project'

    # 反向關聯到 supervision.project
    supervision_project_ids = fields.One2many(
        'supervision.project',
        'project_id',
        string='監造工程案件')

    # Portal 安全規則輔助欄位
    # 儲存所有關聯 supervision.project 的承包廠商 partner IDs
    portal_contractor_partner_ids = fields.Many2many(
        'res.partner',
        'project_project_portal_contractor_rel',
        'project_id', 'partner_id',
        string='Portal 承包廠商',
        compute='_compute_portal_contractor_partner_ids',
        store=True,
        help='關聯監造工程的承包廠商，用於 Portal 安全規則')

    @api.depends('supervision_project_ids', 'supervision_project_ids.contractor_partner_ids')
    def _compute_portal_contractor_partner_ids(self):
        """計算關聯監造工程的所有承包廠商 partner IDs"""
        for project in self:
            partner_ids = project.supervision_project_ids.mapped('contractor_partner_ids')
            project.portal_contractor_partner_ids = partner_ids
