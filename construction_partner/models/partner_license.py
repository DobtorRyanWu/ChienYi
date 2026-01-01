# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import timedelta


class PartnerLicense(models.Model):
    """
    廠商證照資料

    管理工程相關單位的各類證照：
    - 營業執照
    - 營造業登記證
    - 建築師執照
    - 技師執照
    - 安全衛生證照
    - 環保證照
    - 其他專業證照

    自動追蹤證照過期狀態，支援過期提醒。
    """
    _name = 'partner.license'
    _description = '廠商證照資料'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expiry_date, name'
    _rec_name = 'display_name'

    # === 關聯廠商 ===
    partner_id = fields.Many2one(
        'res.partner',
        string='廠商',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help='證照所屬單位')

    # === 基本資料 ===
    name = fields.Char(
        string='證照名稱',
        required=True,
        tracking=True,
        help='證照完整名稱')

    display_name = fields.Char(
        string='顯示名稱',
        compute='_compute_display_name',
        store=True)

    license_type = fields.Selection([
        ('business', '營業執照'),
        ('construction', '營造業登記證'),
        ('architect', '建築師執照'),
        ('engineer', '技師執照'),
        ('safety', '安全衛生證照'),
        ('environment', '環保證照'),
        ('iso', 'ISO 認證'),
        ('quality', '品質認證'),
        ('other', '其他'),
    ], string='證照類型',
       required=True,
       tracking=True,
       help='證照分類類型')

    license_no = fields.Char(
        string='證照字號',
        tracking=True,
        help='證照編號或字號')

    # === 日期資訊 ===
    issue_date = fields.Date(
        string='發證日期',
        tracking=True,
        help='證照核發日期')

    expiry_date = fields.Date(
        string='有效期限',
        tracking=True,
        help='證照有效期限，空白表示永久有效')

    # === 狀態計算 ===
    is_expired = fields.Boolean(
        string='已過期',
        compute='_compute_expiry_status',
        store=True,
        help='證照是否已過期')

    is_expiring_soon = fields.Boolean(
        string='即將過期',
        compute='_compute_expiry_status',
        store=True,
        help='證照是否即將在30天內過期')

    days_until_expiry = fields.Integer(
        string='距離過期天數',
        compute='_compute_expiry_status',
        store=True,
        help='距離過期的天數，負數表示已過期')

    expiry_status = fields.Selection([
        ('valid', '有效'),
        ('expiring', '即將過期'),
        ('expired', '已過期'),
        ('no_expiry', '永久有效'),
    ], string='有效狀態',
       compute='_compute_expiry_status',
       store=True,
       help='證照有效狀態')

    # === 發證機關 ===
    issue_authority = fields.Char(
        string='發證機關',
        help='核發證照的機關單位')

    # === 附件 ===
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'partner_license_attachment_rel',
        'license_id', 'attachment_id',
        string='證照影本',
        help='上傳證照掃描檔或照片')

    attachment_count = fields.Integer(
        string='附件數',
        compute='_compute_attachment_count')

    # === 備註 ===
    note = fields.Text(
        string='備註',
        help='其他相關說明')

    # === 驗證狀態 ===
    verification_state = fields.Selection([
        ('pending', '待驗證'),
        ('verified', '已驗證'),
        ('rejected', '已拒絕'),
    ], string='驗證狀態',
       default='pending',
       tracking=True,
       help='證照真實性驗證狀態')

    verified_by = fields.Many2one(
        'res.users',
        string='驗證人',
        help='執行驗證的使用者')

    verified_date = fields.Datetime(
        string='驗證時間',
        help='驗證執行時間')

    # === SQL 約束 ===
    _sql_constraints = [
        ('unique_partner_license_no',
         'UNIQUE(partner_id, license_type, license_no)',
         '同一廠商的同類型證照字號不可重複！'),
        ('issue_date_check',
         'CHECK(expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date)',
         '有效期限必須晚於或等於發證日期！'),
    ]

    # === 計算方法 ===
    @api.depends('name', 'license_no', 'partner_id.name')
    def _compute_display_name(self):
        """計算顯示名稱"""
        for license_rec in self:
            if license_rec.license_no:
                license_rec.display_name = f"{license_rec.name} ({license_rec.license_no})"
            else:
                license_rec.display_name = license_rec.name

    @api.depends('expiry_date')
    def _compute_expiry_status(self):
        """計算過期狀態"""
        today = fields.Date.today()
        warning_days = 30  # 提前30天警告

        for license_rec in self:
            if not license_rec.expiry_date:
                # 無有效期限 = 永久有效
                license_rec.is_expired = False
                license_rec.is_expiring_soon = False
                license_rec.days_until_expiry = 99999
                license_rec.expiry_status = 'no_expiry'
            else:
                days_diff = (license_rec.expiry_date - today).days
                license_rec.days_until_expiry = days_diff

                if days_diff < 0:
                    # 已過期
                    license_rec.is_expired = True
                    license_rec.is_expiring_soon = False
                    license_rec.expiry_status = 'expired'
                elif days_diff <= warning_days:
                    # 即將過期
                    license_rec.is_expired = False
                    license_rec.is_expiring_soon = True
                    license_rec.expiry_status = 'expiring'
                else:
                    # 有效
                    license_rec.is_expired = False
                    license_rec.is_expiring_soon = False
                    license_rec.expiry_status = 'valid'

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        """計算附件數量"""
        for license_rec in self:
            license_rec.attachment_count = len(license_rec.attachment_ids)

    # === 動作方法 ===
    def action_verify(self):
        """驗證證照"""
        self.ensure_one()
        if self.verification_state == 'verified':
            raise ValidationError('此證照已驗證')
        self.write({
            'verification_state': 'verified',
            'verified_by': self.env.uid,
            'verified_date': fields.Datetime.now(),
        })

    def action_reject(self):
        """拒絕驗證"""
        self.ensure_one()
        self.write({
            'verification_state': 'rejected',
            'verified_by': self.env.uid,
            'verified_date': fields.Datetime.now(),
        })

    def action_reset_pending(self):
        """重設為待驗證"""
        self.ensure_one()
        self.write({
            'verification_state': 'pending',
            'verified_by': False,
            'verified_date': False,
        })

    def action_view_attachments(self):
        """查看附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '證照影本',
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {
                'default_res_model': 'partner.license',
                'default_res_id': self.id,
            },
        }

    # === 排程方法 ===
    @api.model
    def _cron_check_expiring_licenses(self):
        """
        排程檢查即將過期的證照

        每日執行，找出30天內即將過期的證照，
        建立活動提醒通知相關負責人。
        """
        today = fields.Date.today()
        warning_date = today + timedelta(days=30)

        # 找出即將過期且尚未通知的證照
        expiring_licenses = self.search([
            ('expiry_date', '!=', False),
            ('expiry_date', '<=', warning_date),
            ('expiry_date', '>=', today),
            ('is_expiring_soon', '=', True),
        ])

        # 對每個即將過期的證照建立活動
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return

        for license_rec in expiring_licenses:
            # 檢查是否已有未完成的活動
            existing_activity = self.env['mail.activity'].search([
                ('res_model', '=', 'partner.license'),
                ('res_id', '=', license_rec.id),
                ('activity_type_id', '=', activity_type.id),
                ('date_deadline', '>=', today),
            ], limit=1)

            if not existing_activity:
                # 建立新活動
                license_rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    date_deadline=license_rec.expiry_date,
                    summary=f'證照即將過期: {license_rec.name}',
                    note=f'廠商 {license_rec.partner_id.name} 的證照「{license_rec.name}」'
                         f'將於 {license_rec.expiry_date} 過期，請盡速處理更新。',
                )

    # === 顯示名稱 ===
    def name_get(self):
        """顯示名稱"""
        result = []
        for license_rec in self:
            name = license_rec.display_name or license_rec.name
            if license_rec.partner_id:
                name = f'{license_rec.partner_id.name} - {name}'
            result.append((license_rec.id, name))
        return result
