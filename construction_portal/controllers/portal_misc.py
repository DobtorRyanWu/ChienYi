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
    _photo_category_options, _photo_category_to_id, _portal_save_photos,
    _defect_save_photos, _portal_delete_photo, _portal_photo_to_supervision,
    _haversine_km,
)


class MiscRoutesMixin:
    @http.route(['/construction/doc/<int:att_id>'], type='http', auth='user')
    def portal_construction_document_serve(self, att_id, **kw):
        """帶專案權限檢查的文件下載端點（M0.6，取代 public=True 的裸 /web/content）。

        允許清單：只服務屬於某 supervision.document.upload_attachment_ids 的附件，
        依登入者對該文件所屬專案的可見範圍把關；不可見一律 404（不洩漏存在性）。
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
        """檔案管理列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Doc = request.env['supervision.document'].sudo()
        domain = [('project_id', '=', project.id)]

        # 分類篩選
        cat_filter = kw.get('category')
        if cat_filter:
            domain.append(('document_category_id', '=', int(cat_filter)))

        doc_count = Doc.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/documents',
            total=doc_count,
            page=page,
            step=self._items_per_page,
            url_args={'category': cat_filter} if cat_filter else {},
        )

        documents = Doc.search(
            domain,
            order='document_category_id, name',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        # 分類列表
        categories = request.env['supervision.document.category'].sudo().search([], order='sequence, name')

        values = {
            'project': project,
            'documents': documents,
            'categories': categories,
            'cat_filter': int(cat_filter) if cat_filter else 0,
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
        """文件上傳"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        uploaded_file = post.get('file')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read())

            # M0.6：文件附件不再 public（避免 /web/content 枚舉）；
            # 前台下載改走帶權限檢查的 /construction/doc/<att_id>。
            attachment = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': file_data,
                'res_model': 'supervision.document',
                'type': 'binary',
                'public': False,
            })

            cat_id = int(post.get('document_category_id', 0)) or False
            doc_vals = {
                'name': post.get('name') or uploaded_file.filename,
                'project_id': project.id,
                'document_category_id': cat_id,
                'upload_attachment_ids': [(4, attachment.id)],
                'state': 'uploaded',
            }

            request.env['supervision.document'].sudo().create(doc_vals)

            return request.redirect(
                f'/construction/{project_id}/documents?message=uploaded'
            )

        return request.redirect(f'/construction/{project_id}/documents?error=no_file')

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
