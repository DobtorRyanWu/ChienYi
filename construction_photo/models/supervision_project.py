# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class SupervisionProject(models.Model):
    """
    擴展工程案件主檔 - 工程告示牌照片

    設計說明：
    - 從 construction_photo 模組擴展 supervision.project
    - 加入 photo.sync.mixin 繼承，提供照片自動同步功能
    - 加入工程告示牌照片欄位
    - 照片自動同步至照片管理模組
    """
    _name = 'supervision.project'
    _inherit = ['supervision.project', 'photo.sync.mixin']

    # === 工程告示牌 ===
    signboard_photo_ids = fields.Many2many(
        'ir.attachment',
        'supervision_project_signboard_photo_rel',
        'project_id', 'attachment_id',
        string='工程告示牌照片',
        help='上傳工程告示牌照片，將自動同步至照片管理模組')

    # === 工程照片（所有關聯到此專案的 supervision.photo） ===
    photo_ids = fields.One2many(
        'supervision.photo',
        'project_id',
        string='工程照片',
        help='所有關聯到此工程案件的照片')

    photo_count = fields.Integer(
        string='照片數量',
        compute='_compute_photo_count',
        store=False,
        help='此工程案件下的照片總數')

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for project in self:
            project.photo_count = len(project.photo_ids)

    def action_view_photos(self):
        """跳到照片列表（過濾此專案）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - 工程照片',
            'res_model': 'supervision.photo',
            'view_mode': 'kanban,list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    # === 照片自動同步配置 ===
    def _get_photo_sync_config(self):
        """配置工程告示牌照片同步規則"""
        config = super()._get_photo_sync_config() if hasattr(super(), '_get_photo_sync_config') else {}
        config.update({
            'signboard_photo_ids': {
                'source_model': 'other',
                'name_prefix': '工程告示牌',
                'description_template': '工程名稱：{record.name}\n工程地點：{record.location}',
                'location_field': 'location',
            },
        })
        return config
