# -*- coding: utf-8 -*-

import base64
import json
import logging
import math
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.addons.portal.controllers.thread import ThreadController as PortalThreadController
from odoo.addons.construction_quality.models.defect_constants import CATEGORY_TO_CHECK_TYPE
from odoo.addons.construction_supervision_base.utils.local_date import local_today
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.osv.expression import AND
from werkzeug.exceptions import NotFound
from ..models.mail_thread import PORTAL_COMMENT_MODELS
from .portal_utils import (  # M4-a：共用工具抽出
    GROUP_BOSS, GROUP_MANAGER, GROUP_FIELD, GROUP_OBSERVER, GROUP_OPERATOR,
    _photo_category_options, _photo_category_to_id, _post_photo_meta,
    _portal_save_photos,
    _defect_save_photos, _portal_delete_photo, _portal_photo_to_supervision,
    _portal_flash_url, _portal_flash_code, _portal_error_message,
    _haversine_km,
)
from .portal_defect import DefectRoutesMixin  # M4-a：缺失路由 mixin
from .portal_inspection import InspectionRoutesMixin
from .portal_photo import PhotoRoutesMixin
from .portal_daily_log import DailyLogRoutesMixin
from .portal_misc import MiscRoutesMixin
from .portal_water_level import WaterLevelRoutesMixin

_logger = logging.getLogger(__name__)


# 缺失網址 ?model= 的對照（P11）：一般式與預約式的 id 各自編號會撞
DEFECT_MODEL_PARAMS = {
    'general': 'general.defect.improvement',
    'reservation': 'reservation.defect.improvement',
}


class ConstructionPortal(DefectRoutesMixin, InspectionRoutesMixin, PhotoRoutesMixin,
                         DailyLogRoutesMixin, MiscRoutesMixin, WaterLevelRoutesMixin,
                         CustomerPortal):
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

    # S2（2026-11-11）：下面這些守衛的「誰可以」全部呼叫 res.users 的 _portal_* 函式（construction_supervision_base
    # models/res_users.py，全系統各只有一份）；模板裡的按鈕顯示條件呼叫同一個函式，畫面與路由不會分岔。
    # 後台角色帳號（內部帳號、沒有前台角色群組）的手機能力也由那裡推出（範圍合格才有）。

    def _can_manage(self):
        """老闆 / 主管 / 內部系統管理者 / 監造代操作員（含後台角色帳號的老闆、主管）：可建專案、可審核"""
        return request.env.user._portal_can_manage()

    def _require_manage(self, msg=None):
        if not self._can_manage():
            raise AccessError(msg or _('權限不足：此操作限老闆或主管'))

    def _is_field_only(self):
        """現場人員（且非老闆/主管/內部）：寫入只能限自己建立的單據"""
        return request.env.user._portal_is_field_only()

    def _require_owner_or_manager(self, record):
        """現場人員只能編輯自己建立的記錄；老闆/主管/內部不受限；沒有紀錄（新建）放行。
        判斷＝res.users._portal_owns_or_may_edit()（全系統一份；模板的按鈕經 _portal_can_edit_record 呼叫同一支）。"""
        if not request.env.user._portal_owns_or_may_edit(record):
            raise AccessError(_('您只能編輯自己建立的單據'))

    def _require_write(self, msg=None):
        """H1：禁止唯讀角色（定期閱覽者 / viewer / observer）建立或寫入單據。

        前台 create / upload 路由多走 .sudo()（繞過 ir.rule / ir.model.access），
        唯讀 viewer 仍可 POST 進來寫入 → 越權。放行條件＝res.users._portal_can_write()：
        - 監造方內部帳號（_is_supervision_side()：監造單位員工 / 系統管理者）一律放行；
          營造廠主管（後台唯讀帳號）與控台讀取帳號雖是內部帳號，不在此列（公司儀表板合約 §3.6）；
        - 前台角色需現場人員以上（含主管 / 老闆 / 代操作員；後台角色帳號照它的層級，範圍合格才算）；
        - 僅純前台 viewer（只有 base.group_portal + viewer）被擋。
        """
        if not request.env.user._portal_can_write():
            raise AccessError(msg or _('權限不足：閱覽角色不可建立或修改資料'))

    def _require_photo_deleter(self, photos, msg=None):
        """刪除照片：只有上傳者本人與管理層級可以刪（閱覽者已被 _require_write 擋在前面）。

        管理層級＝_can_manage()（老闆／主管／系統管理者／代操作員）；監造方內部帳號
        （_is_supervision_side()，監造單位員工）比照 _require_write 放行（res.users._portal_can_delete_others_photos）。
        其餘（現場人員）只能刪自己上傳的：supervision.photo／ir.attachment 的 create_uid 就是上傳者
        （前台上傳雖用 sudo，sudo 不改 uid）。
        photos 可為多筆，必須全部是自己上傳的；空集合視為沒有東西要刪，放行。
        sudo 只讀 create_uid，範圍是呼叫端已通過 _document_check_access 的那張單據上的照片。
        """
        user = request.env.user
        if user._portal_can_delete_others_photos():
            return
        if all(p.sudo().create_uid.id == user.id for p in photos):
            return
        raise AccessError(msg or _('權限不足：只有上傳者本人或老闆／主管可以刪除照片'))

    def _require_attachment_photo_deleter(self, attachment_id):
        """同 _require_photo_deleter，但以附件 id 指定（日誌／檢查的刪除路由用附件 id）。
        對應到 supervision.photo 就看照片的上傳者；沒有照片行的孤兒附件看附件的建立者。"""
        photos = request.env['supervision.photo'].sudo().with_context(
            active_test=False).search([('attachment_id', '=', attachment_id)])
        if photos:
            return self._require_photo_deleter(photos)
        att = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        return self._require_photo_deleter(att)

    # ==================== 營造方範圍（公司儀表板合約 §3.6） ====================
    # 受限帳號＝營造方（res.users._dash_is_contractor_side()：後台營造廠主管、前台營造組織帳號）
    # ＋控台讀取帳號（_dash_is_console_reader()；隱含 base.group_user，不擋就會被當成監造方，合約 §0b-24）
    # ＋後台角色帳號（_is_role_account()；S1 2026-11-10：內部帳號，不擋就會被當成監造方後台人員）。
    # 前台路由大量用 sudo 列出、取出、寫入營造廠層級紀錄（日誌、照片、缺失、檢查…），
    # sudo 不走 ir.rule，營造廠範圍規則（construction_company_dashboard/models/rule_scope.py）
    # 就被繞過。下面幾個方法讓 sudo 查出來的紀錄對受限帳號「以本人身分再過一次 ir.rule」：
    # 範圍條件只有規則那一份，這裡不另寫一套（控台讀取帳號在規則裡框架以外全拒＝什麼都看不到）。
    # 監造方一律原樣放行（行為與原本相同）。

    def _dash_is_restricted(self):
        """登入者是受限帳號（大集合）——讀取要「以本人身分再過一次 ir.rule」的那些（判定只看帳號本身，不因 sudo 跳過）。

        ＝res.users._dash_is_restricted()（全系統唯一一份）：營造方、控台讀取、後台角色帳號（含監造方角色帳號）。
        「審核類動作要擋營造方」不要用這個（監造方角色帳號不是營造方），用 _dash_is_contractor_or_console()（小集合）。
        （fix1-F：原名 _dash_is_contractor()，名稱與意思顛倒，已刪。）
        """
        return request.env.user._dash_is_restricted()

    def _dash_is_contractor_or_console(self):
        """登入者是營造方或控台讀取帳號（小集合）＝res.users._dash_is_contractor_or_console()（全系統只有那一份）。

        給「這件事限監造單位」的判斷用（審核、結案、解鎖、工程主檔、自動補建樣板／工項）：
        監造方角色帳號不算營造方，不能在這裡被擋下（S1 規格 §2.9）。
        """
        return request.env.user._dash_is_contractor_or_console()

    def _require_not_contractor(self, msg=None):
        """審核類動作（合約 §3.6 寫入矩陣）：營造方（與控台讀取）一律拒；監造方（含監造方角色帳號）照原本的守衛。"""
        if self._dash_is_contractor_or_console():
            raise AccessError(msg or _('權限不足：此操作限監造單位，營造廠帳號不能執行'))

    def _require_review(self, manage_msg=None, contractor_msg=None):
        """審核類（限監造單位）路由的守衛：先問管理權、再問是不是營造方／控台讀取（訊息與順序照舊）。

        能不能做＝res.users._portal_review_visible()，按鈕的顯示條件呼叫同一個函式（S2：畫面與路由同一個判斷）。
        """
        if request.env.user._portal_review_visible():
            return
        self._require_manage(manage_msg)          # 沒有管理權：管理權的訊息
        self._require_not_contractor(contractor_msg)
        raise AccessError(contractor_msg or _('權限不足：此操作限監造單位，營造廠帳號不能執行'))

    def _require_edit_project_info(self):
        """能不能編輯工程資訊的那把尺（全檔只有這一份；fix3-T）：限老闆／主管，而且不是營造方／控台讀取。

        編輯頁 GET、存檔 POST、工程資訊頁的「編輯」按鈕（_can_edit_project_info）都用它，三處才不會分岔
        （fix1-F 修的就是 GET 與 POST 分岔：GET 頁以 sudo 列出全庫內部帳號與公司，存不了就不該看）。
        順序與訊息照舊：先問管理權、再問是不是營造方。草稿狀態由呼叫端另外判斷。
        """
        # 工程主檔與營造廠清單：營造方不能改（公司儀表板合約 §3.6 寫入矩陣；契約「乙方不得自行變更本契約」）
        self._require_review(_('僅老闆或主管可修改工程資訊'),
                             _('權限不足：工程資訊由監造單位維護，營造廠帳號不能修改'))

    def _can_edit_project_info(self):
        """工程資訊頁的「編輯」按鈕（fix2-O）：與編輯頁 GET 同一把尺（_require_edit_project_info）。"""
        try:
            self._require_edit_project_info()
        except AccessError:
            return False
        return True

    def _require_other_data_visible(self, msg=None):
        """「其他」類資料的前台頁（例：水位）：res.users._portal_other_data_visible() 為否就拒。

        營造方、控台讀取一律拒；監造方（含範圍合格的監造方角色帳號，S2：舊的前台監造帳號本來看得到）放行。
        抽屜入口（portal_templates.xml）呼叫同一個函式。
        """
        if not request.env.user._portal_other_data_visible():
            raise AccessError(msg or _('權限不足：您的帳號看不到這類資料'))

    def _dash_visible(self, records):
        """營造方：只留下本人身分讀得到的紀錄（套 ir.rule 範圍）；監造方原樣回傳。

        回傳的紀錄保留原本的 env（呼叫端通常是 sudo，後續讀關聯欄位照舊），順序不變。
        """
        if not records or not self._dash_is_restricted():
            return records
        allowed = set(records.with_user(request.env.user)._filtered_access('read').ids)
        return records.browse([rid for rid in records.ids if rid in allowed])

    def _dash_search(self, model, domain, count=False, **kwargs):
        """sudo 查詢的營造方版本：營造方改以本人身分查（ir.rule 範圍在資料庫層套用，
        分頁與筆數才會對），結果再換回 sudo 紀錄；監造方照原本 sudo 查。"""
        Model = request.env[model].sudo()
        if self._dash_is_restricted():
            Scoped = Model.with_user(request.env.user)
            if count:
                return Scoped.search_count(domain)
            return Model.browse(Scoped.search(domain, **kwargs).ids)
        if count:
            return Model.search_count(domain)
        return Model.search(domain, **kwargs)

    def _dash_attachments_visible(self, attachments):
        """營造方看得到的附件：依來源單據判定（同 ir.attachment 的核心原則）。

        - 沒有來源單據（res_model／res_id 空）＝掛在工程上的文件：看得到工程就看得到
          （呼叫端已用 _user_can_see_project 確認過工程）；
        - 有來源單據：以本人身分讀得到那張單據才看得到（營造廠層級單據只有自家的、
          「其他」類單據一律看不到）；來源模型不存在一律看不到。
        前台帳號不能直接對 ir.attachment 做存取檢查（核心對非內部帳號一律拒），所以查來源單據。
        監造方原樣回傳。
        """
        if not attachments or not self._dash_is_restricted():
            return attachments
        user = request.env.user
        by_model = {}
        for att in attachments:
            if att.res_model and att.res_id:
                by_model.setdefault(att.res_model, set()).add(att.res_id)
        allowed = set()
        for model, res_ids in by_model.items():
            if model not in request.env:
                continue
            sources = request.env[model].sudo().browse(list(res_ids)).exists()
            allowed |= {(model, rid) for rid in sources.with_user(user)._filtered_access('read').ids}
        return attachments.filtered(
            lambda a: not (a.res_model and a.res_id) or (a.res_model, a.res_id) in allowed)

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
        source = self._resolve_photo_source(att)
        return source.project_id if source else None

    def _dash_photo_attachment_visible(self, att):
        """取圖端點的營造方檢查（公司儀表板合約 §3.6）：附件的來源紀錄要以本人身分讀得到。

        監造方一律 True（照原本只看工程）。營造方：照片紀錄（營造廠層級）只有自家的看得到；
        驗收缺失前／後照片（驗收歸「其他」類）一律看不到。
        """
        if not self._dash_is_restricted():
            return True
        source = self._resolve_photo_source(att)
        return bool(source) and bool(self._dash_visible(source))

    def _resolve_photo_source(self, att):
        """反解前台照片附件的來源紀錄（supervision.photo 或驗收缺失），找不到回 None。允許清單同上。"""
        env = request.env
        # 1) supervision.photo 綁定（_portal_save_photos 主流程、slip/test/inspection 關聯）
        photo = env['supervision.photo'].sudo().search(
            [('attachment_id', '=', att.id)], limit=1)
        if photo and photo.project_id:
            return photo
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
                    return rec
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
                            # P11：預約式帶 ?model=，避免 id 撞到同號的一般式缺失
                            if m.model == 'reservation.defect.improvement':
                                url += '?model=reservation'
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
        # portal user 看 /my 與 /my/home 等同 /construction(同 controller render v10 列表)；
        # 後台角色帳號（S2）比照前台帳號（手機首頁）。其他 internal user 維持 Odoo 原生卡片牆,確保後台人員 portal 體驗不變
        if request.env.user._portal_uses_phone_home():
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

        # 台灣日期：今日日誌、今日照片（shot_date 已是台灣日期）、本週排程都用它（公司儀表板合約 §5.3）
        today = local_today()

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
                # sudo 只讀：前台帳號沒有 project.task 讀權；schedule 已由非 sudo 查詢限定在本專案
                weekly_lines = schedule.sudo().line_ids
                week_display = schedule.week_display or ''
                # 組合本週目標文字
                task_names = [l.task_name or l.task_id.name for l in weekly_lines if l.task_name or l.task_id]
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
                # 退單（作廢）的通報單編號保留但不是實際派工，首頁不列、不計數
                active = [('project_id', '=', project.id), ('state', '!=', 'cancelled')]
                slip_count = Slip.search_count(active)
                recent_slips = Slip.search(active, limit=5, order='slip_no desc')
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
            # P5：工期展延入口只給老闆／主管（與路由 _require_manage 同一把尺）
            'can_manage': self._can_manage(),
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
            # 「編輯」按鈕與編輯頁 GET 同一把尺（fix2-O）
            'can_edit_info': self._can_edit_project_info(),
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
        # 與存檔 POST、工程資訊頁的編輯按鈕同一把尺（fix1-F、fix3-T）：頁上用 sudo 列出全庫內部帳號與公司，存不了就不該看
        self._require_edit_project_info()

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

        # 監造 / 承包公司、使用者下拉：與存檔 POST 的驗證同一份（_project_edit_options；F，S2）
        options = self._project_edit_options(project)
        supervision_companies = options['supervision_companies']
        contractor_companies = options['contractor_companies']
        all_users = options['all_users']
        supervision_users = options['supervision_users']

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

    # ==================== 工程資訊的可選值（F，S2：jt 共用庫的跨公司寫入） ====================
    # 編輯頁的下拉與存檔 POST 的驗證都用這一份（畫面與後端同一個判斷）。存檔以 sudo 寫 company_id、承攬廠商、
    # 使用者 id；jt 是多家監造公司共用一個庫，不驗的話帶別家公司的 id 就寫得進去。
    # - 監造公司：公司類型＝監造（沒有分類過時退回全部公司），而且在本人的允許公司內；工程目前的公司照留（沒改不算寫入）。
    # - 承攬廠商（營造廠）：照舊前台規則＝公司類型是營造廠（沒有分類過時退回全部公司）；工程目前的照留。
    # - 使用者（工地主任、活動負責人）：內部帳號，而且至少有一家允許公司跟本人重疊；目前的值照留。
    # - 監造工程師：上面那些裡面的監造方後台人員（_is_backend_staff），而且屬於工程（存檔後）的公司。
    # 前台帳號、後台角色帳號、代操作員都適用。
    def _project_edit_options(self, project, company=None):
        env = request.env
        user = env.user
        Company = env['res.company'].sudo()
        allowed_companies = user.sudo().company_ids
        supervision_companies = Company.search([('company_type', '=', 'supervision')], order='name') \
            or Company.search([], order='name')
        supervision_companies = (supervision_companies & allowed_companies) | project.company_id
        contractor_companies = Company.search([('company_type', '=', 'contractor')], order='name') \
            or Company.search([], order='name')
        contractor_companies |= project.contractor_company_ids
        Users = env['res.users'].sudo()
        current_users = (project.supervision_engineer_id | project.site_manager_id
                         | project.activity_default_user_id | project.activity_test_user_id
                         | project.activity_inspection_user_id).sudo()
        all_users = Users.search([('share', '=', False), ('company_ids', 'in', allowed_companies.ids)], order='name')
        # 監造工程師下拉：只列監造方後台人員——營造廠主管、控台讀取、後台角色帳號也是內部帳號（share=False），
        # 不濾掉會被選成監造工程師（S1）。工地主任、活動負責人用 all_users，照 S1 之前（fix1-D：工地主任本來就是營造方的人）
        company = company if company is not None else project.company_id
        supervision_users = all_users.filtered(lambda u: u._is_backend_staff())
        if company:
            supervision_users = supervision_users.filtered(lambda u: company in u.company_ids)
        return {
            'supervision_companies': supervision_companies,
            'contractor_companies': contractor_companies,
            'all_users': all_users | (current_users - project.supervision_engineer_id),
            'supervision_users': supervision_users | project.supervision_engineer_id.sudo(),
        }

    def _check_project_edit_vals(self, project, vals):
        """存檔 POST 的值必須在 _project_edit_options 的可選值內，否則 AccessError（不寫任何東西）。"""
        company = project.company_id
        if vals.get('company_id'):
            company = request.env['res.company'].sudo().browse(vals['company_id'])
        options = self._project_edit_options(project, company=company)
        denied = _('權限不足：選的公司或人員不在您帳號的允許範圍內')
        if vals.get('company_id') and company not in options['supervision_companies']:
            raise AccessError(denied)
        for command in vals.get('contractor_company_ids') or []:
            ids = command[2] if command[0] == 6 else [command[1]]
            if set(ids) - set(options['contractor_companies'].ids):
                raise AccessError(denied)
        user_options = {
            'supervision_engineer_id': options['supervision_users'],
            'site_manager_id': options['all_users'],
            'activity_default_user_id': options['all_users'],
            'activity_test_user_id': options['all_users'],
            'activity_inspection_user_id': options['all_users'],
        }
        for field_name, allowed in user_options.items():
            if vals.get(field_name) and vals[field_name] not in allowed.ids:
                raise AccessError(denied)

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

        # H1：修改工程編號屬專案主檔異動，限老闆 / 主管；營造方不能改（公司儀表板合約 §3.6 寫入矩陣，
        # hypothesis：契約無明文）。與工程資訊頁的「編輯工程編號」按鈕同一把尺：_require_review
        try:
            self._require_review(_('權限不足：僅老闆或主管可修改工程編號'),
                                 _('權限不足：工程編號由監造單位維護，營造廠帳號不能修改'))
        except AccessError as exc:
            return {'success': False, 'error': str(exc.args[0])}

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
            # G（S2）：只說編號已被使用，不帶出別的工程名稱與公司（jt 共用庫裡那可能是別家的工程，dup 是 sudo 查到的）
            return {
                'success': False,
                'error': f'工程編號「{code}」已被使用，請換一個編號',
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

        # H1：修改工程資訊限老闆／主管、營造方不能改（與編輯頁 GET 同一把尺，fix3-T）
        self._require_edit_project_info()

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
        # 名稱在下面的驗證（F）通過之後才寫（驗證失敗不能留下改到一半的名稱）
        pending_name = _s('name') if _in('name') else ''

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
        # F（S2）：sudo 寫入前驗證公司、承攬廠商、使用者 id 都在可選值內（與編輯頁下拉同一份），不合就 AccessError
        self._check_project_edit_vals(project, vals)
        if pending_name:
            pp = project.sudo()
            for _lang in ('zh_TW', 'en_US'):
                try:
                    pp.with_context(lang=_lang).write({'name': pending_name})
                except Exception as _e:
                    _logger.warning('portal update: name lang=%s failed: %s', _lang, _e)
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
    # 瀏覽 / 下載 docx：全角色；新增 / 編輯 / 刪除 / 停用：限內部帳號（千溢／代操）。
    # 2026-11-04 使用者裁示：前台帳號（含營造廠老闆／主管）只能看和下載——全域樣板
    # 全庫的工程共用，不能交給其中一家營造廠改。

    def _can_manage_inspection_types(self):
        # 限監造方後台人員：營造方（含後台營造廠主管）、後台角色帳號、前台帳號都只能看和下載（公司儀表板合約 §3.6）
        return self._can_manage() and request.env.user._is_backend_staff()

    def _require_manage_inspection_types(self):
        if not self._can_manage_inspection_types():
            raise AccessError(_('權限不足：自主檢查樣板由監造／代操管理，前台帳號只能檢視與下載'))

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

    def _defect_url(self, defect, suffix='', **params):
        """缺失網址。預約式一律帶 model，兩模型 id 會撞（見 _browse_defect）。"""
        if defect._name == 'reservation.defect.improvement':
            params = {'model': 'reservation', **params}
        query = f'?{urlencode(params)}' if params else ''
        return f'/construction/defect/{defect.id}{suffix}{query}'

    def _browse_defect(self, defect_id, access_token=None):
        """以 id 取缺失（先一般式、後預約式）並做存取檢查。

        M1.4：缺失存取一律走登入（auth='user'）＋ ir.rule；general/reservation 缺失模型
        沒有 access_token 欄位，故不把 token 傳進 `_document_check_access`（改名解除撞名後
        本呼叫會落到 Odoo 原生版，帶 token 又缺欄位會 AttributeError）。access_token 參數
        保留簽章相容但不使用。

        P11：兩個模型的 id 各自編號會撞。網址帶 ?model=general／reservation 時只查指定的
        那個模型；沒帶（或值不認得）維持舊行為先一般式後預約式，已發出的舊連結不會壞。
        """
        models = ('general.defect.improvement', 'reservation.defect.improvement')
        hint = DEFECT_MODEL_PARAMS.get(request.httprequest.args.get('model'))
        for model in ((hint,) if hint else models):
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
        """新增工程專案表單（限老闆或主管，與 POST、抽屜／快速新增的「新增專案」入口同一把尺：_require_review）"""
        # 建工程＝建工程主檔：營造方不能（公司儀表板合約 §3.6：營造方只能建立自家的營造廠層級紀錄）
        self._require_review(_('僅老闆或主管可新增工程專案'),
                             _('權限不足：工程由監造單位建立，營造廠帳號不能新增工程'))
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

        # 角色 guard：僅老闆/主管/內部可新增專案，營造方不能（與表單頁同一把尺）
        self._require_review(_('僅老闆或主管可新增工程專案'),
                             _('權限不足：工程由監造單位建立，營造廠帳號不能新增工程'))

        name = post.get('name', '').strip()
        if not name:
            return request.redirect('/construction/project/new?error=no_name')

        # 工程案件＝原生 project.project（監造欄位直接擴充在上面，沒有另一層「監造專案」）。
        # 原本先建一筆原生專案、再用 project_id 建「監造專案」，合併後 project.project 沒有
        # project_id 欄位，這條路由整個 ValueError（P4 實測發現）。
        SuperProject = request.env['project.project'].sudo()
        # F（S2）：工程的公司明寫成目前選的公司 request.env.company（不靠 sudo 建立時的預設值）。
        # 它一定在本人的允許公司內：核心 Environment.company 對非 sudo 的環境，選了允許公司以外的公司（cids）直接 AccessError
        # （odoo/api.py company；tests/test_role_phone_portal.py 實測）。sudo 建立不看任何規則，所以公司只能取自非 sudo 的 env
        vals = {
            'name': name,
            'company_id': request.env.company.id,
            'project_type': post.get('project_type', 'general'),
            'location': post.get('location', ''),
        }

        # P4：業主機關、承包廠商（表單欄位 owner_org／contractor，純文字）
        owner_org = post.get('owner_org', '').strip()
        if owner_org:
            vals['authority_name'] = owner_org
        contractor = post.get('contractor', '').strip()
        if contractor:
            vals['contractor_company_name'] = contractor

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
    # 範圍：先以可存取的工程/單據過濾（_document_check_access / search by project），
    # 非成員專案的單據抓不到 → 自然擋住。
    # 2026-11-04 前台角色的 ORM 寫入權全部收回（tests/test_portal_orm_readonly.py），
    # 所以動作一律 sudo 執行。先 with_user(本人)：_document_check_access 回傳的是系統帳號的
    # record（Odoo 核心 portal.py），不換回來的話審核人、結案人欄位（self.env.uid）都記成「系統」。

    def _run_review_action(self, record, method, ok_url, err_url, supervision_only=False):
        """共用：守門 + 呼叫審核動作 + 導回（攔 UserError/ValidationError 顯示訊息）

        supervision_only：審核類動作（公司儀表板合約 §3.6 寫入矩陣：缺失驗證與結案、
        通報單確認與結案、自主檢查結案）→ 營造方一律拒，監造方照 _require_manage。
        """
        if supervision_only:
            self._require_review(_('僅老闆或主管可審核'), _('權限不足：此審核動作限監造單位，營造廠帳號不能執行'))
        else:
            self._require_manage(_('僅老闆或主管可審核'))
        if not record:
            return request.redirect(err_url)
        try:
            getattr(record.with_user(request.env.user).sudo(), method)()
        except (UserError, ValidationError) as e:
            return request.redirect(_portal_flash_url(err_url, e))
        sep = '&' if '?' in ok_url else '?'
        return request.redirect(f'{ok_url}{sep}msg=reviewed')











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


class ConstructionThreadController(PortalThreadController):
    """前台留言者照舊自動關注那筆紀錄，之後的回覆才會進他的通知中心。

    核心留言路由（mail/controllers/thread.py mail_message_post）看到留言者沒有寫入權，
    就帶 mail_create_nosubscribe 不讓他關注；2026-11-04 前台角色的寫入權收回後，
    每個前台帳號都會被這樣處理。這裡只在「本人讀得到這筆紀錄」時把本人加回關注者
    （拿分享 token 但讀不到的人不加），留言裡提及的人不跟著關注。
    回歸：tests/test_portal_orm_readonly.py 的留言測試。
    """

    @http.route()
    def mail_message_post(self, thread_model, thread_id, post_data, context=None, **kwargs):
        result = super().mail_message_post(thread_model, thread_id, post_data, context=context, **kwargs)
        user = request.env.user
        record = request.env[thread_model].browse(int(thread_id)) if thread_model in PORTAL_COMMENT_MODELS else None
        # 留言者判斷與 _get_mail_message_access 的放寬同一份（MailThread._is_portal_commenter；S2 起含後台角色帳號）
        if record is not None and record._is_portal_commenter():
            if record.has_access('read'):
                record.sudo().message_subscribe(partner_ids=user.partner_id.ids)
        return result
