# -*- coding: utf-8 -*-
"""M4-a：PhotoRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

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


def _post_geo(post):
    """從表單取照片座標，回 (lat, lng)。

    欄位名在本 codebase 有兩套並存：共用模板 cy_photo_geo_fields 與施工日誌
    主上傳表單送的是 photo_latitude / photo_longitude，較早的幾條路由讀的是
    latitude / longitude。兩者都收，避免哪一邊改了另一邊靜默失效
    ——這種錯不會噴例外，只會讓座標恆為 0、照片默默不出現在地圖上。
    """
    return (post.get('photo_latitude') or post.get('latitude') or 0,
            post.get('photo_longitude') or post.get('longitude') or 0)


class PhotoRoutesMixin:
    @http.route(['/construction/img/<int:att_id>',
                 '/construction/img/<int:att_id>/<int:width>x<int:height>'],
                type='http', auth='user')
    def portal_construction_photo_serve(self, att_id, width=0, height=0,
                                        crop=False, download=False, **kw):
        """帶專案權限檢查的照片供圖端點（M0.6，取代裸 public 供圖）。"""
        att = request.env['ir.attachment'].sudo().browse(att_id).exists()
        # 只服務影像附件：非影像（PDF / 簽章 / 任意二進位）一律 404。除了避免本端點
        # 淪為任意附件下載器（抗辯 finding），也修掉「非影像餵進 image pipeline → 500」。
        if not att or not (att.mimetype or '').startswith('image/'):
            raise NotFound()
        project = self._resolve_photo_project(att)
        if not self._user_can_see_project(project):
            raise NotFound()  # 404，不洩漏附件存在性
        try:
            w, h = int(width or 0), int(height or 0)
        except (TypeError, ValueError):
            w = h = 0
        crop = str(crop).lower() in ('1', 'true', 'yes')
        as_download = str(download).lower() in ('1', 'true', 'yes')
        IrBinary = request.env['ir.binary'].sudo()
        if as_download:
            return IrBinary._get_stream_from(att, 'raw').get_response(as_attachment=True)
        return IrBinary._get_image_stream_from(
            att, 'raw', width=w, height=h, crop=crop).get_response()

    @http.route(['/construction/daily-log/<int:log_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_photo_upload(self, log_id, **post):
        """詳情頁追加上傳照片"""
        log = request.env['daily.log.sheet'].sudo().browse(log_id)
        if not log.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'project.project', log.supervision_project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：追加照片限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        # A（2026-07-14）：照片為附加證據、不改動已定稿的日誌欄位內容，
        # 故鎖定（超過 14 天）的日誌仍允許「補上照片」（歷史建檔需求）。
        # 日誌內容編輯仍受 is_locked 保護（在編輯路由把關），此處只加照片。
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'daily_log',
            'latitude': _post_geo(post)[0],
            'longitude': _post_geo(post)[1],
        })
        _portal_save_photos(
            request.env, log, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/construction/{project.id}/daily-log/{log.id}?message=photo_added'
        )

    @http.route(['/construction/daily-log/<int:log_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_photo_delete(self, log_id, att_id, **post):
        """從詳情頁刪除單張照片"""
        log = request.env['daily.log.sheet'].sudo().browse(log_id)
        if not log.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'project.project', log.supervision_project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if log.is_locked:
            return request.redirect(
                f'/construction/{project.id}/daily-log/{log.id}?error=locked'
            )

        # 比對附件 id 而非照片 id：收斂後 photo_ids.ids 是 supervision.photo 的 id，
        # 但本路由的 att_id 來自模板組出的 /photo/<att_id>/delete（附件 id），
        # 兩者對不上會讓守衛永遠不成立、刪除靜默失效。
        if att_id in log.photo_ids.attachment_id.ids:
            _portal_delete_photo(request.env, log, att_id)

        return request.redirect(
            f'/construction/{project.id}/daily-log/{log.id}?message=photo_deleted'
        )

    @http.route(['/construction/inspection/<int:inspection_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_inspection_photo_upload(self, inspection_id, **post):
        """一般式自主檢查詳情頁追加上傳照片"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：追加照片限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'inspection',
            'latitude': _post_geo(post)[0],
            'longitude': _post_geo(post)[1],
        })
        _portal_save_photos(
            request.env, inspection, inspection.project_id,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/construction/inspection/{inspection.id}?message=photo_added'
        )

    @http.route(['/construction/inspection/<int:inspection_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_inspection_photo_delete(self, inspection_id, att_id, **post):
        """一般式自主檢查刪除照片"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # 同施工日誌：比對附件 id 而非照片 id
        if att_id in inspection.photo_ids.attachment_id.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/construction/inspection/{inspection.id}?message=photo_deleted'
        )

    @http.route(['/construction/reservation-inspection/<int:inspection_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_reservation_inspection_photo_upload(self, inspection_id, **post):
        """預約式檢查追加照片"""
        inspection = request.env['reservation.self.inspection'].sudo().browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'project.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：追加照片限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'inspection',
            'latitude': _post_geo(post)[0],
            'longitude': _post_geo(post)[1],
        })
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/construction/reservation-inspection/{inspection.id}?message=photo_added'
        )

    @http.route(['/construction/reservation-inspection/<int:inspection_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_reservation_inspection_photo_delete(self, inspection_id, att_id, **post):
        """預約式檢查刪除照片"""
        inspection = request.env['reservation.self.inspection'].sudo().browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            self._document_check_access(
                'project.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # 同施工日誌：比對附件 id 而非照片 id
        if att_id in inspection.photo_ids.attachment_id.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/construction/reservation-inspection/{inspection.id}?message=photo_deleted'
        )

    @http.route(['/construction/<int:project_id>/photos/grid',
                 '/construction/<int:project_id>/photos/grid/page/<int:page>',
                 '/construction/<int:project_id>/photos/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_photos(self, project_id, page=1, **kw):
        """照片列表（含篩選、日期分群） — 圖庫樣貌（第二順位）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Photo = request.env['supervision.photo']
        domain = [('project_id', '=', project.id)]

        # 篩選
        source_filter = kw.get('source')
        category_filter = kw.get('category')
        if source_filter:
            domain.append(('source_model', '=', source_filter))
        if category_filter:
            domain.append(('category_id', '=', _photo_category_to_id(category_filter)))

        photo_count = Photo.search_count(domain)
        url_args = {}
        if source_filter:
            url_args['source'] = source_filter
        if category_filter:
            url_args['category'] = category_filter

        pager = portal_pager(
            url=f'/construction/{project_id}/photos/grid',
            total=photo_count,
            page=page,
            step=24,
            url_args=url_args,
        )

        photos = Photo.search(
            domain,
            order='shot_date desc, create_date desc',
            limit=24,
            offset=pager['offset']
        )

        # 按日期分群
        date_groups = []
        current_date = None
        current_group = None
        for photo in photos:
            d = photo.shot_date or photo.create_date.date() if photo.create_date else None
            if d != current_date:
                current_date = d
                current_group = {'date': d, 'photos': []}
                date_groups.append(current_group)
            current_group['photos'].append(photo)

        # 篩選面板選項（從 fields_get）
        fields_info = Photo.fields_get(['source_model', 'category', 'construction_phase'])
        source_options = fields_info['source_model']['selection']
        category_options = _photo_category_options(request.env)

        values = {
            'project': project,
            'photos': photos,
            'date_groups': date_groups,
            'page_name': 'construction_photos',
            'pager': pager,
            'default_url': f'/construction/{project_id}/photos/grid',
            'source_options': source_options,
            'category_options': category_options,
            'source_filter': source_filter or '',
            'category_filter': category_filter or '',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_photos', values)

    @http.route(['/construction/<int:project_id>/photo/upload'],
                type='http', auth='user', website=True)
    def portal_construction_photo_upload_form(self, project_id, **kw):
        """照片上傳表單"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Photo = request.env['supervision.photo']
        fields_info = Photo.fields_get(['category', 'construction_phase', 'source_model'])

        values = {
            'project': project,
            'page_name': 'construction_photo_upload',
            'category_options': fields_info['category']['selection'],
            'phase_options': fields_info['construction_phase']['selection'],
            'source_options': fields_info['source_model']['selection'],
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_photo_upload', values)

    @http.route(['/construction/<int:project_id>/signboard/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_signboard_photo_upload(self, project_id, **post):
        """工程告示牌照片上傳（專案層級 signboard_photo_ids）。

        照片資料表收斂後改走共用的 _portal_save_photos：原本這裡自己建
        ir.attachment 再寫 M2M，是「格式不統一」的來源之一（說明欄位是系統
        套版產生、不是使用者填的）。現在與其他入口完全同一條路徑。

        signboard_project_id 這個來源欄位由 _photo_source_field() 依 record
        型別自動選出，所以 record 直接傳 project 即可。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：告示牌照片上傳限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        _portal_save_photos(
            request.env, project, project,
            request.httprequest.files.getlist('photos'),
            dict(_post_photo_meta(post),
                 source_model='other',
                 latitude=_post_geo(post)[0],
                 longitude=_post_geo(post)[1],
                 # 告示牌是使用者指定「可繼承座標」的兩個來源之一：
                 # 告示牌實體就立在工地，照片沒 GPS 時用工程座標誤差可接受。
                 fallback_latitude=project.latitude,
                 fallback_longitude=project.longitude))
        return request.redirect(
            f'/construction/{project.id}/photos?message=signboard_added')

    @http.route(['/construction/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_photo_upload(self, **post):
        """處理照片上傳（支持分類與 GPS）"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：照片上傳限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))

        uploaded_file = post.get('photo')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read())

            vals = {
                'project_id': project_id,
                'filename': uploaded_file.filename,
                'description': post.get('description', ''),
                'photo_date': post.get('photo_date'),
            }

            # 分類欄位（改寫入 category_id，對應後台維護的分類主檔）
            if post.get('category'):
                vals['category_id'] = _photo_category_to_id(post['category'])
            if post.get('construction_phase'):
                vals['construction_phase'] = post['construction_phase']
            if post.get('source_model'):
                vals['source_model'] = post['source_model']
            if post.get('location_description'):
                vals['location_description'] = post['location_description']

            # GPS — 過濾無效值（空字串、0,0、超出地球範圍）避免落在赤道大西洋
            lat = post.get('latitude')
            lng = post.get('longitude')
            if lat and lng:
                try:
                    lat_f = float(lat)
                    lng_f = float(lng)
                    if (lat_f != 0 or lng_f != 0) and -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                        vals['latitude'] = lat_f
                        vals['longitude'] = lng_f
                except (ValueError, TypeError):
                    pass

            Photo = request.env['supervision.photo']
            photo = Photo.create_from_portal(vals, partner, file_data)

            return request.redirect(f'/construction/{project_id}/photos?message=uploaded')

        return request.redirect(f'/construction/{project_id}/photo/upload?error=no_file')

    @http.route(['/construction/photo/upload/ajax'],
                type='json', auth='user', methods=['POST'])
    def portal_construction_photo_upload_ajax(self, **post):
        """AJAX: 單張照片上傳（批次上傳時逐張呼叫）"""
        import base64
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'success': False, 'error': 'access_denied'}

        photo_data = post.get('photo_data')
        filename = post.get('filename', 'photo.jpg')

        if not photo_data:
            return {'success': False, 'error': 'no_data'}

        vals = {
            'project_id': project_id,
            'filename': filename,
            'description': post.get('description', ''),
            'photo_date': post.get('photo_date'),
        }

        # 分類欄位（改寫入 category_id，對應後台維護的分類主檔）
        if post.get('category'):
            vals['category_id'] = _photo_category_to_id(post['category'])
        if post.get('construction_phase'):
            vals['construction_phase'] = post['construction_phase']
        if post.get('source_model'):
            vals['source_model'] = post['source_model']
        if post.get('location_description'):
            vals['location_description'] = post['location_description']

        # GPS — 過濾無效值（同上）
        lat = post.get('latitude')
        lng = post.get('longitude')
        if lat and lng:
            try:
                lat_f = float(lat)
                lng_f = float(lng)
                if (lat_f != 0 or lng_f != 0) and -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                    vals['latitude'] = lat_f
                    vals['longitude'] = lng_f
            except (ValueError, TypeError):
                pass

        try:
            Photo = request.env['supervision.photo']
            photo = Photo.create_from_portal(vals, partner, photo_data)
            return {'success': True, 'photo_id': photo.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route(['/construction/photo/<int:photo_id>'],
                type='http', auth='user', website=True)
    def portal_construction_photo_detail(self, photo_id, **kw):
        """照片詳情"""
        try:
            photo = self._document_check_access(
                'supervision.photo', photo_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'photo': photo,
            'project': photo.project_id,
            'page_name': 'construction_photo_detail',
            'day_count': self._get_project_day_count(photo.project_id),
            'nav_badges': self._get_nav_badges(photo.project_id),
        }

        return request.render('construction_portal.portal_construction_photo_detail', values)

    @http.route(['/construction/<int:project_id>/test/<int:test_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_test_photo_upload(self, project_id, test_id, **post):
        """C（2026-07-14）：檢試驗照片上傳。

        test.record 無 photo_ids 欄位，靠 computed related_photo_ids 反查
        supervision.photo(source_model='test', source_id=test.id)。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if 'supervision.test.record' not in request.env:
            return request.redirect(f'/construction/{project_id}')
        test = request.env['supervision.test.record'].search(
            [('id', '=', test_id), ('project_id', '=', project.id)], limit=1)
        if not test:
            return request.redirect(f'/construction/{project_id}/tests')
        files = request.httprequest.files.getlist('photos')
        _portal_save_photos(
            request.env, test, project, files,
            # 原本這裡漏了 category（表單有下拉、送出後被丟掉），改走
            # _post_photo_meta() 一次補齊說明／分類／拍攝地點說明三欄。
            dict(_post_photo_meta(post),
                 source_model='test',
                 # 檢試驗照片不繼承任何座標（只有告示牌與通報單繼承）：
                 # 抓不到 EXIF 又沒按定位鈕就留空。
                 latitude=_post_geo(post)[0],
                 longitude=_post_geo(post)[1]))
        return request.redirect(f'/construction/{project_id}/test/{test_id}?message=photo_added')

    @http.route(['/construction/<int:project_id>/slip/<int:slip_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_slip_photo_upload(self, project_id, slip_id, **post):
        """C（2026-07-14）：通報單照片上傳。

        slip 無 photo_ids 欄位，靠 computed related_photo_ids 反查
        supervision.photo(source_model='notification', source_id=slip.id)。
        _portal_save_photos 會建好 attachment(public) + supervision.photo，
        故存檔後即出現在通報單詳情頁。
        """
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        slip = request.env['reservation.notification.slip'].search(
            [('id', '=', slip_id), ('project_id', '=', project.id)], limit=1)
        if not slip:
            return request.redirect(f'/construction/{project_id}/slips')
        files = request.httprequest.files.getlist('photos')
        _portal_save_photos(
            request.env, slip, project, files,
            # 原本這裡漏了 category（同檢試驗）。
            dict(_post_photo_meta(post),
                 source_model='notification',
                 # 使用者可手填／按定位鈕；沒填時退回通報單本身的座標。
                 latitude=_post_geo(post)[0],
                 longitude=_post_geo(post)[1],
                 # 通報單是少數允許「照片沒 GPS 就繼承來源座標」的入口之一
                 # （另一個是工程告示牌）。通報單代表工區內一個特定地點，
                 # 比工程案件中心點精確，且現場人員因此不必逐張填座標。
                 fallback_latitude=slip.latitude,
                 fallback_longitude=slip.longitude))
        return request.redirect(f'/construction/{project_id}/slip/{slip_id}?message=photo_added')

    @http.route(['/construction/<int:project_id>/photos',
                 '/construction/<int:project_id>/photos/map'],
                type='http', auth='user', website=True)
    def portal_construction_photos_map(self, project_id, **kw):
        """照片地圖頁面（照片中心預設入口） — 第一順位顯示"""
        try:
            project_sudo = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/construction')

        Photo = request.env['supervision.photo'].sudo()
        project_domain = [('active', '=', True), ('project_id', '=', project_id)]

        total_photos = Photo.search_count(project_domain)
        gps_photos = Photo.search_count(
            project_domain + [('latitude', '!=', 0), ('longitude', '!=', 0)]
        )

        # 篩選選項
        fields_info = Photo.fields_get(['source_model', 'category', 'construction_phase'])
        filter_options = {
            'source_model': fields_info.get('source_model', {}).get('selection', []),
            'category': _photo_category_options(request.env),
            'construction_phase': fields_info.get('construction_phase', {}).get('selection', []),
        }

        # 專案中心座標
        project_center = {
            'lat': project_sudo.latitude or 23.5,
            'lng': project_sudo.longitude or 120.5,
        }

        values = self._prepare_portal_layout_values()
        values.update({
            'project': project_sudo,
            'total_photos': total_photos,
            'gps_photos': gps_photos,
            'filter_options_json': json.dumps(filter_options, ensure_ascii=False),
            'project_center_json': json.dumps(project_center),
            'page_name': 'construction_photos',
        })

        return request.render('construction_portal.portal_construction_photos_map', values)

    @http.route(['/construction/<int:project_id>/photos/api/markers'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_markers(self, project_id, **post):
        """取得專案照片 markers"""
        try:
            self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'error': 'Access denied'}

        Photo = request.env['supervision.photo'].sudo()
        domain = self._portal_map_build_domain(project_id, post, require_gps=True)
        photos = Photo.search(domain, limit=5000, order='shot_date desc')

        total = Photo.search_count([
            ('active', '=', True), ('project_id', '=', project_id),
            ('latitude', '!=', 0), ('longitude', '!=', 0),
        ])

        return {
            'markers': [self._portal_map_photo_to_marker(p) for p in photos],
            'total': total,
            'filtered': len(photos),
        }

    @http.route(['/construction/<int:project_id>/photos/api/area-photos'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_area(self, project_id, **post):
        """取得地圖範圍內照片詳情"""
        try:
            self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'error': 'Access denied'}

        bounds = post.get('bounds', {})
        if not bounds or not all(k in bounds for k in ('north', 'south', 'east', 'west')):
            return {'photos': [], 'total': 0, 'has_more': False}

        Photo = request.env['supervision.photo'].sudo()
        domain = self._portal_map_build_domain(project_id, post, require_gps=True)
        domain += [
            ('latitude', '>=', bounds['south']),
            ('latitude', '<=', bounds['north']),
            ('longitude', '>=', bounds['west']),
            ('longitude', '<=', bounds['east']),
        ]

        limit = min(int(post.get('limit', 50)), 100)
        offset = int(post.get('offset', 0))
        total = Photo.search_count(domain)
        photos = Photo.search(domain, limit=limit, offset=offset, order='shot_date desc')

        source_labels = dict(Photo._fields['source_model'].selection)
        category_labels = dict(Photo._fields['category'].selection)

        return {
            'photos': [self._portal_map_photo_to_detail(p, source_labels, category_labels) for p in photos],
            'total': total,
            'has_more': (offset + limit) < total,
        }

    @http.route(['/construction/<int:project_id>/photos/api/nearby'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_nearby(self, project_id, **post):
        """取得附近照片（依距離排序）"""
        try:
            self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return {'error': 'Access denied'}

        lat = float(post.get('lat', 0))
        lng = float(post.get('lng', 0))
        radius_km = float(post.get('radius', 1.0))
        limit = min(int(post.get('limit', 20)), 100)

        if not lat or not lng:
            return {'photos': []}

        Photo = request.env['supervision.photo'].sudo()

        # Bounding box 粗篩
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

        domain = [
            ('active', '=', True), ('project_id', '=', project_id),
            ('latitude', '>=', lat - lat_delta), ('latitude', '<=', lat + lat_delta),
            ('longitude', '>=', lng - lng_delta), ('longitude', '<=', lng + lng_delta),
            ('latitude', '!=', 0), ('longitude', '!=', 0),
        ]
        if post.get('source_model'):
            domain.append(('source_model', '=', post['source_model']))

        photos = Photo.search(domain, limit=200)

        # 精算距離排序
        results = []
        for p in photos:
            d = self._haversine(lat, lng, p.latitude, p.longitude)
            if d <= radius_km:
                results.append((p, d))
        results.sort(key=lambda x: x[1])
        results = results[:limit]

        source_labels = dict(Photo._fields['source_model'].selection)
        category_labels = dict(Photo._fields['category'].selection)

        photos_data = []
        for p, d in results:
            detail = self._portal_map_photo_to_detail(p, source_labels, category_labels)
            detail['distance'] = round(d, 3)
            detail['distance_label'] = '%.0f 公尺' % (d * 1000) if d < 1 else '%.1f 公里' % d
            photos_data.append(detail)

        return {'photos': photos_data}
