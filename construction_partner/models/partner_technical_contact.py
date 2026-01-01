# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PartnerTechnicalContact(models.Model):
    """
    技術聯絡人

    管理工程相關單位的技術聯絡人資料：
    - 專案經理
    - 工地主任
    - 安全衛生人員
    - 品管人員
    - 技術人員
    - 監造人員

    記錄聯絡方式與專業證照資訊。
    """
    _name = 'partner.technical.contact'
    _description = '技術聯絡人'
    _order = 'partner_id, sequence, name'
    _rec_name = 'display_name'

    # === 關聯單位 ===
    partner_id = fields.Many2one(
        'res.partner',
        string='所屬單位',
        required=True,
        ondelete='cascade',
        index=True,
        help='聯絡人所屬的工程單位')

    # === 基本資料 ===
    name = fields.Char(
        string='姓名',
        required=True,
        help='聯絡人姓名')

    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True)

    sequence = fields.Integer(
        string='排序',
        default=10,
        help='顯示順序')

    active = fields.Boolean(
        string='在職',
        default=True,
        help='取消勾選表示已離職')

    # === 角色與職務 ===
    role = fields.Selection([
        ('project_manager', '專案經理'),
        ('site_manager', '工地主任'),
        ('safety_officer', '安全衛生人員'),
        ('quality_officer', '品管人員'),
        ('technician', '技術人員'),
        ('supervisor', '監造人員'),
        ('foreman', '領班'),
        ('admin', '行政人員'),
        ('other', '其他'),
    ], string='角色',
       required=True,
       help='聯絡人在工程中的角色')

    job_title = fields.Char(
        string='職稱',
        help='正式職稱')

    department = fields.Char(
        string='部門',
        help='所屬部門')

    # === 聯絡方式 ===
    phone = fields.Char(
        string='電話',
        help='辦公室電話')

    mobile = fields.Char(
        string='手機',
        help='行動電話')

    email = fields.Char(
        string='電子郵件',
        help='電子郵件信箱')

    fax = fields.Char(
        string='傳真',
        help='傳真號碼')

    # === 專業證照 ===
    license_type = fields.Char(
        string='專業證照類型',
        help='持有的專業證照類型，如：土木技師、建築師等')

    license_no = fields.Char(
        string='證照字號',
        help='專業證照編號')

    license_expiry_date = fields.Date(
        string='證照有效期限',
        help='專業證照有效期限')

    is_license_valid = fields.Boolean(
        string='證照有效',
        compute='_compute_license_valid',
        store=True,
        help='專業證照是否在有效期內')

    # === 專案指派 ===
    assigned_project_ids = fields.Many2many(
        'supervision.project',
        'technical_contact_project_rel',
        'contact_id', 'project_id',
        string='指派專案',
        help='此聯絡人被指派參與的工程專案')

    assigned_project_count = fields.Integer(
        string='專案數',
        compute='_compute_assigned_project_count',
        help='被指派的專案數量')

    # === 照片 ===
    image_128 = fields.Image(
        string='照片',
        max_width=128, max_height=128,
        help='聯絡人照片')

    # === 備註 ===
    note = fields.Text(
        string='備註',
        help='其他相關說明')

    # === SQL 約束 ===
    _sql_constraints = [
        ('unique_partner_name_role',
         'UNIQUE(partner_id, name, role)',
         '同一單位相同角色的聯絡人姓名不可重複！'),
    ]

    # === 計算方法 ===
    @api.depends('name', 'role', 'partner_id.name')
    def _compute_display_name(self):
        """計算顯示名稱"""
        role_labels = dict(self._fields['role'].selection)
        for contact in self:
            role_name = role_labels.get(contact.role, '')
            contact.display_name = f"{contact.name} ({role_name})"

    @api.depends('license_expiry_date')
    def _compute_license_valid(self):
        """計算證照是否有效"""
        today = fields.Date.today()
        for contact in self:
            if not contact.license_expiry_date:
                # 無到期日視為永久有效
                contact.is_license_valid = True
            else:
                contact.is_license_valid = contact.license_expiry_date >= today

    @api.depends('assigned_project_ids')
    def _compute_assigned_project_count(self):
        """計算指派專案數"""
        for contact in self:
            contact.assigned_project_count = len(contact.assigned_project_ids)

    # === 約束驗證 ===
    @api.constrains('email')
    def _check_email(self):
        """驗證電子郵件格式"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for contact in self:
            if contact.email and not re.match(email_pattern, contact.email):
                raise ValidationError(f'電子郵件格式不正確: {contact.email}')

    # === 動作方法 ===
    def action_view_projects(self):
        """查看指派的專案"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 指派專案',
            'res_model': 'supervision.project',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.assigned_project_ids.ids)],
        }

    def action_send_email(self):
        """發送電子郵件"""
        self.ensure_one()
        if not self.email:
            raise ValidationError('此聯絡人未設定電子郵件')
        return {
            'type': 'ir.actions.act_url',
            'url': f'mailto:{self.email}',
            'target': 'new',
        }

    def action_call_mobile(self):
        """撥打手機"""
        self.ensure_one()
        if not self.mobile:
            raise ValidationError('此聯絡人未設定手機號碼')
        return {
            'type': 'ir.actions.act_url',
            'url': f'tel:{self.mobile}',
            'target': 'new',
        }

    # === 顯示名稱 ===
    def name_get(self):
        """顯示名稱"""
        result = []
        role_labels = dict(self._fields['role'].selection)
        for contact in self:
            role_name = role_labels.get(contact.role, '')
            if contact.partner_id:
                name = f'{contact.partner_id.name} - {contact.name} ({role_name})'
            else:
                name = f'{contact.name} ({role_name})'
            result.append((contact.id, name))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """搜尋時比對姓名、手機、電子郵件"""
        domain = domain or []
        if name:
            domain = [
                '|', '|', '|',
                ('name', operator, name),
                ('mobile', operator, name),
                ('email', operator, name),
                ('partner_id.name', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
