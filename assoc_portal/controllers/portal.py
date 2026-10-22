"""會員自助頁與一次性開通頁（計畫 P2、P5、P6、§4）。

P2：**share 使用者對 assoc.* 沒有任何 ACL**，所有讀寫都走 sudo，
守衛只有一個地方——`_me()`。有 ACL 的話，會員就能直接打 `/web/dataset/call_kw`，
之後任何一個欄位漏標 groups、或新模型漏寫 rule，資料就外流。
"""

import base64
import json
import re
import time

from psycopg2.errors import UniqueViolation

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import content_disposition, request
from odoo.addons.portal.controllers.portal import CustomerPortal

from odoo.addons.assoc_base.models.assoc_member_document import (
    ALLOWED_MIMETYPES, DOC_MAX_MB, image_is_readable)
from odoo.addons.assoc_base.tools import ASSOC_TZ, PASS_WINDOW_SECONDS, pass_data_uri
from ..models.res_users import MIN_PASSWORD_LEN
from odoo.tools.mimetypes import guess_mimetype

MAX_PENDING_DOCS = 10          # 每位會員的待審文件上限（避免灌爆 filestore）
SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._\u4e00-\u9fff-]')
DOTS_RE = re.compile(r'\.{2,}')
MAX_FILENAME_LEN = 80


def _safe_filename(name):
    """檔名會進 Content-Disposition 與清單畫面，一律清洗後才用。

    CRLF 會讓 werkzeug 丟 500、引號可以偽裝副檔名、連續的點是路徑穿越的記號
    （現在只當識別用，但這個值日後很容易被誰拿去接路徑）。
    """
    cleaned = SAFE_FILENAME_RE.sub('_', name or '')
    cleaned = DOTS_RE.sub('.', cleaned).lstrip('.')
    return cleaned[:MAX_FILENAME_LEN] or 'document'


def _me():
    """登入者對應的會員；不是會員就 404（前台所有頁面的唯一守衛）。"""
    member = request.env['assoc.member']._member_for_user()
    if not member:
        raise request.not_found()
    return member


# 「還沒對外公告」的場次狀態。會員前台**任何一頁**都不得呈現這種場次的名稱、
# 日期或地點——`action_build_roster()`／`gift.campaign.action_ready()` 在 draft
# 都跑得動，所以承辦一做前置作業就會外洩。三輪抗辯各抓到一條漏掉的路
# （積分頁、積分證明 PDF、禮品頁），所以這裡給它一個名字，新增查詢時好對照。
MEETING_UNANNOUNCED = 'draft'

class AssocPortal(CustomerPortal):

    # ------------------------------------------------------------------
    # 開通／重設密碼（紙本通知單上的一次性連結）
    # ------------------------------------------------------------------
    # website=True：用 web.frontend_layout 的頁面需要 frontend 環境
    # （portal.language_selector 會讀 frontend_languages，少了就 500）
    @http.route('/assoc/activate', type='http', auth='public', methods=['GET', 'POST'],
                website=True, sitemap=False)
    def assoc_activate(self, **post):
        """GET 的頁面不含 token（token 在網址的 # 後面，由 JS 搬進表單）。"""
        if request.httprequest.method == 'GET':
            return request.render('assoc_portal.activate_page', {})

        token = post.get('token') or ''
        password = post.get('password') or ''
        confirm = post.get('confirm') or ''
        values = {'error': ''}
        member, user, _nonce = request.env['assoc.member'].sudo()._member_from_token(token)
        if not member:
            values['error'] = _('這張通知單已經失效，請洽公會辦公室重印。')
        elif len(password) < MIN_PASSWORD_LEN:
            values['error'] = _('密碼至少要 %s 個字元。', MIN_PASSWORD_LEN)
        elif password != confirm:
            values['error'] = _('兩次輸入的密碼不一致。')
        elif not user.share:
            values['error'] = _('這個帳號不能用通知單設定密碼。')
        if values['error']:
            # 把 token 回填：JS 讀完 fragment 就把網址清掉了，不回填的話
            # 使用者改完密碼再送一次，只會拿到「通知單已失效」
            values['token'] = token
            return request.render('assoc_portal.activate_page', values)

        member._consume_activation(password)     # 同一交易內設密碼並讓通知單失效
        return request.redirect('/web/login')

    # ------------------------------------------------------------------
    # 會員自助頁
    # ------------------------------------------------------------------
    def _assoc_values(self, member, **extra):
        """portal.portal_layout 需要 _prepare_portal_layout_values() 準備的值
        （少了它會在 len(frontend_languages) 炸掉）。"""
        values = self._prepare_portal_layout_values()
        # `assoc_tz` 給樣板釘死時間的呈現時區——公會當地發生的事實不隨觀看者變
        values.update({'member': member, 'page_name': 'assoc', 'assoc_tz': ASSOC_TZ},
                      **extra)
        return values

    @http.route('/my/assoc', type='http', auth='user', website=True)
    def assoc_home(self, **kw):
        """會員專區已併進 /my（與 My account 同一層，入口卡見 portal_my_home_assoc）。
        舊網址（書籤、紙本說明）導回 /my；**守衛照舊先跑**——非會員一樣 404，不因轉址而改變。"""
        _me()
        return request.redirect('/my')

    @http.route('/my/assoc/profile', type='http', auth='user', website=True)
    def assoc_profile(self, **kw):
        """唯讀會員資料＋證明文件（清單與上傳表單從原本的會員專區首頁搬過來）。"""
        member = _me()
        document_model = request.env['assoc.member.document']
        return request.render('assoc_portal.member_profile', self._assoc_values(
            member,
            documents=member.document_ids.sorted('id', reverse=True),
            # QWeb 不能存取底線開頭的屬性（_fields），標籤在這裡先展開
            doc_type_labels=dict(document_model._fields['doc_type'].selection),
            state_labels=dict(document_model._fields['state'].selection),
            upload_result=request.params.get('upload'),
        ))

    @http.route('/my/assoc/pass', type='http', auth='user', website=True)
    def assoc_pass(self, **kw):
        """電子會員證＋動態報到 QR（計畫 P8：兩者同一頁）。"""
        member = _me()
        payload = self._pass_payload(member)
        # QWeb 的版型快取不吃 list（會丟 "value type of 't-nocache-codes' cannot be cached"），
        # 所以畫面只收字串：第一張圖 + JSON 字串，其餘由 JS 取
        values = self._assoc_values(
            member, first_code=payload['codes'][0], codes_json=json.dumps(payload['codes']),
            window_seconds=payload['window_seconds'], fee_valid=payload['fee_valid'])
        response = request.render('assoc_portal.member_pass', values)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route('/my/assoc/pass/tokens', type='json', auth='user', methods=['POST'],
                website=False)
    def assoc_pass_tokens(self, **kw):
        """手機每 30 秒回來換新的 QR。只預取 2 個時窗（轉傳有效期最長 90 秒）。"""
        return self._pass_payload(_me())

    def _pass_payload(self, member):
        """伺服器直接產圖：token 不進網址、不進 log。

        只預取 2 個時窗：第二個碼在它自己的時窗＋下一個時窗都有效，
        所以截圖轉傳的有效期最長 90 秒（預取越多越長，這是取捨的下限）。
        """
        now = time.time()
        return {
            'codes': [pass_data_uri(request.env, member, at=now + offset * PASS_WINDOW_SECONDS)
                      for offset in (0, 1)],
            # 用共用的判斷：預繳明年那期的人今天還不算有效
            'fee_valid': member._fee_is_current(),
            'window_seconds': PASS_WINDOW_SECONDS,
        }

    @http.route('/my/assoc/documents/upload', type='http', auth='user', methods=['POST'],
                website=False)
    def assoc_document_upload(self, **post):
        member = _me()
        upload = request.httprequest.files.get('file')
        doc_type = post.get('doc_type')
        if not upload or doc_type not in dict(
                request.env['assoc.member.document']._fields['doc_type'].selection):
            return request.redirect('/my/assoc/profile?upload=invalid')
        # 這裡沒有「在讀進來之前擋掉」這種選項：Odoo 的 get_http_params() 在進 controller
        # 之前就碰過 httprequest.files（http.py:1846-1850），body 已經被 werkzeug 解析完
        # （檔案部分落在暫存檔，不是記憶體）。真正的上限在兩個地方：
        # Odoo 的 max_content_length = 128 MiB（http.py:1330，超過回 413）、
        # 以及正式站反向代理的 client_max_body_size（見 README 部署需求）。
        pending = request.env['assoc.member.document'].sudo().search_count([
            ('member_id', '=', member.id), ('state', '=', 'submitted')])
        if pending >= MAX_PENDING_DOCS:
            return request.redirect('/my/assoc/profile?upload=too_many')
        content = upload.read(DOC_MAX_MB * 1024 * 1024 + 1)
        if len(content) > DOC_MAX_MB * 1024 * 1024:
            return request.redirect('/my/assoc/profile?upload=too_big')
        mimetype = guess_mimetype(content)
        if mimetype not in ALLOWED_MIMETYPES:
            return request.redirect('/my/assoc/profile?upload=bad_type')
        # 壞掉的圖要在 create 之前擋：ir.attachment 會對圖片跑 Pillow，
        # 而截斷的檔會丟未被接住的 OSError → 整條路由 500（見 image_is_readable）
        if mimetype.startswith('image/') and not image_is_readable(content):
            return request.redirect('/my/assoc/profile?upload=bad_image')
        request.env['assoc.member.document'].sudo().create({
            'member_id': member.id,
            'doc_type': doc_type,
            'cert_no': post.get('cert_no') or False,
            'file': base64.b64encode(content),
            'file_name': _safe_filename(upload.filename),
            'submitted_via': 'portal',
        })
        return request.redirect('/my/assoc/profile?upload=ok')

    @http.route('/my/assoc/documents/<int:doc_id>/file', type='http', auth='user', website=False)
    def assoc_document_file(self, doc_id, **kw):
        member = _me()
        doc = request.env['assoc.member.document'].sudo().search([
            ('id', '=', doc_id), ('member_id', '=', member.id)], limit=1)
        if not doc:
            raise request.not_found()
        content = base64.b64decode(doc.file or b'')
        mimetype = guess_mimetype(content)
        if mimetype not in ALLOWED_MIMETYPES:
            raise request.not_found()
        # 一律當附件下載＋固定 Content-Type：避免上傳的檔在同源被當網頁執行
        return request.make_response(content, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', len(content)),
            # 一定要走核心的 content_disposition（http.py:315，RFC 5987 的
            # filename*=UTF-8''<percent-encoded>）：自己拼 filename="..." 的話，
            # 「技師證書.png」這種中文檔名會在 WSGI 寫標頭時丟
            # UnicodeEncodeError（latin-1），連線直接斷、連 500 都沒有。
            ('Content-Disposition', content_disposition(_safe_filename(doc.file_name))),
            # 核心的 _post_dispatch 對每個回應都會加這個標頭（http.py:2253→2524），
            # 這裡明寫是為了「上游哪天不加了也還在」——所以 mutation 殺不掉它
            ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'no-store'),
        ])

    # ------------------------------------------------------------------
    # 擋掉核心的帳號頁：會員不能自己改姓名、照片、公司、Email
    # ------------------------------------------------------------------
    # 下面兩條擋的是「核心的帳號頁」，判斷要用 `_member_account_for_user`（不看 active）：
    # 用 `_member_for_user` 的話，會員一被停權（`active=False`）查詢就回空 →
    # 守衛認定「這不是會員」→ 放行核心，而核心的 account() 是 partner.sudo().write，
    # 等於停權的人反而可以從前台改掉名冊姓名與 Email。守衛反轉比沒有守衛更糟。
    @http.route()
    def account(self, redirect=None, **post):
        if request.env['assoc.member']._member_account_for_user():
            return request.redirect('/my/assoc/profile')
        return super().account(redirect=redirect, **post)

    @http.route()
    def deactivate_account(self, validation, password, **post):
        if request.env['assoc.member']._member_account_for_user():
            raise AccessError(_('會員帳號不能自行停用，請洽公會辦公室。'))
        return super().deactivate_account(validation, password, **post)

    # ------------------------------------------------------------------
    # 委託出席（§7）與研討會積分（§8）
    # ------------------------------------------------------------------
    @http.route('/my/assoc/proxies', type='http', auth='user', website=True)
    def assoc_proxies(self, **kw):
        member = _me()
        Proxy = request.env['assoc.meeting.proxy'].sudo()
        # 只列「名冊已經建好」的場次：draft 場次要到 `action_open_checkin` 才建名冊，
        # 而委託的約束要求雙方都在名冊上——列出來只會讓會員拿到泛用的失敗訊息。
        now = fields.Datetime.now()
        on_roster = request.env['assoc.meeting.attendance'].sudo().search([
            ('member_id', '=', member.id), ('meeting_id.kind', '=', 'assembly'),
            ('meeting_id.state', '=', 'checkin_open'),
        ])
        open_meetings = on_roster.meeting_id.filtered(
            lambda m: not m.proxy_deadline or m.proxy_deadline >= now)
        return request.render('assoc_portal.member_proxies', self._assoc_values(
            member,
            proxies=Proxy.search([('principal_member_id', '=', member.id)], order='id desc'),
            held=Proxy.search([('holder_member_id', '=', member.id),
                               ('state', 'in', ('requested', 'waiting', 'active'))]),
            open_meetings=open_meetings,
            purpose_labels=dict(Proxy._fields['purpose'].selection),
            state_labels=dict(Proxy._fields['state'].selection),
            proxy_result=request.params.get('proxy'),
        ))

    @http.route('/my/assoc/proxies/new', type='http', auth='user', methods=['POST'], website=False)
    def assoc_proxy_new(self, **post):
        """會員自己指定受託人。**一律停在 requested**：人團法要書面委託，
        電子委託是否等同尚待社會局函釋，所以要辦公室或報到台收到紙本才生效。
        """
        member = _me()
        meeting = request.env['assoc.meeting'].sudo().browse(int(post.get('meeting_id') or 0)).exists()
        if not meeting or meeting.company_id != member.company_id or meeting.kind != 'assembly':
            return request.redirect('/my/assoc/proxies?proxy=invalid')
        now = fields.Datetime.now()
        if meeting.state != 'checkin_open' or (
                meeting.proxy_deadline and meeting.proxy_deadline < now):
            return request.redirect('/my/assoc/proxies?proxy=closed')
        # 受託人要「會員編號 + 姓名」都吻合：只給編號的話，打錯一碼就委託給別人
        holder = request.env['assoc.member'].sudo().search([
            ('company_id', '=', member.company_id.id),
            ('member_no', '=', (post.get('holder_no') or '').strip()),
            ('name', '=', (post.get('holder_name') or '').strip()),
            ('active', '=', True),
        ], limit=1)
        if not holder or holder == member:
            return request.redirect('/my/assoc/proxies?proxy=no_holder')
        purpose = post.get('purpose') if post.get('purpose') in ('attend', 'gift') else 'attend'
        try:
            # partial unique index 是在 flush 才檢查的，不逼它在這裡出來的話，
            # 例外會在請求結束時才炸 → 使用者看到 500。
            # `cr.savepoint()` 預設是 _FlushingSavepoint（sql_db.py:182-189），
            # 進出都會 flush，所以包起來就夠、不必自己再呼叫一次。
            # 只攔下面兩種（§16 通則 4）：40001／55P03／40P01 要往外拋給 retrying。
            with request.env.cr.savepoint():
                request.env['assoc.meeting.proxy'].sudo()._new_proxy(
                    meeting, member, holder, purpose=purpose, channel='portal')
        except UniqueViolation:
            return request.redirect('/my/assoc/proxies?proxy=duplicate')
        except (UserError, ValidationError):
            return request.redirect('/my/assoc/proxies?proxy=refused')
        return request.redirect('/my/assoc/proxies?proxy=ok')

    @http.route('/my/assoc/proxies/<int:proxy_id>/cancel', type='http', auth='user',
                methods=['POST'], website=False)
    def assoc_proxy_cancel(self, proxy_id, **post):
        member = _me()
        proxy = request.env['assoc.meeting.proxy'].sudo().browse(proxy_id).exists()
        # 硬帶 principal_member_id：少了它，任何會員都能取消別人的委託
        if not proxy or proxy.principal_member_id != member:
            raise request.not_found()
        if proxy.state in ('cancelled', 'superseded', 'rejected'):
            return request.redirect('/my/assoc/proxies?proxy=already')
        try:
            # `_cancel` 而不是 `action_cancel`：權限由這條路由的
            # `principal_member_id` 比對負責，`action_cancel` 是管理員專用的入口
            proxy._cancel(_('會員自行取消'))
        except UserError:
            # 大會已經開議或結束：這時撤回等於回頭改法定人數與表決權重
            return request.redirect('/my/assoc/proxies?proxy=too_late')
        return request.redirect('/my/assoc/proxies?proxy=cancelled')

    @http.route('/my/assoc/proxies/<int:proxy_id>/form', type='http', auth='user',
                methods=['POST'], website=False)
    def assoc_proxy_form(self, proxy_id, **post):
        """列印帶單號的委託書。**POST，因為它會鑄新碼並讓外面那張舊的失效。**

        用 GET 的話，瀏覽器預抓、使用者按上一頁、或任何爬蟲都會把已經印出去的
        那張紙作廢——開通通知單的 docstring 已經記過這個坑。

        硬帶 `principal_member_id`：**只有委託人本人**印得出來。受託人不行
        （他手上該有的是委託人簽好名交給他的那張紙，不是再印一張新的）。
        """
        member = _me()
        proxy = request.env['assoc.meeting.proxy'].sudo().browse(proxy_id).exists()
        if not proxy or proxy.principal_member_id != member:
            raise request.not_found()
        if proxy.state not in ('requested', 'waiting'):
            # 已生效／已取消的不給印：印了也沒有用途，而且會作廢報到台可能正拿著的那張
            return request.redirect('/my/assoc/proxies?proxy=already')
        Report = request.env['ir.actions.report'].sudo()
        # wkhtmltopdf 不可用時核心會**退回 HTML**；不檢查的話會把一份 HTML
        # 標成 application/pdf 送出去（積分證明與通知單都踩過同一個退路）
        if Report.get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            raise UserError(_('PDF 產生器目前不可用，請稍後再試或洽公會辦公室。'))
        code = proxy._issue_form_code()
        pdf, _content_type = Report._render_qweb_pdf(
            'assoc_meeting.report_proxy_form', res_ids=proxy.ids, data={'code': code})
        name = '委託書-%s.pdf' % proxy.meeting_id.name
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(name)),
            ('Cache-Control', 'no-store'),
        ])

    def _my_credit_attendances(self, member, attendance_id=None):
        """積分紀錄。**列表與證明 PDF 一定要共用這一支。**

        原本兩邊各寫一份 domain，而 PDF 那一份少了 `kind` 與 `meeting_id.state`
        兩道——紅隊實跑把一份含「未公告研討會名稱＋日期＋認可文號」的 PDF 抓出來，
        還讓系統對一場**大會**簽發了「繼續教育積分證明（時數 0.0）」這種實質無效的
        official 文件。這是同一個改動裡第三次「守衛只裝在兩條路的其中一條」，
        所以這裡改成結構上不可能分叉：只有一個 domain。
        """
        domain = [('member_id', '=', member.id),
                  ('meeting_id.kind', '=', 'seminar'),
                  ('meeting_id.state', '!=', MEETING_UNANNOUNCED)]
        if attendance_id is not None:
            domain += [('id', '=', attendance_id), ('credit_status', '=', 'eligible')]
        return request.env['assoc.meeting.attendance'].sudo().search(
            domain, order='id desc')

    @http.route('/my/assoc/credits', type='http', auth='user', website=True)
    def assoc_credits(self, **kw):
        member = _me()
        attendances = self._my_credit_attendances(member)
        return request.render('assoc_portal.member_credits', self._assoc_values(
            member,
            attendances=attendances,
            total_points=sum(attendances.mapped('credit_points')),
            status_labels=dict(
                request.env['assoc.meeting.attendance']._fields['credit_status'].selection),
        ))

    @http.route('/my/assoc/credits/<int:attendance_id>/certificate', type='http', auth='user',
                website=False)
    def assoc_credit_certificate(self, attendance_id, **kw):
        """積分證明 PDF。只有判定為 eligible 的才給。"""
        member = _me()
        attendance = self._my_credit_attendances(member, attendance_id)[:1]
        if not attendance:
            raise request.not_found()
        # wkhtmltopdf 不可用時核心會**退回 HTML**；不檢查的話會把一份 HTML
        # 標成 application/pdf 送出去（M6 的通知單也踩過同一個退路）
        Report = request.env['ir.actions.report'].sudo()
        if Report.get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            raise UserError(_('PDF 產生器目前不可用，請稍後再試或洽公會辦公室。'))
        pdf, _content_type = Report._render_qweb_pdf(
            'assoc_meeting.report_credit_certificate', res_ids=attendance.ids)
        name = '積分證明-%s.pdf' % attendance.meeting_id.name
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(name)),
            ('Cache-Control', 'no-store'),
        ])

    # ------------------------------------------------------------------
    # 我的禮品（§4、§9）
    # ------------------------------------------------------------------
    @http.route('/my/assoc/gifts', type='http', auth='user', website=True)
    def assoc_gifts(self, **kw):
        """我有哪些禮品、領了沒。

        只讀：領取一律在報到台（要核對本人），前台不給任何「我要領」的按鈕。
        """
        member = _me()
        Entitlement = request.env['assoc.gift.entitlement'].sudo()
        # 禮品活動綁在大會上，而 `action_ready()` 不看大會狀態——承辦在大會還是
        # 籌備中時先把名單造好（正常作業），活動名稱（實務上就是場次名稱）就會
        # 立刻出現在全體會員的這一頁。沒綁大會的活動不受影響。
        rows = Entitlement.search([
            ('member_id', '=', member.id),
            '|', ('campaign_id.meeting_id', '=', False),
            ('campaign_id.meeting_id.state', '!=', MEETING_UNANNOUNCED),
        ], order='campaign_id desc, id')
        # 我委託給別人代領的，以及別人委託我代領的——兩邊都要看得到，
        # 否則會員只會看到「未領取」卻不知道自己已經委託出去了
        proxies = request.env['assoc.meeting.proxy'].sudo().search([
            ('purpose', '=', 'gift'), ('state', '=', 'active'),
            '|', ('principal_member_id', '=', member.id),
            ('holder_member_id', '=', member.id),
        ])
        return request.render('assoc_portal.member_gifts', self._assoc_values(
            member, gifts=rows, gift_proxies=proxies,
            state_labels=dict(Entitlement._fields['state'].selection),
        ))

    # ------------------------------------------------------------------
    # 我的大會：把同一場大會的事收攏成一頁
    # ------------------------------------------------------------------
    def _meeting_hub_extra(self, member, meeting):
        """給別的模組掛東西用的鉤子。

        `assoc_portal` 不依賴 `assoc_election`（計畫 D8），所以「這場的選舉」
        不能寫在這裡；`assoc_portal_election` 覆寫這支把選舉塞進來，
        樣板那邊對應一個空的 anchor。沒裝那個模組就什麼都不會多出來。
        """
        return {}

    def _my_attendances(self, member, meeting=None):
        """名冊是「這場與我有關」的唯一判準。

        用它當入口的 guard 也順便擋掉跨公會：出席列是逐會員建的，
        不在名冊上就看不到那場，而且**不區分「不存在」與「不是你的」**。
        """
        # **籌備中的場次不算**：`action_build_roster` 在 draft 就跑得動
        # （按鈕的 invisible 只排除 closed，方法本身也只對 closed raise），
        # 承辦一補建名冊，還沒對外公告的開會時間與地點就會出現在每位會員的頁面上。
        # 既有的 `/my/assoc/proxies` 同理帶了 `meeting_id.state`（:245-248）。
        domain = [('member_id', '=', member.id),
                  ('meeting_id.state', '!=', MEETING_UNANNOUNCED)]
        if meeting is not None:
            domain.append(('meeting_id', '=', meeting))
        return request.env['assoc.meeting.attendance'].sudo().search(
            domain, order='id desc')

    @http.route('/my/assoc/meetings', type='http', auth='user', website=True)
    def assoc_meetings(self, **kw):
        member = _me()
        attendances = self._my_attendances(member)
        return request.render('assoc_portal.member_meetings', self._assoc_values(
            member, attendances=attendances,
            att_labels=dict(attendances._fields['state'].selection),
            kind_labels=dict(request.env['assoc.meeting']._fields['kind'].selection),
            meeting_labels=dict(request.env['assoc.meeting']._fields['state'].selection),
        ))

    @http.route('/my/assoc/meetings/<int:meeting_id>', type='http', auth='user',
                website=True)
    def assoc_meeting_hub(self, meeting_id, **kw):
        member = _me()
        attendance = self._my_attendances(member, meeting_id)[:1]
        if not attendance:
            raise request.not_found()
        meeting = attendance.meeting_id
        Proxy = request.env['assoc.meeting.proxy'].sudo()
        values = self._assoc_values(
            member,
            meeting=meeting,
            attendance=attendance,
            mine=Proxy.search([('meeting_id', '=', meeting.id),
                               ('principal_member_id', '=', member.id)], order='id'),
            # 狀態條件要與 `/my/assoc/proxies`（:254-255）同口徑：`rejected` 是公會對
            # **委託人**書面委託的處置、`superseded` 是委託人當天自己到場，兩件事都
            # 發生在受託人這一側之後，既有頁面刻意不給受託人看。
            held=Proxy.search([('meeting_id', '=', meeting.id),
                               ('holder_member_id', '=', member.id),
                               ('state', 'in', ('requested', 'waiting', 'active'))],
                              order='id'),
            gifts=request.env['assoc.gift.entitlement'].sudo().search([
                ('member_id', '=', member.id),
                ('campaign_id.meeting_id', '=', meeting.id)], order='id'),
            att_labels=dict(attendance._fields['state'].selection),
            kind_labels=dict(meeting._fields['kind'].selection),
            meeting_labels=dict(meeting._fields['state'].selection),
            purpose_labels=dict(Proxy._fields['purpose'].selection),
            proxy_labels=dict(Proxy._fields['state'].selection),
            gift_labels=dict(
                request.env['assoc.gift.entitlement']._fields['state'].selection),
            credit_labels=dict(attendance._fields['credit_status'].selection),
        )
        # **在消費端驗鉤子的整個回傳值。** 放在橋接模組自己的生產端有兩個問題：
        # ①它只驗自己那個字面 dict（生產路徑永遠不可能 raise）②`super()` 帶上來的
        # 鍵原封放行。而核心 `ir_qweb` 對 `user_id`／`res_company`／`debug` 用的是
        # `setdefault`，鉤子回這三個就會贏，`web.frontend_layout` 正是讀它們畫導覽列
        # 與頁尾公會名——「可信的值最後贏」救不了它們。這裡是所有覆寫（現在的、
        # 未來的、不經橋接模組的）唯一都會經過的信任邊界。
        extra = self._meeting_hub_extra(member, meeting)
        bad = sorted(key for key in extra if not key.startswith('hub_'))
        if bad:
            raise ValueError('大會專區的鉤子只能加 hub_ 開頭的鍵，收到：%s'
                             % ', '.join(bad))
        values.update(extra)
        return request.render('assoc_portal.member_meeting', values)

    # ------------------------------------------------------------------
    # 繳費紀錄與收據（§4）
    # ------------------------------------------------------------------
    @http.route('/my/assoc/dues', type='http', auth='user', website=True)
    def assoc_dues(self, **kw):
        member = _me()
        Dues = request.env['assoc.dues'].sudo()
        return request.render('assoc_portal.member_dues', self._assoc_values(
            member,
            dues=Dues.search([('member_id', '=', member.id)], order='date_from desc, id desc'),
            payments=request.env['assoc.payment'].sudo().search([
                ('member_id', '=', member.id), ('state', '=', 'posted'),
            ], order='date desc, id desc'),
            state_labels=dict(Dues._fields['state'].selection),
            fee_valid=member._fee_is_current(),
        ))

    @http.route('/my/assoc/receipts/<int:payment_id>', type='http', auth='user', website=False)
    def assoc_receipt(self, payment_id, **kw):
        """下載收據。

        只給**已過帳**的：作廢的那張在前台看不到（它還留著是為了稽核），
        而且一律串流存檔的那份，不重新產生——金額與抬頭要凍結。
        """
        member = _me()
        payment = request.env['assoc.payment'].sudo().search([
            ('id', '=', payment_id), ('member_id', '=', member.id), ('state', '=', 'posted'),
        ], limit=1)
        attachment = payment.receipt_attachment_id
        # 這條路是 sudo 串流附件內容，所以要回頭確認這份附件真的屬於這張收款：
        # 少了這道，任何一條「沒走 _store_receipt_pdf 就把收款標成 posted」的路徑
        # 都會把別人的檔案（例如證書、身分證明）直接送給會員。
        if not payment or not attachment or (
                attachment.res_model != payment._name or attachment.res_id != payment.id):
            raise request.not_found()
        content = base64.b64decode(attachment.datas or b'')
        if not content:
            # 空檔案回 200 是靜默失敗：會員拿到 0 byte 的「收據」
            raise request.not_found()
        return request.make_response(content, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition('收據-%s.pdf' % payment.receipt_no)),
            ('Cache-Control', 'no-store'),
        ])
