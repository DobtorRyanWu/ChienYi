# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class SupervisionProject(models.Model):
    """
    擴展工程案件主檔 - 工程告示牌照片

    設計說明：
    - 照片資料表收斂後，告示牌照片直接就是 supervision.photo，
      靠 signboard_project_id 掛在工程案件上，不再經過 M2M 中間表，
      也不再需要 photo.sync.mixin 把附件「同步」成照片。
    """
    _inherit = 'project.project'

    # === 工程告示牌 ===
    # 收斂前：Many2many('ir.attachment', 'supervision_project_signboard_photo_rel')
    # 收斂後：One2many('supervision.photo')。好處是告示牌照片天生就有
    # 說明／分類／拍攝地點說明／座標，而 ir.attachment 放不下這些欄位。
    signboard_photo_ids = fields.One2many(
        'supervision.photo',
        'signboard_project_id',
        string='工程告示牌照片',
        help='工程告示牌照片。照片本身沒有 GPS 時會自動沿用本工程的座標。')

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
