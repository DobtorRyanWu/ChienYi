# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """
    擴展 res.partner - 工程相關單位欄位

    設計參考: contacts 模組
    - 階層結構 (parent_id / child_ids)
    - 商業欄位委託 (commercial_partner_id)

    新增欄位:
    - 工程單位類型
    - 工程分類標籤
    - 營造廠商等級
    - 證照資料關聯
    - 技術聯絡人關聯
    - 工程表現評鑑
    """
    _inherit = 'res.partner'

    # === 工程單位類型 ===
    construction_partner_type = fields.Selection([
        ('owner', '業主'),
        ('contractor', '施工廠商'),
        ('subcontractor', '分包商'),
        ('supervision', '監造單位'),
        ('design', '設計單位'),
        ('government', '政府部門'),
        ('supplier', '供應商'),
    ], string='工程單位類型',
       tracking=True,
       help='此單位在工程專案中的角色類型')

    # === 分類標籤 ===
    supervision_category_ids = fields.Many2many(
        'supervision.partner.category',
        'supervision_partner_category_rel',
        'partner_id', 'category_id',
        string='工程分類標籤',
        help='可多選的工程單位分類標籤')

    # === 廠商等級 (施工廠商專用) ===
    contractor_grade = fields.Selection([
        ('grade_a', '甲級'),
        ('grade_b', '乙級'),
        ('grade_c', '丙級'),
    ], string='營造廠商等級',
       help='依營造業法規定的營造廠商等級分類')

    contractor_registration_no = fields.Char(
        string='營造業登記證號',
        help='營造業登記證書號碼')

    contractor_registration_expiry = fields.Date(
        string='登記證有效期限',
        help='營造業登記證有效期限')

    # === 資質證照 ===
    license_ids = fields.One2many(
        'partner.license',
        'partner_id',
        string='證照資料',
        help='廠商持有的各類證照')

    license_count = fields.Integer(
        string='證照數量',
        compute='_compute_license_count',
        help='證照總數')

    valid_license_count = fields.Integer(
        string='有效證照數',
        compute='_compute_license_count',
        help='有效期內的證照數量')

    expiring_license_count = fields.Integer(
        string='即將過期證照',
        compute='_compute_license_count',
        help='30天內即將過期的證照數量')

    # === 技術聯絡人 ===
    technical_contact_ids = fields.One2many(
        'partner.technical.contact',
        'partner_id',
        string='技術聯絡人',
        help='工程技術聯絡人清單')

    technical_contact_count = fields.Integer(
        string='聯絡人數',
        compute='_compute_technical_contact_count',
        help='技術聯絡人總數')

    # === 專案關聯 ===
    supervision_project_ids = fields.Many2many(
        'supervision.project',
        string='參與專案',
        compute='_compute_supervision_project_ids',
        help='此單位參與的工程專案')

    supervision_project_count = fields.Integer(
        string='專案數量',
        compute='_compute_supervision_project_count',
        help='參與的工程專案總數')

    # === 評鑑資訊 ===
    performance_rating = fields.Float(
        string='工程表現評分',
        default=0.0,
        digits=(3, 1),
        help='整體工程表現評分 (0-100)')

    quality_score = fields.Float(
        string='品質評分',
        default=0.0,
        digits=(3, 1),
        help='工程品質評分 (0-100)')

    safety_score = fields.Float(
        string='安全評分',
        default=0.0,
        digits=(3, 1),
        help='工安表現評分 (0-100)')

    schedule_adherence = fields.Float(
        string='進度遵守率 (%)',
        default=100.0,
        digits=(5, 2),
        help='進度遵守率百分比')

    # === 工程經歷 ===
    construction_experience = fields.Text(
        string='工程經歷',
        help='重要工程經歷說明')

    specialization = fields.Char(
        string='專業領域',
        help='專精的工程領域，如：土木、機電、裝修等')

    established_year = fields.Integer(
        string='成立年份',
        help='公司成立年份')

    employee_count = fields.Integer(
        string='員工人數',
        help='公司員工總人數')

    capital = fields.Float(
        string='資本額',
        digits=(16, 2),
        help='公司登記資本額')

    currency_capital_id = fields.Many2one(
        'res.currency',
        string='資本額幣別',
        default=lambda self: self.env.company.currency_id)

    # === 備註 ===
    construction_note = fields.Text(
        string='工程備註',
        help='與工程相關的備註說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('check_performance_rating',
         'CHECK(performance_rating >= 0 AND performance_rating <= 100)',
         '工程表現評分必須介於 0 到 100 之間！'),
        ('check_quality_score',
         'CHECK(quality_score >= 0 AND quality_score <= 100)',
         '品質評分必須介於 0 到 100 之間！'),
        ('check_safety_score',
         'CHECK(safety_score >= 0 AND safety_score <= 100)',
         '安全評分必須介於 0 到 100 之間！'),
        ('check_schedule_adherence',
         'CHECK(schedule_adherence >= 0 AND schedule_adherence <= 200)',
         '進度遵守率必須介於 0 到 200 之間！'),
    ]

    # === 計算方法 ===
    @api.depends('license_ids', 'license_ids.is_expired', 'license_ids.is_expiring_soon')
    def _compute_license_count(self):
        """計算證照統計"""
        for partner in self:
            licenses = partner.license_ids
            partner.license_count = len(licenses)
            partner.valid_license_count = len(licenses.filtered(
                lambda l: not l.is_expired))
            partner.expiring_license_count = len(licenses.filtered(
                lambda l: l.is_expiring_soon))

    @api.depends('technical_contact_ids')
    def _compute_technical_contact_count(self):
        """計算技術聯絡人數"""
        for partner in self:
            partner.technical_contact_count = len(
                partner.technical_contact_ids.filtered('active'))

    @api.depends('construction_partner_type')
    def _compute_supervision_project_ids(self):
        """計算關聯的工程專案"""
        Project = self.env['supervision.project']
        for partner in self:
            projects = Project.browse()

            # 作為業主的專案
            if partner.construction_partner_type == 'owner':
                projects |= Project.search([('authority_id', '=', partner.id)])

            partner.supervision_project_ids = projects

    @api.depends('supervision_project_ids')
    def _compute_supervision_project_count(self):
        """計算專案數量"""
        for partner in self:
            partner.supervision_project_count = len(partner.supervision_project_ids)

    # === Onchange 方法 ===
    @api.onchange('construction_partner_type')
    def _onchange_construction_partner_type(self):
        """
        當工程單位類型變更時，自動設定 partner_type
        保持與 construction_supervision_base 的相容性
        """
        type_mapping = {
            'owner': 'authority',
            'contractor': 'contractor',
            'subcontractor': 'subcontractor',
            'supervision': 'supervision',
            'design': 'supervision',
            'government': 'authority',
            'supplier': 'supplier',
        }
        if self.construction_partner_type:
            self.partner_type = type_mapping.get(
                self.construction_partner_type, 'other')

        # 非施工廠商清除等級
        if self.construction_partner_type not in ('contractor', 'subcontractor'):
            self.contractor_grade = False

    # === 約束驗證 ===
    @api.constrains('contractor_grade', 'construction_partner_type')
    def _check_contractor_grade(self):
        """驗證營造廠商等級只能設定在施工廠商類型"""
        for partner in self:
            if partner.contractor_grade and \
               partner.construction_partner_type not in ('contractor', 'subcontractor'):
                raise ValidationError(
                    '只有施工廠商或分包商可以設定營造廠商等級！')

    # === 動作方法 ===
    def action_view_licenses(self):
        """查看證照資料"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 證照資料',
            'res_model': 'partner.license',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_view_technical_contacts(self):
        """查看技術聯絡人"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 技術聯絡人',
            'res_model': 'partner.technical.contact',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_view_supervision_projects(self):
        """查看工程專案"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 工程專案',
            'res_model': 'supervision.project',
            'view_mode': 'tree,kanban,form',
            'domain': [('id', 'in', self.supervision_project_ids.ids)],
        }

    def action_view_expiring_licenses(self):
        """查看即將過期的證照"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 即將過期證照',
            'res_model': 'partner.license',
            'view_mode': 'tree,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('is_expiring_soon', '=', True),
            ],
            'context': {'default_partner_id': self.id},
        }
