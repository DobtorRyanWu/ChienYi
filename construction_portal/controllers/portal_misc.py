# -*- coding: utf-8 -*-
"""M4-a：MiscRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

import base64
import json
from datetime import date, datetime, timedelta

from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.construction_quality.models.defect_constants import CATEGORY_TO_CHECK_TYPE
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.osv.expression import AND
from werkzeug.exceptions import NotFound

from .portal_utils import (
    GROUP_BOSS, GROUP_MANAGER, GROUP_FIELD, GROUP_OBSERVER, GROUP_OPERATOR,
    _photo_category_options, _photo_category_to_id, _post_photo_meta,
    _portal_save_photos,
    _defect_save_photos, _portal_delete_photo, _portal_photo_to_supervision,
    _haversine_km,
)


class MiscRoutesMixin:
    @http.route(['/construction/doc/<int:att_id>'], type='http', auth='user')
    def portal_construction_document_serve(self, att_id, **kw):
        """帶專案權限檢查的文件下載端點（M0.6，取代 public=True 的裸 /web/content）。

        允許清單：只服務**帶有 supervision_project_id 的附件**（見
        `_resolve_document_project`），依登入者對該工程的可見範圍把關；
        不可見一律 404（不洩漏存在性）。系統裡沒有這個欄位值的附件
        （頭像、logo、郵件附件、報表暫存…）一律反解不出工程 → 404。
        文件非影像，一律以下載串流回應。
        """
        att = request.env['ir.attachment'].sudo().browse(att_id).exists()
        if not att:
            raise NotFound()
        project = self._resolve_document_project(att)
        if not self._user_can_see_project(project):
            raise NotFound()
        return request.env['ir.binary'].sudo()._get_stream_from(
            att, 'raw').get_response(as_attachment=True)

    @http.route(['/construction/<int:project_id>/notifications'],
                type='http', auth='user', website=True)
    def portal_construction_notifications(self, project_id, **kw):
        """前台通知中心：列出派給當前使用者的所有通知；進頁即標記全部已看（未讀 badge 歸零）。"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        notif_items = self._get_portal_notifications(limit=100)
        values = {
            'project': project,
            'notif_items': notif_items,
            'notif_count': len(notif_items),
            'page_name': 'notifications',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        # 進頁即標記全部已看（只寫 res.users 自有欄位，走 sudo）
        request.env.user.sudo().write({'portal_notif_last_seen': fields.Datetime.now()})
        return request.render('construction_portal.portal_construction_notifications', values)

    @http.route(['/construction/<int:project_id>/slips', '/construction/<int:project_id>/slips/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_slips(self, project_id, page=1, **kw):
        """通報單列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if project.project_type != 'reservation':
            return request.redirect(f'/construction/{project_id}')

        Slip = request.env['reservation.notification.slip']
        domain = [('project_id', '=', project.id)]

        slip_count = Slip.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/slips',
            total=slip_count,
            page=page,
            step=self._items_per_page,
        )

        slips = Slip.search(
            domain,
            order='slip_no desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'project': project,
            'slips': slips,
            'page_name': 'construction_slips',
            'pager': pager,
            'default_url': f'/construction/{project_id}/slips',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_slips', values)

    @http.route(['/construction/<int:project_id>/slip/<int:slip_id>'],
                type='http', auth='user', website=True)
    def portal_construction_slip_detail(self, project_id, slip_id, **kw):
        """通報單詳情"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Slip = request.env['reservation.notification.slip']
        slip = Slip.search([
            ('id', '=', slip_id),
            ('project_id', '=', project.id),
        ], limit=1)
        if not slip:
            return request.redirect(f'/construction/{project_id}/slips')

        state_selection = dict(
            Slip.fields_get(['state'])['state']['selection']
        )

        # 連結的檢查和缺失
        slip_inspections = []
        slip_defects = []
        try:
            slip_inspections = request.env['reservation.self.inspection'].search([
                ('slip_id', '=', slip.id),
            ], limit=5, order='inspection_date desc')
        except Exception:
            pass
        try:
            slip_defects = request.env['reservation.defect.improvement'].search([
                ('slip_id', '=', slip.id),
            ], limit=5, order='found_date desc')
        except Exception:
            pass

        values = {
            'project': project,
            'slip': slip,
            'page_name': 'construction_slip_detail',
            'state_selection': state_selection,
            'slip_inspections': slip_inspections,
            'slip_defects': slip_defects,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            # chatter
            'object': slip,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_slip_detail', values)

    @http.route(['/construction/<int:project_id>/tests',
                 '/construction/<int:project_id>/tests/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_tests(self, project_id, page=1, **kw):
        """檢試驗管制列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # construction_test 非硬依賴（沿用 _get_test_alerts 的存在性守衛慣例）
        if 'supervision.test.record' not in request.env:
            return request.redirect(f'/construction/{project_id}')
        Test = request.env['supervision.test.record']
        domain = [('project_id', '=', project.id)]
        result_filter = kw.get('result')
        if result_filter in ('pass', 'fail', 'pending'):
            domain.append(('result', '=', result_filter))

        test_count = Test.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/tests',
            url_args={'result': result_filter} if result_filter else {},
            total=test_count,
            page=page,
            step=self._items_per_page,
        )
        tests = Test.search(
            domain, order='sample_date desc, id desc',
            limit=self._items_per_page, offset=pager['offset'])

        values = {
            'project': project,
            'tests': tests,
            'test_count': test_count,
            'page_name': 'construction_tests',
            'pager': pager,
            'result_filter': result_filter or '',
            'default_url': f'/construction/{project_id}/tests',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_tests', values)

    @http.route(['/construction/<int:project_id>/test/<int:test_id>'],
                type='http', auth='user', website=True)
    def portal_construction_test_detail(self, project_id, test_id, **kw):
        """檢試驗管制詳情"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if 'supervision.test.record' not in request.env:
            return request.redirect(f'/construction/{project_id}')
        Test = request.env['supervision.test.record']
        test = Test.search(
            [('id', '=', test_id), ('project_id', '=', project.id)], limit=1)
        if not test:
            return request.redirect(f'/construction/{project_id}/tests')

        result_selection = dict(Test.fields_get(['result'])['result']['selection'])
        status_selection = dict(
            Test.fields_get(['processing_status'])['processing_status']['selection'])

        values = {
            'project': project,
            'test': test,
            'page_name': 'construction_test_detail',
            'result_selection': result_selection,
            'status_selection': status_selection,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'object': test,
            'disable_composer': False,
            'message_per_page': 10,
        }
        return request.render('construction_portal.portal_construction_test_detail', values)

    @http.route(['/construction/<int:project_id>/documents', '/construction/<int:project_id>/documents/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_documents(self, project_id, page=1, **kw):
        """檔案管理列表

        2026-08-21：資料源從 `supervision.document` 改成 `ir.attachment`
        ——與後台「檔案總覽」同一份資料。前台上傳的檔案後台看得到，
        後台上傳的契約圖說前台也查得到，不再是兩套各自為政的檔案櫃。

        篩選改用**資料夾**而非文件分類：分類已經有 44 個，攤成 pills 在手機上會爆版；
        而且資料夾才是使用者腦中「檔案放在哪」的模型。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Attachment = request.env['ir.attachment'].sudo()
        domain = [
            ('supervision_project_id', '=', project.id),
            # 照片走「照片管理」專責，不在檔案管理裡重複出現
            ('res_model', '!=', 'supervision.photo'),
        ]

        # 資料夾篩選（含所有下層）
        folder_filter = kw.get('folder')
        folder_id = int(folder_filter) if folder_filter and folder_filter.isdigit() else 0
        if folder_id:
            domain.append(('folder_id', 'child_of', folder_id))

        att_count = Attachment.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/documents',
            total=att_count,
            page=page,
            step=self._items_per_page,
            url_args={'folder': folder_id} if folder_id else {},
        )

        attachments = Attachment.search(
            domain,
            order='create_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        # 本案的資料夾清單（供篩選與上傳選擇）。
        # 前台**不提供建立資料夾**——結構由後台維護，現場人員只挑既有的丟。
        folders = request.env['supervision.folder'].sudo().search(
            [('project_id', '=', project.id)], order='complete_name')

        values = {
            'project': project,
            'attachments': attachments,
            'folders': folders,
            'folder_filter': folder_id,
            'page_name': 'construction_documents',
            'pager': pager,
            'default_url': f'/construction/{project_id}/documents',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_documents', values)

    @http.route(['/construction/<int:project_id>/document/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_document_upload(self, project_id, **post):
        """檔案上傳（前台）

        2026-08-21：不再建立 `supervision.document`，只建 `ir.attachment`
        並把四個歸位欄位一次補齊——與後台上傳精靈、附件 mixin 完全同一套規則。
        少補任何一個，檔案在「檔案總覽」裡就會變成孤兒。

        資料夾**只能挑既有的**，前台不提供建立資料夾（依使用者要求：會太混亂）。
        沒挑或挑到別案的資料夾時不擋人——檔案照樣掛到本工程，只是資料夾留空，
        事後在後台補即可。現場人員在工地被系統擋住，比事後補歸檔麻煩得多。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        uploaded_file = post.get('file')
        if not uploaded_file:
            return request.redirect(f'/construction/{project_id}/documents?error=no_file')

        folder = request.env['supervision.folder'].sudo().browse(
            int(post.get('folder_id') or 0)).exists()
        # 防跨案：挑到別案的資料夾一律視為沒挑
        if folder and folder.project_id != project:
            folder = request.env['supervision.folder'].sudo().browse()

        # 分類沿用資料夾的（沿樹往上找），與後台上傳精靈同一套邏輯
        category = folder._inherited_category() if folder \
            else request.env['supervision.document.category'].sudo().browse()

        # M0.6：附件不再 public（避免 /web/content 枚舉）；
        # 前台下載走帶權限檢查的 /construction/doc/<att_id>。
        request.env['ir.attachment'].sudo().create({
            'name': post.get('name') or uploaded_file.filename,
            'datas': base64.b64encode(uploaded_file.read()),
            'type': 'binary',
            'public': False,
            # 四個歸位欄位
            'res_model': 'supervision.folder' if folder else False,
            'res_id': folder.id if folder else 0,
            'folder_id': folder.id if folder else False,
            'document_category_id': category.id if category else False,
            'supervision_project_id': project.id,
        })

        return request.redirect(
            f'/construction/{project_id}/documents?message=uploaded'
        )

    @http.route(['/construction/<int:project_id>/slip/<int:slip_id>/confirm'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_slip_confirm(self, project_id, slip_id, **post):
        """通報單：核定（draft → not_started）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        slip = request.env['reservation.notification.slip'].search(
            [('id', '=', slip_id), ('project_id', '=', project.id)], limit=1)
        return self._run_review_action(
            slip, 'action_confirm',
            f'/construction/{project_id}/slip/{slip_id}', f'/construction/{project_id}/slip/{slip_id}')

    @http.route(['/construction/<int:project_id>/slip/<int:slip_id>/close'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_slip_close(self, project_id, slip_id, **post):
        """通報單：結案（in_progress → closed）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        slip = request.env['reservation.notification.slip'].search(
            [('id', '=', slip_id), ('project_id', '=', project.id)], limit=1)
        return self._run_review_action(
            slip, 'action_close',
            f'/construction/{project_id}/slip/{slip_id}', f'/construction/{project_id}/slip/{slip_id}')

    @http.route(['/construction/<int:project_id>/slip/<int:slip_id>/set-geo'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_slip_set_geo(self, project_id, slip_id, **post):
        """通報單：設定施工地點座標。

        這組座標的用途是讓**本通報單的照片**在沒有 GPS EXIF 時自動沿用
        （見 portal_photo.py 的通報單照片上傳），現場人員因此不必逐張填座標。
        通報單代表工區內一個特定地點，比工程案件的中心點精確。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        self._require_write(_('權限不足：閱覽角色不可修改通報單'))
        slip = request.env['reservation.notification.slip'].sudo().search(
            [('id', '=', slip_id), ('project_id', '=', project.id)], limit=1)
        back = f'/construction/{project_id}/slip/{slip_id}'
        if not slip:
            return request.redirect(f'/construction/{project_id}/slips')
        try:
            lat = float(post.get('latitude') or 0)
            lng = float(post.get('longitude') or 0)
        except (TypeError, ValueError):
            return request.redirect(f'{back}?error=geo_invalid')
        try:
            # 範圍由模型的 _check_slip_coordinates 把關，這裡只負責把錯誤
            # 轉成前台看得懂的訊息，而不是丟一頁 500。
            slip.write({'latitude': lat, 'longitude': lng})
        except ValidationError:
            return request.redirect(f'{back}?error=geo_invalid')
        return request.redirect(f'{back}?message=geo_saved')

    @http.route(['/construction/<int:project_id>/schedule/extend'],
                type='http', auth='user', website=True)
    def portal_schedule_extend_page(self, project_id, **kw):
        """工期展延頁面：顯示 draft 進度表並提供展延輸入"""
        try:
            project = request.env['project.project'].browse(project_id)
            project.check_access_rule('read')
            project.check_access_rights('read')
        except (AccessError, MissingError):
            return request.redirect('/my')

        Schedule = request.env['progress.schedule'].sudo()
        draft_schedule = Schedule.search([
            ('project_id', '=', project.id),
            ('state', '=', 'draft'),
        ], order='id desc', limit=1)

        values = {
            'project': project,
            'schedule': draft_schedule,
            'page_name': 'construction_schedule_extend',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'error': kw.get('error'),
            'success': kw.get('success'),
        }
        return request.render('construction_portal.portal_schedule_extend', values)

    @http.route(['/construction/<int:project_id>/schedule/<int:schedule_id>/extend'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_schedule_extend_submit(self, project_id, schedule_id, **post):
        """提交工期展延：寫入 current_extension 並呼叫 action_extend_lines"""
        try:
            project = request.env['project.project'].browse(project_id)
            project.check_access_rule('write')
            project.check_access_rights('write')
        except (AccessError, MissingError):
            return request.redirect('/my')

        schedule = request.env['progress.schedule'].sudo().browse(schedule_id)
        if not schedule.exists() or schedule.project_id.id != project.id:
            return request.redirect(
                f'/construction/{project_id}/schedule/extend?error=not_found')
        if schedule.state != 'draft':
            return request.redirect(
                f'/construction/{project_id}/schedule/extend?error=not_draft')

        try:
            current_extension = int(post.get('current_extension') or 0)
        except (TypeError, ValueError):
            return request.redirect(
                f'/construction/{project_id}/schedule/extend?error=invalid_value')
        if current_extension < 0:
            return request.redirect(
                f'/construction/{project_id}/schedule/extend?error=negative')

        try:
            schedule.write({'current_extension': current_extension})
            schedule.action_extend_lines()
        except (UserError, ValidationError) as e:
            _logger.warning('schedule extend failed: %s', e)
            return request.redirect(
                f'/construction/{project_id}/schedule/extend?error=action_failed')

        return request.redirect(
            f'/construction/{project_id}/schedule/extend?success=1')
