from psycopg2.errors import UniqueViolation
from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import content_disposition, request

from odoo.addons.assoc_base.tools import DESK_SOURCE_MANUAL, DESK_SOURCE_SCAN
from odoo.addons.assoc_base.tools import desk_ref as make_desk_ref
from odoo.addons.assoc_base.tools import desk_ref_source

from ..models import credit_export
from ..models.assoc_meeting_proxy import ACTIVATABLE_MEETING_STATES

DESK_GROUP = 'assoc_meeting.group_meeting_desk'
# 報到台輪詢間隔（毫秒）
DESK_POLL_INTERVAL_MS = 3000
# 手動簽到搜尋：最少字數與最多筆數
SEARCH_MIN_CHARS = 1
SEARCH_LIMIT = 10


def _as_id(value):
    """JSON 送來的 id 可能是字串、數字、陣列或 null——一律收斂成 int。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


EXPORT_TYPES = {'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'csv': 'text/csv'}


class AssocDesk(http.Controller):
    """報到台。選舉模組繼承本類別擴充 scan／poll 的回應。"""

    def _desk_meeting(self, mid):
        """報到台守衛：須具報到台權限，且大會屬於使用者可用的公會（由 global company rule 判定）。"""
        if not request.env.user.has_group(DESK_GROUP):
            raise AccessError(_('權限不足：此頁限報到台人員'))
        meeting = request.env['assoc.meeting'].browse(int(mid)).exists()
        if not meeting:
            raise NotFound()
        meeting.check_access('read')
        return meeting

    def _desk_qcontext(self, meeting):
        return {
            'meeting': meeting,
            'poll_interval_ms': DESK_POLL_INTERVAL_MS,
            'title': _('報到台 - %s', meeting.name),
        }

    @http.route('/assoc/desk/<int:mid>', type='http', auth='user', methods=['GET'])
    def desk_page(self, mid, **kw):
        meeting = self._desk_meeting(mid)
        return request.render('assoc_meeting.desk_page', self._desk_qcontext(meeting))

    @http.route('/assoc/desk/<int:mid>/scan', type='json', auth='user')
    def desk_scan(self, mid, barcode=None, **kw):
        """掃碼一律進同一個入口，由模型依長度分流（會員卡／動態碼／其他）。"""
        meeting = self._desk_meeting(mid)
        result = request.env['assoc.meeting.attendance']._checkin_by_code(meeting, barcode)
        return self._with_desk_context(meeting, result)

    def _with_desk_context(self, meeting, result, source=DESK_SOURCE_SCAN):
        """掃到（或手動簽到）某位會員之後，附上代簽需要的東西。

        `source` 會簽進參照碼裡：手動簽到也要給一把（不然沒帶卡的人沒辦法代簽），
        但那把**不能**拿去當「卡被掃過」用——否則報到台手動簽到某人就等於
        取得他的掃碼憑證。
        """
        member_id = result.get('member_id')
        if member_id:
            # 代簽與禮品領取是第二段請求：帶回這個參照碼，之後才分得出
            # 「掃過碼」與「純手動」，對帳用的手動筆數才有意義
            result['desk_ref'] = make_desk_ref(
                request.env, request.env.uid, meeting.id, member_id, source=source)
            result['proxies'] = self._pending_proxies(meeting, member_id)
        return result

    def _pending_proxies(self, meeting, holder_member_id):
        """這位受託人身上還沒生效的委託（報到台掃到他時一併顯示）。"""
        proxies = request.env['assoc.meeting.proxy'].sudo().search([
            ('meeting_id', '=', meeting.id),
            ('holder_member_id', '=', holder_member_id),
            ('state', 'in', ('requested', 'waiting')),
        ])
        return [{
            'proxy_id': proxy.id,
            'principal_name': proxy.principal_member_id.name,
            'principal_no': proxy.principal_member_id.member_no,
            'purpose': proxy.purpose,
            'state': proxy.state,
            'paper_received': proxy.paper_received,
            'channel': proxy.channel,
        } for proxy in proxies]

    @http.route('/assoc/desk/<int:mid>/proxy/activate', type='json', auth='user')
    def desk_proxy_activate(self, mid, proxy_id=None, desk_ref=None, **kw):
        """代簽：受託人已報到，讓他身上的委託生效。"""
        meeting = self._desk_meeting(mid)
        proxy = request.env['assoc.meeting.proxy'].sudo().browse(_as_id(proxy_id)).exists()
        if not proxy or proxy.meeting_id != meeting:
            return {'status': 'invalid'}
        if not desk_ref_source(request.env, desk_ref, request.env.uid, meeting.id,
                               proxy.holder_member_id.id):
            # 沒有有效的掃碼參照就不是「掃碼代簽」：這條路徑只給報到台掃到受託人之後用
            return {'status': 'need_scan'}
        try:
            return {'status': proxy._try_activate()}
        except UserError as err:
            return {'status': 'error', 'message': str(err)}

    @http.route('/assoc/desk/<int:mid>/proxy/register', type='json', auth='user')
    def desk_proxy_register(self, mid, holder_member_id=None, principal_member_id=None,
                            purpose='attend', desk_ref=None, **kw):
        """現場登錄紙本委託書：掃受託人 → 搜委託人 → 勾「已收書面」→ 立刻嘗試生效。"""
        meeting = self._desk_meeting(mid)
        # JSON 送得進來的不只數字：`int('abc')` 會 ValueError 變成 500
        holder_id, principal_id = _as_id(holder_member_id), _as_id(principal_member_id)
        if not desk_ref_source(request.env, desk_ref, request.env.uid, meeting.id, holder_id):
            return {'status': 'need_scan'}
        Attendance = request.env['assoc.meeting.attendance'].sudo()
        on_roster = Attendance.search([
            ('meeting_id', '=', meeting.id), ('member_id', 'in', [holder_id, principal_id])])
        if len(on_roster) != 2:
            return {'status': 'invalid'}
        if purpose not in ('attend', 'gift'):
            return {'status': 'invalid'}
        Member = request.env['assoc.member'].sudo()
        try:
            # 建立與生效要一起成功或一起退回：分開的話，生效失敗會留下一張
            # requested 的委託書佔住唯一索引，委託人從此送不出委託、重送也只會撞約束。
            # savepoint 只攔下面兩種（§16 通則 4）：40001 等仍往外拋給 retrying。
            with request.env.cr.savepoint():
                proxy = request.env['assoc.meeting.proxy'].sudo()._new_proxy(
                    meeting, Member.browse(principal_id), Member.browse(holder_id),
                    purpose=purpose, channel='desk_paper', paper_received=True)
                status = proxy._try_activate()
                # `rejected` 是正常的終局（受託人名額已滿），而且不佔委託人的唯一索引
                # → 留著當軌跡。只有「沒做完」的狀態才要整筆退回，否則會留下一張
                # requested 的委託書卡住委託人（他之後送不出任何委託）。
                if status not in ('active', 'waiting', 'rejected'):
                    raise UserError(_('無法登錄：%s', status))
                return {'status': status, 'proxy_id': proxy.id}
        except UniqueViolation:
            return {'status': 'error', 'message': _('這位委託人在本場已經有一張委託書。')}
        except (UserError, ValidationError) as err:
            return {'status': 'error', 'message': str(err)}

    @http.route('/assoc/desk/<int:mid>/proxy/receive', type='json', auth='user')
    def desk_proxy_receive(self, mid, proxy_id=None, desk_ref=None, **kw):
        """對**已存在**的委託書勾「已收書面」並嘗試生效（掃到委託書之後按的那一鍵）。

        為什麼需要這條：前台送出的委託停在 `requested`，而報到台今天**沒有路**
        讓它生效——`action_receive_paper` 是 admin-only，而 `/proxy/register`
        會撞 `assoc_proxy_principal` 這條 partial unique index（委託人已經有一筆了）。
        於是會員在前台委託完、帶紙來會場，報到台只能請公會管理員上後台。

        **這不是新權限**：報到台本來就能對同兩個人建一張 `desk_paper` +
        `paper_received=True` 的委託。這條只是讓它對「已經存在的那一筆」也做得到。

        `desk_ref_source`（不是 `verify_desk_ref`）：與 `/proxy/activate` 一致，
        手動點名的受託人也要能代簽，所以接受 manual 來源的參照碼。
        """
        meeting = self._desk_meeting(mid)
        proxy = request.env['assoc.meeting.proxy'].sudo().browse(_as_id(proxy_id)).exists()
        if not proxy or proxy.meeting_id != meeting:
            return {'status': 'invalid'}
        if not desk_ref_source(request.env, desk_ref, request.env.uid, meeting.id,
                               proxy.holder_member_id.id):
            return {'status': 'need_scan'}
        if proxy.meeting_id.state not in ACTIVATABLE_MEETING_STATES:
            # 報到走的 `_checkin_by_code` 有 `OPEN_MEETING_STATES` 閘，這條也要有：
            # `paper_received` 是**不可逆**的，而 `_try_activate` 的狀態閘在它之後才跑，
            # 於是大會已 closed 時報到台仍翻得動旗標＋寫一筆軌跡（第十四輪 skeptic）。
            return {'status': 'meeting_closed'}
        if proxy.state not in ('requested', 'waiting'):
            # 已生效／已取消／本人已到場的不要再翻一次書面旗標。
            # **`waiting` 要收**：候補中的前台委託帶紙來現場，書面旗標翻不了的話
            # `_activate_waiting_proxies()` 到開議時仍然過不了 `channel='portal'`
            # 那道閘門，於是這張紙永遠沒有用途——而前台還一直給它列印。
            return {'status': 'invalid'}
        try:
            proxy._mark_paper_received()
            return {'status': proxy._try_activate(), 'proxy_id': proxy.id}
        except (UserError, ValidationError) as err:
            return {'status': 'error', 'message': str(err)}

    @http.route('/assoc/desk/<int:mid>/proxy/principal_lookup', type='json', auth='user')
    def desk_proxy_principal_lookup(self, mid, code=None, desk_ref=None, holder_member_id=None,
                                    **kw):
        """把**委託人的會員編號條碼**解析成一位本場名冊上的會員。唯讀、零寫入。

        這是空白委託書那一條路：公會印一疊空白單，委託人在上面填／貼自己的
        **會員編號**條碼（**不是會員卡條碼**——那是「掃了就被標成親自出席」的
        持有者憑證，印在會離開會員手中的紙上等於放寬 §38 的 1/3 分母）。

        會員編號的形狀與掃描槍打出來的其他東西無法在伺服器端分辨，所以
        **唯一的區分是「承辦掃進哪一格」**：這條路由只做 id 解析、不寫任何資料，
        誤掃進去最壞的結果是畫面上多出一個人名。
        """
        meeting = self._desk_meeting(mid)
        holder_id = _as_id(holder_member_id)
        if not desk_ref_source(request.env, desk_ref, request.env.uid, meeting.id, holder_id):
            return {'status': 'need_scan'}
        member_no = (code or '').strip() if isinstance(code, str) else ''
        if not member_no:
            return {'status': 'invalid'}
        attendance = request.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', meeting.id), ('member_no', '=', member_no)], limit=1)
        if not attendance:
            return {'status': 'invalid'}
        # **不回 barcode、也不回 `member_id` 這個鍵名**（後者會讓上層鑄 desk_ref）
        return {'status': 'found', 'principal_member_id': attendance.member_id.id,
                'principal_no': attendance.member_no,
                'principal_name': attendance.member_id.sudo().name}

    @http.route('/assoc/desk/<int:mid>/search', type='json', auth='user')
    def desk_search(self, mid, q=None, **kw):
        meeting = self._desk_meeting(mid)
        q = (q or '').strip()
        if len(q) < SEARCH_MIN_CHARS:
            return []
        attendances = request.env['assoc.meeting.attendance'].search([
            ('meeting_id', '=', meeting.id),
            '|', ('member_no', 'ilike', q), ('member_id.name', 'ilike', q),
        ], limit=SEARCH_LIMIT)
        return [att._desk_info() for att in attendances]

    @http.route('/assoc/desk/<int:mid>/manual', type='json', auth='user')
    def desk_manual(self, mid, attendance_id=None, reason=None, **kw):
        meeting = self._desk_meeting(mid)
        attendance = request.env['assoc.meeting.attendance'].browse(int(attendance_id or 0)).exists()
        if not attendance or attendance.meeting_id != meeting:
            return {'status': 'invalid'}
        try:
            result = attendance._checkin_manual(reason)
        except UserError as e:
            # _checkin_manual 在任何寫入之前就檢查原因，這裡攔下不會留下半套資料
            return {'status': 'error', 'message': str(e)}
        # 手動簽到也要給 desk_ref 與委託清單：沒帶卡的受託人否則按不到代簽。
        # 但它是 **manual** 來源的碼：拿去領禮品時會被當成手動（要填原因、寫稽核）
        return self._with_desk_context(meeting, result, source=DESK_SOURCE_MANUAL)

    @http.route('/assoc/desk/<int:mid>/poll', type='json', auth='user')
    def desk_poll(self, mid, **kw):
        meeting = self._desk_meeting(mid)
        return meeting._desk_poll_data()


class AssocCreditExport(http.Controller):
    """積分名冊匯出（計畫 §8）。"""

    @http.route('/assoc/meeting/<int:mid>/credits/export', type='http', auth='user')
    def credits_export(self, mid, file_type='xlsx', reveal='0', **kw):
        meeting = request.env['assoc.meeting'].browse(mid).exists()
        if not meeting:
            raise NotFound()
        meeting.check_access('read')
        if not request.env.user.has_group('assoc_base.group_assoc_admin'):
            raise AccessError(_('只有公會管理員可以匯出積分名冊。'))
        if file_type not in EXPORT_TYPES:
            raise NotFound()
        attendances = request.env['assoc.meeting.attendance'].search([
            ('meeting_id', '=', meeting.id), ('credit_status', '=', 'eligible')])
        reveal_id = reveal == '1'
        if reveal_id:
            # 少一個人的身分證就讓整份匯不出來（而且不說是誰）不是可用的行為：
            # 先把缺的列出來，承辦才知道要補誰
            missing = attendances.member_id.sudo().filtered(lambda m: not m.national_id_enc)
            if missing:
                raise UserError(_('下列會員沒有身分證字號資料，無法匯出明文名冊：%s',
                                  ', '.join(missing.mapped('member_no'))))
        content = credit_export.write_credit_file(
            attendances, file_type=file_type, reveal_national_id=reveal_id)
        # 明文匯出另記 export_pii：那是「誰把幾筆身分證帶出系統」的軌跡
        request.env['assoc.audit.log']._log(
            'export_pii' if reveal_id else 'credit_export',
            records=attendances.member_id, company=meeting.company_id,
            detail={'meeting_id': meeting.id, 'file_type': file_type,
                    'columns': [col[0] for col in credit_export.CREDIT_EXPORT_COLUMNS],
                    'masked': not reveal_id})
        name = '積分名冊-%s.%s' % (meeting.name, file_type)
        return request.make_response(content, headers=[
            ('Content-Type', EXPORT_TYPES[file_type]),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition(name)),
            ('Cache-Control', 'no-store'),
        ])
