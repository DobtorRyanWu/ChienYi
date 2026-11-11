# -*- coding: utf-8 -*-
"""前台留言的 partner_ids：受限的內部帳號在業務單據留言時只留追蹤者（比照核心對前台帳號）。為什麼見 models/restricted_mail.py 檔頭七。"""
from odoo.http import request

from odoo.addons.construction_portal.controllers.portal import ConstructionThreadController

DISCUSS_MODEL = 'discuss.channel'


class RoleThreadController(ConstructionThreadController):

    def _prepare_post_data(self, post_data, thread, **kwargs):
        post_data = super()._prepare_post_data(post_data, thread, **kwargs)
        user = request.env.user
        if thread._name != DISCUSS_MODEL and user._dash_is_restricted_internal() and post_data.get('partner_ids'):
            partners = request.env['res.partner'].browse(post_data['partner_ids'])
            post_data['partner_ids'] = (partners & self._filter_message_post_partners(thread, partners)).ids
        return post_data
