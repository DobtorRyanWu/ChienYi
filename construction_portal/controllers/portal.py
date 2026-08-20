# -*- coding: utf-8 -*-

import base64
import json
import logging
import math
from datetime import date, datetime, timedelta
from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.addons.construction_quality.models.defect_constants import CATEGORY_TO_CHECK_TYPE
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.osv.expression import AND
from werkzeug.exceptions import NotFound
from .portal_utils import (  # M4-a：共用工具抽出
    GROUP_BOSS, GROUP_MANAGER, GROUP_FIELD, GROUP_OBSERVER, GROUP_OPERATOR,
    _photo_category_options, _photo_category_to_id, _post_photo_meta,
    _portal_save_photos,
    _defect_save_photos, _portal_delete_photo, _portal_photo_to_supervision,
    _haversine_km,
)
from .portal_defect import DefectRoutesMixin  # M4-a：缺失路由 mixin
from .portal_inspection import InspectionRoutesMixin
from .portal_photo import PhotoRoutesMixin
from .portal_daily_log import DailyLogRoutesMixin
from .portal_misc import MiscRoutesMixin

_logger = logging.getLogger(__name__)


class ConstructionPortal(DefectRoutesMixin, InspectionRoutesMixin, PhotoRoutesMixin,
                         DailyLogRoutesMixin, MiscRoutesMixin, CustomerPortal):
    """
    工程監造系統 Portal Controller（v10）

    提供承包廠商 Portal 用戶存取:
    - 工程案件列表與首頁（HUD + 事件通知 + 排程）
    - 自主檢查填寫與查詢
    - 缺失改善提交
    - 照片上傳
    """

    # ==================== 角色權限 Guard（v11） ====================
    # 因前台 create/write 多走 .sudo()（會繞過 ir.rule / ir.model.access），
    # 「建專案/審核限老闆+主管」「現場人員只改自己建的」由以下 guard 在 controller 強制。

    def _can_manage(self):
        """老闆 / 主管 / 內部系統管理者 / 監造代操作員：可建專案、可審核"""
        user = request.env.user
        return (user.has_group(GROUP_BOSS) or user.has_group(GROUP_MANAGER)
                or user.has_group('base.group_system')
                or user.has_group(GROUP_OPERATOR))

    def _require_manage(self, msg=None):
        if not self._can_manage():
            raise AccessError(msg or _('權限不足：此操作限老闆或主管'))

    def _is_field_only(self):
        """現場人員（且非老闆/主管/內部）：寫入只能限自己建立的單據"""
        user = request.env.user
        if (user.has_group(GROUP_BOSS) or user.has_group(GROUP_MANAGER)
                or user.has_group('base.group_system')):
            return False
        return user.has_group(GROUP_FIELD)

    def _require_owner_or_manager(self, record):
        """現場人員只能編輯自己建立的記錄；老闆/主管/內部不受限"""
        if self._is_field_only() and record and record.sudo().create_uid.id != request.env.user.id:
            raise AccessError(_('您只能編輯自己建立的單據'))

    def _require_write(self, msg=None):
        """H1：禁止唯讀角色（定期閱覽者 / viewer / observer）建立或寫入單據。

        前台 create / upload 路由多走 .sudo()（繞過 ir.rule / ir.model.access），
        唯讀 viewer 仍可 POST 進來寫入 → 越權。放行條件：
        - 內部使用者（base.group_user：監造單位員工 / 系統管理者）一律放行；
        - 前台角色需現場人員（GROUP_FIELD）以上（含主管 / 老闆 / 代操作員）；
        - 僅純前台 viewer（只有 base.group_portal + viewer）被擋。
        """
        user = request.env.user
        if (user.has_group('base.group_user')
                or self._can_manage()
                or user.has_group(GROUP_FIELD)):
            return
        raise AccessError(msg or _('權限不足：閱覽角色不可建立或修改資料'))

    # ==================== 帶權限的照片供圖（M0.6） ====================
    # 取代 public=True 的裸 /web/content：附件不再 public，改由本端點以
    # 「登入者對照片所屬專案的可見範圍」把關，通過後 sudo 委派 Odoo 影像
    # pipeline（保留 resize/crop）。不在可見範圍一律 404（不洩漏存在性）。

    def _resolve_photo_project(self, att):
        """反解一張「前台照片」附件所屬的工程案件（project.project）。找不到回 None。

        刻意採**允許清單**：只認得四種前台照片綁定型別，不做泛用
        res_model→project_id 反解——否則本端點會淪為「任意附件下載器」，讓專案成員
        枚舉下載掛在專案上的非照片附件（chatter / 計價 / 簽章）。（M0.6 抗辯 finding）
        """
        env = request.env
        # 1) supervision.photo 綁定（_portal_save_photos 主流程、slip/test/inspection 關聯）
        photo = env['supervision.photo'].sudo().search(
            [('attachment_id', '=', att.id)], limit=1)
        if photo and photo.project_id:
            return photo.project_id
        # 2)（已移除）缺失改善照片行的 image 欄位附件。
        #    照片資料表收斂後，缺失照片就是 supervision.photo，第 1 步已涵蓋；
        #    兩個照片行模型與其欄位附件都不存在了。
        # 3) 被前台照片 m2m 直接引用：驗收缺失前/後照片
        #    （signboard 已收斂成 supervision.photo，同樣由第 1 步涵蓋）
        for model_name, field in (
                ('acceptance.defect', 'before_photo_ids'),
                ('acceptance.defect', 'after_photo_ids')):
            if model_name in env and field in env[model_name]._fields:
                rec = env[model_name].sudo().search([(field, 'in', att.id)], limit=1)
                if rec:
                    return rec.project_id
        return None

    def _user_can_see_project(self, project):
        """登入者是否可看到此工程案件（與 /construction 列表同一條可見性 domain）。"""
        if not project:
            return False
        partner = request.env.user.partner_id
        domain = request.env['project.project']._get_portal_projects_domain(partner)
        return bool(request.env['project.project'].sudo().search_count(
            [('id', '=', project.id)] + domain))


    def _resolve_document_project(self, att):
        """反解一個附件所屬的工程案件；反解不出來一律 None（→404）。

        2026-08-21：判斷依據從「掛在某筆 supervision.document 上」改成
        「附件本身的 supervision_project_id 有值」——前台檔案管理已改成直接讀
        ir.attachment（＝後台「檔案總覽」同一份資料），不再經過 supervision.document。

        **這仍然是允許清單，不是泛用反解。** 系統裡絕大多數附件
        （使用者頭像、公司 logo、郵件附件、報表暫存、樣板檔…）沒有這個欄位值，
        一律回 None → 404，端點不會淪為任意附件下載器。

        真正的權限把關在呼叫端的 `_user_can_see_project()`：
        看不到那個工程就 404（不洩漏存在性）。
        """
        if att.supervision_project_id:
            return att.supervision_project_id
        return None


    def _prepare_home_portal_values(self, counters):
        """Portal 首頁計數器"""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

        if 'construction_count' in counters:
            domain = request.env['project.project']._get_portal_projects_domain(partner)
            values['construction_count'] = request.env['project.project'].search_count(domain)

        return values

    def _get_construction_projects_domain(self, partner):
        """取得 Portal 用戶可存取的工程案件 domain"""
        return request.env['project.project']._get_portal_projects_domain(partner)

    def _get_project_day_count(self, project):
        """計算 DAY 天數（從開工日到今天；已竣工則凍結至實際完工日）

        含頭含尾：與 actual_duration 一致 = (end - start).days + 1
        """
        if not project.contract_start_date:
            return 0
        end_date = project.actual_end_date or date.today()
        delta = (end_date - project.contract_start_date).days
        return max(delta + 1, 0) if end_date >= project.contract_start_date else 0

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
            badges['def'] = request.env[self._defect_model(project)].search_count([
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
        try:
            badges['notif'] = self._get_notif_unread_count()
        except Exception:
            badges['notif'] = 0
        return badges

    # ==================== 前台通知中心 ====================

    def _portal_notif_domain(self):
        """當前前台使用者「被通知」的訊息（mail.message）domain。

        以 notified_partner_ids = 當前 partner 為界（每人只看自己的通知）、
        subtype = mail.mt_comment（construction 各模組發通知用的 subtype）。
        """
        partner = request.env.user.partner_id
        mt_comment = request.env.ref('mail.mt_comment')
        return [
            ('notified_partner_ids', 'in', partner.ids),
            ('subtype_id', '=', mt_comment.id),
        ]

    def _get_notif_unread_count(self):
        """未讀通知數 = 晚於使用者「上次查看時間」的通知（前台通知天生 is_read，故自建浮水印）。"""
        Message = request.env['mail.message'].sudo()
        domain = self._portal_notif_domain()
        last_seen = request.env.user.portal_notif_last_seen
        if last_seen:
            domain = domain + [('date', '>', last_seen)]
        return Message.search_count(domain)

    def _get_portal_notifications(self, limit=100):
        """使用者的通知清單（新到舊），每筆附前台記錄連結（access_url）。"""
        Message = request.env['mail.message'].sudo()
        msgs = Message.search(self._portal_notif_domain(), order='date desc', limit=limit)
        last_seen = request.env.user.portal_notif_last_seen
        items = []
        for m in msgs:
            url = None
            if m.model and m.res_id:
                try:
                    rec = request.env[m.model].sudo().browse(m.res_id)
                    if rec.exists():
                        if 'access_url' in rec._fields and rec.access_url:
                            url = rec.access_url
                        elif m.model in ('general.defect.improvement',
                                         'reservation.defect.improvement'):
                            # 前台缺失模型無 access_url，照 _browse_defect 的 /construction/defect/<id>
                            url = '/construction/defect/%s' % m.res_id
                except Exception:
                    url = None
            items.append({
                'msg': m,
                'url': url,
                'is_unread': bool(not last_seen or (m.date and m.date > last_seen)),
            })
        return items


    # ==================== Portal 首頁 override ====================

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        # portal user 看 /my 與 /my/home 等同 /construction(同 controller render v10 列表)
        # internal user 維持 Odoo 原生卡片牆,確保後台人員 portal 體驗不變
        user = request.env.user
        if user.has_group('base.group_portal') or not user.has_group('base.group_user'):
            return self.portal_my_construction_projects(**kw)
        return super().home(**kw)

    # ==================== /contactus 停用 ====================

    @http.route('/contactus', type='http', auth='public', website=True)
    def contactus_disabled(self, **kw):
        # 客服走另一個 Odoo 系統,本站不需要聯絡頁。
        # 注意:@http.route 回 not_found() 會被 website module 接住 fallback 渲染
        # website.page,所以改用 302 redirect 到首頁(已登入用戶會被首頁的 portal 邏輯
        # 接到 /construction)。navbar/footer 的「聯絡我們」連結另由 data XML 拔除。
        return request.redirect('/', code=302)

    # ==================== Legacy /my/construction* → /construction* (Phase 4) ====================

    @http.route(['/my/construction', '/my/construction/<path:subpath>'],
                type='http', auth='public', website=True)
    def my_construction_legacy_redirect(self, subpath=None, **kw):
        # 舊書籤、外部分享連結、E2E 既存 spec 仍打 /my/construction*,308 永久轉址保留 method
        target = '/construction' + (('/' + subpath) if subpath else '')
        qs = request.httprequest.query_string.decode()
        if qs:
            target += '?' + qs
        return request.redirect(target, code=308)

    # ==================== 工程案件 ====================

    @http.route(['/construction', '/construction/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_construction_projects(self, page=1, sortby=None, **kw):
        """工程案件入口

        行為:
        - `?view=list` 或翻頁(page>1) → 直接顯示列表頁
        - 0 個可見專案 → 顯示列表頁(空狀態)
        - 1 個可見專案 → server-side 直接 redirect 到該專案 HUD
        - 多個可見專案 → render GPS 定位中介頁(splash),
          由前端 JS 取得座標後 POST 到 /construction/nearest 拿最近專案 id 再跳轉
        """
        partner = request.env.user.partner_id
        Project = request.env['project.project']
        domain = self._get_construction_projects_domain(partner)

        force_list = kw.get('view') == 'list' or page > 1
        if not force_list:
            accessible = Project.search(domain)
            if not accessible:
                # 落到列表頁顯示空狀態
                pass
            elif len(accessible) == 1:
                return request.redirect('/construction/%s' % accessible.id)
            else:
                # v11.1: 純 GPS splash — 找到最近立刻 redirect。
                # 「手動列表」入口從 drawer 的「工程列表」走 /construction?view=list,
                # 跳過此 splash。
                return request.render(
                    'construction_portal.portal_construction_locator',
                    {'page_name': 'construction'},
                )

        return self._render_construction_list(page=page, sortby=sortby, **kw)

    def _render_construction_list(self, page=1, sortby=None, **kw):
        """工程案件列表(原 portal_my_construction_projects 邏輯)"""
        partner = request.env.user.partner_id
        Project = request.env['project.project']

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
            url='/construction',
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
            'default_url': '/construction',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        }

        return request.render('construction_portal.portal_my_construction_projects', values)

    @http.route(['/construction/nearest'], type='json', auth='user', website=True)
    def portal_construction_nearest(self, lat=None, lng=None, **kw):
        """回傳離使用者(lat,lng)最近、且使用者有權限的工程案件 id

        供 /construction 的 splash 頁前端呼叫。
        若沒有任何「有座標的」可見專案,回傳 {'project_id': None},
        前端應改導去 /construction?view=list。
        """
        try:
            user_lat = float(lat)
            user_lng = float(lng)
        except (TypeError, ValueError):
            return {'project_id': None}

        partner = request.env.user.partner_id
        Project = request.env['project.project']
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
        distance_km = _haversine_km(
            user_lat, user_lng, nearest.latitude, nearest.longitude,
        )
        return {
            'project_id': nearest.id,
            'project_name': nearest.name or '',
            'distance_km': round(distance_km, 2),
        }

    @http.route(['/construction/splash-preview'], type='http', auth='user', website=True)
    def portal_construction_splash_preview(self, **kw):
        """Splash 最終定格預覽頁（設計用）。
        預設：立即定格（所有元素在終態，不跑動畫、不 fadeout）。
        `?play=1`：播放一次動畫後停住不 fadeout。
        """
        return request.render('construction_portal.portal_construction_splash_preview', {
            'play_animation': kw.get('play') == '1',
        })

    @http.route(['/construction/<int:project_id>'],
                type='http', auth='user', website=True)
    def portal_construction_project_detail(self, project_id, **kw):
        """工程首頁（v10 HUD 設計）"""
        try:
            project = self._document_check_access(
                'project.project', project_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        today = date.today()

        # DAY 計數：(today - contract_start_date).days；已竣工凍結至 actual_end_date
        day_count = self._get_project_day_count(project)

        # 進度百分比：從 actual_progress 或計算
        progress_pct = project.actual_progress or 0.0

        # 逾期缺失
        overdue_defects = request.env[self._defect_model(project)].search([
            ('project_id', '=', project.id),
            ('state', 'not in', ['verified', 'closed']),
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
        open_defect_count = request.env[self._defect_model(project)].search_count([
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

    @http.route(['/construction/<int:project_id>/info'],
                type='http', auth='user', website=True)
    def portal_construction_project_info(self, project_id, **kw):
        """工程資訊頁面（底部導航第一 tab）"""
        try:
            project = self._document_check_access(
                'project.project', project_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # DAY 計數：已竣工則凍結至 actual_end_date
        day_count = self._get_project_day_count(project)

        # 工程進度：從進度表 cumulative_actual 取（= project.actual_progress）
        progress_pct = project.actual_progress or 0.0
        # 工期進度：已過天數佔總工期比例（含展延）
        total_duration = project.total_approved_duration or project.contract_duration or 0
        schedule_pct = (day_count / total_duration * 100.0) if total_duration else 0.0
        # 已竣工：剩餘工期 = 0（不再倒數）
        if project.actual_end_date:
            remaining = 0
        elif project.total_approved_duration:
            remaining = max(project.total_approved_duration - day_count, 0)
        else:
            remaining = 0

        values = {
            'project': project,
            'page_name': 'construction_info',
            'day_count': day_count,
            'progress_pct': progress_pct,
            'schedule_pct': schedule_pct,
            'remaining_days': remaining,
            'nav_badges': self._get_nav_badges(project),
        }

        return request.render('construction_portal.portal_construction_project_info', values)

    # ==================== 工程資訊編輯 ====================

    @http.route(['/construction/<int:project_id>/edit'],
                type='http', auth='user', website=True)
    def portal_construction_project_edit(self, project_id, **kw):
        """工程資訊編輯頁（補填/修改 supervision.project，僅 draft 狀態可用）"""
        try:
            project = self._document_check_access(
                'project.project', project_id,
                access_token=kw.get('access_token'),
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 僅允許 draft 編輯
        if project.state != 'draft':
            return request.redirect(
                f'/construction/{project_id}/info?error=not_draft'
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
        # 業主/承辦人已改為純文字欄位(authority_name)，無 per-project FK 關聯。
        # authorities 僅作為 datalist 的建議來源；承辦人建議列出各業主機關底下的聯絡人。
        authority_contacts = (
            Partner.search([('parent_id', 'in', authorities.ids)], order='name')
            if authorities
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
        year_field = env['project.project']._fields['year'].selection
        if callable(year_field):
            year_selection = year_field(env['project.project'])
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

    @http.route(['/construction/<int:project_id>/code/update'],
                type='json', auth='user', methods=['POST'])
    def portal_construction_project_code_update(self, project_id, **kw):
        """工程編號單欄位更新（inline edit，不受 state 限制）。

        為什麼獨立路由：完整 /update 強制 state=='draft' 才能改，
        但工程編號可能在標案匯入後、案件已開工才需要校正，
        因此 code 單欄位放寬限制。其他欄位仍走 /update + state guard。
        """
        try:
            project = self._document_check_access(
                'project.project', project_id,
            )
        except (AccessError, MissingError):
            return {'success': False, 'error': '無權限或案件不存在'}

        # H1：修改工程編號屬專案主檔異動，限老闆 / 主管
        if not self._can_manage():
            return {'success': False, 'error': '權限不足：僅老闆或主管可修改工程編號'}

        code = (kw.get('code') or '').strip()
        if not code:
            return {'success': False, 'error': '工程編號不可為空'}
        if len(code) > 64:
            return {'success': False, 'error': '工程編號最多 64 字元'}

        # 重複檢查（同編號不同案件視為衝突）
        Project = request.env['project.project'].sudo()
        dup = Project.search(
            [('code', '=', code), ('id', '!=', project_id)], limit=1,
        )
        if dup:
            return {
                'success': False,
                'error': f'工程編號「{code}」已被案件「{dup.name}」使用',
            }

        try:
            project.sudo().write({'code': code})
        except Exception as e:
            _logger.warning(
                'portal code update failed pid=%s: %s', project_id, e,
            )
            return {'success': False, 'error': str(e)}

        return {'success': True, 'code': code}

    @http.route(['/construction/<int:project_id>/update'],
                type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_construction_project_update(self, project_id, **post):
        """儲存工程資訊編輯"""
        try:
            project = self._document_check_access(
                'project.project', project_id,
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # H1：修改工程資訊限老闆 / 主管（現場人員不得改專案主檔）
        self._require_manage(_('僅老闆或主管可修改工程資訊'))

        if project.state != 'draft':
            return request.redirect(
                f'/construction/{project_id}/info?error=not_draft'
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
                pp = project.sudo()
                for _lang in ('zh_TW', 'en_US'):
                    try:
                        pp.with_context(lang=_lang).write({'name': name})
                    except Exception as _e:
                        _logger.warning('portal update: name lang=%s failed: %s', _lang, _e)

        if _in('code'):
            code = _s('code')
            if code:
                vals['code'] = code

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
        for _m2o in ('supervision_engineer_id', 'site_manager_id',
                     'activity_default_user_id', 'activity_test_user_id',
                     'activity_inspection_user_id'):
            if _in(_m2o):
                vals[_m2o] = _to_int(_m2o)

        # 業主/承辦人改為純文字欄位，直接存字串
        if _in('authority_name'):
            vals['authority_name'] = (post.get('authority_name') or '').strip()
        if _in('authority_contact_name'):
            vals['authority_contact_name'] = (post.get('authority_contact_name') or '').strip()

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
                f'/construction/{project_id}/edit?error=date_invalid'
            )

        # ---- 寫入 ----
        try:
            if vals:
                project.sudo().write(vals)
        except (ValidationError, UserError) as e:
            _logger.warning('portal project edit write failed: %s', e)
            return request.redirect(
                f'/construction/{project_id}/edit?error=save_failed'
            )
        except Exception:
            _logger.exception('portal project edit unexpected error')
            return request.redirect(
                f'/construction/{project_id}/edit?error=save_failed'
            )

        return request.redirect(
            f'/construction/{project_id}/info?message=updated'
        )

    # ==================== 施工日誌 ====================



    # ==================== 施工日誌批次匯入 (XLSM) ====================










    # ==================== 自主檢查 ====================




    # ==================== 自主檢查樣板庫管理（v11） ====================
    # 管理 self.inspection.type：全域樣板庫（project_id=False）+ 各工程專案層級樣板。
    # 瀏覽 / 下載 docx：全角色；新增 / 編輯 / 刪除 / 停用：限 _can_manage()（老闆 / 主管 / 內部）。

    def _inspection_type_categories(self):
        """工程類別 Selection 從 fields_get 拉（不寫死）"""
        return request.env['self.inspection.type'].fields_get(
            ['category'])['category']['selection']

    def _accessible_type_domain(self):
        """可見樣板 domain：全域(project_id=False) + 用戶可存取專案的 type。"""
        partner = request.env.user.partner_id
        proj_domain = self._get_construction_projects_domain(partner)
        proj_ids = request.env['project.project'].sudo().search(proj_domain).ids
        return ['|', ('project_id', '=', False), ('project_id', 'in', proj_ids)]

    def _get_visible_inspection_type(self, type_id):
        """取得使用者可見的樣板 record，不可見回 None。"""
        InspType = request.env['self.inspection.type'].sudo()
        rec = InspType.browse(type_id)
        if not rec.exists():
            return None
        # 用可見 domain 二次過濾（含已停用：active 預設過濾，故用 active_test=False）
        visible = InspType.with_context(active_test=False).search(
            AND([self._accessible_type_domain(), [('id', '=', type_id)]]))
        return rec if rec.id in visible.ids else None

    def _inspection_type_stage_groups(self, rec):
        """把 default_item_ids 依查驗段落分群，回傳 [{key,label,items}]（只留有項目的段落）。

        段落名稱是唯一真相來源（self.inspection.type.stage.name），
        前台不再有任何硬編的階段中文字。
        """
        groups = []
        for stage in rec.stage_ids:        # _order = 'sequence, id'
            items = rec.default_item_ids.filtered(lambda i, s=stage: i.stage_id == s)
            if items:
                groups.append({'key': stage.id, 'label': stage.name, 'items': items})
        orphans = rec.default_item_ids.filtered(lambda i: not i.stage_id)
        if orphans:
            groups.append({'key': 0, 'label': '未分段', 'items': orphans})
        return groups

    def _inspection_stage_groups(self, lines):
        """把逐項檢查列依段落分群，回傳 {stage_id or 0: {'label':…, 'items':[…]}}。

        lines 已由 _order='stage_sequence, sequence, id' 排好，
        dict 保序即得段落順序。
        """
        groups = {}
        for item in lines:
            key = item.stage_id.id or 0
            groups.setdefault(key, {
                'label': item.stage_id.name or '未分段',
                'items': [],
            })['items'].append(item)
        return groups





    def _save_inspection_type_items(self, rec, post):
        """依表單提交同步 default_item_ids：保留/更新提交的、刪除被移除的、新增新列。

        表單欄位慣例（idx 連續）：
          item_id_<idx>（既有列 id，空=新列）、item_name_<idx>、
          item_stage_<idx>（段落 id）、item_standard_<idx>、item_seq_<idx>
        """
        Item = request.env['self.inspection.type.item'].sudo()
        # 段落改成 m2o 後，POST 進來的是可被竄改的整數 id：
        # 未經白名單就寫入，等於允許把別的工程/類型的段落塞進本類型的項目。
        valid_stage_ids = rec.stage_ids.ids
        fallback_stage_id = valid_stage_ids[0] if valid_stage_ids else False
        submitted_ids = set()
        idx = 0
        while True:
            if post.get('item_name_%d' % idx) is None and \
                    post.get('item_id_%d' % idx) is None:
                # 連續 idx 中斷即結束（容忍中間空列）
                if idx > 0 and ('item_name_%d' % (idx + 1)) not in post and \
                        ('item_id_%d' % (idx + 1)) not in post:
                    break
                idx += 1
                if idx > 500:   # 安全上限，避免異常無限迴圈
                    break
                continue
            name = (post.get('item_name_%d' % idx) or '').strip()
            item_id = post.get('item_id_%d' % idx)
            raw_stage = (post.get('item_stage_%d' % idx) or '').strip()
            stage_id = int(raw_stage) if raw_stage.isdigit() else 0
            ivals = {
                'name': name,
                'stage_id': (stage_id if stage_id in valid_stage_ids
                             else fallback_stage_id),
                'check_standard': post.get('item_standard_%d' % idx) or '',
                'sequence': int(post.get('item_seq_%d' % idx) or ((idx + 1) * 10)),
                'type_id': rec.id,
            }
            if item_id:
                item = Item.browse(int(item_id))
                if item.exists() and item.type_id.id == rec.id:
                    if name:
                        item.write(ivals)
                        submitted_ids.add(item.id)
                    else:
                        item.unlink()      # 名稱清空＝刪除該列
            elif name:
                new_item = Item.create(ivals)
                submitted_ids.add(new_item.id)
            idx += 1
            if idx > 500:
                break
        # 刪除未出現在提交中的既有列
        for old in rec.default_item_ids:
            if old.id not in submitted_ids:
                old.unlink()











    # ==================== 預約式自主檢查 ====================







    # ==================== 缺失管理 ====================







    # ── 缺失改善：依工程類型選擇模型 ──
    def _defect_model(self, project):
        """一般式 → general.defect.improvement；預約式 → reservation.defect.improvement。

        supervision.defect（NCR）已整個移除：它是停用的第二套缺失模型（後台選單
        active="0"、全庫僅 1 筆測試資料），欄位/狀態機/編號規則與這兩個模型完全不共用。
        general 才承載監造實務所需欄位（每日編號、監造/營造 record_type、施工/安衛
        check_type、severity、罰款、複查、前中後三階段照片）。

        三條前台缺失匯入路由（defects/import、enrich、import-docx）現在也走本函式，
        不再各自硬寫模型，故匯入的缺失一定會出現在缺失列表。
        """
        if project and getattr(project, 'project_type', False) == 'reservation':
            return 'reservation.defect.improvement'
        return 'general.defect.improvement'

    def _browse_defect(self, defect_id, access_token=None):
        """以 id 取缺失（先一般式、後預約式）並做存取檢查。

        M1.4：缺失存取一律走登入（auth='user'）＋ ir.rule；general/reservation 缺失模型
        沒有 access_token 欄位，故不把 token 傳進 `_document_check_access`（改名解除撞名後
        本呼叫會落到 Odoo 原生版，帶 token 又缺欄位會 AttributeError）。access_token 參數
        保留簽章相容但不使用。
        """
        for model in ('general.defect.improvement',
                      'reservation.defect.improvement'):
            if request.env[model].sudo().browse(defect_id).exists():
                return self._document_check_access(model, defect_id)
        raise MissingError(_('找不到缺失紀錄'))







    # ==================== 照片管理 ====================







    # ==================== 通報單（預約式）====================



    # ==================== 檢試驗管制（C 2026-07-14）====================




    # ==================== 檔案管理 ====================



    # ==================== 新增專案 ====================

    @http.route(['/construction/project/new'],
                type='http', auth='user', website=True)
    def portal_construction_project_new(self, **kw):
        """新增工程專案表單"""
        # 從 query string 取得來源專案 ID，讓 breadcrumb 可以回首頁
        from_project_id = kw.get('from_project')
        back_url = '/construction'
        back_label = '工程列表'
        if from_project_id:
            try:
                pid = int(from_project_id)
                back_url = f'/construction/{pid}'
                back_label = '首頁'
            except (ValueError, TypeError):
                pass

        values = {
            'page_name': 'construction_project_new',
            'back_url': back_url,
            'back_label': back_label,
        }
        return request.render('construction_portal.portal_construction_project_new', values)

    @http.route(['/construction/project/create'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_project_create(self, **post):
        """建立工程專案（限老闆或主管）"""
        from datetime import datetime as dt

        # 角色 guard：僅老闆/主管/內部可新增專案
        self._require_manage(_('僅老闆或主管可新增工程專案'))

        name = post.get('name', '').strip()
        if not name:
            return request.redirect('/construction/project/new?error=no_name')

        # 建立 Odoo 原生專案
        Project = request.env['project.project'].sudo()
        odoo_project = Project.create({
            'name': name,
        })

        # 建立監造專案
        SuperProject = request.env['project.project'].sudo()
        vals = {
            'project_id': odoo_project.id,
            'project_type': post.get('project_type', 'general'),
            'location': post.get('location', ''),
        }

        # 管理公司（自由輸入）
        management_company_name = post.get('management_company_name', '').strip()
        if management_company_name:
            vals['management_company_name'] = management_company_name

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

        # 加入建立者為專案參與成員（逐帳號可見性；建立者本人才看得到自己剛建的專案）
        request.env['supervision.project.member'].sudo().create({
            'project_id': sup_project.id,
            'user_id': request.env.user.id,
        })

        return request.redirect(f'/construction/{sup_project.id}')

    # ==================== 前台審核（限老闆 + 主管，v11） ====================
    # 每個審核動作 = 一條 POST route → _require_manage() 守 → 呼叫 model 的 action 方法。
    # 以建立者本人身分呼叫（boss/manager 透過 implied 舊群組已具寫入 ACL），
    # 故 action 內 self.env.uid 設定的審核人欄位（verifier_id/supervisor_id…）歸屬正確。
    # 範圍：先以可存取的工程/單據過濾（_document_check_access / search by project），
    # 非成員專案的單據抓不到 → 自然擋住。

    def _run_review_action(self, record, method, ok_url, err_url):
        """共用：守門 + 呼叫審核動作 + 導回（攔 UserError/ValidationError 顯示訊息）"""
        self._require_manage(_('僅老闆或主管可審核'))
        if not record:
            return request.redirect(err_url)
        try:
            getattr(record, method)()
        except (UserError, ValidationError) as e:
            from urllib.parse import quote
            return request.redirect(f'{err_url}?error={quote(str(e))}')
        return request.redirect(f'{ok_url}?msg=reviewed')











    # ==================== 設定 ====================

    @http.route(['/construction/settings'],
                type='http', auth='user', website=True)
    def portal_construction_settings(self, **kw):
        """個人帳號入口 — v11 起併入 Odoo 原生 /my/account,直接 redirect。
        Drawer user block 已直接連 /my/account,此路由保留作舊書籤/外部連結相容。"""
        return request.redirect('/my/account')

    @http.route(['/construction/switch-project'],
                type='http', auth='user', website=True)
    def portal_construction_switch_project(self, **kw):
        """切換工程（重導向到工程列表）"""
        return request.redirect('/construction')

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
            domain.append(('category_id', '=', _photo_category_to_id(post['category'])))
        if post.get('construction_phase'):
            domain.append(('construction_phase', '=', post['construction_phase']))
        if post.get('date_from'):
            domain.append(('shot_date', '>=', post['date_from']))
        if post.get('date_to'):
            domain.append(('shot_date', '<=', post['date_to']))
        # 全文搜尋:照片說明 / 檔案名稱 / 位置敘述
        search_q = (post.get('search') or '').strip()
        if search_q:
            domain += ['|', '|',
                       ('name', 'ilike', search_q),
                       ('image_filename', 'ilike', search_q),
                       ('location_description', 'ilike', search_q)]
        return domain

    def _portal_map_photo_to_marker(self, photo):
        """照片記錄轉為 marker 字典（輕量）"""
        return {
            'id': photo.id,
            'lat': photo.latitude,
            'lng': photo.longitude,
            'name': photo.name or '',
            'source_model': photo.source_model or 'other',
            'category': photo.category_id.name or photo.category or '',
            'shot_date': str(photo.shot_date) if photo.shot_date else '',
            'thumbnail_url': (
                '/construction/img/%d/80x80?crop=true' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'image_url': (
                '/construction/img/%d' % photo.attachment_id.id
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
            'category_label': photo.category_id.name or category_labels.get(photo.category, photo.category or ''),
            'source_model': photo.source_model or '',
            'source_label': source_labels.get(photo.source_model, photo.source_model or ''),
            'shot_date': str(photo.shot_date) if photo.shot_date else '',
            'thumbnail_url': (
                '/construction/img/%d/200x200?crop=true' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'image_url': (
                '/construction/img/%d' % photo.attachment_id.id
                if photo.attachment_id else ''
            ),
            'location_description': photo.location_description or '',
        }





    # ==================== 工期展延（action_extend_lines）====================

