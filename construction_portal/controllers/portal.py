# -*- coding: utf-8 -*-

import base64
import json
import logging
import math
from datetime import date, datetime, timedelta
from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.osv.expression import AND

_logger = logging.getLogger(__name__)


def _portal_save_photos(env, record, supervision_project, files, meta):
    """把 multipart 上傳檔案存成 ir.attachment + supervision.photo,並 link 到 record.photo_ids

    繞過 photo.sync.mixin(對 daily.log.sheet 因 project_id 型別錯誤而失效),
    直接寫入正確的 supervision.project.id。

    files: list of werkzeug FileStorage(來自 request.httprequest.files.getlist('photos'))
    meta: dict 含 description / category / source_model / latitude / longitude / location_description
    回傳: 新增的 attachment id list
    """
    Attachment = env['ir.attachment'].sudo()
    Photo = env['supervision.photo'].sudo()
    new_atts = []
    try:
        lat = float(meta.get('latitude') or 0)
    except (TypeError, ValueError):
        lat = 0.0
    try:
        lng = float(meta.get('longitude') or 0)
    except (TypeError, ValueError):
        lng = 0.0
    description = meta.get('description') or ''
    category = meta.get('category') or False
    source_model = meta.get('source_model') or 'other'
    location_description = meta.get('location_description') or ''

    for f in files:
        if not f or not f.filename:
            continue
        data = f.read()
        if not data:
            continue
        att = Attachment.create({
            'name': f.filename,
            'datas': base64.b64encode(data),
            'res_model': record._name,
            'res_id': record.id,
            'mimetype': f.mimetype or 'image/jpeg',
        })
        # 直接建 supervision.photo,不依賴 mixin
        if not Photo.search([('attachment_id', '=', att.id)], limit=1):
            Photo.create({
                'project_id': supervision_project.id,
                'attachment_id': att.id,
                'description': description or f.filename,
                'category': category,
                'source_model': source_model,
                'source_id': record.id,
                'shot_at': fields.Datetime.now(),
                'latitude': lat,
                'longitude': lng,
                'location_description': location_description,
            })
        new_atts.append(att.id)

    if new_atts:
        record.sudo().write({'photo_ids': [(4, aid) for aid in new_atts]})
    return new_atts


def _portal_delete_photo(env, record, attachment_id):
    """從 record.photo_ids 移除一張 + 同步刪 supervision.photo + ir.attachment"""
    record.sudo().write({'photo_ids': [(3, attachment_id)]})
    env['supervision.photo'].sudo().search([
        ('attachment_id', '=', attachment_id),
    ]).unlink()
    env['ir.attachment'].sudo().browse(attachment_id).unlink()


def _portal_photo_to_supervision(env, attachments):
    """給 detail 頁用:回傳 {attachment_id: supervision_photo_id} dict"""
    if not attachments:
        return {}
    photos = env['supervision.photo'].sudo().search([
        ('attachment_id', 'in', attachments.ids),
    ])
    return {p.attachment_id.id: p.id for p in photos}


def _haversine_km(lat1, lng1, lat2, lng2):
    # 兩點球面距離(公里),用於比較大小,精度足夠
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class ConstructionPortal(CustomerPortal):
    """
    工程監造系統 Portal Controller（v10）

    提供承包廠商 Portal 用戶存取:
    - 工程案件列表與首頁（HUD + 事件通知 + 排程）
    - 自主檢查填寫與查詢
    - 缺失改善提交
    - 照片上傳
    """

    def _prepare_home_portal_values(self, counters):
        """Portal 首頁計數器"""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

        if 'construction_count' in counters:
            domain = request.env['supervision.project']._get_portal_projects_domain(partner)
            values['construction_count'] = request.env['supervision.project'].search_count(domain)

        return values

    def _get_construction_projects_domain(self, partner):
        """取得 Portal 用戶可存取的工程案件 domain"""
        return request.env['supervision.project']._get_portal_projects_domain(partner)

    def _get_project_day_count(self, project):
        """計算 DAY 天數（從開工日到今天）"""
        if project.contract_start_date:
            return (date.today() - project.contract_start_date).days
        return 0

    def _get_nav_badges(self, project):
        """計算底部導航 badge 數字（檢查/缺失/日誌）"""
        today = date.today()
        badges = {}
        try:
            badges['insp'] = request.env['general.self.inspection'].search_count([
                ('project_id', '=', project.id),
                ('state', '=', 'draft'),
            ])
        except Exception:
            badges['insp'] = 0
        try:
            badges['def'] = request.env['supervision.defect'].search_count([
                ('project_id', '=', project.id),
                ('state', 'not in', ['verified', 'closed']),
            ])
        except Exception:
            badges['def'] = 0
        try:
            week_start = today - timedelta(days=today.weekday())
            DailyLog = request.env['daily.log.sheet']
            filled = DailyLog.search_count([
                ('supervision_project_id', '=', project.id),
                ('log_date', '>=', week_start),
                ('log_date', '<=', today),
            ])
            # 本週到今天的工作天數（週一到週五，不含週六日）
            workdays = sum(1 for i in range((today - week_start).days + 1)
                          if (week_start + timedelta(days=i)).weekday() < 5)
            badges['log'] = max(workdays - filled, 0)
        except Exception:
            badges['log'] = 0
        return badges

    # ==================== 工程案件 ====================

    @http.route(['/my/construction', '/my/construction/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_construction_projects(self, page=1, sortby=None, **kw):
        """工程案件入口

        行為:
        - `?view=list` 或翻頁(page>1) → 直接顯示列表頁
        - 0 個可見專案 → 顯示列表頁(空狀態)
        - 1 個可見專案 → server-side 直接 redirect 到該專案 HUD
        - 多個可見專案 → render GPS 定位中介頁(splash),
          由前端 JS 取得座標後 POST 到 /my/construction/nearest 拿最近專案 id 再跳轉
        """
        partner = request.env.user.partner_id
        Project = request.env['supervision.project']
        domain = self._get_construction_projects_domain(partner)

        force_list = kw.get('view') == 'list' or page > 1
        if not force_list:
            accessible = Project.search(domain)
            if not accessible:
                # 落到列表頁顯示空狀態
                pass
            elif len(accessible) == 1:
                return request.redirect('/my/construction/%s' % accessible.id)
            else:
                return request.render(
                    'construction_portal.portal_construction_locator',
                    {'page_name': 'construction'},
                )

        return self._render_construction_list(page=page, sortby=sortby, **kw)

    def _render_construction_list(self, page=1, sortby=None, **kw):
        """工程案件列表(原 portal_my_construction_projects 邏輯)"""
        partner = request.env.user.partner_id
        Project = request.env['supervision.project']

        domain = self._get_construction_projects_domain(partner)

        # 排序選項
        searchbar_sortings = {
            'date': {'label': _('最新'), 'order': 'create_date desc'},
            'name': {'label': _('名稱'), 'order': 'name'},
            'state': {'label': _('狀態'), 'order': 'state'},
        }
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # 計數與分頁
        project_count = Project.search_count(domain)
        pager = portal_pager(
            url='/my/construction',
            total=project_count,
            page=page,
            step=self._items_per_page,
            url_args={'sortby': sortby},
        )

        projects = Project.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'projects': projects,
            'page_name': 'construction',
            'pager': pager,
            'default_url': '/my/construction',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        }

        return request.render('construction_portal.portal_my_construction_projects', values)

    @http.route('/my/construction/nearest', type='json', auth='user', website=True)
    def portal_construction_nearest(self, lat=None, lng=None, **kw):
        """回傳離使用者(lat,lng)最近、且使用者有權限的工程案件 id

        供 /my/construction 的 splash 頁前端呼叫。
        若沒有任何「有座標的」可見專案,回傳 {'project_id': None},
        前端應改導去 /my/construction?view=list。
        """
        try:
            user_lat = float(lat)
            user_lng = float(lng)
        except (TypeError, ValueError):
            return {'project_id': None}

        partner = request.env.user.partner_id
        Project = request.env['supervision.project']
        domain = self._get_construction_projects_domain(partner)
        # 排除沒填座標的專案(latitude/longitude 預設 0.0 → 不可信)
        domain = AND([domain, [
            ('latitude', '!=', 0),
            ('longitude', '!=', 0),
        ]])
        projects = Project.search(domain)
        if not projects:
            return {'project_id': None}

        nearest = min(
            projects,
            key=lambda p: _haversine_km(user_lat, user_lng, p.latitude, p.longitude),
        )
        return {'project_id': nearest.id}

    @http.route(['/my/construction/<int:project_id>'],
                type='http', auth='user', website=True)
    def portal_construction_project_detail(self, project_id, **kw):
        """工程首頁（v10 HUD 設計）"""
        try:
            project = self._document_check_access(
                'supervision.project', project_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        today = date.today()

        # DAY 計數：(today - contract_start_date).days
        day_count = 0
        if project.contract_start_date:
            delta = today - project.contract_start_date
            day_count = max(delta.days, 0)

        # 進度百分比：從 actual_progress 或計算
        progress_pct = project.actual_progress or 0.0

        # 逾期缺失
        overdue_defects = request.env['supervision.defect'].search([
            ('project_id', '=', project.id),
            ('state', '=', 'open'),
            ('is_overdue', '=', True),
        ], limit=5, order='deadline asc')

        # 待填自主檢查（draft 狀態）
        draft_inspections = request.env['general.self.inspection'].search([
            ('project_id', '=', project.id),
            ('state', '=', 'draft'),
        ], limit=10, order='create_date desc')

        # 本週排程（construction.weekly.schedule）
        weekly_lines = []
        week_display = ''
        week_target = ''
        planned_progress = 0.0
        actual_progress = 0.0
        try:
            WeeklySchedule = request.env['construction.weekly.schedule']
            week_start_date = today - timedelta(days=today.weekday())
            schedule = WeeklySchedule.search([
                ('supervision_project_id', '=', project.id),
                ('week_start', '<=', today),
                ('week_end', '>=', today),
            ], limit=1, order='week_start desc')
            if schedule:
                weekly_lines = schedule.line_ids
                week_display = schedule.week_display or ''
                # 組合本週目標文字
                task_names = [l.task_name or l.task_id.name for l in schedule.line_ids if l.task_name or l.task_id]
                week_target = ' + '.join(task_names[:3])
                if len(task_names) > 3:
                    week_target += f' 等 {len(task_names)} 項'
        except Exception:
            pass

        # 本週進度（從 progress.schedule 或 actual_duration/total 計算）
        if project.total_approved_duration and project.total_approved_duration > 0:
            actual_progress = round(day_count / project.total_approved_duration * 100, 1)
            # planned 用線性比例估算
            planned_progress = round(day_count / project.total_approved_duration * 100, 1)
        # 若有 actual_progress 欄位則用它
        if project.actual_progress:
            actual_progress = round(project.actual_progress, 1)

        # 今日日誌
        today_log = False
        try:
            DailyLog = request.env['daily.log.sheet']
            today_log = DailyLog.search([
                ('supervision_project_id', '=', project.id),
                ('log_date', '=', today),
            ], limit=1)
        except Exception:
            pass

        # 今日照片數
        today_photo_count = request.env['supervision.photo'].search_count([
            ('project_id', '=', project.id),
            ('shot_date', '=', today),
        ])

        # 計數
        inspection_count = request.env['general.self.inspection'].search_count([
            ('project_id', '=', project.id),
        ])
        draft_insp_count = len(draft_inspections)
        open_defect_count = request.env['supervision.defect'].search_count([
            ('project_id', '=', project.id),
            ('state', 'not in', ['verified', 'closed']),
        ])
        photo_count = request.env['supervision.photo'].search_count([
            ('project_id', '=', project.id),
        ])

        # 本週日誌（用於日誌列表頁的日曆式顯示）
        log_days = []
        try:
            DailyLog = request.env['daily.log.sheet']
            week_start_dt = today - timedelta(days=today.weekday())
            for i in range(7):
                d = week_start_dt + timedelta(days=i)
                weekday_names = ['一', '二', '三', '四', '五', '六', '日']
                log = DailyLog.search([
                    ('supervision_project_id', '=', project.id),
                    ('log_date', '=', d),
                ], limit=1)
                status = 'off' if i >= 6 else ('today' if d == today else ('filled' if log else 'empty'))
                weather_str = ''
                if log and log.weather_am:
                    weather_sel = dict(DailyLog.fields_get(['weather_am'])['weather_am']['selection'])
                    weather_str = weather_sel.get(log.weather_am, '')
                    if log.weather_pm:
                        weather_str += '/' + weather_sel.get(log.weather_pm, '')
                log_days.append({
                    'date': d.strftime('%m/%d'),
                    'date_full': d.isoformat(),
                    'weekday': weekday_names[i],
                    'status': status,
                    'weather': weather_str,
                    'items': len(log.line_ids) if log else 0,
                })
        except Exception:
            pass

        # 通報單（預約式）
        recent_slips = []
        slip_count = 0
        if project.project_type == 'reservation':
            try:
                Slip = request.env['reservation.notification.slip']
                slip_count = Slip.search_count([('project_id', '=', project.id)])
                recent_slips = Slip.search([
                    ('project_id', '=', project.id),
                ], limit=5, order='slip_no desc')
            except Exception:
                pass

        values = {
            'project': project,
            'page_name': 'construction_detail',
            # HUD
            'day_count': day_count,
            'progress_pct': progress_pct,
            'open_defect_count': open_defect_count,
            # 事件通知
            'overdue_defects': overdue_defects,
            'draft_inspections': draft_inspections,
            # 本週進度
            'week_display': week_display,
            'week_target': week_target,
            'planned_progress': planned_progress,
            'actual_progress': actual_progress,
            'weekly_lines': weekly_lines,
            # 任務狀態
            'today_log': today_log,
            'today_photo_count': today_photo_count,
            'log_days': log_days,
            # 計數
            'inspection_count': inspection_count,
            'draft_insp_count': draft_insp_count,
            'photo_count': photo_count,
            # 通報單（預約式）
            'recent_slips': recent_slips,
            'slip_count': slip_count,
            # 底部導航 badge
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_project_detail', values)

    @http.route(['/my/construction/<int:project_id>/info'],
                type='http', auth='user', website=True)
    def portal_construction_project_info(self, project_id, **kw):
        """工程資訊頁面（底部導航第一 tab）"""
        try:
            project = self._document_check_access(
                'supervision.project', project_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        today = date.today()
        day_count = 0
        if project.contract_start_date:
            day_count = max((today - project.contract_start_date).days, 0)

        # 工程進度：從進度表 cumulative_actual 取（= project.actual_progress）
        progress_pct = project.actual_progress or 0.0
        # 工期進度：已過天數佔總工期比例（含展延）
        total_duration = project.total_approved_duration or project.contract_duration or 0
        schedule_pct = (day_count / total_duration * 100.0) if total_duration else 0.0
        remaining = 0
        if project.total_approved_duration:
            remaining = project.total_approved_duration - day_count

        values = {
            'project': project,
            'page_name': 'construction_info',
            'day_count': day_count,
            'progress_pct': progress_pct,
            'schedule_pct': schedule_pct,
            'remaining_days': remaining,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_project_info', values)

    # ==================== 工程資訊編輯 ====================

    @http.route(['/my/construction/<int:project_id>/edit'],
                type='http', auth='user', website=True)
    def portal_construction_project_edit(self, project_id, **kw):
        """工程資訊編輯頁（補填/修改 supervision.project，僅 draft 狀態可用）"""
        try:
            project = self._document_check_access(
                'supervision.project', project_id,
                access_token=kw.get('access_token'),
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 僅允許 draft 編輯
        if project.state != 'draft':
            return request.redirect(
                f'/my/construction/{project_id}/info?error=not_draft'
            )

        env = request.env

        # 業主機關下拉：
        # 1. 優先取 partner_type='authority' 的記錄
        # 2. 若完全沒分類好，fallback 到所有獨立 company partner，
        #    並排除 res.company 的 main partner（避免承包 / 監造公司混進來）
        Partner = env['res.partner'].sudo()
        Company = env['res.company'].sudo()
        authorities = Partner.search(
            [('partner_type', '=', 'authority')], order='name'
        )
        if not authorities:
            company_main_ids = Company.search([]).mapped('partner_id').ids
            authorities = Partner.search([
                ('is_company', '=', True),
                ('parent_id', '=', False),
                ('id', 'not in', company_main_ids),
            ], order='name', limit=500)
        # 確保目前已綁定的業主仍在下拉內（避免 domain 收斂後選不到）
        if project.authority_id and project.authority_id not in authorities:
            authorities = authorities | project.authority_id

        # 承辦人：已綁定業主的所有 child partner
        authority_contacts = (
            Partner.search(
                [('parent_id', '=', project.authority_id.id)],
                order='name'
            )
            if project.authority_id
            else Partner.browse()
        )

        # 監造 / 承包公司下拉：
        # 用 company_type 分類過濾；若分類結果為空（master data 尚未分類），
        # fallback 到所有公司。已綁定的公司不論 domain 結果如何都補進列表。
        supervision_companies = Company.search(
            [('company_type', '=', 'supervision')], order='name'
        )
        contractor_companies = Company.search(
            [('company_type', '=', 'contractor')], order='name'
        )
        if not supervision_companies:
            supervision_companies = Company.search([], order='name')
        if not contractor_companies:
            contractor_companies = Company.search([], order='name')
        if project.company_id and project.company_id not in supervision_companies:
            supervision_companies = supervision_companies | project.company_id
        if project.contractor_company_ids:
            missing = project.contractor_company_ids - contractor_companies
            if missing:
                contractor_companies = contractor_companies | missing

        # 使用者下拉
        Users = env['res.users'].sudo()
        all_users = Users.search([('share', '=', False)], order='name')
        if project.company_id:
            supervision_users = Users.search(
                [('share', '=', False),
                 ('company_ids', 'in', project.company_id.ids)],
                order='name'
            )
        else:
            supervision_users = all_users

        # Year Selection（callable）
        year_field = env['supervision.project']._fields['year'].selection
        if callable(year_field):
            year_selection = year_field(env['supervision.project'])
        else:
            year_selection = year_field or []

        values = {
            'project': project,
            'page_name': 'construction_info',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            'year_selection': year_selection,
            'authorities': authorities,
            'authority_contacts': authority_contacts,
            'supervision_companies': supervision_companies,
            'contractor_companies': contractor_companies,
            'supervision_users': supervision_users,
            'all_users': all_users,
            'error': kw.get('error'),
        }
        return request.render(
            'construction_portal.portal_construction_project_edit', values
        )

    @http.route(['/my/construction/<int:project_id>/update'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_project_update(self, project_id, **post):
        """儲存工程資訊編輯"""
        try:
            project = self._document_check_access(
                'supervision.project', project_id,
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        if project.state != 'draft':
            return request.redirect(
                f'/my/construction/{project_id}/info?error=not_draft'
            )

        def _s(key):
            return (post.get(key) or '').strip()

        def _to_int(key):
            raw = post.get(key)
            if raw in (None, '', False):
                return False
            try:
                v = int(raw)
                return v or False
            except (TypeError, ValueError):
                return False

        def _to_float(key):
            raw = _s(key)
            if not raw:
                return False
            try:
                return float(raw)
            except ValueError:
                return False

        def _to_date(key):
            raw = _s(key)
            if not raw:
                return False
            try:
                return datetime.strptime(raw, '%Y-%m-%d').date()
            except ValueError:
                return False

        # Partial-update 語意：只寫入 POST 中實際有出現的 key。
        # 完整 form submission 會帶 hidden `_edit_form=1` marker，
        # marker 存在時 M2M 若 key 不在 POST 代表使用者勾 0 項 -> 清空。
        vals = {}
        is_form_submit = post.get('_edit_form') == '1'

        def _in(key):
            return key in post

        # ---- 基本資訊 ----
        # name 特殊處理：jsonb translation 同時寫 zh_TW + en_US，
        # 避免 session 單一語言造成另一語言 fallback 到舊值
        if _in('name'):
            name = _s('name')
            if name:
                pp = project.project_id.sudo()
                for _lang in ('zh_TW', 'en_US'):
                    try:
                        pp.with_context(lang=_lang).write({'name': name})
                    except Exception as _e:
                        _logger.warning('portal update: name lang=%s failed: %s', _lang, _e)

        if _in('project_type'):
            project_type = _s('project_type')
            if project_type in ('general', 'reservation'):
                vals['project_type'] = project_type

        if _in('year'):
            year = _s('year')
            if year:
                vals['year'] = year

        if _in('location'):
            vals['location'] = _s('location')
        if _in('location_detail'):
            vals['location_detail'] = _s('location_detail')

        if _in('latitude'):
            lat = _to_float('latitude')
            vals['latitude'] = lat if lat is not False else 0.0
        if _in('longitude'):
            lng = _to_float('longitude')
            vals['longitude'] = lng if lng is not False else 0.0

        # ---- 契約資訊 ----
        if _in('contract_no'):
            vals['contract_no'] = _s('contract_no')

        if _in('contract_amount'):
            amount_raw = _s('contract_amount')
            if amount_raw and not project.task_count:
                try:
                    vals['contract_amount'] = float(amount_raw)
                except ValueError:
                    pass

        if _in('contract_start_date'):
            vals['contract_start_date'] = _to_date('contract_start_date') or False
        if _in('contract_end_date'):
            vals['contract_end_date'] = _to_date('contract_end_date') or False
        if _in('actual_start_date'):
            vals['actual_start_date'] = _to_date('actual_start_date') or False
        if _in('actual_end_date'):
            vals['actual_end_date'] = _to_date('actual_end_date') or False

        if _in('extension_duration'):
            ext_raw = _s('extension_duration')
            if ext_raw:
                try:
                    vals['extension_duration'] = int(ext_raw)
                except ValueError:
                    vals['extension_duration'] = 0
            else:
                vals['extension_duration'] = 0

        # ---- 相關單位 ----
        for _m2o in ('authority_id', 'authority_contact_id',
                     'supervision_engineer_id', 'site_manager_id',
                     'activity_default_user_id', 'activity_test_user_id',
                     'activity_inspection_user_id'):
            if _in(_m2o):
                vals[_m2o] = _to_int(_m2o)

        if _in('company_id'):
            vals['company_id'] = _to_int('company_id') or project.company_id.id

        # contractor_company_ids (M2M checkbox) —
        # 若 key 存在於 POST，或是完整 form submit (marker 存在)，就寫入
        if _in('contractor_company_ids') or is_form_submit:
            contractor_ids_raw = request.httprequest.form.getlist('contractor_company_ids')
            contractor_ids = []
            for cid in contractor_ids_raw:
                try:
                    contractor_ids.append(int(cid))
                except (TypeError, ValueError):
                    continue
            vals['contractor_company_ids'] = [(6, 0, contractor_ids)]

        # ---- 備註 ----
        if _in('notes'):
            notes = post.get('notes')
            vals['notes'] = notes if notes else False

        # ---- 預檢日期一致性 ----
        # 若使用者只更新其中一個日期，要跟既有值比對
        eff_start = (
            vals['contract_start_date']
            if 'contract_start_date' in vals
            else project.contract_start_date
        )
        eff_end = (
            vals['contract_end_date']
            if 'contract_end_date' in vals
            else project.contract_end_date
        )
        if eff_start and eff_end and eff_end < eff_start:
            return request.redirect(
                f'/my/construction/{project_id}/edit?error=date_invalid'
            )

        # ---- 寫入 ----
        try:
            if vals:
                project.sudo().write(vals)
        except (ValidationError, UserError) as e:
            _logger.warning('portal project edit write failed: %s', e)
            return request.redirect(
                f'/my/construction/{project_id}/edit?error=save_failed'
            )
        except Exception:
            _logger.exception('portal project edit unexpected error')
            return request.redirect(
                f'/my/construction/{project_id}/edit?error=save_failed'
            )

        return request.redirect(
            f'/my/construction/{project_id}/info?message=updated'
        )

    # ==================== 施工日誌 ====================

    @http.route(['/my/construction/<int:project_id>/daily-logs',
                 '/my/construction/<int:project_id>/daily-logs/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_daily_logs(self, project_id, page=1, **kw):
        """施工日誌列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        domain = [('supervision_project_id', '=', project.id)]

        log_count = DailyLog.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/daily-logs',
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

        open_defects = request.env['supervision.defect'].search([
            ('project_id', '=', project.id),
            ('state', '=', 'open'),
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
            'default_url': f'/my/construction/{project_id}/daily-logs',
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

    @http.route(['/my/construction/<int:project_id>/daily-log/<int:log_id>'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_detail(self, project_id, log_id, **kw):
        """施工日誌詳情"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/my/construction/{project_id}/daily-logs')

        # 天氣 Selection 選項（從 fields_get 拉）
        weather_selection = dict(
            DailyLog.fields_get(['weather_am'])['weather_am']['selection']
        )

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

        values = {
            'project': project,
            'log': log,
            'weather_selection': weather_selection,
            'page_name': 'construction_daily_log_detail',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            # 照片區塊變數
            'photos': log.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, log.photo_ids),
            'photo_categories': photo_categories,
            'upload_url': f'/my/construction/daily-log/{log.id}/photo/upload',
            'delete_url_tpl': f'/my/construction/daily-log/{log.id}/photo/%s/delete',
            'is_locked': log.is_locked,
            # chatter
            'object': log,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_daily_log_detail', values)

    # ==================== 施工日誌批次匯入 (XLSM) ====================

    @http.route(['/my/construction/<int:project_id>/daily-logs/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_daily_logs_import(self, project_id, **kw):
        """施工日誌批次匯入頁（GET）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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

    @http.route(['/my/construction/<int:project_id>/daily-logs/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_daily_logs_import_submit(self, project_id, **post):
        """施工日誌批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
        base_url = f'/my/construction/{project_id}/daily-logs/import'
        project_record_id = project.project_id.id
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

    @http.route(['/my/construction/<int:project_id>/daily-log/new'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_new(self, project_id, **kw):
        """新增施工日誌表單"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']

        # 天氣 Selection 選項
        weather_selection = DailyLog.fields_get(['weather_am'])['weather_am']['selection']

        # 工項列表（只取最細項，非彙總項）— 用 sudo() 避免 Portal 權限問題
        tasks = request.env['project.task'].sudo().search([
            ('project_id', '=', project.project_id.id),
            ('is_summary_item', '=', False),
            ('active', '=', True),
        ], order='sequence, item_no')

        # 天氣 emoji 映射
        weather_emoji = {'sunny': '☀', 'cloudy': '⛅', 'overcast': '☁', 'rainy': '🌧', 'heavy_rain': '⛈', 'typhoon': '🌀', 'foggy': '🌫'}

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

        values = {
            'project': project,
            'weather_options': weather_selection,
            'weather_emoji': weather_emoji,
            'tasks': tasks,
            'photo_categories': photo_categories,
            'is_edit': False,
            'log': False,
            'form_action': '/my/construction/daily-log/create',
            'page_name': 'construction_daily_log_new',
            'today': date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_daily_log_form', values)

    @http.route(['/my/construction/daily-log/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_create(self, **post):
        """建立施工日誌"""
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

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

        # 處理工項明細（line_ids）
        line_index = 0
        while True:
            work_item_id = post.get(f'line_work_item_id_{line_index}')
            if work_item_id is None:
                break
            if work_item_id:
                daily_qty = post.get(f'line_daily_qty_{line_index}', '0')
                location = post.get(f'line_location_{line_index}', '')
                work_desc = post.get(f'line_work_description_{line_index}', '')
                has_issue = post.get(f'line_has_issue_{line_index}') == 'on'
                issue_desc = post.get(f'line_issue_description_{line_index}', '')

                line_vals = {
                    'sheet_id': log.id,
                    'work_item_id': int(work_item_id),
                    'daily_qty': float(daily_qty) if daily_qty else 0.0,
                    'location': location,
                    'work_description': work_desc,
                    'has_issue': has_issue,
                    'issue_description': issue_desc if has_issue else '',
                }
                request.env['daily.log.line'].sudo().create(line_vals)

            line_index += 1

        # 處理上傳照片(統一走 helper,直建 supervision.photo)
        meta = {
            'description': post.get('photo_description') or '',
            'category': post.get('photo_category') or False,
            'source_model': 'daily_log',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
            'location_description': post.get('photo_location_description') or '',
        }
        _portal_save_photos(
            request.env,
            log,
            project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/my/construction/{project_id}/daily-log/{log.id}?message=created'
        )

    @http.route(['/my/construction/<int:project_id>/daily-log/<int:log_id>/edit'],
                type='http', auth='user', website=True)
    def portal_construction_daily_log_edit(self, project_id, log_id, **kw):
        """編輯施工日誌(共用 form 模板)"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet']
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/my/construction/{project_id}/daily-logs')
        if log.is_locked:
            return request.redirect(
                f'/my/construction/{project_id}/daily-log/{log.id}?error=locked'
            )

        weather_selection = DailyLog.fields_get(['weather_am'])['weather_am']['selection']
        weather_emoji = {'sunny': '☀', 'cloudy': '⛅', 'overcast': '☁', 'rainy': '🌧', 'heavy_rain': '⛈', 'typhoon': '🌀', 'foggy': '🌫'}

        tasks = request.env['project.task'].sudo().search([
            ('project_id', '=', project.project_id.id),
            ('is_summary_item', '=', False),
            ('active', '=', True),
        ], order='sequence, item_no')

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

        values = {
            'project': project,
            'log': log,
            'weather_options': weather_selection,
            'weather_emoji': weather_emoji,
            'tasks': tasks,
            'photo_categories': photo_categories,
            'is_edit': True,
            'form_action': f'/my/construction/{project_id}/daily-log/{log.id}/update',
            'page_name': 'construction_daily_log_edit',
            'today': log.log_date.isoformat() if log.log_date else date.today().isoformat(),
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_daily_log_form', values)

    @http.route(['/my/construction/<int:project_id>/daily-log/<int:log_id>/update'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_update(self, project_id, log_id, **post):
        """更新施工日誌(編輯儲存)"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        DailyLog = request.env['daily.log.sheet'].sudo()
        log = DailyLog.search([
            ('id', '=', log_id),
            ('supervision_project_id', '=', project.id),
        ], limit=1)
        if not log:
            return request.redirect(f'/my/construction/{project_id}/daily-logs')
        if log.is_locked:
            return request.redirect(
                f'/my/construction/{project_id}/daily-log/{log.id}?error=locked'
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
        meta = {
            'description': post.get('photo_description') or '',
            'category': post.get('photo_category') or False,
            'source_model': 'daily_log',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
            'location_description': post.get('photo_location_description') or '',
        }
        _portal_save_photos(
            request.env, log, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/my/construction/{project_id}/daily-log/{log.id}?message=updated'
        )

    @http.route(['/my/construction/daily-log/<int:log_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_photo_upload(self, log_id, **post):
        """詳情頁追加上傳照片"""
        log = request.env['daily.log.sheet'].sudo().browse(log_id)
        if not log.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'supervision.project', log.supervision_project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if log.is_locked:
            return request.redirect(
                f'/my/construction/{project.id}/daily-log/{log.id}?error=locked'
            )

        meta = {
            'description': post.get('description') or '',
            'category': post.get('category') or False,
            'source_model': 'daily_log',
            'latitude': post.get('latitude') or 0,
            'longitude': post.get('longitude') or 0,
            'location_description': post.get('location_description') or '',
        }
        _portal_save_photos(
            request.env, log, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/my/construction/{project.id}/daily-log/{log.id}?message=photo_added'
        )

    @http.route(['/my/construction/daily-log/<int:log_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_daily_log_photo_delete(self, log_id, att_id, **post):
        """從詳情頁刪除單張照片"""
        log = request.env['daily.log.sheet'].sudo().browse(log_id)
        if not log.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'supervision.project', log.supervision_project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if log.is_locked:
            return request.redirect(
                f'/my/construction/{project.id}/daily-log/{log.id}?error=locked'
            )

        if att_id in log.photo_ids.ids:
            _portal_delete_photo(request.env, log, att_id)

        return request.redirect(
            f'/my/construction/{project.id}/daily-log/{log.id}?message=photo_deleted'
        )

    # ==================== 自主檢查 ====================

    @http.route(['/my/construction/<int:project_id>/inspections/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_inspections_import(self, project_id, **kw):
        """自主檢查批次匯入頁（GET）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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

    @http.route(['/my/construction/<int:project_id>/inspections/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_inspections_import_submit(self, project_id, **post):
        """自主檢查批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
        base_url = f'/my/construction/{project_id}/inspections/import'
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
                                'stage': di.stage or 'stage2',
                                'sequence': di.sequence or 10,
                                'check_item': di.name,
                                'design_standard': di.check_standard or '',
                                'check_result': 'pass',
                            }))
                    else:
                        checklist_cmds.append((0, 0, {
                            'stage': 'stage2',
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

    @http.route(['/my/construction/<int:project_id>/inspections',
                 '/my/construction/<int:project_id>/inspections/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_inspections(self, project_id, page=1, **kw):
        """自主檢查列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Inspection = request.env['general.self.inspection']
        domain = [('project_id', '=', project.id)]

        inspection_count = Inspection.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/inspections',
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
            'default_url': f'/my/construction/{project_id}/inspections',
            'slip_list': slip_list,
            'slip_filter': int(slip_filter) if slip_filter else 0,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_inspections', values)

    @http.route(['/my/construction/<int:project_id>/inspection/new'],
                type='http', auth='user', website=True)
    def portal_construction_inspection_new(self, project_id, **kw):
        """新增自主檢查表單"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        InspType = request.env['self.inspection.type'].sudo()
        inspection_types = InspType.search([])

        # inspection_timing 選項從 fields_get 拉
        Inspection = request.env['general.self.inspection']
        timing_selection = Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

        values = {
            'project': project,
            'inspection_types': inspection_types,
            'timing_options': timing_selection,
            'photo_categories': photo_categories,
            'page_name': 'construction_inspection_new',
            'today': date.today().isoformat(),
        }

        return request.render('construction_portal.portal_construction_inspection_form', values)

    @http.route(['/my/construction/inspection/create'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_inspection_create(self, **post):
        """建立自主檢查（含 checklist 項目提交）"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

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
        meta = {
            'description': post.get('photo_description') or '',
            'category': post.get('photo_category') or False,
            'source_model': 'inspection',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
            'location_description': post.get('photo_location_description') or '',
        }
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        # 處理 checklist 項目結果
        idx = 0
        while True:
            item_id_str = post.get(f'checklist_item_id_{idx}')
            if item_id_str is None:
                break
            if item_id_str:
                check_result = post.get(f'checklist_result_{idx}', 'pass')
                actual_result = post.get(f'checklist_actual_{idx}', '')
                item = request.env['general.self.inspection.item'].sudo().browse(int(item_id_str))
                if item.exists() and item.inspection_id.id == inspection.id:
                    item.write({
                        'check_result': check_result,
                        'actual_result': actual_result,
                    })
            idx += 1

        return request.redirect(
            f'/my/construction/{project_id}/daily-log/../inspection/{inspection.id}'.replace(
                '/daily-log/../', '/'
            ) if False else f'/my/construction/inspection/{inspection.id}?message=created'
        )

    @http.route(['/my/construction/inspection/get-items'],
                type='json', auth='user', methods=['POST'])
    def portal_construction_inspection_get_items(self, **post):
        """AJAX: 取得檢查類型的預設 checklist items"""
        type_id = int(post.get('type_id', 0))
        if not type_id:
            return {'items': [], 'stages': []}

        InspType = request.env['self.inspection.type'].sudo().browse(type_id)
        if not InspType.exists():
            return {'items': [], 'stages': []}

        stage_labels = {'stage1': '第一查驗階段', 'stage2': '第二查驗階段', 'stage3': '第三查驗階段'}
        items = []
        for item in InspType.default_item_ids:
            items.append({
                'id': item.id,
                'name': item.name,
                'standard': item.check_standard or '',
                'stage': item.stage or 'stage1',
                'note': item.note or '',
            })

        # 按 stage 分群
        stages_seen = []
        for item in items:
            if item['stage'] not in stages_seen:
                stages_seen.append(item['stage'])

        stages = [{'key': s, 'label': stage_labels.get(s, s)} for s in stages_seen]

        return {'items': items, 'stages': stages}

    @http.route(['/my/construction/inspection/<int:inspection_id>'],
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

        # 按 stage 分群 checklist items
        stage_groups = {}
        stage_labels = {'stage1': '第一查驗階段', 'stage2': '第二查驗階段', 'stage3': '第三查驗階段'}
        for item in inspection.checklist_ids:
            stage = item.stage or 'stage1'
            if stage not in stage_groups:
                stage_groups[stage] = {'label': stage_labels.get(stage, stage), 'items': []}
            stage_groups[stage]['items'].append(item)

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

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

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
            'photos': inspection.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, inspection.photo_ids),
            'photo_categories': photo_categories,
            'upload_url': f'/my/construction/inspection/{inspection.id}/photo/upload',
            'delete_url_tpl': f'/my/construction/inspection/{inspection.id}/photo/%s/delete',
            'is_locked': False,
            # chatter
            'object': inspection,
            'disable_composer': False,
            'message_per_page': 10,
        }

        return request.render('construction_portal.portal_construction_inspection_detail', values)

    @http.route(['/my/construction/inspection/<int:inspection_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_inspection_photo_upload(self, inspection_id, **post):
        """一般式自主檢查詳情頁追加上傳照片"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        meta = {
            'description': post.get('description') or '',
            'category': post.get('category') or False,
            'source_model': 'inspection',
            'latitude': post.get('latitude') or 0,
            'longitude': post.get('longitude') or 0,
            'location_description': post.get('location_description') or '',
        }
        _portal_save_photos(
            request.env, inspection, inspection.project_id,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/my/construction/inspection/{inspection.id}?message=photo_added'
        )

    @http.route(['/my/construction/inspection/<int:inspection_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_inspection_photo_delete(self, inspection_id, att_id, **post):
        """一般式自主檢查刪除照片"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if att_id in inspection.photo_ids.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/my/construction/inspection/{inspection.id}?message=photo_deleted'
        )

    # ==================== 預約式自主檢查 ====================

    @http.route(['/my/construction/<int:project_id>/reservation-inspections',
                 '/my/construction/<int:project_id>/reservation-inspections/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspections(self, project_id, page=1, **kw):
        """預約式自主檢查列表(掛在通報單下,但這裡彙總顯示)"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            url=f'/my/construction/{project_id}/reservation-inspections',
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
            'default_url': f'/my/construction/{project_id}/reservation-inspections',
            'slip_list': slip_list,
            'slip_filter': slip_filter,
            'page_name': 'construction_reservation_inspections',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }
        return request.render('construction_portal.portal_construction_reservation_inspections', values)

    @http.route(['/my/construction/<int:project_id>/reservation-inspection/new'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspection_new(self, project_id, slip_id=None, **kw):
        """預約式檢查新增表單(必須帶 slip_id)"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not slip_id:
            return request.redirect(f'/my/construction/{project_id}/slips')

        Slip = request.env['reservation.notification.slip']
        slip = Slip.search([
            ('id', '=', int(slip_id)),
            ('project_id', '=', project.id),
        ], limit=1)
        if not slip:
            return request.redirect(f'/my/construction/{project_id}/slips')

        InspType = request.env['self.inspection.type'].sudo()
        inspection_types = InspType.search([])

        Inspection = request.env['reservation.self.inspection']
        timing_selection = Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

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

    @http.route(['/my/construction/reservation-inspection/create'],
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
            project = self._document_check_access('supervision.project', slip.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')

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

        # 處理上傳照片
        meta = {
            'description': post.get('photo_description') or '',
            'category': post.get('photo_category') or False,
            'source_model': 'inspection',
            'latitude': post.get('photo_latitude') or 0,
            'longitude': post.get('photo_longitude') or 0,
            'location_description': post.get('photo_location_description') or '',
        }
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )

        return request.redirect(
            f'/my/construction/reservation-inspection/{inspection.id}?message=created'
        )

    @http.route(['/my/construction/reservation-inspection/<int:inspection_id>'],
                type='http', auth='user', website=True)
    def portal_construction_reservation_inspection_detail(self, inspection_id, **kw):
        """預約式自主檢查詳情"""
        Inspection = request.env['reservation.self.inspection'].sudo()
        inspection = Inspection.browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'supervision.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 按 stage 分群
        stage_groups = {}
        stage_labels = {'stage1': '施工前', 'stage2': '施工中', 'stage3': '施工後'}
        for item in inspection.checklist_ids:
            stage = item.stage or 'stage1'
            if stage not in stage_groups:
                stage_groups[stage] = {'label': stage_labels.get(stage, stage), 'items': []}
            stage_groups[stage]['items'].append(item)

        timing_selection = dict(
            Inspection.fields_get(['inspection_timing'])['inspection_timing']['selection']
        )

        photo_categories = request.env['supervision.photo'].fields_get(
            ['category'])['category']['selection']

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
            'photos': inspection.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, inspection.photo_ids),
            'photo_categories': photo_categories,
            'upload_url': f'/my/construction/reservation-inspection/{inspection.id}/photo/upload',
            'delete_url_tpl': f'/my/construction/reservation-inspection/{inspection.id}/photo/%s/delete',
            'is_locked': False,
        }
        return request.render(
            'construction_portal.portal_construction_reservation_inspection_detail', values)

    @http.route(['/my/construction/reservation-inspection/<int:inspection_id>/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_reservation_inspection_photo_upload(self, inspection_id, **post):
        """預約式檢查追加照片"""
        inspection = request.env['reservation.self.inspection'].sudo().browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            project = self._document_check_access(
                'supervision.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        meta = {
            'description': post.get('description') or '',
            'category': post.get('category') or False,
            'source_model': 'inspection',
            'latitude': post.get('latitude') or 0,
            'longitude': post.get('longitude') or 0,
            'location_description': post.get('location_description') or '',
        }
        _portal_save_photos(
            request.env, inspection, project,
            request.httprequest.files.getlist('photos'),
            meta,
        )
        return request.redirect(
            f'/my/construction/reservation-inspection/{inspection.id}?message=photo_added'
        )

    @http.route(['/my/construction/reservation-inspection/<int:inspection_id>/photo/<int:att_id>/delete'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_reservation_inspection_photo_delete(self, inspection_id, att_id, **post):
        """預約式檢查刪除照片"""
        inspection = request.env['reservation.self.inspection'].sudo().browse(inspection_id)
        if not inspection.exists():
            return request.redirect('/my')
        try:
            self._document_check_access(
                'supervision.project', inspection.project_id.id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if att_id in inspection.photo_ids.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/my/construction/reservation-inspection/{inspection.id}?message=photo_deleted'
        )

    # ==================== 缺失管理 ====================

    @http.route(['/my/construction/<int:project_id>/defects/import'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_import(self, project_id, **kw):
        """缺失批次匯入頁（GET）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            'failed_details': request.session.pop(
                'defect_import_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_import', values)

    @http.route(['/my/construction/<int:project_id>/defects/import'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_import_submit(self, project_id, **post):
        """缺失批次匯入提交（POST multipart）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_xlsm_parser import parse_defect_tracking_xlsx

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_IMPORT] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env['supervision.defect'].sudo()
        base_url = f'/my/construction/{project_id}/defects/import'
        supervision_project_id = project.id

        imported = 0
        skipped = 0
        failed = 0
        failed_details = []

        for upload in files:
            fname = upload.filename or 'unnamed.xlsx'
            try:
                raw = upload.read()
                rows = parse_defect_tracking_xlsx(raw, filename=fname)
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
                        ('description', '=', description),
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

                    # 狀態：若有 improvement_date → closed；否則 open
                    state = 'closed' if improvement_date else 'open'

                    vals = {
                        'project_id': supervision_project_id,
                        'defect_type': row['defect_type'],
                        'source': 'daily_check',
                        'source_description': register_no,
                        'description': description,
                        'found_date': found_date,
                        'deadline': deadline or False,
                        'state': state,
                    }
                    if improvement_date:
                        from datetime import datetime, time
                        imp_dt = datetime.combine(improvement_date, time(12, 0))
                        vals.update({
                            'improvement_date': imp_dt,
                            'improvement_description': (
                                f'（總表單匯入，原始資料無詳細改善說明）'),
                            'close_date': imp_dt,
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

    @http.route(['/my/construction/<int:project_id>/defects/enrich'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_enrich(self, project_id, **kw):
        """缺失改善明細補充頁（GET）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            'failed_details': request.session.pop(
                'defect_enrich_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_enrich', values)

    @http.route(['/my/construction/<int:project_id>/defects/enrich'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_enrich_submit(self, project_id, **post):
        """缺失改善明細補充提交（POST multipart，上傳 zip）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_docx_parser import parse_defect_zip

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_ENRICH] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env['supervision.defect'].sudo()
        base_url = f'/my/construction/{project_id}/defects/enrich'
        supervision_project_id = project.id

        # index 現有缺失 by source_description (register_no)
        defects = Defect.search([('project_id', '=', supervision_project_id)])
        idx = {}
        for d in defects:
            if d.source_description:
                idx.setdefault(d.source_description, d)

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
                reg = row.get('register_no')
                if row.get('error'):
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': row['error'],
                    })
                    continue
                if not reg:
                    unmatched += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': '檔名無法推導 register_no',
                    })
                    continue
                target = idx.get(reg)
                if not target:
                    unmatched += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': f'{reg} 無對應缺失紀錄',
                    })
                    continue

                try:
                    write_vals = {}
                    if row.get('improvement'):
                        write_vals['improvement_description'] = row['improvement']
                    if row.get('close_comment'):
                        write_vals['close_comment'] = row['close_comment']
                    if not write_vals:
                        unmatched += 1
                        failed_details.append({
                            'filename': inner_fn,
                            'error': f'{reg}: 解析結果為空',
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
                        'error': f'{reg}: {e}'[:200],
                    })

        request.session['defect_enrich_failed_details'] = failed_details
        return request.redirect(
            f'{base_url}?updated={updated}&unmatched={unmatched}&failed={failed}')

    @http.route(['/my/construction/<int:project_id>/defects/import-docx'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_construction_defects_import_docx(self, project_id, **kw):
        """從 docx zip 直接建立缺失紀錄（沒有總表單的案場用）。"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            'failed_details': request.session.pop(
                'defect_create_docx_failed_details', []),
        }
        return request.render(
            'construction_portal.portal_construction_defect_import_docx', values)

    @http.route(['/my/construction/<int:project_id>/defects/import-docx'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_defects_import_docx_submit(self, project_id, **post):
        """從 docx zip 建立缺失紀錄提交。"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        from ..utils.defect_docx_parser import parse_defect_zip

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_CREATE_DOCX] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env['supervision.defect'].sudo()
        base_url = f'/my/construction/{project_id}/defects/import-docx'
        supervision_project_id = project.id

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
                defect_type = row.get('defect_type') or 'other'
                improvement = row.get('improvement') or ''
                close_comment = row.get('close_comment') or ''

                if not description or not found_date:
                    failed += 1
                    failed_details.append({
                        'filename': inner_fn,
                        'error': f'缺失必要欄位 desc={bool(description)} date={bool(found_date)}',
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
                                ('description', '=', description),
                            ], limit=1)
                        if not existing:
                            existing = Defect.search([
                                ('project_id', '=', supervision_project_id),
                                ('found_date', '=', found_date),
                                ('description', '=', description),
                            ], limit=1)
                        if existing:
                            skipped += 1
                            failed_details.append({
                                'filename': inner_fn,
                                'error': f'{reg or found_date}: 已有紀錄 id={existing.id}',
                            })
                            continue

                        state = 'closed' if close_comment else (
                            'action_taken' if improvement else 'open')

                        vals = {
                            'project_id': supervision_project_id,
                            'defect_type': defect_type,
                            'source': 'daily_check',
                            'source_description': reg or '',
                            'description': description,
                            'found_date': found_date,
                            'state': state,
                        }
                        if improvement:
                            vals['improvement_description'] = improvement
                        if close_comment:
                            from datetime import datetime, time
                            vals['close_comment'] = close_comment
                            vals['close_date'] = datetime.combine(found_date, time(12, 0))

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

    @http.route(['/my/construction/<int:project_id>/defects',
                 '/my/construction/<int:project_id>/defects/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_defects(self, project_id, page=1, filterby=None, **kw):
        """缺失列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env['supervision.defect']
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
            url=f'/my/construction/{project_id}/defects',
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
            'default_url': f'/my/construction/{project_id}/defects',
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_defects', values)

    @http.route(['/my/construction/<int:project_id>/defect/new'],
                type='http', auth='user', website=True)
    def portal_construction_defect_new(self, project_id, **kw):
        """新增缺失表單"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env['supervision.defect']
        fields_info = Defect.fields_get(['defect_type', 'source'])
        type_options = fields_info['defect_type']['selection']
        source_options = fields_info['source']['selection']

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

    @http.route(['/my/construction/defect/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_defect_create(self, **post):
        """建立缺失"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        vals = {
            'project_id': project_id,
            'description': post.get('description', ''),
            'location': post.get('location', ''),
            'defect_type': post.get('defect_type') or 'quality',
            'source': post.get('source') or 'daily_check',
            'found_date': post.get('found_date') or date.today().isoformat(),
            'deadline': post.get('deadline') or False,
        }

        Defect = request.env['supervision.defect'].sudo()
        defect = Defect.create(vals)

        # 處理照片上傳
        uploaded_file = post.get('photo')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read())
            attachment = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': file_data,
                'res_model': 'supervision.defect',
                'res_id': defect.id,
                'type': 'binary',
            })
            defect.write({'before_photo_ids': [(4, attachment.id)]})

        return request.redirect(f'/my/construction/defect/{defect.id}?message=created')

    @http.route(['/my/construction/defect/<int:defect_id>'],
                type='http', auth='user', website=True)
    def portal_construction_defect_detail(self, defect_id, **kw):
        """缺失詳情"""
        try:
            defect = self._document_check_access(
                'supervision.defect', defect_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env['supervision.defect']
        fields_info = Defect.fields_get(['defect_type', 'source', 'state', 'responsible_party'])
        type_selection = dict(fields_info['defect_type']['selection'])
        source_selection = dict(fields_info['source']['selection'])
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

    @http.route(['/my/construction/defect/<int:defect_id>/improve'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_defect_improve(self, defect_id, **post):
        """提交缺失改善"""
        partner = request.env.user.partner_id

        try:
            defect = self._document_check_access('supervision.defect', defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        improvement_text = post.get('improvement_description', '')
        defect.portal_submit_improvement(improvement_text, partner)

        return request.redirect(f'/my/construction/defect/{defect_id}?message=success')

    # ==================== 照片管理 ====================

    @http.route(['/my/construction/<int:project_id>/photos',
                 '/my/construction/<int:project_id>/photos/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_photos(self, project_id, page=1, **kw):
        """照片列表（含篩選、日期分群）"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            domain.append(('category', '=', category_filter))

        photo_count = Photo.search_count(domain)
        url_args = {}
        if source_filter:
            url_args['source'] = source_filter
        if category_filter:
            url_args['category'] = category_filter

        pager = portal_pager(
            url=f'/my/construction/{project_id}/photos',
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
        category_options = fields_info['category']['selection']

        values = {
            'project': project,
            'photos': photos,
            'date_groups': date_groups,
            'page_name': 'construction_photos',
            'pager': pager,
            'default_url': f'/my/construction/{project_id}/photos',
            'source_options': source_options,
            'category_options': category_options,
            'source_filter': source_filter or '',
            'category_filter': category_filter or '',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_photos', values)

    @http.route(['/my/construction/<int:project_id>/photo/upload'],
                type='http', auth='user', website=True)
    def portal_construction_photo_upload_form(self, project_id, **kw):
        """照片上傳表單"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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

    @http.route(['/my/construction/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_photo_upload(self, **post):
        """處理照片上傳（支持分類與 GPS）"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

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

            # 分類欄位
            if post.get('category'):
                vals['category'] = post['category']
            if post.get('construction_phase'):
                vals['construction_phase'] = post['construction_phase']
            if post.get('source_model'):
                vals['source_model'] = post['source_model']
            if post.get('location_description'):
                vals['location_description'] = post['location_description']

            # GPS
            lat = post.get('latitude')
            lng = post.get('longitude')
            if lat and lng:
                try:
                    vals['latitude'] = float(lat)
                    vals['longitude'] = float(lng)
                except (ValueError, TypeError):
                    pass

            Photo = request.env['supervision.photo']
            photo = Photo.create_from_portal(vals, partner, file_data)

            return request.redirect(f'/my/construction/{project_id}/photos?message=uploaded')

        return request.redirect(f'/my/construction/{project_id}/photo/upload?error=no_file')

    @http.route(['/my/construction/photo/upload/ajax'],
                type='json', auth='user', methods=['POST'])
    def portal_construction_photo_upload_ajax(self, **post):
        """AJAX: 單張照片上傳（批次上傳時逐張呼叫）"""
        import base64
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
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

        # 分類欄位
        if post.get('category'):
            vals['category'] = post['category']
        if post.get('construction_phase'):
            vals['construction_phase'] = post['construction_phase']
        if post.get('source_model'):
            vals['source_model'] = post['source_model']
        if post.get('location_description'):
            vals['location_description'] = post['location_description']

        # GPS
        lat = post.get('latitude')
        lng = post.get('longitude')
        if lat and lng:
            try:
                vals['latitude'] = float(lat)
                vals['longitude'] = float(lng)
            except (ValueError, TypeError):
                pass

        try:
            Photo = request.env['supervision.photo']
            photo = Photo.create_from_portal(vals, partner, photo_data)
            return {'success': True, 'photo_id': photo.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route(['/my/construction/photo/<int:photo_id>'],
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

    # ==================== 通報單（預約式）====================

    @http.route(['/my/construction/<int:project_id>/slips',
                 '/my/construction/<int:project_id>/slips/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_slips(self, project_id, page=1, **kw):
        """通報單列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if project.project_type != 'reservation':
            return request.redirect(f'/my/construction/{project_id}')

        Slip = request.env['reservation.notification.slip']
        domain = [('project_id', '=', project.id)]

        slip_count = Slip.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/slips',
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
            'default_url': f'/my/construction/{project_id}/slips',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_slips', values)

    @http.route(['/my/construction/<int:project_id>/slip/<int:slip_id>'],
                type='http', auth='user', website=True)
    def portal_construction_slip_detail(self, project_id, slip_id, **kw):
        """通報單詳情"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Slip = request.env['reservation.notification.slip']
        slip = Slip.search([
            ('id', '=', slip_id),
            ('project_id', '=', project.id),
        ], limit=1)
        if not slip:
            return request.redirect(f'/my/construction/{project_id}/slips')

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

    # ==================== 檔案管理 ====================

    @http.route(['/my/construction/<int:project_id>/documents',
                 '/my/construction/<int:project_id>/documents/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_documents(self, project_id, page=1, **kw):
        """檔案管理列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
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
            url=f'/my/construction/{project_id}/documents',
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
            'default_url': f'/my/construction/{project_id}/documents',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_documents', values)

    @http.route(['/my/construction/<int:project_id>/document/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_document_upload(self, project_id, **post):
        """文件上傳"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        uploaded_file = post.get('file')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read())

            # 建立 attachment
            attachment = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': file_data,
                'res_model': 'supervision.document',
                'type': 'binary',
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
                f'/my/construction/{project_id}/documents?message=uploaded'
            )

        return request.redirect(f'/my/construction/{project_id}/documents?error=no_file')

    # ==================== 新增專案 ====================

    @http.route(['/my/construction/project/new'],
                type='http', auth='user', website=True)
    def portal_construction_project_new(self, **kw):
        """新增工程專案表單"""
        # 從 query string 取得來源專案 ID，讓 breadcrumb 可以回首頁
        from_project_id = kw.get('from_project')
        back_url = '/my/construction'
        back_label = '工程列表'
        if from_project_id:
            try:
                pid = int(from_project_id)
                back_url = f'/my/construction/{pid}'
                back_label = '首頁'
            except (ValueError, TypeError):
                pass

        values = {
            'page_name': 'construction_project_new',
            'back_url': back_url,
            'back_label': back_label,
        }
        return request.render('construction_portal.portal_construction_project_new', values)

    @http.route(['/my/construction/project/create'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_project_create(self, **post):
        """建立工程專案"""
        from datetime import datetime as dt

        name = post.get('name', '').strip()
        if not name:
            return request.redirect('/my/construction/project/new?error=no_name')

        # 建立 Odoo 原生專案
        Project = request.env['project.project'].sudo()
        odoo_project = Project.create({
            'name': name,
        })

        # 建立監造專案
        SuperProject = request.env['supervision.project'].sudo()
        vals = {
            'project_id': odoo_project.id,
            'project_type': post.get('project_type', 'general'),
            'location': post.get('location', ''),
        }

        # 契約金額
        amount = post.get('amount', '').strip()
        if amount:
            try:
                vals['contract_amount'] = float(amount)
            except ValueError:
                pass

        # 契約工期
        duration = post.get('duration', '').strip()
        if duration:
            try:
                vals['contract_duration'] = int(duration)
            except ValueError:
                pass

        # 開工日期
        start_date = post.get('start_date', '').strip()
        if start_date:
            try:
                vals['contract_start_date'] = dt.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        # 預定竣工
        end_date = post.get('end_date', '').strip()
        if end_date:
            try:
                vals['contract_end_date'] = dt.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        # GPS
        lat = post.get('latitude', '').strip()
        lng = post.get('longitude', '').strip()
        if lat and lng:
            try:
                vals['latitude'] = float(lat)
                vals['longitude'] = float(lng)
            except ValueError:
                pass

        sup_project = SuperProject.create(vals)

        # 加入當前用戶為專案成員
        partner = request.env.user.partner_id
        try:
            request.env['supervision.project.member'].sudo().create({
                'project_id': sup_project.id,
                'partner_id': partner.id,
                'permission_level': 'admin',
            })
        except Exception:
            pass

        return request.redirect(f'/my/construction/{sup_project.id}')

    # ==================== 設定 ====================

    @http.route(['/my/construction/settings'],
                type='http', auth='user', website=True)
    def portal_construction_settings(self, **kw):
        """設定頁面"""
        partner = request.env.user.partner_id
        Project = request.env['supervision.project']
        domain = self._get_construction_projects_domain(partner)
        projects = Project.search(domain, order='name')

        # 從 query string 取得來源專案，讓 breadcrumb 可以回首頁
        from_project_id = kw.get('from_project')
        back_url = '/my/construction'
        back_label = '工程列表'
        if from_project_id:
            try:
                pid = int(from_project_id)
                back_url = f'/my/construction/{pid}'
                back_label = '首頁'
            except (ValueError, TypeError):
                pass

        values = {
            'user': request.env.user,
            'partner': partner,
            'projects': projects,
            'page_name': 'construction_settings',
            'back_url': back_url,
            'back_label': back_label,
        }

        return request.render('construction_portal.portal_construction_settings', values)

    @http.route(['/my/construction/switch-project'],
                type='http', auth='user', website=True)
    def portal_construction_switch_project(self, **kw):
        """切換工程（重導向到工程列表）"""
        return request.redirect('/my/construction')

    # ================================================================
    # 照片地圖
    # ================================================================

    @staticmethod
    def _haversine(lat1, lng1, lat2, lng2):
        """Haversine 公式計算兩點距離（公里）"""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(dlng / 2) ** 2)
        return R * 2 * math.asin(math.sqrt(a))

    def _portal_map_build_domain(self, project_id, post, require_gps=True):
        """建立照片地圖搜尋 domain（專案範圍）"""
        domain = [('active', '=', True), ('project_id', '=', project_id)]
        if require_gps:
            domain += [('latitude', '!=', 0), ('longitude', '!=', 0)]
        if post.get('source_model'):
            domain.append(('source_model', '=', post['source_model']))
        if post.get('category'):
            domain.append(('category', '=', post['category']))
        if post.get('construction_phase'):
            domain.append(('construction_phase', '=', post['construction_phase']))
        if post.get('date_from'):
            domain.append(('shot_date', '>=', post['date_from']))
        if post.get('date_to'):
            domain.append(('shot_date', '<=', post['date_to']))
        return domain

    def _portal_map_photo_to_marker(self, photo):
        """照片記錄轉為 marker 字典（輕量）"""
        return {
            'id': photo.id,
            'lat': photo.latitude,
            'lng': photo.longitude,
            'name': photo.name or '',
            'source_model': photo.source_model or 'other',
            'category': photo.category or '',
            'shot_date': str(photo.shot_date) if photo.shot_date else '',
            'thumbnail_url': (
                '/web/image/ir.attachment/%d/datas/80x80?crop=true' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'image_url': (
                '/web/image/ir.attachment/%d/datas' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'location_description': photo.location_description or '',
        }

    def _portal_map_photo_to_detail(self, photo, source_labels, category_labels):
        """照片記錄轉為詳情字典"""
        return {
            'id': photo.id,
            'name': photo.name or '',
            'lat': photo.latitude,
            'lng': photo.longitude,
            'category_label': category_labels.get(photo.category, photo.category or ''),
            'source_model': photo.source_model or '',
            'source_label': source_labels.get(photo.source_model, photo.source_model or ''),
            'shot_date': str(photo.shot_date) if photo.shot_date else '',
            'thumbnail_url': (
                '/web/image/ir.attachment/%d/datas/200x200?crop=true' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'image_url': (
                '/web/image/ir.attachment/%d/datas' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'location_description': photo.location_description or '',
        }

    @http.route(['/my/construction/<int:project_id>/photos/map'],
                type='http', auth='user', website=True)
    def portal_construction_photos_map(self, project_id, **kw):
        """照片地圖頁面"""
        try:
            project_sudo = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my/construction')

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
            'category': fields_info.get('category', {}).get('selection', []),
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

    @http.route(['/my/construction/<int:project_id>/photos/api/markers'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_markers(self, project_id, **post):
        """取得專案照片 markers"""
        try:
            self._document_check_access('supervision.project', project_id)
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

    @http.route(['/my/construction/<int:project_id>/photos/api/area-photos'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_area(self, project_id, **post):
        """取得地圖範圍內照片詳情"""
        try:
            self._document_check_access('supervision.project', project_id)
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

    @http.route(['/my/construction/<int:project_id>/photos/api/nearby'],
                type='json', auth='user', methods=['POST'])
    def portal_photos_map_nearby(self, project_id, **post):
        """取得附近照片（依距離排序）"""
        try:
            self._document_check_access('supervision.project', project_id)
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
