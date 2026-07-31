# -*- coding: utf-8 -*-
"""M4-a：InspectionRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

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


class InspectionRoutesMixin:
    @http.route(['/construction/<int:project_id>/inspections/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_inspections_import(self, project_id, **kw):
        """自主檢查批次匯入頁（GET）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_inspections',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'imported': int(kw.get('imported', 0) or 0),
            'skipped': int(kw.get('skipped', 0) or 0),
            'failed': int(kw.get('failed', 0) or 0),
            'failed_details': request.session.pop(
                'inspection_import_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_inspection_import', values)

    @http.route(['/construction/<int:project_id>/inspections/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_inspections_import_submit(self, project_id, **post):
        """自主檢查批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.inspection_xlsm_parser import parse_inspection_summary_xlsm
        from ..utils.inspection_b_xlsm_parser import parse_inspection_b_xlsx

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[INSP_IMPORT] POST entered, files count=%s, post keys=%s',
            len(files), list(post.keys()))

        env = request.env
        Insp = env['general.self.inspection'].sudo()
        InspType = env['self.inspection.type'].sudo()
        base_url = f'/construction/{project_id}/inspections/import'
        supervision_project_id = project.id

        imported = 0
        skipped = 0
        failed = 0
        failed_details = []
        type_cache = {}   # name -> record
        POC_LIMIT = 10000  # 全量匯入

        total_rows_processed = 0

        for upload in files:
            fname = upload.filename or 'unnamed.xlsx'
            rows = []
            try:
                raw = upload.read()
                # 先試 A 標格式（多 category sheet）
                rows = parse_inspection_summary_xlsm(raw, filename=fname)
                # 若 A 格式抽不到，試 B 標交叉表格格式
                if not rows:
                    rows = parse_inspection_b_xlsx(raw, filename=fname)
            except ValueError as e:
                failed += 1
                failed_details.append({'filename': fname, 'error': str(e)[:200]})
                continue
            except Exception as e:
                _logger.exception('[INSP_IMPORT] parse failed for %s', fname)
                failed += 1
                failed_details.append(
                    {'filename': fname, 'error': f'解析失敗：{e}'[:200]})
                continue

            for row in rows:
                if total_rows_processed >= POC_LIMIT:
                    break
                total_rows_processed += 1

                type_name = row['type_name']
                insp_date = row['inspection_date']
                location = row['location']
                note = row.get('note') or ''

                try:
                    # 1. find or create self.inspection.type
                    t = type_cache.get(type_name)
                    if not t:
                        t = InspType.search([
                            ('name', '=', type_name),
                            '|',
                            ('project_id', '=', supervision_project_id),
                            ('project_id', '=', False),
                        ], limit=1)
                        if not t:
                            t = InspType.create({
                                'name': type_name,
                                'project_id': supervision_project_id,
                                'category': 'civil',
                                'description': f'[auto-stub from 自檢總表單 {row["sheet_label"]}]',
                            })
                        type_cache[type_name] = t

                    # 2. duplicate check
                    existing = Insp.search([
                        ('project_id', '=', supervision_project_id),
                        ('inspection_date', '=', insp_date),
                        ('inspection_type_id', '=', t.id),
                        ('inspection_location', '=', location),
                    ], limit=1)
                    if existing:
                        skipped += 1
                        failed_details.append({
                            'filename': fname,
                            'error': (f'{insp_date} {type_name} @ {location} '
                                      f'已有紀錄 (id={existing.id})，跳過'),
                        })
                        continue

                    # 3. build checklist (fallback: default_item_ids or placeholder)
                    checklist_cmds = []
                    if t.default_item_ids:
                        for di in t.default_item_ids:
                            checklist_cmds.append((0, 0, {
                                'type_item_id': di.id,
                                'stage_id': di.stage_id.id or False,
                                'sequence': di.sequence or 10,
                                'check_item': di.name,
                                'design_standard': di.check_standard or '',
                                'check_result': 'pass',
                            }))
                    else:
                        checklist_cmds.append((0, 0, {
                            # 類型必有段落（新建時 default 帶三段、既有的由 migration 補），
                            # 取第一段當 placeholder 的落點
                            'stage_id': t.stage_ids[:1].id or False,
                            'sequence': 10,
                            'check_item': f'{type_name} - 施工中檢查',
                            'check_result': 'pass',
                            'note': '(自檢總表單批次匯入，無逐項明細資料)',
                        }))

                    # 4. create inspection
                    Insp.with_context(
                        tracking_disable=True,
                        mail_create_nolog=True,
                    ).create({
                        'project_id': supervision_project_id,
                        'inspection_type_id': t.id,
                        'sub_project_name': type_name,
                        'inspection_date': insp_date,
                        'inspection_location': location,
                        'inspection_timing': 'during',
                        'note': note,
                        'checklist_ids': checklist_cmds,
                    })
                    imported += 1

                except Exception as e:
                    _logger.exception('[INSP_IMPORT] row create failed')
                    failed += 1
                    failed_details.append({
                        'filename': fname,
                        'error': (f'{insp_date} {type_name}: {e}')[:200],
                    })

            if total_rows_processed >= POC_LIMIT:
                break

        request.session['inspection_import_failed_details'] = failed_details
        return request.redirect(
            f'{base_url}?imported={imported}&skipped={skipped}&failed={failed}')

    @http.route(['/construction/<int:project_id>/inspections', '/construction/<int:project_id>/inspections/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_inspections(self, project_id, page=1, **kw):
        """自主檢查列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Inspection = request.env['general.self.inspection']
        domain = [('project_id', '=', project.id)]

        inspection_count = Inspection.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/inspections',
            total=inspection_count,
            page=page,
            step=self._items_per_page,
        )

        inspections = Inspection.search(
            domain,
            order='inspection_date desc, create_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        # 預約式通報單篩選 chips
        slip_filter = kw.get('slip_id')
        slip_list = []
        if project.project_type == 'reservation':
            try:
                slip_list = request.env['reservation.notification.slip'].search([
                    ('project_id', '=', project.id),
                ], order='slip_no')
            except Exception:
                pass

        values = {
            'project': project,
            'inspections': inspections,
            'inspection_count': inspection_count,
            'page_name': 'construction_inspections',
            'pager': pager,
            'default_url': f'/construction/{project_id}/inspections',
            'slip_list': slip_list,
            'slip_filter': int(slip_filter) if slip_filter else 0,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_inspections', values)

    @http.route(['/construction/inspection-types'],
                type='http', auth='user', website=True)
    def portal_inspection_types(self, category=None, scope=None, search=None, **kw):
        """自主檢查樣板庫列表（分類 / 範圍篩選 + 關鍵字搜尋）"""
        InspType = request.env['self.inspection.type'].sudo()
        domain = self._accessible_type_domain()
        if category:
            domain = AND([domain, [('category', '=', category)]])
        if scope == 'global':
            domain = AND([domain, [('project_id', '=', False)]])
        elif scope == 'project':
            domain = AND([domain, [('project_id', '!=', False)]])
        if search:
            domain = AND([domain, ['|', ('name', 'ilike', search),
                                   ('code', 'ilike', search)]])
        types = InspType.search(domain)

        # 統計（不受目前篩選影響，給 chips 顯示總量）
        base = self._accessible_type_domain()
        values = {
            'types': types,
            'categories_map': dict(self._inspection_type_categories()),
            'count_global': InspType.search_count(
                AND([base, [('project_id', '=', False)]])),
            'count_project': InspType.search_count(
                AND([base, [('project_id', '!=', False)]])),
            'cur_category': category or '',
            'cur_scope': scope or '',
            'search': search or '',
            'can_manage': self._can_manage(),
            'page_name': 'inspection_types',
        }
        return request.render('construction_portal.portal_inspection_type_list', values)

    @http.route(['/construction/inspection-types/new'],
                type='http', auth='user', website=True)
    def portal_inspection_type_new(self, **kw):
        """新增樣板表單（限管理者）"""
        self._require_manage()
        values = {
            'rec': False,
            'categories': self._inspection_type_categories(),
            # 尚未建檔，還沒有段落可選。儲存時類型會自動帶「施工前/中/後」三段，
            # 項目一律落到第一段，之後可到編輯頁調整。
            'stages': request.env['self.inspection.type.stage'].browse(),
            'page_name': 'inspection_types',
        }
        return request.render('construction_portal.portal_inspection_type_form', values)

    @http.route(['/construction/inspection-types/<int:type_id>/edit'],
                type='http', auth='user', website=True)
    def portal_inspection_type_edit(self, type_id, **kw):
        """編輯樣板表單（限管理者）"""
        self._require_manage()
        rec = self._get_visible_inspection_type(type_id)
        if not rec:
            return request.redirect('/construction/inspection-types')
        values = {
            'rec': rec,
            'categories': self._inspection_type_categories(),
            'stages': rec.stage_ids,
            'page_name': 'inspection_types',
        }
        return request.render('construction_portal.portal_inspection_type_form', values)

    @http.route(['/construction/inspection-types/save'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_type_save(self, **post):
        """新增 / 編輯儲存（含 items 增刪改、docx 上傳）。限管理者。"""
        self._require_manage()
        InspType = request.env['self.inspection.type'].sudo()
        type_id = int(post.get('type_id') or 0)

        vals = {
            'name': (post.get('name') or '').strip(),
            'code': (post.get('code') or '').strip(),
            'category': post.get('category') or 'structure',
            'sequence': int(post.get('sequence') or 10),
            'description': post.get('description') or '',
        }
        if not vals['name']:
            return request.redirect('/construction/inspection-types/new?error=name')

        # docx 上傳（可選，未選則不動原檔）
        upload = request.httprequest.files.get('template_file')
        if upload and upload.filename:
            data = base64.b64encode(upload.read())
            vals['template_file'] = data
            vals['template_filename'] = upload.filename

        if type_id:
            rec = self._get_visible_inspection_type(type_id)
            if not rec:
                return request.redirect('/construction/inspection-types')
            rec.write(vals)
        else:
            rec = InspType.create(vals)
            # 新增頁沒有段落可選，所以不顯示項目編輯區；
            # 建檔後（此時已自動帶三個預設段落）轉到編輯頁設定項目
            return request.redirect(
                '/construction/inspection-types/%s/edit?message=created' % rec.id)

        self._save_inspection_type_items(rec, post)
        return request.redirect(
            '/construction/inspection-types/%s?message=saved' % rec.id)

    @http.route(['/construction/inspection-types/<int:type_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_type_delete(self, type_id, **post):
        """刪除樣板；被檢查記錄引用則改停用（archive）。限管理者。"""
        self._require_manage()
        rec = self._get_visible_inspection_type(type_id)
        if not rec:
            return request.redirect('/construction/inspection-types')
        if rec.inspection_count:
            # 有檢查記錄引用，FK 擋下硬刪 → 改停用，保留資料完整
            rec.write({'active': False})
            return request.redirect(
                '/construction/inspection-types?message=archived')
        rec.unlink()
        return request.redirect('/construction/inspection-types?message=deleted')

    @http.route(['/construction/inspection-types/<int:type_id>/toggle'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_type_toggle(self, type_id, **post):
        """切換啟用 / 停用。限管理者。"""
        self._require_manage()
        rec = self._get_visible_inspection_type(type_id)
        if not rec:
            return request.redirect('/construction/inspection-types')
        rec.write({'active': not rec.active})
        return request.redirect(
            '/construction/inspection-types/%s?message=toggled' % rec.id)

    @http.route(['/construction/inspection-types/<int:type_id>/template/download'],
                type='http', auth='user', website=True)
    def portal_inspection_type_download(self, type_id, **kw):
        """下載樣板 docx 原檔（全角色可下載）。"""
        from urllib.parse import quote
        rec = self._get_visible_inspection_type(type_id)
        if not rec or not rec.template_file:
            return request.redirect('/construction/inspection-types')
        content = base64.b64decode(rec.template_file)
        filename = rec.template_filename or ('%s.docx' % rec.name)
        return request.make_response(content, headers=[
            ('Content-Type',
             'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
            ('Content-Disposition',
             "attachment; filename*=UTF-8''%s" % quote(filename)),
        ])

    @http.route(['/construction/inspection-types/<int:type_id>'],
                type='http', auth='user', website=True)
    def portal_inspection_type_detail(self, type_id, **kw):
        """樣板詳情：類型資訊 + 分階段項目 + 檢查標準 + docx 下載。"""
        rec = self._get_visible_inspection_type(type_id)
        if not rec:
            return request.redirect('/construction/inspection-types')
        values = {
            'rec': rec,
            'categories_map': dict(self._inspection_type_categories()),
            'stage_groups': self._inspection_type_stage_groups(rec),
            'can_manage': self._can_manage(),
            'page_name': 'inspection_types',
        }
        return request.render('construction_portal.portal_inspection_type_detail', values)

    @http.route(['/construction/<int:project_id>/inspection/new'],
                type='http', auth='user', website=True)
    def portal_construction_inspection_new(self, project_id, **kw):
        """新增自主檢查表單"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        InspType = request.env['self.inspection.type'].sudo()
        # 只顯示全域樣板 + 當前專案專屬樣板（避免撈到別專案的設定）
        inspection_types = InspType.search(
            ['|', ('project_id', '=', False), ('project_id', '=', project.id)])

        # inspection_timing 選項從 fields_get 拉
        Inspection = request.env['general.self.inspection']
        timing_selection = Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']

        photo_categories = _photo_category_options(request.env)

        values = {
            'project': project,
            'inspection_types': inspection_types,
            'timing_options': timing_selection,
            'photo_categories': photo_categories,
            'page_name': 'construction_inspection_new',
            'today': date.today().isoformat(),
        }

        return request.render('construction_portal.portal_construction_inspection_form', values)

    @http.route(['/construction/inspection/create'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_inspection_create(self, **post):
        """建立自主檢查（含 checklist 項目提交）"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：建立自主檢查限現場人員以上，閱覽角色不可寫入
        self._require_write(_('權限不足：閱覽角色不可建立自主檢查'))

        vals = {
            'project_id': project_id,
            'inspection_type_id': int(post.get('inspection_type_id', 0)) or False,
            'inspection_date': post.get('inspection_date') or date.today().isoformat(),
            'inspection_location': post.get('inspection_location', ''),
            'inspection_timing': post.get('inspection_timing') or 'during',
            'sub_project_name': post.get('sub_project_name', ''),
            'note': post.get('note', ''),
        }

        Inspection = request.env['general.self.inspection']
        inspection = Inspection.create_from_portal(vals, partner)

        # 處理上傳照片
        # 三個描述欄位走 _post_photo_meta()：本表單已改用共用片段
        # cy_photo_meta_fields（不帶前綴），helper 同時相容舊的 photo_ 前綴。
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'inspection',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
        })
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        # 處理 checklist 項目結果（前台送出的 checklist_item_id 為「檢查類型預設項目 id」，
        # 對應建立時由 action_load_default_items 複製、並記錄 type_item_id 的檢查項目）
        idx = 0
        while True:
            item_id_str = post.get(f'checklist_item_id_{idx}')
            if item_id_str is None:
                break
            if item_id_str:
                check_result = post.get(f'checklist_result_{idx}', 'pass')
                actual_result = post.get(f'checklist_actual_{idx}', '')
                item = inspection.sudo().checklist_ids.filtered(
                    lambda l: l.type_item_id.id == int(item_id_str))
                if item:
                    item.write({
                        'check_result': check_result,
                        'actual_result': actual_result,
                    })
            idx += 1

        return request.redirect(
            f'/construction/inspection/{inspection.id}?message=created'
        )

    @http.route(['/construction/inspection/get-items'],
                type='json', auth='user', methods=['POST'])
    def portal_construction_inspection_get_items(self, **post):
        """AJAX: 取得檢查類型的預設 checklist items"""
        type_id = int(post.get('type_id', 0))
        if not type_id:
            return {'items': [], 'stages': []}

        InspType = request.env['self.inspection.type'].sudo().browse(type_id)
        if not InspType.exists():
            return {'items': [], 'stages': []}

        items = []
        for item in InspType.default_item_ids:
            items.append({
                'id': item.id,
                'name': item.name,
                'standard': item.check_standard or '',
                'stage_id': item.stage_id.id or 0,
                'note': item.note or '',
            })

        # 依段落分群。迭代 stage_ids 而非 items 的出現順序，
        # 才會照段落自己的 sequence 排（原本是照項目出現順序，順序可能是錯的）。
        used = {i['stage_id'] for i in items}
        stages = [{'key': s.id, 'label': s.name}
                  for s in InspType.stage_ids if s.id in used]
        if 0 in used:
            stages.append({'key': 0, 'label': '未分段'})

        return {'items': items, 'stages': stages}

    @http.route(['/construction/inspection/<int:inspection_id>'],
                type='http', auth='user', website=True)
    def portal_construction_inspection_detail(self, inspection_id, **kw):
        """自主檢查詳情"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 依查驗段落分群 checklist items
        stage_groups = self._inspection_stage_groups(inspection.checklist_ids)

        # inspection_timing Selection 選項
        timing_selection = dict(
            request.env['general.self.inspection'].fields_get(
                ['inspection_timing']
            )['inspection_timing']['selection']
        )

        # overall_result Selection 選項
        result_selection = dict(
            request.env['general.self.inspection'].fields_get(
                ['overall_result']
            )['overall_result']['selection']
        )

        photo_categories = _photo_category_options(request.env)

        values = {
            'inspection': inspection,
            'project': inspection.project_id,
            'page_name': 'construction_inspection_detail',
            'stage_groups': stage_groups,
            'timing_selection': timing_selection,
            'result_selection': result_selection,
            'day_count': self._get_project_day_count(inspection.project_id),
            'nav_badges': self._get_nav_badges(inspection.project_id),
            # 照片區塊
            # ⚠️ 送 ir.attachment 不是 supervision.photo（見 portal_daily_log.py
            # 同一處的說明）：共用區塊用 att.id 組圖片與刪除網址，
            # 送錯型別會縮圖 404、刪除靜默失效。
            'photos': inspection.photo_ids.attachment_id,
            'photo_to_supervision': _portal_photo_to_supervision(
                request.env, inspection.photo_ids.attachment_id),
            'photo_categories': photo_categories,
            'upload_url': f'/construction/inspection/{inspection.id}/photo/upload',
            'delete_url_tpl': f'/construction/inspection/{inspection.id}/photo/%s/delete',
            'is_locked': False,
            # chatter
            'object': inspection,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_inspection_detail', values)

    @http.route(['/construction/<int:project_id>/reservation-inspections', '/construction/<int:project_id>/reservation-inspections/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspections(self, project_id, page=1, **kw):
        """預約式自主檢查列表(掛在通報單下,但這裡彙總顯示)"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Inspection = request.env['reservation.self.inspection']
        domain = [('project_id', '=', project.id)]
        slip_filter = kw.get('slip_id')
        if slip_filter:
            try:
                domain.append(('slip_id', '=', int(slip_filter)))
            except ValueError:
                pass

        inspection_count = Inspection.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/reservation-inspections',
            total=inspection_count,
            page=page,
            step=self._items_per_page,
            url_args={'slip_id': slip_filter} if slip_filter else None,
        )

        inspections = Inspection.search(
            domain,
            order='inspection_date desc, id desc',
            limit=self._items_per_page,
            offset=pager['offset'],
        )

        # 提供通報單篩選 chips
        slip_list = request.env['reservation.notification.slip'].search([
            ('project_id', '=', project.id),
        ], order='create_date desc', limit=20)

        values = {
            'project': project,
            'inspections': inspections,
            'pager': pager,
            'default_url': f'/construction/{project_id}/reservation-inspections',
            'slip_list': slip_list,
            'slip_filter': slip_filter,
            'page_name': 'construction_reservation_inspections',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_reservation_inspections', values)

    @http.route(['/construction/<int:project_id>/reservation-inspection/new'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspection_new(self, project_id, slip_id=None, **kw):
        """預約式檢查新增表單(必須帶 slip_id)"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not slip_id:
            return request.redirect(f'/construction/{project_id}/slips')

        Slip = request.env['reservation.notification.slip']
        slip = Slip.search([
            ('id', '=', int(slip_id)),
            ('project_id', '=', project.id),
        ], limit=1)
        if not slip:
            return request.redirect(f'/construction/{project_id}/slips')

        InspType = request.env['self.inspection.type'].sudo()
        # 只顯示全域樣板 + 當前專案專屬樣板（避免撈到別專案的設定）
        inspection_types = InspType.search(
            ['|', ('project_id', '=', False), ('project_id', '=', project.id)])

        Inspection = request.env['reservation.self.inspection']
        timing_selection = Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']

        photo_categories = _photo_category_options(request.env)

        values = {
            'project': project,
            'slip': slip,
            'inspection_types': inspection_types,
            'timing_options': timing_selection,
            'photo_categories': photo_categories,
            'page_name': 'construction_reservation_inspection_new',
            'today': date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_reservation_inspection_form', values)

    @http.route(['/construction/reservation-inspection/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_reservation_inspection_create(self, **post):
        """建立預約式自主檢查"""
        slip_id = int(post.get('slip_id', 0))
        if not slip_id:
            return request.redirect('/my')

        Slip = request.env['reservation.notification.slip'].sudo()
        slip = Slip.browse(slip_id)
        if not slip.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access('project.project', slip.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：建立預約式自主檢查限現場人員以上，閱覽角色不可寫入
        self._require_write(_('權限不足：閱覽角色不可建立自主檢查'))

        vals = {
            'slip_id': slip.id,
            'inspection_type_id': int(post.get('inspection_type_id', 0)) or False,
            'sub_project_name': post.get('sub_project_name', ''),
            'inspection_date': post.get('inspection_date') or date.today().isoformat(),
            'inspection_location': post.get('inspection_location', ''),
            'inspection_timing': post.get('inspection_timing') or 'during',
            'contractor_name': post.get('contractor_name', ''),
            'subcontractor_name': post.get('subcontractor_name', ''),
            'note': post.get('note', ''),
        }
        Inspection = request.env['reservation.self.inspection'].sudo()
        inspection = Inspection.create(vals)

        # 載入預設檢查項目(若 type 有 default_item_ids)
        try:
            inspection.action_load_default_items()
        except Exception:
            pass

        # 套用 POST 帶來的 checklist 結果(對應預載項目順序)
        if inspection.checklist_ids:
            items = list(inspection.checklist_ids)
            for idx, item in enumerate(items):
                check_result = post.get(f'checklist_result_{idx}')
                actual_result = post.get(f'checklist_actual_{idx}', '')
                if check_result:
                    item.write({
                        'check_result': check_result,
                        'actual_result': actual_result,
                    })

        # 處理上傳照片（同一般式，見上方說明）
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'inspection',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
        })
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/construction/reservation-inspection/{inspection.id}?message=created'
        )

    @http.route(['/construction/reservation-inspection/<int:inspection_id>'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspection_detail(self, inspection_id, **kw):
        """預約式自主檢查詳情"""
        Inspection = request.env['reservation.self.inspection'].sudo()
        inspection = Inspection.browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'project.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 依查驗段落分群
        stage_groups = self._inspection_stage_groups(inspection.checklist_ids)

        timing_selection = dict(
            Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']
        )

        photo_categories = _photo_category_options(request.env)

        values = {
            'project': project,
            'slip': inspection.slip_id,
            'inspection': inspection,
            'stage_groups': stage_groups,
            'timing_selection': timing_selection,
            'page_name': 'construction_reservation_inspection_detail',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            # 照片區塊
            # ⚠️ 送 ir.attachment 不是 supervision.photo（見 portal_daily_log.py
            # 同一處的說明）：共用區塊用 att.id 組圖片與刪除網址，
            # 送錯型別會縮圖 404、刪除靜默失效。
            'photos': inspection.photo_ids.attachment_id,
            'photo_to_supervision': _portal_photo_to_supervision(
                request.env, inspection.photo_ids.attachment_id),
            'photo_categories': photo_categories,
            'upload_url': f'/construction/reservation-inspection/{inspection.id}/photo/upload',
            'delete_url_tpl': f'/construction/reservation-inspection/{inspection.id}/photo/%s/delete',
            'is_locked': False,
        }
        return request.render(
            'construction_portal.portal_construction_reservation_inspection_detail', values)

    @http.route(['/construction/inspection/<int:inspection_id>/confirm'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_confirm(self, inspection_id, **post):
        """自主檢查：確認（inspected → confirmed）"""
        try:
            insp = self._document_check_access('general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._run_review_action(
            insp, 'action_confirm',
            f'/construction/inspection/{inspection_id}', f'/construction/inspection/{inspection_id}')

    @http.route(['/construction/inspection/<int:inspection_id>/close'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_close(self, inspection_id, **post):
        """自主檢查：結案（confirmed → closed）"""
        try:
            insp = self._document_check_access('general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._run_review_action(
            insp, 'action_close',
            f'/construction/inspection/{inspection_id}', f'/construction/inspection/{inspection_id}')

    @http.route(['/construction/inspection/<int:inspection_id>/inspect'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_inspection_inspect(self, inspection_id, **post):
        """自主檢查：完成檢查（draft → inspected）。建立者本人或老闆/主管可執行。"""
        try:
            insp = self._document_check_access('general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        try:
            self._require_owner_or_manager(insp)
            insp.action_inspect()
        except (AccessError, UserError, ValidationError) as e:
            from urllib.parse import quote
            return request.redirect(
                f'/construction/inspection/{inspection_id}?error={quote(str(e))}')
        return request.redirect(
            f'/construction/inspection/{inspection_id}?msg=inspected')
