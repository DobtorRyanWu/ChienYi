# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.water_level_core.models.water_level_site import SITE_TYPE_COMMUNITY


class WaterLevelDevice(models.Model):
    _inherit = 'water.level.device'

    # tracking：設備換池會留在 chatter。週期報表目前依「現在」的池取讀值（換池的歷史不追溯），
    # 日後要追溯就從這裡的紀錄還原
    tank_id = fields.Many2one(
        'water.level.tank', string='蓄水池',
        ondelete='set null', index=True, tracking=True,
        help='社區場域用：這台設備裝在哪一個蓄水池。工程測站留空。')

    @api.model_create_multi
    def create(self, vals_list):
        """社區場域的設備沒帶等級就跟著場域（core 的預設是基本，會和場域不一樣而被下面的約束擋下）。"""
        site_ids = {vals['site_id'] for vals in vals_list if vals.get('site_id') and 'service_level' not in vals}
        levels = {site.id: site.service_level
                  for site in self.env['water.level.site'].sudo().browse(site_ids)
                  if site.site_type == SITE_TYPE_COMMUNITY}
        for vals in vals_list:
            if 'service_level' not in vals and vals.get('site_id') in levels:
                vals['service_level'] = levels[vals['site_id']]
        return super().create(vals_list)

    @api.constrains('site_id', 'tank_id')
    def _check_tank_site(self):
        for device in self:
            if device.tank_id and device.tank_id.site_id != device.site_id:
                raise ValidationError(_(
                    '設備「%(name)s」的蓄水池不屬於場域「%(site)s」。',
                    name=device.name, site=device.site_id.name))

    @api.constrains('site_id', 'service_level', 'active')
    def _check_community_service_level(self):
        """社區場域的設備等級必須等於場域：方案是社區簽的，改方案請改社區（會同步到每一台）。"""
        for device in self:
            site = device.site_id
            if site.site_type == SITE_TYPE_COMMUNITY and device.service_level != site.service_level:
                raise ValidationError(_(
                    '「%(name)s」屬於社區「%(site)s」，方案等級跟著社區走；要改方案請到社區場域改。',
                    name=device.name, site=site.name))

    @api.onchange('site_id')
    def _onchange_site_id_tank(self):
        if self.tank_id and self.tank_id.site_id != self.site_id:
            self.tank_id = False
        if self.site_id.site_type == SITE_TYPE_COMMUNITY:
            self.service_level = self.site_id.service_level
