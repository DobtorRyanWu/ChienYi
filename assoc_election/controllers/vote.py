import secrets
import time
from urllib.parse import urlsplit

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from ..models.assoc_election import VOTING_STATES
from ..tools import AssocVoteError, clean_token, is_election_uuid

NONCE_COOKIE = 'ax_nonce'
# 領取頁 GET 時發給這支手機的識別：領取回應沒送達時，同一裝置重送才能被認出來
DEVICE_COOKIE = 'ax_device'
# 票券 cookie 效期：涵蓋一整場大會
NONCE_COOKIE_SECONDS = 8 * 3600
MAX_UUID_LENGTH = 36
MAX_NONCE_LENGTH = 64
DEVICE_BYTES = 24
WRITEIN_MIN_CHARS = 2
WRITEIN_MAX_CHARS = 50
WRITEIN_LIMIT = 10

MESSAGES = {
    'invalid': '這個領取碼無效或已過期，請回報到台重新領票。',
    'conflict': '這張選票已被其他裝置領取。請立即告知報到台人員。',
    'no_ticket': '找不到您的選票（票券可能已被作廢重發）。請洽報到台。',
    'closed': '投票時間已結束。',
    'origin': '請直接用手機相機掃描報到台螢幕上的 QR Code。',
}
BALLOT_ERRORS = {
    'over_mark': '圈選人數超過上限，請重新圈選。',
    'invalid_choice': '選票內容無效，請重新圈選。',
    'not_armed': '尚未完成配對：請把手機畫面上的配對碼出示給報到台人員。',
    'closed': '投票時間已結束。',
    'ticket': '這張票券目前不能投票，請洽報到台。',
}


class AssocVote(http.Controller):
    """手機投票頁。全部 auth='public'：

    global company rule 對 public user 也生效（公會乙的資料對它不可見），
    所以一律 sudo，並且每個查詢都硬帶 election_id。身分只認 HttpOnly 的票券 cookie。
    """

    def _election(self, uuid):
        # 形狀先擋：`%00` 不擋的話會一路走到 psycopg2 才爆，
        # 而這五條都是公開路由（type='json' 的還會把 traceback 吐給匿名呼叫者）
        if not is_election_uuid(uuid):
            raise NotFound()
        election = request.env['assoc.election'].sudo().search([('uuid', '=', uuid)], limit=1)
        if not election or election.state in ('draft', 'cancelled'):
            raise NotFound()
        return election

    def _is_https(self):
        # 以凍結的 web.base.url 判定，不依賴 request.httprequest.is_secure（反向代理後面恆為 False）
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return base_url.startswith('https://')

    def _voter(self, election):
        nonce = clean_token(request.httprequest.cookies.get(NONCE_COOKIE), MAX_NONCE_LENGTH)
        Voter = request.env['assoc.election.voter'].sudo()
        if not nonce:
            return Voter.browse()
        return Voter.search([('election_id', '=', election.id), ('session_nonce', '=', nonce)], limit=1)

    def _page(self, template, election, values=None):
        qcontext = {'election': election, 'insecure': not self._is_https(),
                    'title': election.name, **(values or {})}
        return request.render(template, qcontext, headers={'Cache-Control': 'no-store'})

    def _message(self, election, key):
        return self._page('assoc_election.vote_message', election, {'message': MESSAGES[key]})

    def _set_ticket_cookie(self, response, election, name, value):
        response.set_cookie(
            name, value, max_age=NONCE_COOKIE_SECONDS, expires=time.time() + NONCE_COOKIE_SECONDS,
            path=f'/assoc/vote/{election.uuid}', secure=self._is_https(), httponly=True, samesite='Lax')

    @staticmethod
    def _ballot_url(election):
        return f'/assoc/vote/{election.uuid}/ballot'

    @staticmethod
    def _same_origin():
        origin = request.httprequest.headers.get('Origin')
        if not origin or origin == 'null':
            # 部分行動瀏覽器不送 Origin；領取碼本身就是秘密，這裡只防跨站燒掉別人的領取碼
            return True
        return urlsplit(origin).netloc == request.httprequest.host

    @http.route('/assoc/vote/<string:uuid>/claim', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def claim(self, uuid, t=None, **kw):
        election = self._election(uuid)
        cookies = request.httprequest.cookies
        if request.httprequest.method == 'GET':
            # 領取碼在網址的 #fragment，不會送到伺服器；由頁面 JS 讀出後以 POST 送來
            response = self._page('assoc_election.vote_claim', election)
            if not clean_token(cookies.get(DEVICE_COOKIE), MAX_NONCE_LENGTH):
                self._set_ticket_cookie(response, election, DEVICE_COOKIE, secrets.token_urlsafe(DEVICE_BYTES))
            return response
        if not self._same_origin():
            return self._message(election, 'origin')
        result = request.env['assoc.election.voter'].sudo()._claim(
            election, t, cookies.get(NONCE_COOKIE), cookies.get(DEVICE_COOKIE))
        status = result['status']
        if status not in ('claimed', 'already_mine'):
            return self._message(election, status)
        response = request.redirect(self._ballot_url(election))
        if result.get('nonce'):
            # 新領取，或同一裝置上次的回應沒送達：（補）發票券 cookie
            self._set_ticket_cookie(response, election, NONCE_COOKIE, result['nonce'])
        return response

    @http.route('/assoc/vote/<string:uuid>/ballot', type='http', auth='public', methods=['GET'])
    def ballot(self, uuid, e=None, **kw):
        election = self._election(uuid)
        voter = self._voter(election)
        if not voter:
            return self._message(election, 'no_ticket')
        if voter.state == 'voted':
            return self._page('assoc_election.vote_receipt', election, {'receipt_code': voter.receipt_code})
        if election.state not in VOTING_STATES:
            return self._message(election, 'closed')
        if voter.state != 'issued':
            return self._message(election, 'no_ticket')
        return self._page('assoc_election.vote_ballot', election, {
            # §6 的四要件之三（團體名稱、屆次、年月日）由模型算，M12 的紙本
            # 選票 PDF 要呼叫同一支。QWeb 不讓模板呼叫底線開頭的方法，先取好。
            # **只給選票頁**：領取頁與錯誤頁是匿名可達的（有 uuid 就打得到，
            # 而 uuid 就是公開大螢幕的網址），§6 要求載明的是**選舉票**本身，
            # 沒有理由讓每一頁都把大會日期送出去。
            'ballot_header': election._ballot_header(),
            'pair_code': voter.pair_code,
            'armed': bool(voter.armed_at),
            'offices': election._ballot_offices(),
            'error': BALLOT_ERRORS.get(e),
        })

    @http.route('/assoc/vote/<string:uuid>/status', type='json', auth='public')
    def ballot_status(self, uuid, **kw):
        election = self._election(uuid)
        voter = self._voter(election)
        return {
            'state': voter.state if voter else 'none',
            'armed': bool(voter and voter.armed_at),
            'election_state': election.state,
        }

    @http.route('/assoc/vote/<string:uuid>/members', type='json', auth='public')
    def writein_members(self, uuid, q=None, **kw):
        election = self._election(uuid)
        voter = self._voter(election)
        if not voter or voter.state != 'issued' or election.state not in VOTING_STATES:
            return []
        q = q.strip() if isinstance(q, str) else ''
        if not WRITEIN_MIN_CHARS <= len(q) <= WRITEIN_MAX_CHARS:
            return []
        rows = election._search_roster(q, WRITEIN_LIMIT)
        return [{'id': row.member_id.id, 'member_no': row.member_no, 'name': row.member_name} for row in rows]

    @http.route('/assoc/vote/<string:uuid>/cast', type='http', auth='public', methods=['POST'])
    def cast(self, uuid, **kw):
        election = self._election(uuid)
        voter = self._voter(election)
        if not voter:
            return self._message(election, 'no_ticket')
        form = request.httprequest.form
        choices = {office: form.getlist(office) for office in election._active_offices()}
        try:
            with request.env.cr.savepoint():
                voter._cast(choices)
        except AssocVoteError as err:
            # 只攔可預期的拒絕（都發生在寫入前）；40001 必須往外拋給 retrying
            request.env.invalidate_all()
            return request.redirect(f'{self._ballot_url(election)}?e={err.code}')
        return request.redirect(self._ballot_url(election))
