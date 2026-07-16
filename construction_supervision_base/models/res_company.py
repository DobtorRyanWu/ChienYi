# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    """
    公司類型擴展

    擴展 res.company 支援工程監造系統的多公司架構：
    - supervision: 設計監造單位
    - contractor: 施工廠商
    """
    _inherit = 'res.company'

    # === 公司類型 ===
    company_type = fields.Selection([
        ('supervision', '設計監造單位'),
        ('contractor', '施工廠商'),
    ], string='公司類型', default='contractor',
       help='決定此公司在工程管理系統中的角色')

    # === 證照資訊 ===
    contractor_license = fields.Char(
        string='營造業登記證號',
        help='營造業登記證書號碼')

    contractor_grade = fields.Selection([
        ('A', '甲級'),
        ('B', '乙級'),
        ('C', '丙級'),
    ], string='營造廠商等級',
       help='依營造業法規定之等級分類')

    license_expiry_date = fields.Date(
        string='證照有效期限',
        help='營造業登記證有效期限')

    # === 技師資訊 (設計監造單位) ===
    engineer_license = fields.Char(
        string='技師事務所登記證號',
        help='技師事務所或工程顧問公司登記證號')

    engineer_categories = fields.Char(
        string='技師執業類別',
        help='如：土木工程技師、結構工程技師等')

    # === 專案關聯 ===
    supervised_project_ids = fields.One2many(
        'project.project', 'company_id',
        string='管理的專案',
        help='此公司作為設計監造單位管理的專案')

    contracted_project_ids = fields.Many2many(
        'project.project', 'supervision_project_contractor_rel',
        'company_id', 'project_id',
        string='承包的專案',
        help='此公司作為施工廠商參與的專案')

    # === 統計欄位 ===
    supervised_project_count = fields.Integer(
        string='管理專案數',
        compute='_compute_project_counts')

    contracted_project_count = fields.Integer(
        string='承包專案數',
        compute='_compute_project_counts')

    @api.depends('supervised_project_ids', 'contracted_project_ids')
    def _compute_project_counts(self):
        for company in self:
            company.supervised_project_count = len(company.supervised_project_ids)
            company.contracted_project_count = len(company.contracted_project_ids)

    def action_view_supervised_projects(self):
        """查看管理的專案"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '管理的專案',
            'res_model': 'project.project',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.id)],
            'context': {'default_company_id': self.id},
        }

    def action_view_contracted_projects(self):
        """查看承包的專案"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '承包的專案',
            'res_model': 'project.project',
            'view_mode': 'list,form',
            'domain': [('contractor_company_ids', 'in', [self.id])],
        }


class ResPartner(models.Model):
    """
    聯絡人類型擴展

    擴展 res.partner 支援業主/機關識別
    """
    _inherit = 'res.partner'

    partner_type = fields.Selection([
        ('authority', '政府機關'),
        ('supervision', '設計監造單位'),
        ('contractor', '施工廠商'),
        ('subcontractor', '分包商'),
        ('supplier', '供應商'),
        ('other', '其他'),
    ], string='單位類型',
       help='標識此聯絡人在工程管理系統中的角色')

    # === 機關資訊 ===
    authority_level = fields.Selection([
        ('central', '中央機關'),
        ('municipal', '直轄市政府'),
        ('county', '縣市政府'),
        ('township', '鄉鎮市區公所'),
        ('other', '其他'),
    ], string='機關層級')

    authority_code = fields.Char(
        string='機關代碼',
        help='政府機關代碼')

    # === 工程專案關聯 ===
    # 註：V2 的「主辦工程(owned_project_ids)」依賴 supervision.project.authority_id (Many2one)，
    #     但本系統「業主/主辦機關」維持文字欄位(authority_name)，故此關聯不適用，已移除。
