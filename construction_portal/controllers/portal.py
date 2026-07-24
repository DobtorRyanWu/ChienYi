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
            # M0.6：不再 public（避免 /web/content 枚舉洩漏）；
            # 前台顯圖改走帶權限檢查的 /construction/img/<att_id>。
            'public': False,
        })
        # 直接建 supervision.photo,不依賴 mixin
        if not Photo.search([('attachment_id', '=', att.id)], limit=1):
            Photo.create({
                'project_id': supervision_project.id,
                'attachment_id': att.id,
                'description': description or f.filename,
                'category_id': _photo_category_to_id(category),
                'source_model': source_model,
                'source_id': record.id,
                'shot_at': fields.Datetime.now(),
                'latitude': lat,
                'longitude': lng,
                'location_description': location_description,
            })
        new_atts.append(att.id)

    # C（2026-07-14）：僅在 record 真有 photo_ids 欄位時才寫入。
    # 通報單(reservation.notification.slip)沒有 photo_ids，靠 computed
    # related_photo_ids 反查 supervision.photo(source_model='notification')，
    # 上面已建好 supervision.photo，故此處跳過即可正確顯示。
    if new_atts and 'photo_ids' in record._fields:
        record.sudo().write({'photo_ids': [(4, aid) for aid in new_atts]})
    return new_atts


def _photo_category_options(env):
    """照片分類下拉／篩選選項。

    改用後台可自由維護的 supervision.photo.category 主檔（取代舊的固定
    11 項 Selection `category`），讓前台選項與後台維護的分類一致。
    回傳 [(str(id), name), ...]，沿用既有模板/JS 的 (value, label) 結構，
    其中 value = 分類記錄 id 的字串。
    """
    cats = env['supervision.photo.category'].sudo().search(
        [('active', '=', True)], order='sequence, name')
    return [(str(c.id), c.name) for c in cats]


def _photo_category_to_id(value):
    """把前台送來的分類值（分類 id 字串）轉為可寫入 category_id 的整數。

    空值或非數字（例如舊 Selection key 'civil'）一律回傳 False（視為未選）。
    """
    try:
        return int(value) if value else False
    except (TypeError, ValueError):
        return False


def _defect_save_photos(env, defect, files, stage):
    """建立缺失改善照片行(general/reservation.defect.improvement.photo)。

    缺失的 before_photo_ids / during_photo_ids / after_photo_ids 是 One2many
    到專用照片行模型(<defect_model>.photo),而非 ir.attachment 的 M2M。
    因此照片要用 create 照片行(image 為 binary,模型 create() 會自動建 attachment),
    不能用 (4, attachment_id) 去 link——那會被當成照片行 id 造成 MissingError。

    files: list of werkzeug FileStorage
    stage: 'before' / 'during' / 'after'
    回傳: 新增照片行數
    """
    # C2：supervision.defect 的照片是 M2M→ir.attachment（無 .photo 子模型）。
    if defect._name == 'supervision.defect':
        Attachment = env['ir.attachment'].sudo()
        field = 'after_photo_ids' if stage == 'after' else 'before_photo_ids'
        att_ids = []
        for f in files:
            if not f or not f.filename:
                continue
            raw = f.read()
            if not raw:
                continue
            att = Attachment.create({
                'name': f.filename,
                'datas': base64.b64encode(raw),
                'res_model': 'supervision.defect',
                'res_id': defect.id,
                'mimetype': f.mimetype or 'image/jpeg',
                # M0.6：非 public，前台走 /construction/img（_resolve_photo_project 認得
                # supervision.defect before/after m2m）
                'public': False,
            })
            att_ids.append(att.id)
        if att_ids:
            defect.sudo().write({field: [(4, a) for a in att_ids]})
        return len(att_ids)

    Photo = env[defect._name + '.photo'].sudo()
    count = 0
    for f in files:
        if not f or not f.filename:
            continue
        raw = f.read()
        if not raw:
            continue
        line = Photo.create({
            'defect_improvement_id': defect.id,
            'image': base64.b64encode(raw),
            'image_filename': f.filename,
            'photo_stage': stage,
        })
        # M0.6：不再把附件設 public。缺失照片行的 image 欄位附件預設非 public，
        # 前台改走帶權限檢查的 /construction/img/<att_id>（依 defect→專案成員判定）。
        count += 1
    return count


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


# 前台角色群組 XML id
# 註：v18.0.4.3.0 已將 boss/manager/field/observer 往下合併進
#     subscriber/leader/user/viewer（改名為 老闆/主管/現場人員/定期閱覽者），
#     故以下常數指向合併後的舊 xml_id。因四群組為單一繼承鏈
#     （viewer⊂user⊂leader⊂subscriber），guard 的 has_group 判斷語意等價：
#     _can_manage=subscriber or leader（老闆/主管）、_is_field_only=user 且非 leader。
GROUP_BOSS = 'construction_supervision_base.group_portal_subscriber'
GROUP_MANAGER = 'construction_supervision_base.group_portal_leader'
GROUP_FIELD = 'construction_supervision_base.group_portal_user'
GROUP_OBSERVER = 'construction_supervision_base.group_portal_viewer'
# 監造代操作員（內部）→ 前台管理權比照老闆/主管：可建案/審核/樣板 CRUD（_can_manage）。
# 註：可見範圍由內部使用者的核心多公司 rule 決定（見 supervision_project._get_portal_projects_domain）。
GROUP_OPERATOR = 'construction_supervision_base.group_operator'


class ConstructionPortal(CustomerPortal):
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
        # 2) 缺失改善照片行的 image 欄位附件（<defect_model>.improvement.photo）
        rm, rid = att.res_model, att.res_id
        if rm and rid and rm.endswith('.improvement.photo') and rm in env:
            rec = env[rm].sudo().browse(rid).exists()
            if rec and 'defect_improvement_id' in rec._fields:
                defect = rec.defect_improvement_id
                if defect and 'project_id' in defect._fields and defect.project_id:
                    return defect.project_id
        # 3) 被前台照片 m2m 直接引用：signboard、缺失前/後照片、驗收缺失前/後照片
        for model_name, field in (
                ('project.project', 'signboard_photo_ids'),
                ('supervision.defect', 'before_photo_ids'),
                ('supervision.defect', 'after_photo_ids'),
                ('acceptance.defect', 'before_photo_ids'),
                ('acceptance.defect', 'after_photo_ids')):
            if model_name in env and field in env[model_name]._fields:
                rec = env[model_name].sudo().search([(field, 'in', att.id)], limit=1)
                if rec:
                    return rec if model_name == 'project.project' else rec.project_id
        return None

    def _user_can_see_project(self, project):
        """登入者是否可看到此工程案件（與 /construction 列表同一條可見性 domain）。"""
        if not project:
            return False
        partner = request.env.user.partner_id
        domain = request.env['project.project']._get_portal_projects_domain(partner)
        return bool(request.env['project.project'].sudo().search_count(
            [('id', '=', project.id)] + domain))

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

    def _resolve_document_project(self, att):
        """反解一個文件附件所屬工程案件（只認 supervision.document.upload_attachment_ids）。

        與照片端點同樣採允許清單：不做泛用反解，非文件庫附件一律 None（→404），
        避免本端點淪為任意附件下載器。
        """
        env = request.env
        doc = env['supervision.document'].sudo().search(
            [('upload_attachment_ids', 'in', att.id)], limit=1)
        if doc and 'project_id' in doc._fields and doc.project_id:
            return doc.project_id
        return None

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
                                         'reservation.defect.improvement',
                                         'supervision.defect'):
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
        values = {
            'project': project,
            'log': log,
            'log_lines': log_lines,
            'log_materials': log_materials,
            'weather_selection': weather_selection,
            'page_name': 'construction_daily_log_detail',
            'day_count': self._get_project_day_count(project),
            'nav_badges': self._get_nav_badges(project),
            # 照片區塊變數
            'photos': log.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, log.photo_ids),
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

    # ==================== 施工日誌批次匯入 (XLSM) ====================

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
            f'/construction/{project_id}/daily-log/{log.id}?message=updated'
        )

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

        if att_id in log.photo_ids.ids:
            _portal_delete_photo(request.env, log, att_id)

        return request.redirect(
            f'/construction/{project.id}/daily-log/{log.id}?message=photo_deleted'
        )

    # ==================== 自主檢查 ====================

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

    # ==================== 自主檢查樣板庫管理（v11） ====================
    # 管理 self.inspection.type：全域樣板庫（project_id=False）+ 各工程專案層級樣板。
    # 瀏覽 / 下載 docx：全角色；新增 / 編輯 / 刪除 / 停用：限 _can_manage()（老闆 / 主管 / 內部）。

    # 查驗階段中文標籤（對齊模型 stage Selection）
    INSP_STAGE_LABELS = [('stage1', '施工前'), ('stage2', '施工中'), ('stage3', '施工後')]

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
        """把 default_item_ids 依 stage 分群，回傳 [{key,label,items}]（保留有項目的階段）。"""
        groups = []
        for key, label in self.INSP_STAGE_LABELS:
            items = rec.default_item_ids.filtered(lambda i, k=key: i.stage == k)
            if items:
                groups.append({'key': key, 'label': label, 'items': items})
        return groups

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
            'stage_labels': self.INSP_STAGE_LABELS,
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
            'stage_labels': self.INSP_STAGE_LABELS,
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

        self._save_inspection_type_items(rec, post)
        return request.redirect(
            '/construction/inspection-types/%s?message=saved' % rec.id)

    def _save_inspection_type_items(self, rec, post):
        """依表單提交同步 default_item_ids：保留/更新提交的、刪除被移除的、新增新列。

        表單欄位慣例（idx 連續）：
          item_id_<idx>（既有列 id，空=新列）、item_name_<idx>、
          item_stage_<idx>、item_standard_<idx>、item_seq_<idx>
        """
        Item = request.env['self.inspection.type.item'].sudo()
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
            ivals = {
                'name': name,
                'stage': post.get('item_stage_%d' % idx) or 'stage1',
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
            'photos': inspection.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, inspection.photo_ids),
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
        if att_id in inspection.photo_ids.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/construction/inspection/{inspection.id}?message=photo_deleted'
        )

    # ==================== 預約式自主檢查 ====================

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
            'photos': inspection.photo_ids,
            'photo_to_supervision': _portal_photo_to_supervision(request.env, inspection.photo_ids),
            'photo_categories': photo_categories,
            'upload_url': f'/construction/reservation-inspection/{inspection.id}/photo/upload',
            'delete_url_tpl': f'/construction/reservation-inspection/{inspection.id}/photo/%s/delete',
            'is_locked': False,
        }
        return request.render(
            'construction_portal.portal_construction_reservation_inspection_detail', values)

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
        if att_id in inspection.photo_ids.ids:
            _portal_delete_photo(request.env, inspection, att_id)
        return request.redirect(
            f'/construction/reservation-inspection/{inspection.id}?message=photo_deleted'
        )

    # ==================== 缺失管理 ====================

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

        from ..utils.defect_xlsm_parser import parse_defect_tracking_xlsx

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_IMPORT] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env['supervision.defect'].sudo()
        base_url = f'/construction/{project_id}/defects/import'
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

        from ..utils.defect_docx_parser import parse_defect_zip

        files = request.httprequest.files.getlist('files')
        _logger.warning(
            '[DEFECT_ENRICH] POST entered, files count=%s', len(files))

        env = request.env
        Defect = env['supervision.defect'].sudo()
        base_url = f'/construction/{project_id}/defects/enrich'
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
        Defect = env['supervision.defect'].sudo()
        base_url = f'/construction/{project_id}/defects/import-docx'
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

    # ── 缺失改善：依工程類型選擇模型 ──
    def _defect_model(self, project):
        """一般式 → supervision.defect（157 筆真資料、NCR 語意）；預約式 → reservation.defect.improvement。

        C2：一般式缺失原本誤讀 general.defect.improvement（僅 07-14 批次測試資料），
        真資料在 supervision.defect（匯入路由本就寫這裡）。已透過 supervision.defect 的前台
        相容層（construction_portal/models/supervision_defect.py）讓共用模板/路由零改名相容。
        """
        if project and getattr(project, 'project_type', False) == 'reservation':
            return 'reservation.defect.improvement'
        return 'supervision.defect'

    def _browse_defect(self, defect_id, access_token=None):
        """以 id 取缺失（先一般式、後預約式）並做存取檢查。

        M1.4：缺失存取一律走登入（auth='user'）＋ ir.rule；general/reservation 缺失模型
        沒有 access_token 欄位，故不把 token 傳進 `_document_check_access`（改名解除撞名後
        本呼叫會落到 Odoo 原生版，帶 token 又缺欄位會 AttributeError）。access_token 參數
        保留簽章相容但不使用。
        """
        for model in ('supervision.defect', 'general.defect.improvement',
                      'reservation.defect.improvement'):
            if request.env[model].sudo().browse(defect_id).exists():
                return self._document_check_access(model, defect_id)
        raise MissingError(_('找不到缺失紀錄'))

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

    # ==================== 照片管理 ====================

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
        """C（2026-07-14）：工程告示牌照片上傳（專案層級 signboard_photo_ids）。"""
        try:
            project = self._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        # H1：告示牌照片上傳限現場人員以上，閱覽角色不可上傳
        self._require_write(_('權限不足：閱覽角色不可上傳照片'))
        att_ids = []
        for f in request.httprequest.files.getlist('photos'):
            if not f or not f.filename:
                continue
            data = f.read()
            if not data:
                continue
            att = request.env['ir.attachment'].sudo().create({
                'name': f.filename,
                'datas': base64.b64encode(data),
                'res_model': 'project.project',
                'res_id': project.id,
                'mimetype': f.mimetype or 'image/jpeg',
                # M0.6：告示牌照片不再 public，前台走 /construction/img/<att_id>
                'public': False,
            })
            att_ids.append(att.id)
        if att_ids:
            project.sudo().write(
                {'signboard_photo_ids': [(4, aid) for aid in att_ids]})
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

    # ==================== 通報單（預約式）====================

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

    # ==================== 檢試驗管制（C 2026-07-14）====================

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
            {'source_model': 'test',
             'description': post.get('description') or '',
             'location_description': post.get('location_description') or ''})
        return request.redirect(f'/construction/{project_id}/test/{test_id}?message=photo_added')

    # ==================== 檔案管理 ====================

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
            {'source_model': 'notification',
             'description': post.get('description') or '',
             'location_description': post.get('location_description') or ''})
        return request.redirect(f'/construction/{project_id}/slip/{slip_id}?message=photo_added')

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

    # ==================== 工期展延（action_extend_lines）====================
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
