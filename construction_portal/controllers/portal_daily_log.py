# -*- coding: utf-8 -*-
"""M4-a：DailyLogRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

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


class DailyLogRoutesMixin:
    @http.route(['/construction/<int:project_id>/daily-logs', '/construction/<int:project_id>/daily-logs/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_daily_logs(self, project_id, page=1, **kw):
        """施工日誌列表"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        domain = [('supervision_project_id', '=', project.id)]

        log_count = DailyLog.search_count(domain)
        pager = portal_pager(
            url=f'/construction/{project_id}/daily-logs',
            total=log_count,
            page=page,
            step=self._items_per_page,
        )

        logs = DailyLog.search(
            domain,
            order='log_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        # Alert 資料（本週目標 + 待處理缺失 + 待完成檢查）
        today = date.today()
        week_start_dt = today - timedelta(days=today.weekday())
        week_target = ''
        week_range = f'{week_start_dt.strftime("%Y/%m/%d")} — {(week_start_dt + timedelta(days=6)).strftime("%m/%d")}'
        try:
            schedule = request.env['construction.weekly.schedule'].search([
                ('supervision_project_id', '=', project.id),
                ('week_start', '<=', today),
                ('week_end', '>=', today),
            ], limit=1)
            if schedule:
                task_names = [l.task_name or l.task_id.name for l in schedule.line_ids if l.task_name or l.task_id]
                week_target = ' + '.join(task_names[:3])
        except Exception:
            pass

        open_defects = request.env[self._defect_model(project)].search([
            ('project_id', '=', project.id),
            ('state', 'not in', ['verified', 'closed']),
        ], limit=10)
        draft_inspections = request.env['general.self.inspection'].search([
            ('project_id', '=', project.id),
            ('state', '=', 'draft'),
        ], limit=10)

        # 本週日曆
        weather_emoji = {'sunny': '☀', 'cloudy': '⛅', 'overcast': '☁', 'rainy': '🌧', 'heavy_rain': '⛈', 'typhoon': '🌀', 'foggy': '🌫'}
        log_days = []
        weekday_names = ['一', '二', '三', '四', '五', '六', '日']
        for i in range(7):
            d = week_start_dt + timedelta(days=i)
            day_log = DailyLog.search([
                ('supervision_project_id', '=', project.id),
                ('log_date', '=', d),
            ], limit=1)
            status = 'off' if i >= 6 else ('today' if d == today else ('filled' if day_log else 'empty'))
            weather_str = ''
            if day_log and day_log.weather_am:
                w_am = weather_emoji.get(day_log.weather_am, '')
                w_pm = weather_emoji.get(day_log.weather_pm, '') if day_log.weather_pm else ''
                weather_str = f'{w_am}/{w_pm}' if w_pm else w_am
            log_days.append({
                'date': d.strftime('%m/%d'),
                'date_full': d.isoformat(),
                'weekday': weekday_names[i],
                'status': status,
                'weather': weather_str,
                'items': len(day_log.line_ids) if day_log else 0,
            })

        values = {
            'project': project,
            'logs': logs,
            'page_name': 'construction_daily_logs',
            'pager': pager,
            'default_url': f'/construction/{project_id}/daily-logs',
            # Alert 資料
            'week_target': week_target,
            'week_range': week_range,
            'open_defects': open_defects,
            'draft_inspections': draft_inspections,
            # 本週日曆
            'log_days': log_days,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_daily_logs', values)

    @http.route(['/construction/<int:project_id>/daily-log/<int:log_id>'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_detail(self, project_id, log_id, **kw):
        """施工日誌詳情"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/construction/{project_id}/daily-logs')

        # 天氣 Selection 選項（從 fields_get 拉）
        weather_selection = dict(
            DailyLog.fields_get(['weather_am'])['weather_am']['selection']
        )

        photo_categories = _photo_category_options(request.env)

        # daily.log.line _inherits account.analytic.line，timesheet ir.rule 會擋到 line_ids
        # 用 sudo 預讀 + SimpleNamespace 包裝（QWeb 才能用 dot-access）
        from types import SimpleNamespace
        log_su = log.sudo()
        log_lines = []
        for ln in log_su.line_ids:
            log_lines.append(SimpleNamespace(
                id=ln.id,
                entry_type=ln.entry_type or 'contract',
                custom_name=ln.custom_name or '',
                item_no=ln.item_no or '',
                item_name=ln.item_name or ln.custom_name or (ln.work_item_id.name if ln.work_item_id else ''),
                unit=ln.unit or '',
                contract_qty=ln.contract_qty or 0.0,
                daily_qty=ln.daily_qty or 0.0,
                cumulative_qty=ln.cumulative_qty or 0.0,
                completion_rate=ln.completion_rate or 0.0,
                is_over_contract=ln.is_over_contract or False,
                location=ln.location or '',
                work_description=ln.work_description or '',
                has_issue=ln.has_issue or False,
                issue_description=ln.issue_description or '',
            ))
        log_materials = []
        for mat in log_su.material_ids:
            log_materials.append(SimpleNamespace(
                id=mat.id,
                name=mat.name or '',
                unit=mat.unit or '',
                contract_qty=mat.contract_qty or 0.0,
                daily_qty=mat.daily_qty or 0.0,
                cumulative_qty=mat.cumulative_qty or 0.0,
                note=mat.note or '',
            ))
        log_specific_items = []
        for spec in log_su.specific_item_ids:
            log_specific_items.append(SimpleNamespace(
                id=spec.id,
                name=spec.name or '',
                unit=spec.unit or '',
                contract_qty=spec.contract_qty or 0.0,
                daily_qty=spec.daily_qty or 0.0,
                cumulative_qty=spec.cumulative_qty or 0.0,
                note=spec.note or '',
            ))
        values = {
            'project': project,
            'log': log,
            'log_lines': log_lines,
            'log_materials': log_materials,
            'log_specific_items': log_specific_items,
            'weather_selection': weather_selection,
            'page_name': 'construction_daily_log_detail',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            # 照片區塊變數
            # ⚠️ 這裡要送 ir.attachment 不是 supervision.photo。
            # 照片收斂（2B）後 photo_ids 從 M2M→ir.attachment 變成
            # One2many→supervision.photo，但共用區塊 portal_construction_photos_block
            # 與 _portal_photo_to_supervision() 的契約仍是 ir.attachment：
            # 區塊用 att.id 組 /construction/img/<att_id> 與刪除網址。
            # 直接送照片記錄的話 att.id 會是「照片 id」被當成「附件 id」用 —— 症狀是
            # 縮圖 404 破圖、詳情連結指向 /construction/photo/0、刪除鈕靜默失效。
            'photos': log.photo_ids.attachment_id,
            'photo_to_supervision': _portal_photo_to_supervision(
                request.env, log.photo_ids.attachment_id),
            'photo_categories': photo_categories,
            'upload_url': f'/construction/daily-log/{log.id}/photo/upload',
            'delete_url_tpl': f'/construction/daily-log/{log.id}/photo/%s/delete',
            'is_locked': log.is_locked,
            # chatter
            'object': log,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_daily_log_detail', values)

    @http.route(['/construction/<int:project_id>/daily-logs/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_daily_logs_import(self, project_id, **kw):
        """施工日誌批次匯入頁（GET）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_daily_logs',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'imported': int(kw.get('imported', 0) or 0),
            'skipped': int(kw.get('skipped', 0) or 0),
            'failed': int(kw.get('failed', 0) or 0),
            'failed_details': request.session.pop('daily_log_import_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_daily_log_import', values
        )

    @http.route(['/construction/<int:project_id>/daily-logs/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_daily_logs_import_submit(self, project_id, **post):
        """施工日誌批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.daily_log_xlsm_parser import parse_daily_log_xlsm
        from ..utils.daily_log_b_xlsx_parser import parse_daily_log_b_xlsx

        files = request.httprequest.files.getlist('files')
        _logger.warning('[IMPORT] POST handler entered, files count=%s, post keys=%s',
                        len(files), list(post.keys()))
        imported = 0
        skipped = 0
        failed = 0
        failed_details = []

        env = request.env
        DailyLog = env['daily.log.sheet'].sudo()
        ProjectTask = env['project.task'].sudo()
        base_url = f'/construction/{project_id}/daily-logs/import'
        project_record_id = project.id
        supervision_project_id = project.id

        for f in files:
            fname = f.filename if f and f.filename else '(unknown)'
            try:
                raw = f.read() if f else b''
                if not raw:
                    failed += 1
                    failed_details.append({'filename': fname, 'error': '檔案為空'})
                    continue

                # 先試 A 標格式（sheet '施工日誌'），失敗退回 B 標（sheet '日報'）
                try:
                    parsed = parse_daily_log_xlsm(raw, filename=fname)
                except ValueError as _e:
                    if '缺少「施工日誌」' in str(_e) or '缺少 日報' in str(_e):
                        parsed = parse_daily_log_b_xlsx(raw, filename=fname)
                    else:
                        raise

                # 日期重複檢查
                existing = DailyLog.search([
                    ('supervision_project_id', '=', supervision_project_id),
                    ('log_date', '=', parsed['log_date']),
                ], limit=1)
                if existing:
                    skipped += 1
                    failed_details.append({
                        'filename': fname,
                        'error': f"{parsed['log_date']} 已有日誌 (id={existing.id})，跳過",
                    })
                    continue

                # 解析工項行 → 對應 / 建立 stub project.task
                line_cmds = []
                for lr in parsed['line_rows']:
                    task_name = lr['name']
                    if not task_name:
                        continue
                    task = ProjectTask.search([
                        ('project_id', '=', project_record_id),
                        ('name', '=', task_name),
                    ], limit=1)
                    if not task:
                        task = ProjectTask.with_context(
                            tracking_disable=True, mail_create_nolog=True
                        ).create({
                            'name': task_name,
                            'project_id': project_record_id,
                            'unit': lr['unit'] or '式',
                            'planned_qty': lr['planned_qty'] or 0.0,
                            'unit_price': 0.0,
                        })
                    line_cmds.append((0, 0, {
                        'work_item_id': task.id,
                        'daily_qty': lr['daily_qty'] or 0.0,
                        'work_description': lr.get('note') or '',
                    }))

                # 材料行（daily.log.material 欄位：name / unit / contract_qty / daily_qty / cumulative_qty / note）
                material_cmds = []
                for mr in parsed['material_rows']:
                    if not mr['name']:
                        continue
                    material_cmds.append((0, 0, {
                        'name': mr['name'],
                        'unit': mr['unit'] or '',
                        'contract_qty': mr['contract_qty'] or 0.0,
                        'daily_qty': mr['daily_qty'] or 0.0,
                        'cumulative_qty': mr['cumulative_qty'] or 0.0,
                        'note': mr.get('note') or '',
                    }))

                sheet_vals = {
                    'supervision_project_id': supervision_project_id,
                    'log_date': parsed['log_date'],
                    'weather_am': parsed['weather_am'] or False,
                    'weather_pm': parsed['weather_pm'] or False,
                    'actual_progress': parsed.get('actual_progress') or 0.0,
                    'has_technician_requirement': parsed['has_technician_requirement'] or False,
                    'safety_pre_work_education': parsed.get('safety_pre_work_education') or False,
                    'safety_labor_insurance_check': parsed.get('safety_labor_insurance_check') or False,
                    'safety_ppe_check': parsed.get('safety_ppe_check') or False,
                    'safety_other_matters': parsed['safety_other_matters'] or '',
                    'sampling_test_record': parsed['sampling_test_record'] or '',
                    'subcontractor_notification': parsed['subcontractor_notification'] or '',
                    'important_matters': parsed['important_matters'] or '',
                    'line_ids': line_cmds,
                }
                if material_cmds:
                    sheet_vals['material_ids'] = material_cmds

                DailyLog.with_context(
                    allowed_company_ids=[project.company_id.id],
                    company_id=project.company_id.id,
                    tracking_disable=True,
                    mail_create_nolog=True,
                ).create(sheet_vals)
                imported += 1

            except ValueError as e:
                failed += 1
                failed_details.append({'filename': fname, 'error': str(e)[:200]})
                _logger.warning('daily log import parse failed: %s: %s', fname, e)
            except (ValidationError, UserError) as e:
                failed += 1
                failed_details.append({'filename': fname, 'error': str(e)[:200]})
                _logger.warning('daily log import write failed: %s: %s', fname, e)
            except Exception as e:
                failed += 1
                failed_details.append({'filename': fname, 'error': f'{type(e).__name__}: {e}'[:200]})
                _logger.exception('daily log import unexpected error: %s', fname)

        if failed_details:
            request.session['daily_log_import_failed_details'] = failed_details

        return request.redirect(
            f'{base_url}?imported={imported}&skipped={skipped}&failed={failed}'
        )

    @http.route(['/construction/<int:project_id>/daily-log/new'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_new(self, project_id, **kw):
        """新增施工日誌表單"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']

        # 天氣 Selection 選項
        weather_selection = DailyLog.fields_get(['weather_am'])['weather_am']['selection']

        # 工項列表（只取最細項，非彙總項）— 用 sudo() 避免 Portal 權限問題
        tasks = request.env['project.task'].sudo().search([
            ('project_id', '=', project.id),
            ('is_summary_item', '=', False),
            ('active', '=', True),
        ], order='sequence, item_no')

        # 天氣 emoji 映射
        weather_emoji = {'sunny': '☀', 'cloudy': '⛅', 'overcast': '☁', 'rainy': '🌧', 'heavy_rain': '⛈', 'typhoon': '🌀', 'foggy': '🌫'}

        photo_categories = _photo_category_options(request.env)

        values = {
            'project': project,
            'weather_options': weather_selection,
            'weather_emoji': weather_emoji,
            'tasks': tasks,
            'photo_categories': photo_categories,
            'is_edit': False,
            'log': False,
            'form_action': '/construction/daily-log/create',
            'page_name': 'construction_daily_log_new',
            'today': date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_daily_log_form', values)

    @http.route(['/construction/daily-log/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_create(self, **post):
        """建立施工日誌"""
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：建立施工日誌限現場人員以上，閱覽角色不可寫入
        self._require_write(_('權限不足：閱覽角色不可建立施工日誌'))

        # 基本欄位
        vals = {
            'supervision_project_id': project.id,
            'log_date': post.get('log_date') or date.today().isoformat(),
            'weather_am': post.get('weather_am') or False,
            'weather_pm': post.get('weather_pm') or False,
            'work_summary': post.get('work_summary', ''),
            'safety_pre_work_education': post.get('safety_pre_work_education') or False,
            'safety_labor_insurance_check': post.get('safety_labor_insurance_check') or False,
            'safety_ppe_check': post.get('safety_ppe_check') or False,
            'has_technician_requirement': post.get('has_technician_requirement') or False,
            'safety_other_matters': post.get('safety_other_matters', ''),
            'sampling_test_record': post.get('sampling_test_record', ''),
            'subcontractor_notification': post.get('subcontractor_notification', ''),
            'important_matters': post.get('important_matters', ''),
            'notes': post.get('notes', ''),
        }

        # 通報單連結（預約式）
        slip_id = post.get('notification_slip_id')
        if slip_id:
            vals['notification_slip_id'] = int(slip_id)

        DailyLog = request.env['daily.log.sheet'].sudo()
        log = DailyLog.create(vals)

        # 處理工項明細（line_ids）：支援「契約工項」與「自填項目（純文字）」
        # 排序由 daily.log.line.type_order 決定（契約恆在自填之前），與建立先後無關。
        line_index = 0
        while True:
            entry_type = post.get(f'line_entry_type_{line_index}')
            work_item_id = post.get(f'line_work_item_id_{line_index}')
            custom_name = post.get(f'line_custom_name_{line_index}')
            # 三個 key 都不存在 → 沒有更多明細列
            if entry_type is None and work_item_id is None and custom_name is None:
                break

            location = post.get(f'line_location_{line_index}', '')
            work_desc = post.get(f'line_work_description_{line_index}', '')
            has_issue = post.get(f'line_has_issue_{line_index}') == 'on'
            issue_desc = post.get(f'line_issue_description_{line_index}', '')

            if (entry_type or 'contract') == 'extra':
                # 自填項目：純文字，不登記為契約工項
                name = (custom_name or '').strip()
                if name:
                    request.env['daily.log.line'].sudo().create({
                        'sheet_id': log.id,
                        'entry_type': 'extra',
                        'custom_name': name,
                        'name': f'施工記錄 - {name}',
                        'location': location,
                        'work_description': work_desc,
                        'has_issue': has_issue,
                        'issue_description': issue_desc if has_issue else '',
                    })
            else:
                # 契約工項
                if work_item_id and str(work_item_id).isdigit():
                    daily_qty = post.get(f'line_daily_qty_{line_index}', '0')
                    request.env['daily.log.line'].sudo().create({
                        'sheet_id': log.id,
                        'entry_type': 'contract',
                        'work_item_id': int(work_item_id),
                        'daily_qty': float(daily_qty) if daily_qty else 0.0,
                        'location': location,
                        'work_description': work_desc,
                        'has_issue': has_issue,
                        'issue_description': issue_desc if has_issue else '',
                    })

            line_index += 1

        # 處理上傳照片(統一走 helper,直建 supervision.photo)
        # 三個描述欄位走 _post_photo_meta()：本表單送 photo_ 前綴的欄位名，
        # 共用片段 cy_photo_meta_fields 送不帶前綴的，該 helper 兩套都收。
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'daily_log',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
        })
        _portal_save_photos(
            request.env,
            log,
            project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/construction/{project_id}/daily-log/{log.id}?message=created'
        )

    @http.route(['/construction/<int:project_id>/daily-log/<int:log_id>/edit'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_edit(self, project_id, log_id, **kw):
        """編輯施工日誌(共用 form 模板)"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/construction/{project_id}/daily-logs')
        if log.is_locked:
            return request.redirect(
                f'/construction/{project_id}/daily-log/{log.id}?error=locked'
            )

        weather_selection = DailyLog.fields_get(['weather_am'])['weather_am']['selection']
        weather_emoji = {'sunny': '☀', 'cloudy': '⛅', 'overcast': '☁', 'rainy': '🌧', 'heavy_rain': '⛈', 'typhoon': '🌀', 'foggy': '🌫'}

        tasks = request.env['project.task'].sudo().search([
            ('project_id', '=', project.id),
            ('is_summary_item', '=', False),
            ('active', '=', True),
        ], order='sequence, item_no')

        photo_categories = _photo_category_options(request.env)

        values = {
            'project': project,
            'log': log,
            'weather_options': weather_selection,
            'weather_emoji': weather_emoji,
            'tasks': tasks,
            'photo_categories': photo_categories,
            'is_edit': True,
            'form_action': f'/construction/{project_id}/daily-log/{log.id}/update',
            'page_name': 'construction_daily_log_edit',
            'today': log.log_date.isoformat() if log.log_date else date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_daily_log_form', values)

    @http.route(['/construction/<int:project_id>/daily-log/<int:log_id>/unlock'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_daily_log_unlock(self, project_id, log_id, **post):
        """前台解鎖已鎖定日誌（限老闆/主管/代操，限時 3 天）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        log = request.env['daily.log.sheet'].search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/construction/{project_id}/daily-logs')
        if not log.can_unlock:
            return request.redirect(
                f'/construction/{project_id}/daily-log/{log.id}?error=no_unlock_permission')
        log.sudo().portal_unlock(hours=72, reason='前台解鎖')
        return request.redirect(
            f'/construction/{project_id}/daily-log/{log.id}?message=unlocked')

    @http.route(['/construction/<int:project_id>/daily-log/<int:log_id>/update'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_update(self, project_id, log_id, **post):
        """更新施工日誌(編輯儲存)"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet'].sudo()
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/construction/{project_id}/daily-logs')
        if log.is_locked:
            return request.redirect(
                f'/construction/{project_id}/daily-log/{log.id}?error=locked'
            )

        # 角色 guard：現場人員只能編輯自己建立的日誌（老闆/主管不受限）
        try:
            self._require_owner_or_manager(log)
        except AccessError:
            return request.redirect(
                f'/construction/{project_id}/daily-log/{log.id}?error=not_owner'
            )

        log.write({
            'log_date': post.get('log_date') or log.log_date,
            'weather_am': post.get('weather_am') or False,
            'weather_pm': post.get('weather_pm') or False,
            'work_summary': post.get('work_summary', ''),
            'safety_pre_work_education': post.get('safety_pre_work_education') or False,
            'safety_labor_insurance_check': post.get('safety_labor_insurance_check') or False,
            'safety_ppe_check': post.get('safety_ppe_check') or False,
            'has_technician_requirement': post.get('has_technician_requirement') or False,
            'safety_other_matters': post.get('safety_other_matters', ''),
            'sampling_test_record': post.get('sampling_test_record', ''),
            'subcontractor_notification': post.get('subcontractor_notification', ''),
            'important_matters': post.get('important_matters', ''),
            'notes': post.get('notes', ''),
        })

        # 編輯時若有上傳新照片
        meta = _post_photo_meta(post)
        meta.update({
            'source_model': 'daily_log',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
        })
        _portal_save_photos(
            request.env, log, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/construction/{project_id}/daily-log/{log.id}?message=updated'
        )

    @http.route(['/construction/<int:project_id>/daily-log/<int:log_id>/mark-filled'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_daily_log_mark_filled(self, project_id, log_id, **post):
        """施工日誌：鎖定/定稿（draft → filled）"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        log = request.env['daily.log.sheet'].search(
            [('id', '=', log_id), ('supervision_project_id', '=', project.id)], limit=1)
        return self._run_review_action(
            log, 'action_mark_filled',
            f'/construction/{project_id}/daily-log/{log_id}', f'/construction/{project_id}/daily-log/{log_id}')
