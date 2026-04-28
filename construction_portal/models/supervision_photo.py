# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SupervisionPhotoPortal(models.Model):
    """
    工程照片 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可上傳照片
    """
    _inherit = ['supervision.photo', 'portal.mixin']
    _name = 'supervision.photo'

    def _compute_access_url(self):
        super()._compute_access_url()
        for photo in self:
            photo.access_url = f'/construction/photo/{photo.id}'

    # === Portal 專用欄位 ===
    portal_uploader_id = fields.Many2one(
        'res.partner',
        string='Portal 上傳者',
        help='由 Portal 用戶上傳時記錄的聯絡人')

    is_portal_uploaded = fields.Boolean(
        string='Portal 上傳',
        default=False,
        help='是否由 Portal 用戶上傳')

    @api.model
    def _get_portal_photos_domain(self, partner, project_ids=None):
        """
        取得 Portal 用戶可存取的照片 domain
        """
        domain = []
        if project_ids:
            domain.append(('project_id', 'in', project_ids))
        return domain

    @api.model
    def create_from_portal(self, vals, partner, attachment_data):
        """
        從 Portal 上傳照片

        Args:
            vals: 照片資料
            partner: Portal 用戶的 partner
            attachment_data: 附件資料 (base64 encoded)

        Returns:
            新建立的照片記錄
        """
        # 建立附件(public=True 讓 portal user 能透過 /web/image 看圖)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': vals.get('filename', 'photo.jpg'),
            'datas': attachment_data,
            'res_model': 'supervision.photo',
            'type': 'binary',
            'public': True,
        })

        # 移除 filename，使用 name 作為照片說明
        photo_name = vals.pop('filename', 'Portal 上傳')
        if vals.get('description'):
            photo_name = vals.pop('description')

        # 處理日期欄位
        shot_date = vals.pop('photo_date', None)

        vals.update({
            'name': photo_name,
            'attachment_id': attachment.id,
            'portal_uploader_id': partner.id,
            'is_portal_uploaded': True,
            'source_model': 'other',
        })

        if shot_date:
            vals['shot_date'] = shot_date

        photo = self.sudo().create(vals)

        # 更新附件關聯
        attachment.sudo().write({
            'res_id': photo.id,
        })

        return photo
