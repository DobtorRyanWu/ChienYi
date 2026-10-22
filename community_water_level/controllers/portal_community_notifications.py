# -*- coding: utf-8 -*-
"""社區前台：LINE 通知設定（旗艦方案）。

列出本社區的 LINE 收件人、新增（產生一次性綁定碼）、停用。收件人模型 portal 沒有任何 ACL，
一律走這裡：門（`_community_site_or_none`）→ 方案（旗艦，路由端擋）→ 收件人屬於這個社區，再用 sudo 寫。
"""

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.community_water_level.controllers.common import community_tabs
from odoo.addons.community_water_level.controllers.portal_community_water import CommunityWaterPortal
from odoo.addons.community_water_level.models.water_level_line import BIND_CODE_TTL_HOURS, CHANNEL_LINE
from odoo.addons.community_water_level.utils import FULL_STAMP_FORMAT, local_stamp
from odoo.addons.water_level_core.models.water_level_device import LEVEL_FLAGSHIP

FORBIDDEN = 403
BAD_REQUEST = 400


class CommunityWaterNotifications(http.Controller):

    @http.route(['/community/<int:site_id>/notifications'], type='http', auth='user', website=True)
    def community_notifications(self, site_id, **kw):
        site, denied = self._community_flagship_site(site_id)
        if denied:
            return denied
        return self._community_render(site, created_id=kw.get('created'))

    @http.route(['/community/<int:site_id>/notifications/new'], type='http', auth='user', website=True,
                methods=['POST'])
    def community_notification_new(self, site_id, name='', **kw):
        site, denied = self._community_flagship_site(site_id)
        if denied:
            return denied
        channel = self._community_line_channel(site)
        if not channel:
            return self._community_render(site, error='千溢還沒有替這個社區開通 LINE 通道。', status=BAD_REQUEST)
        try:
            recipient = request.env['water.level.line.recipient']._community_new(site, channel, name, request.env.user)
        except UserError as exc:
            return self._community_render(site, error=str(exc), status=BAD_REQUEST)
        return request.redirect('/community/%s/notifications?created=%s' % (site.id, recipient.id))

    @http.route(['/community/<int:site_id>/notifications/<int:recipient_id>/disable'], type='http', auth='user',
                website=True, methods=['POST'])
    def community_notification_disable(self, site_id, recipient_id, **kw):
        site, denied = self._community_flagship_site(site_id)
        if denied:
            return denied
        recipient = request.env['water.level.line.recipient'].sudo().browse(recipient_id).exists()
        if not recipient or recipient.site_id != site:
            return request.not_found()
        recipient._line_disable(request.env.user, '前台停用（%s）' % request.env.user.name)
        return request.redirect('/community/%s/notifications' % site.id)

    # ==================== 內部工具 ====================

    @staticmethod
    def _community_flagship_site(site_id):
        """(site, None) 或 (None, 該回的 response)。不是成員導回社區清單；方案不含回 403 說明頁。"""
        site = CommunityWaterPortal._community_site_or_none(site_id)
        if not site:
            return None, request.redirect('/community')
        if not site._community_level_at_least(LEVEL_FLAGSHIP):
            return None, request.render('community_water_level.portal_community_plan_required', {
                'site': site, 'feature': 'LINE 通知', 'level_label': '旗艦',
                'tabs': community_tabs(site, 'notify'), 'header_title': site.name,
                'back_url': '/community/%s/water' % site.id, 'page_name': 'community_water',
            }, status=FORBIDDEN)
        return site, None

    @staticmethod
    def _community_line_channel(site):
        """這個社區用哪個 LINE 通道：適用場域留空（＝全部）或含這個社區的第一個。"""
        channels = request.env['water.level.alert.channel'].sudo().search(
            [('channel_type', '=', CHANNEL_LINE)], order='sequence, id')
        for channel in channels:
            sites = channel.with_context(active_test=False).site_ids
            if not sites or site in sites:
                return channel
        return channels.browse()

    def _community_render(self, site, created_id=None, error=None, status=200):
        Recipient = request.env['water.level.line.recipient'].sudo()
        now = fields.Datetime.now()
        rows = []
        for recipient in Recipient.with_context(active_test=False).search([('site_id', '=', site.id)]):
            if not recipient.active:
                state = 'disabled'
            elif recipient.bound_at:
                state = 'bound'
            elif recipient.bind_code and recipient.bind_code_expires and recipient.bind_code_expires > now:
                state = 'pending'
            else:
                state = 'expired'
            rows.append({'record': recipient, 'state': state, 'code': recipient.bind_code if state == 'pending' else '',
                         'is_new': str(recipient.id) == str(created_id)})
        channel = self._community_line_channel(site)
        return request.render('community_water_level.portal_community_notifications', {
            'site': site,
            'rows': rows,
            'channel': channel,
            'friend_url': channel.line_add_friend_url if channel else '',
            'ttl_hours': BIND_CODE_TTL_HOURS,
            'stamp': lambda dt: local_stamp(dt, FULL_STAMP_FORMAT),
            'error': error,
            'tabs': community_tabs(site, 'notify'),
            'header_title': site.name,
            'back_url': '/community/%s/water' % site.id,
            'page_name': 'community_water',
        }, status=status)
