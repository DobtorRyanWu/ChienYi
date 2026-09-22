# -*- coding: utf-8 -*-
"""前台的更新公告：登入後跳一次的視窗、回查頁，以及維護橫幅。

🔴 客戶只拿得到：公告標題、公告內容、發布日、**系統版本號**。
   模組版號、版本清單、更新紀錄（原因／做法／commit）一律不給。
"""
from odoo import http
from odoo.http import request

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

RELEASE = 'construction.release'


class ReleaseAnnouncementPortal(ConstructionPortal):

    def _announcement_project(self, project_id):
        """從哪個工程進來（抽屜連結帶 from_project）。看不到的工程一律當作沒有。"""
        try:
            pid = int(project_id or 0)
        except (TypeError, ValueError):
            return request.env['project.project']
        if not pid:
            return request.env['project.project']
        project = request.env['project.project'].sudo().browse(pid).exists()
        if not project or not self._user_can_see_project(project):
            return request.env['project.project']
        return project

    @http.route(['/construction/announcements'], type='http', auth='user', website=True)
    def portal_announcement_list(self, from_project=None, **kw):
        project = self._announcement_project(from_project)
        Release = request.env[RELEASE]
        values = {
            'project': project or False,
            'announcements': Release._announcement_payload(Release._published_announcements()),
        }
        if project:
            values.update({
                'day_count': self._get_project_day_count(project),
                'nav_badges': self._get_nav_badges(project),
            })
        return request.render('construction_release.portal_announcement_list', values)

    @http.route(['/construction/announcements/read'], type='json', auth='user')
    def portal_announcement_mark_read(self, release_ids=None, **kw):
        """前台按「知道了」；與後台共用同一份已讀名單。"""
        ids = [int(i) for i in (release_ids or [])]
        return request.env[RELEASE].mark_announcements_read(ids)
