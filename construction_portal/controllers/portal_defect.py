# -*- coding: utf-8 -*-
"""M4-a：DefectRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

import base64
import json
import logging
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
    _haversine_km, resolve_record_type,
)

# M4-a 抽檔時漏了 _logger（只定義在 portal.py），導致三條匯入路由 POST 一進入
# 就 NameError。函式的 globals 綁在定義它的模組，必須在本檔自行定義。
_logger = logging.getLogger(__name__)


class DefectRoutesMixin:

    # ── 缺失匯入共用輔助 ──────────────────────────────────────────
    @staticmethod
    def _defect_prefix_configured(project):
        """該工程是否已設定缺失編號前綴。

        general/reservation 的 defect_no 由 `_compute_defect_no` 依
        `defect.improvement.prefix.config` 產生；沒設定會 raise UserError。
        匯入前先整批擋下，比讓每一列各噴一次錯誤有用。
        """
        return bool(request.env['defect.improvement.prefix.config'].sudo()
                    .search_count([('project_id', '=', project.id)]))

    @staticmethod
    def _defect_fallback_record_type(post):
        """匯入頁下拉帶來的 record_type，只在資料判不出時當兜底用。"""
        rt = (post.get('record_type') or '').strip()
        return rt if rt in ('supervision', 'contractor') else 'supervision'

    @http.route(['/construction/<int:project_id>/defects/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_import(self, project_id, **kw):
        """缺失批次匯入頁（GET）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_defects',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'imported': int(kw.get('imported', 0) or 0),
            'skipped': int(kw.get('skipped', 0) or 0),
            'failed': int(kw.get('failed', 0) or 0),
            'error': kw.get('error') or '',
            'failed_details': request.session.pop(
                'defect_import_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_import', values)

    @http.route(['/construction/<int:project_id>/defects/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_import_submit(self, project_id, **post):
        """缺失批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_xlsm_parser import parse_defect_tracking_xlsx_verbose

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_IMPORT] POST entered, files count=%s', len(files))

        env = request.env
        base_url = f'/construction/{project_id}/defects/import'

        # 缺失編號需要工程層級的前綴設定，否則 _compute_defect_no 會 raise UserError
        # 導致每一列都失敗。整批擋下並給明確指示，比逐筆噴紅字有用。
        if not self._defect_prefix_configured(project):
            return request.redirect(f'{base_url}?error=no_prefix')

        Defect = env[self._defect_model(project)].sudo()
        supervision_project_id = project.id
        fallback_rt = self._defect_fallback_record_type(post)

        imported = 0
        skipped = 0
        failed = 0
        failed_details = []

        for upload in files:
            fname = upload.filename or 'unnamed.xlsx'
            try:
                raw = upload.read()
                rows, sheets_skipped = parse_defect_tracking_xlsx_verbose(
                    raw, filename=fname)
            except ValueError as e:
                failed += 1
                failed_details.append({'filename': fname, 'error': str(e)[:200]})
                continue
            except Exception as e:
                _logger.exception('[DEFECT_IMPORT] parse failed for %s', fname)
                failed += 1
                failed_details.append(
                    {'filename': fname, 'error': f'解析失敗：{e}'[:200]})
                continue

            # 被略過的工作表要講出來，不能靜默丟掉 —— 使用者才知道
            # 是「那張表本來就不是缺失表」還是「表頭沒被認出來」
            for sheet_name, why in sheets_skipped:
                failed_details.append({
                    'filename': fname,
                    'error': f'工作表「{sheet_name}」略過：{why}',
                })
            if rows:
                sheet_summary = ', '.join(sorted(
                    {r.get('sheet_name') or '?' for r in rows}))
                failed_details.append({
                    'filename': fname,
                    'error': f'已解析工作表：{sheet_summary}（共 {len(rows)} 筆）',
                })

            for row in rows:
                register_no = row.get('register_no') or ''
                description = row['description']
                found_date = row['found_date']
                deadline = row.get('deadline')
                improvement_date = row.get('improvement_date')

                try:
                    # duplicate check: (register_no + description) 或 (found_date + description)
                    existing = Defect.search([
                        ('project_id', '=', supervision_project_id),
                        ('found_date', '=', found_date),
                        ('defect_description', '=', description),
                    ], limit=1)
                    if existing:
                        skipped += 1
                        failed_details.append({
                            'filename': fname,
                            'error': (f'{register_no or found_date}: '
                                      f'{description[:30]} 已有紀錄 '
                                      f'(id={existing.id})，跳過'),
                        })
                        continue

                    # deadline 不可早於 found_date（model 有 constraint）
                    if deadline and found_date and deadline < found_date:
                        deadline = found_date

                    # 狀態：若有確認完成改善日期 → closed；否則 notified。
                    # 不用 draft —— general 的防竄改邏輯以離開草稿為界，
                    # 且匯入的歷史缺失本來就已經通知過了。
                    state = 'closed' if improvement_date else 'notified'

                    category = row.get('defect_category') or 'other'
                    vals = {
                        'project_id': supervision_project_id,
                        'record_type': resolve_record_type(
                            row, sheet_name=row.get('sheet_name'),
                            fallback=fallback_rt),
                        'defect_category': category,
                        'check_type': CATEGORY_TO_CHECK_TYPE.get(
                            category, 'construction'),
                        'source_type': 'daily_check',
                        'source_description': register_no,
                        'defect_description': description,
                        'found_date': found_date,
                        # 彙總表那欄就是「通知/改正日期」，一併帶入讓列表排序正確
                        'notification_date': found_date,
                        'deadline': deadline or False,
                        'state': state,
                    }
                    if row.get('note'):
                        vals['note'] = row['note']
                    if row.get('category_inferred'):
                        # 彙總表沒有「改正單位」欄，類別是由工作表名 QA/QR 推論的，
                        # 在備註留下痕跡，日後查得出來這欄不是原始資料
                        vals['note'] = ((vals.get('note') or '') +
                                        '\n（缺失類別由工作表名「%s」推論，'
                                        '原始彙總表無「改正單位」欄）'
                                        % row.get('sheet_name', '')).strip()
                    if improvement_date:
                        # general 的 improvement_date/closure_date 都是 Date，
                        # 不要再 datetime.combine 成 Datetime。
                        vals.update({
                            'improvement_date': improvement_date,
                            'improvement_result': (
                                '（總表單匯入，原始資料無詳細改善說明）'),
                            'closure_date': improvement_date,
                            'close_comment': '自總表單匯入，原紀錄已標記完成',
                        })

                    Defect.with_context(
                        tracking_disable=True,
                        mail_create_nolog=True,
                    ).create(vals)
                    imported += 1

                except Exception as e:
                    _logger.exception('[DEFECT_IMPORT] row create failed')
                    failed += 1
                    failed_details.append({
                        'filename': fname,
                        'error': (f'{register_no or found_date}: {e}')[:200],
                    })

        request.session['defect_import_failed_details'] = failed_details
        return request.redirect(
            f'{base_url}?imported={imported}&skipped={skipped}&failed={failed}')

    @http.route(['/construction/<int:project_id>/defects/enrich'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_enrich(self, project_id, **kw):
        """缺失改善明細補充頁（GET）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_defects',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'updated': int(kw.get('updated', 0) or 0),
            'unmatched': int(kw.get('unmatched', 0) or 0),
            'failed': int(kw.get('failed', 0) or 0),
            'error': kw.get('error') or '',
            'failed_details': request.session.pop(
                'defect_enrich_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_enrich', values)

    @http.route(['/construction/<int:project_id>/defects/enrich'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_enrich_submit(self, project_id, **post):
        """缺失改善明細補充提交（POST multipart，上傳 zip）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_docx_parser import (
            parse_defect_zip, build_defect_index, match_defect, docx_hint_text)

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_ENRICH] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env[self._defect_model(project)].sudo()
        base_url = f'/construction/{project_id}/defects/enrich'
        supervision_project_id = project.id

        # 建分層索引（登錄編號 → 編號推出的日期 → 發現日期），docx 那側也產生
        # 一組鍵，由精確到寬鬆逐層比對。這取代舊版「把檔名日期捏造成 Q01-xxx
        # 再做等值比對」的 A 標專屬做法。
        defects = Defect.search([('project_id', '=', supervision_project_id)])
        idx, ambiguous = build_defect_index(defects)

        updated = 0
        unmatched = 0
        failed = 0
        failed_details = []

        for upload in files:
            fname = upload.filename or 'unnamed.zip'
            try:
                raw = upload.read()
                parsed_rows = parse_defect_zip(raw)
            except Exception as e:
                _logger.exception('[DEFECT_ENRICH] zip parse failed for %s', fname)
                failed += 1
                failed_details.append(
                    {'filename': fname, 'error': f'ZIP 解析失敗：{e}'[:200]})
                continue

            for row in parsed_rows:
                inner_fn = row.get('filename', '')
                keys = row.get('match_keys') or []
                label = row.get('register_no') or (keys[0] if keys else inner_fn)
                if row.get('error'):
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': row['error'],
                    })
                    continue
                if not keys:
                    unmatched += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': '檔名推不出登錄編號也推不出日期，無從比對',
                    })
                    continue

                target, hit_ambiguous = match_defect(
                    keys, idx, ambiguous, hint=docx_hint_text(row))
                if not target:
                    unmatched += 1
                    if hit_ambiguous:
                        why = (f'比對鍵 {hit_ambiguous} 對應到多筆缺失，無法確定是哪一筆'
                               f'（該檔名沒有唯一登錄編號）')
                    else:
                        why = f'{"/".join(keys)} 無對應缺失紀錄'
                    failed_details.append({'filename': inner_fn, 'error': why})
                    continue

                try:
                    write_vals = {}
                    if row.get('improvement'):
                        write_vals['improvement_result'] = row['improvement']
                    if row.get('close_comment'):
                        write_vals['close_comment'] = row['close_comment']
                    if row.get('location') and not target.defect_location:
                        write_vals['defect_location'] = row['location']
                    if not write_vals:
                        unmatched += 1
                        failed_details.append({
                            'filename': inner_fn,
                            'error': f'{label}: 解析結果為空',
                        })
                        continue
                    target.with_context(
                        tracking_disable=True,
                        mail_create_nolog=True,
                    ).write(write_vals)
                    updated += 1
                except Exception as e:
                    _logger.exception('[DEFECT_ENRICH] update failed')
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': f'{label}: {e}'[:200],
                    })

        request.session['defect_enrich_failed_details'] = failed_details
        return request.redirect(
            f'{base_url}?updated={updated}&unmatched={unmatched}&failed={failed}')

    @http.route(['/construction/<int:project_id>/defects/import-docx'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_import_docx(self, project_id, **kw):
        """從 docx zip 直接建立缺失紀錄（沒有總表單的案場用）。"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_defects',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'imported': int(kw.get('imported', 0) or 0),
            'skipped': int(kw.get('skipped', 0) or 0),
            'failed': int(kw.get('failed', 0) or 0),
            'error': kw.get('error') or '',
            'failed_details': request.session.pop(
                'defect_create_docx_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_import_docx', values)

    @http.route(['/construction/<int:project_id>/defects/import-docx'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_import_docx_submit(self, project_id, **post):
        """從 docx zip 建立缺失紀錄提交。"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_docx_parser import parse_defect_zip

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_CREATE_DOCX] POST entered, files count=%s', len(files))

        env = request.env
        base_url = f'/construction/{project_id}/defects/import-docx'

        if not self._defect_prefix_configured(project):
            return request.redirect(f'{base_url}?error=no_prefix')

        Defect = env[self._defect_model(project)].sudo()
        supervision_project_id = project.id
        fallback_rt = self._defect_fallback_record_type(post)

        imported = 0
        skipped = 0
        failed = 0
        failed_details = []

        for upload in files:
            fname = upload.filename or 'unnamed.zip'
            try:
                raw = upload.read()
                parsed_rows = parse_defect_zip(raw)
            except Exception as e:
                _logger.exception('[DEFECT_CREATE_DOCX] zip parse failed')
                failed += 1
                failed_details.append(
                    {'filename': fname, 'error': f'ZIP 解析失敗：{e}'[:200]})
                continue

            for row in parsed_rows:
                inner_fn = row.get('filename', '')
                if row.get('error'):
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn, 'error': row['error']})
                    continue

                reg = row.get('register_no')
                found_date = row.get('found_date')
                description = row.get('description') or ''
                category = row.get('defect_category') or 'other'
                improvement = row.get('improvement') or ''
                close_comment = row.get('close_comment') or ''

                if not description or not found_date:
                    failed += 1
                    missing = []
                    if not description:
                        missing.append('缺失說明（docx 內文找不到「不符情形」或「缺失事項」）')
                    if not found_date:
                        missing.append(
                            '發現日期（檔名開頭沒有 7 位民國日期。'
                            '像 1-0803-…(QA-001).docx 只有月日沒有年份，'
                            '這種請先用「批次匯入總表單」建立缺失，再用「補充改善明細」補內容）')
                    failed_details.append({
                        'filename': inner_fn,
                        'error': '無法建立：' + '；'.join(missing),
                    })
                    continue

                # 每筆包 savepoint，單筆失敗不影響其它
                try:
                    with env.cr.savepoint():
                        existing = False
                        if reg:
                            existing = Defect.search([
                                ('project_id', '=', supervision_project_id),
                                ('source_description', '=', reg),
                                ('defect_description', '=', description),
                            ], limit=1)
                        if not existing:
                            existing = Defect.search([
                                ('project_id', '=', supervision_project_id),
                                ('found_date', '=', found_date),
                                ('defect_description', '=', description),
                            ], limit=1)
                        if existing:
                            skipped += 1
                            failed_details.append({
                                'filename': inner_fn,
                                'error': f'{reg or found_date}: 已有紀錄 id={existing.id}',
                            })
                            continue

                        state = 'closed' if close_comment else (
                            'improved' if improvement else 'notified')

                        vals = {
                            'project_id': supervision_project_id,
                            'record_type': resolve_record_type(
                                row, sheet_name=row.get('sheet_name'),
                                fallback=fallback_rt),
                            'defect_category': category,
                            # 內文的「☑施工抽查／□安衛、環境清潔」勾選比檔名括號可靠，
                            # 有抓到就用它，抓不到才由缺失類別反推
                            'check_type': (row.get('check_type')
                                           or CATEGORY_TO_CHECK_TYPE.get(
                                               category, 'construction')),
                            'source_type': 'daily_check',
                            'source_description': reg or '',
                            'defect_description': description,
                            'found_date': found_date,
                            'notification_date': found_date,
                            'state': state,
                        }
                        if row.get('location'):
                            vals['defect_location'] = row['location']
                        if improvement:
                            vals['improvement_result'] = improvement
                        if close_comment:
                            # closure_date 是 Date，直接給 date 物件
                            vals['close_comment'] = close_comment
                            vals['closure_date'] = found_date

                        Defect.with_context(
                            tracking_disable=True,
                            mail_create_nolog=True,
                        ).create(vals)
                        imported += 1

                except Exception as e:
                    _logger.exception('[DEFECT_CREATE_DOCX] create failed')
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': f'{reg or found_date}: {e}'[:200],
                    })

        request.session['defect_create_docx_failed_details'] = failed_details
        return request.redirect(
            f'{base_url}?imported={imported}&skipped={skipped}&failed={failed}')

    @http.route(['/construction/<int:project_id>/defects', '/construction/<int:project_id>/defects/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_defects(self, project_id, page=1, filterby=None, **kw):
        """缺失列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env[self._defect_model(project)]
        domain = [('project_id', '=', project.id)]

        # 篩選選項
        searchbar_filters = {
            'all': {'label': _('全部'), 'domain': []},
            'open': {'label': _('待處理'), 'domain': [('state', 'not in', ['verified', 'closed'])]},
            'closed': {'label': _('已結案'), 'domain': [('state', 'in', ['verified', 'closed'])]},
        }
        if not filterby:
            filterby = 'all'
        domain = AND([domain, searchbar_filters[filterby]['domain']])

        defect_count = Defect.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/defects',
            total=defect_count,
            page=page,
            step=self._items_per_page,
            url_args={'filterby': filterby},
        )

        defects = Defect.search(
            domain,
            order='create_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'project': project,
            'defects': defects,
            'defect_count': defect_count,
            'page_name': 'construction_defects',
            'pager': pager,
            'default_url': f'/construction/{project_id}/defects',
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_defects', values)

    @http.route(['/construction/<int:project_id>/defect/new'],
                type='http', auth='user', website=True)
    def portal_construction_defect_new(self, project_id, **kw):
        """新增缺失表單"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env[self._defect_model(project)]
        fields_info = Defect.fields_get(['defect_category', 'source_type'])
        type_options = fields_info['defect_category']['selection']
        source_options = fields_info['source_type']['selection']

        values = {
            'project': project,
            'type_options': type_options,
            'source_options': source_options,
            'page_name': 'construction_defect_new',
            'today': date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_defect_form', values)

    @http.route(['/construction/defect/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_defect_create(self, **post):
        """建立缺失"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：建立缺失限現場人員以上，閱覽角色不可寫入
        self._require_write(_('權限不足：閱覽角色不可建立缺失'))

        model = self._defect_model(project)
        # portal 反推：依所選缺失類別自動決定檢查類型（影響缺失編號首字 施/安）
        category = post.get('defect_type') or 'workmanship'
        vals = {
            'project_id': project_id,
            'defect_description': post.get('description', ''),
            'defect_location': post.get('location', ''),
            'defect_category': category,
            'check_type': CATEGORY_TO_CHECK_TYPE.get(category, 'construction'),
            'source_type': post.get('source') or 'daily_check',
            'found_date': post.get('found_date') or date.today().isoformat(),
            'deadline': post.get('deadline') or False,
        }

        Defect = request.env[model].sudo()
        defect = Defect.create(vals)

        # 處理照片上傳（建立缺失改善照片行，stage=before；
        # before_photo_ids 是 One2many 到照片行模型，不可用 attachment id link）
        _defect_save_photos(
            request.env, defect,
            request.httprequest.files.getlist('photo'), 'before')

        return request.redirect(f'/construction/defect/{defect.id}?message=created')

    @http.route(['/construction/defect/<int:defect_id>'],
                type='http', auth='user', website=True)
    def portal_construction_defect_detail(self, defect_id, **kw):
        """缺失詳情"""
        try:
            defect = self._browse_defect(defect_id, access_token=kw.get('access_token'))
        except (AccessError, MissingError):
            return request.redirect('/my')

        fields_info = defect.fields_get(['defect_category', 'source_type', 'state', 'responsible_party'])
        type_selection = dict(fields_info['defect_category']['selection'])
        source_selection = dict(fields_info['source_type']['selection'])
        state_selection = dict(fields_info['state']['selection'])
        party_selection = dict(fields_info['responsible_party']['selection'])

        values = {
            'defect': defect,
            'project': defect.project_id,
            'page_name': 'construction_defect_detail',
            'type_selection': type_selection,
            'source_selection': source_selection,
            'state_selection': state_selection,
            'party_selection': party_selection,
            'day_count': self._get_project_day_count(defect.project_id),
            'nav_badges': self._get_nav_badges(defect.project_id),
            # chatter
            'object': defect,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_defect_detail', values)

    @http.route(['/construction/defect/<int:defect_id>/improve'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_defect_improve(self, defect_id, **post):
        """提交缺失改善（改善說明、矯正措施、預防措施、改善後照片）"""
        partner = request.env.user.partner_id

        try:
            defect = self._browse_defect(defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：提交缺失改善限現場人員以上，閱覽角色不可寫入
        self._require_write(_('權限不足：閱覽角色不可提交缺失改善'))

        # 收齊文字欄位
        improvement_text = post.get('improvement_description', '').strip()
        corrective_action = post.get('corrective_action', '').strip()
        preventive_action = post.get('preventive_action', '').strip()

        # 收改善後照片（建立照片行 stage=after；after_photo_ids 為 One2many
        # 到照片行模型，不可用 attachment id link，否則 MissingError）
        _defect_save_photos(
            request.env, defect,
            request.httprequest.files.getlist('after_photo'), 'after')

        if hasattr(defect, 'portal_submit_improvement'):
            defect.portal_submit_improvement(
                improvement_text, partner,
                corrective_action=corrective_action or None,
                preventive_action=preventive_action or None,
            )
        else:
            # 一般式/預約式：直接寫入改善文字欄位（照片已建立照片行）
            wvals = {}
            if improvement_text:
                wvals['improvement_result'] = improvement_text
            if corrective_action:
                wvals['improvement_action'] = corrective_action
            if wvals:
                defect.sudo().write(wvals)

        # 提交改善即推進狀態（notified → improving → improved），讓監造的「驗證」按鈕出現
        defect_sudo = defect.sudo()
        if defect_sudo.state in ('notified', 'improving'):
            try:
                if defect_sudo.state == 'notified':
                    defect_sudo.action_start_improvement()
                if defect_sudo.state == 'improving':
                    defect_sudo.action_complete_improvement()
            except (UserError, ValidationError) as e:
                from urllib.parse import quote
                return request.redirect(
                    f'/construction/defect/{defect_id}?error={quote(str(e))}')

        return request.redirect(f'/construction/defect/{defect_id}?message=success')

    @http.route(['/construction/defect/<int:defect_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_defect_photo_upload(self, defect_id, **post):
        """缺失照片上傳（任何狀態皆可，draft 缺失也能加照片）。

        修復月月真琴回報「缺失改善照片都無法上傳」：原本只有 notified/improving
        狀態的改善表單能上傳，draft 缺失完全沒有上傳入口。此路由不限狀態。
        依缺失狀態決定 photo_stage：improved/verified/closed→after、improving→during、
        其餘(draft/notified)→before；可由 stage 參數覆寫。
        """
        try:
            defect = self._browse_defect(defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：追加缺失照片限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        stage = post.get('stage')
        if stage not in ('before', 'during', 'after'):
            if defect.state in ('improved', 'verified', 'closed'):
                stage = 'after'
            elif defect.state == 'improving':
                stage = 'during'
            else:
                stage = 'before'
        _defect_save_photos(
            request.env, defect,
            request.httprequest.files.getlist('photos'), stage)
        return request.redirect(f'/construction/defect/{defect_id}?message=photo_added')

    @http.route(['/construction/defect/<int:defect_id>/verify'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_defect_verify(self, defect_id, **post):
        """缺失：驗證改善（improved → verified）"""
        try:
            defect = self._browse_defect(defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._run_review_action(
            defect, 'action_verify_pass',
            f'/construction/defect/{defect_id}', f'/construction/defect/{defect_id}')

    @http.route(['/construction/defect/<int:defect_id>/close'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_defect_close(self, defect_id, **post):
        """缺失：結案（verified → closed）"""
        try:
            defect = self._browse_defect(defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._run_review_action(
            defect, 'action_close',
            f'/construction/defect/{defect_id}', f'/construction/defect/{defect_id}')

    @http.route(['/construction/defect/<int:defect_id>/notify'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_defect_notify(self, defect_id, **post):
        """缺失：通知改善（draft → notified）。限老闆/主管。"""
        try:
            defect = self._browse_defect(defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return self._run_review_action(
            defect, 'action_notify',
            f'/construction/defect/{defect_id}', f'/construction/defect/{defect_id}')
