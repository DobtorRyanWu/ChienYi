# -*- coding: utf-8 -*-
"""M4-a：DailyLogRoutesMixin —— 從 portal.py 抽出的路由（plain mixin，由 ConstructionPortal 合併）。"""

import base64
import json
import logging
import re
from datetime import date, datetime, timedelta

from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.construction_quality.models.defect_constants import CATEGORY_TO_CHECK_TYPE
from odoo.addons.construction_daily_log.models.daily_log_material import MAX_MATERIAL_DAILY_QTY
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.osv.expression import AND
from werkzeug.exceptions import NotFound

# 這三支 mixin 都是從 portal.py 抽出來的，_logger 沒跟著搬過來——
# 而用到它的地方全在 except 區塊裡，於是「記錄錯誤」自己炸成 NameError，
# 把原始錯誤蓋掉並回 500。2026-09-10 補上。
_logger = logging.getLogger(__name__)

from .portal_utils import (
    GROUP_BOSS, GROUP_MANAGER, GROUP_FIELD, GROUP_OBSERVER, GROUP_OPERATOR,
    _photo_category_options, _photo_category_to_id, _post_photo_meta,
    _portal_save_photos,
    _defect_save_photos, _portal_delete_photo, _portal_photo_to_supervision,
    _haversine_km,
)


# 前台「工地材料（約定重要材料）」本日數量欄位的名稱前綴：
#   新增：key_material_qty_<契約材料清單項 id>；編輯：material_qty_<材料列 id>
KEY_MATERIAL_QTY_PREFIX = 'key_material_qty_'
MATERIAL_QTY_PREFIX = 'material_qty_'
# id 只認 ASCII 數字、長度有上限（str.isdigit() 會把「²」當數字，int() 再丟例外 → 500）
MATERIAL_ID_RE = re.compile(r'[0-9]{1,12}')


def _parse_material_qtys(post, prefix):
    """從 POST 取出 {id: 數量}。空字串＝0（編輯時把數量清空要真的歸零）；
    負數、非數字、nan/inf、超過上限、不是文字（multipart 檔案欄位）回 None。"""
    qtys = {}
    for key, raw in post.items():
        if not key.startswith(prefix) or not MATERIAL_ID_RE.fullmatch(key[len(prefix):]):
            continue
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        try:
            qty = float(text) if text else 0.0
        except ValueError:
            return None
        # NaN 的比較一律為 False、inf 超過上限，都會被這一行擋下
        if not 0 <= qty <= MAX_MATERIAL_DAILY_QTY:
            return None
        qtys[int(key[len(prefix):])] = qty
    return qtys


class DailyLogRoutesMixin:
    def _daily_log_form_materials(self, project, log=None):
        """表單用的材料清單（唯讀欄位 + 一個本日數量輸入）。

        新增（log 為空）：該案啟用中的重要材料，輸入欄名 key_material_qty_<清單項 id>，
        累計顯示「已累計（不含本日）」＝既有日誌該材料 daily_qty 總和。
        編輯：這張日誌「已連結契約材料」的列，輸入欄 material_qty_<列 id>。沒連結的人工列不列在這一節
        （詳情頁照常顯示）：沒有契約材料清單的案件（例如任泰）編輯頁不會多出這一節。
        """
        from types import SimpleNamespace
        if not log:
            items = request.env['construction.contract.material'].sudo().search([
                ('project_id', '=', project.id),
                ('is_key', '=', True),
                ('active', '=', True),
            ])
            totals = {}
            if items:
                groups = request.env['daily.log.material'].sudo()._read_group(
                    [('catalog_item_id', 'in', items.ids)],
                    ['catalog_item_id'], ['daily_qty:sum'])
                totals = {item.id: total for item, total in groups}
            return [SimpleNamespace(
                name=i.name or '', unit=i.unit or '',
                contract_qty=i.contract_qty or 0.0,
                cumulative_qty=totals.get(i.id, 0.0), daily_qty=0.0,
                input_name='%s%s' % (KEY_MATERIAL_QTY_PREFIX, i.id),
            ) for i in items]
        return [SimpleNamespace(
            name=m.name or '', unit=m.unit or '',
            contract_qty=m.contract_qty or 0.0,
            cumulative_qty=m.cumulative_qty or 0.0, daily_qty=m.daily_qty or 0.0,
            input_name='%s%s' % (MATERIAL_QTY_PREFIX, m.id),
        ) for m in log.sudo().material_ids.filtered('catalog_item_id')]

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
                    # 歷史日誌匯入：材料照 xlsm 原樣（人工列，帶實際數量），不再補 0 數量的重要材料列
                    skip_key_material_autofill=True,
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
            'form_materials': self._daily_log_form_materials(project),
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

        # 約定重要材料的本日數量：先驗證，數字不合法就不建日誌
        key_qtys = _parse_material_qtys(post, KEY_MATERIAL_QTY_PREFIX)
        if key_qtys is None:
            return request.redirect(
                f'/construction/{project_id}/daily-log/new?error=invalid_qty')

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

        # 約定重要材料本日數量：create() 已依案件清單自動帶入材料列，這裡只填數量。
        # 只認「這張日誌自己、對應到該清單項」的列（外來的清單項 id 找不到列就略過）。
        # 直接寫材料列而不經 log.write()：建立日誌本來就不受 14 天鎖定限制（補登舊日期），
        # 與下面工項明細的建立方式一致。
        if key_qtys:
            for row in log.material_ids.filtered(
                    lambda m: m.catalog_item_id.id in key_qtys):
                row.write({'daily_qty': key_qtys[row.catalog_item_id.id]})

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
            'form_materials': self._daily_log_form_materials(project, log),
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

        # H1：閱覽角色不可寫入。_is_field_only() 對閱覽者回 False，下面的
        # _require_owner_or_manager 不會擋他，所以要在這裡先擋（create 路由同寫法）。
        self._require_write(_('權限不足：閱覽角色不可修改施工日誌'))

        DailyLog = request.env['daily.log.sheet'].sudo()
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/construction/{project_id}/daily-logs')
        # 鎖定用即時判斷：stored is_locked 會 stale（H2）。下面的 log.write() 也會擋（材料指令併在同一次
        # write 裡），這裡先擋是為了導回提示頁，而不是讓 write() 的 UserError 變成 500
        if log._is_edit_locked():
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

        # 約定重要材料本日數量。只接受「這張日誌自己、已連結契約材料」的列 id：
        # Odoo 18 的 (1, id, vals) 指令不檢查 id 是否屬於父記錄，偽造別張日誌的列 id
        # 會在 sudo 下直接寫到別張。數字不合法就整筆不寫。
        material_qtys = _parse_material_qtys(post, MATERIAL_QTY_PREFIX)
        if material_qtys is None:
            # 導回編輯頁（表單有 invalid_qty 提示）；整筆未儲存
            return request.redirect(
                f'/construction/{project_id}/daily-log/{log.id}/edit?error=invalid_qty'
            )
        own_linked_ids = set(log.material_ids.filtered('catalog_item_id').ids)
        material_cmds = [
            (1, row_id, {'daily_qty': qty})
            for row_id, qty in material_qtys.items() if row_id in own_linked_ids
        ]

        vals = {
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
        }
        if material_cmds:
            # 併進同一次 write：14 天鎖定在 write() 判斷，材料指令也要被它擋得到
            vals['material_ids'] = material_cmds
        log.write(vals)

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
