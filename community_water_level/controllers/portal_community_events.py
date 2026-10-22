# -*- coding: utf-8 -*-
"""社區前台：事件清單、詳情、簽收、事件影像、單一事件 PDF。

門與 portal_community_water.py 同一支（`_community_site_or_none`：非 sudo 讀場域、讀不到就不是成員）；
過了門之後的 sudo 查詢一律帶場域條件，子記錄（事件、影像）再驗屬於這個場域——不屬於就當作不存在（404），
不回「沒有權限」，免得用 id 試探別的社區有哪些事件。
方案：影像與事件 PDF 要進階，**在路由端擋**（只藏按鈕的話直接打網址就拿得到）。
"""

from odoo import http
from odoo.http import content_disposition, request

from odoo.addons.community_water_level.controllers.common import community_tabs
from odoo.addons.community_water_level.controllers.portal_community_water import CommunityWaterPortal
from odoo.addons.community_water_level.models.water_level_event import ACK_NOTE_MAX
from odoo.addons.community_water_level.utils import FULL_STAMP_FORMAT, LOCAL_TZ_NAME, local_stamp
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.water_level_core.models.water_level_device import LEVEL_ADVANCED

EVENTS_PER_PAGE = 20
FILTER_OPEN = 'open'      # 未處理＝還沒有人簽收（不是 state——簽收不結束事件）
FILTER_ALL = 'all'
EVENT_REPORT = 'water_level_core.action_report_water_level_event'
FRAME_MODEL = 'water.level.event.frame'


class CommunityWaterEvents(http.Controller):

    # ==================== 頁面 ====================

    @http.route(['/community/<int:site_id>/events',
                 '/community/<int:site_id>/events/page/<int:page>'],
                type='http', auth='user', website=True)
    def community_events(self, site_id, page=1, filter=FILTER_OPEN, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        if not site:
            return request.redirect('/community')
        current = filter if filter in (FILTER_OPEN, FILTER_ALL) else FILTER_OPEN
        Event = request.env['water.level.event'].sudo()
        site_domain = [('site_id', '=', site.id)]
        open_domain = site_domain + [('ack_user_id', '=', False)]
        domain = open_domain if current == FILTER_OPEN else site_domain
        total = Event.search_count(domain)
        pager = portal_pager(url='/community/%s/events' % site.id, total=total, page=page,
                             step=EVENTS_PER_PAGE, url_args={'filter': current})
        events = Event.search(domain, limit=EVENTS_PER_PAGE, offset=pager['offset'])
        return request.render('community_water_level.portal_community_events', {
            'site': site,
            'events': events,
            'pager': pager,
            'filter': current,
            'open_count': Event.search_count(open_domain),
            'all_count': Event.search_count(site_domain),
            'labels': self._community_event_labels(),
            'stamp': lambda dt: local_stamp(dt, FULL_STAMP_FORMAT),
            'tabs': community_tabs(site, 'events'),
            'header_title': site.name,
            'back_url': '/community/%s/water' % site.id,
            'page_name': 'community_water',
        })

    @http.route(['/community/<int:site_id>/events/<int:event_id>'],
                type='http', auth='user', website=True)
    def community_event_detail(self, site_id, event_id, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        event = self._community_event_or_none(site, event_id)
        if not event:
            return request.not_found()
        with_images = site._community_level_at_least(LEVEL_ADVANCED)
        return request.render('community_water_level.portal_community_event_detail', {
            'site': site,
            'event': event,
            'frames': event.frame_ids if with_images else event.frame_ids.browse(),
            'with_images': with_images,
            'labels': self._community_event_labels(),
            'stamp': lambda dt: local_stamp(dt, FULL_STAMP_FORMAT),
            'ack_note_max': ACK_NOTE_MAX,
            'acked_now': kw.get('acked') == '1',
            'tabs': community_tabs(site, 'events'),
            'header_title': site.name,
            'back_url': '/community/%s/events' % site.id,
            'page_name': 'community_water',
        })

    # ==================== 簽收 ====================

    @http.route(['/community/<int:site_id>/events/<int:event_id>/ack'],
                type='http', auth='user', website=True, methods=['POST'])
    def community_event_ack(self, site_id, event_id, note='', **kw):
        """CSRF 由 Odoo 對 type='http' 的 POST 預設檢查。已簽收就不覆寫，照樣回詳情頁（頁上會顯示是誰簽的）。"""
        site = CommunityWaterPortal._community_site_or_none(site_id)
        event = self._community_event_or_none(site, event_id)
        if not event:
            return request.not_found()
        done = event._community_ack(request.env.user, note)
        return request.redirect('/community/%s/events/%s%s' % (site.id, event.id, '?acked=1' if done else ''))

    # ==================== 影像與 PDF（進階） ====================

    @http.route(['/community/<int:site_id>/events/<int:event_id>/frames/<int:frame_id>'],
                type='http', auth='user')
    def community_event_frame(self, site_id, event_id, frame_id, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        event = self._community_event_or_none(site, event_id)
        if not event or not site._community_level_at_least(LEVEL_ADVANCED):
            return request.not_found()
        frame = event.frame_ids.filtered(lambda f: f.id == frame_id)
        attachment = frame.attachment_id
        # 附件要真的是這一張 frame 的：內部帳號改得了 frame 的 attachment_id，指到任意附件就會被這裡用 sudo 串出去
        if (not frame or attachment.res_model != FRAME_MODEL or attachment.res_id != frame.id
                or not (attachment.mimetype or '').startswith('image/')):
            return request.not_found()
        return request.env['ir.binary'].sudo()._get_image_stream_from(attachment, 'raw').get_response()

    @http.route(['/community/<int:site_id>/events/<int:event_id>/report.pdf'],
                type='http', auth='user')
    def community_event_pdf(self, site_id, event_id, **kw):
        site = CommunityWaterPortal._community_site_or_none(site_id)
        event = self._community_event_or_none(site, event_id)
        if not event or not site._community_level_at_least(LEVEL_ADVANCED):
            return request.not_found()
        # 報表模板用 t-field 印時間，跟著 context 的時區走——固定台灣，不看帳號
        report = request.env['ir.actions.report'].sudo().with_context(tz=LOCAL_TZ_NAME)
        pdf, _report_type = report._render_qweb_pdf(EVENT_REPORT, event.ids)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition('%s.pdf' % event.name)),
            ('Cache-Control', 'no-store'),
        ])

    # ==================== 內部工具 ====================

    @staticmethod
    def _community_event_or_none(site, event_id):
        """這個社區的事件（sudo）；不是這個社區的、或門沒過（site 為 None）都回 None。"""
        if not site:
            return None
        event = request.env['water.level.event'].sudo().browse(event_id).exists()
        if not event or event.site_id != site:
            return None
        return event

    @staticmethod
    def _community_event_labels():
        fields_ = request.env['water.level.event']._fields
        return {
            'type': dict(fields_['event_type'].selection),
            'severity': dict(fields_['severity'].selection),
            'state': dict(fields_['state'].selection),
        }
