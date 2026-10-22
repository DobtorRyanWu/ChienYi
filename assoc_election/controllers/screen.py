"""大螢幕與跑馬燈（計畫 §10、§4）。

兩條都是**公開**路由（會場投影機沒有帳號），所以：
- 一律 sudo＋硬帶 uuid／published 條件（公開路由看不到 record rule）
- **零寫入**：投票進行中 `election` 這一列不能被碰（D4：RR 下對已更新提交的列
  讀寫會 40001，尖峰時整個會場的投票都會退避重試）。測試用
  `xmin::text` 在輪詢前後相同來證明這件事。
- 依狀態決定回傳什麼：**開票完成到公告之間不給任何數字**——
  票開完了但還沒宣布，螢幕上先跑出票數等於提前公告。
"""


from odoo import http
from odoo.http import content_disposition, request

from ..models.assoc_election import CHAIN_HEAD_DISPLAY, OFFICES, TICKER_LIMIT
from ..tools import is_election_uuid

# 大螢幕輪詢間隔（毫秒）。5 秒是計畫 D9 的值：夠即時，又不會把
# 投票尖峰的連線吃光（400 人的會場，每台螢幕每分鐘 12 次）
SCREEN_POLL_INTERVAL_MS = 5000
# `?c=` 每個公司 id 的最大位數。PG 的 integer 上限是 10 位，取 12 留餘裕；
# 真正的理由是不要讓超長字串走進 `int()`（Python 3.11 對 >4300 位直接 ValueError）
COMPANY_ID_MAX_DIGITS = 12
OFFICE_LABELS = dict(OFFICES)


def _screen_payload(election):
    """依狀態決定螢幕上能看到什麼。

    刻意用 if/elif 逐段列出而不是一個共用 dict 再刪欄位：
    「哪個狀態看得到哪些數字」是這支程式唯一的職責，
    寫成「先全給再刪」的話，日後新增欄位會預設外洩。
    """
    state = election.state
    if state in ('draft', 'cancelled'):
        # 還沒凍結名冊的場次連名字都不給：草稿期的選舉名稱可能還在改，
        # 而這條路由是公開的
        return {'state': state, 'message': '尚未開始',
                'poll_interval_ms': SCREEN_POLL_INTERVAL_MS}
    base = {'state': state, 'name': election.name, 'company': election.company_id.name,
            'poll_interval_ms': SCREEN_POLL_INTERVAL_MS}
    head = election.log_ids.filtered('is_head')[:1]
    if state == 'ballot_ready':
        # 抽籤亂數**故意公開**：號次的公式是公開的，承辦如果可以自己挑亂數就可以挑號次。
        # 唯一擋得住的是「擲骰的當下全場都看到這組數字上了大螢幕」——
        # 事後任何人拿封存包重算，用的就是這一組。
        return dict(base, roster=election.voter_count, message='名冊已審定，尚未開始投票',
                    draw_entropy=election.draw_entropy or '')
    if state in ('open', 'closing', 'closed'):
        return dict(
            base,
            voted=election.voted_count,
            roster=election.voter_count,
            chain_length=len(election.log_ids),
            chain_head=(head.entry_hash or '')[:CHAIN_HEAD_DISPLAY],
            message='投票中' if state == 'open' else (
                '已停止領票，在途選票仍可投出' if state == 'closing' else '已關票，等待開票'),
            # 同票抽籤亂數在關票後、開票前填入，它**直接決定跨界同票誰當選**。
            # 與號次抽籤亂數同一個道理：上牆讓全場看到「承辦用的就是剛剛擲出來的那一組」
            tie_entropy=election.tie_entropy or '',
        )
    # 開票之後鏈頭繼續顯示：監票員在會場抄下來的那一串，要有地方可以再看一次。
    if state == 'counted':
        # **不含任何票數**：票開完了但還沒公告，螢幕先跑出數字等於提前公告。
        # 鏈頭不是結果，給它不會洩漏誰當選。
        return dict(base, message='開票完成，待公告',
                    tie_entropy=election.tie_entropy or '',
                    chain_length=len(election.log_ids),
                    chain_head=(head.entry_hash or '')[:CHAIN_HEAD_DISPLAY])
    if state == 'published':
        return dict(base, message='已公告', result=_public_result(election),
                    tie_entropy=election.tie_entropy or '',
                    chain_length=len(election.log_ids),
                    chain_head=(head.entry_hash or '')[:CHAIN_HEAD_DISPLAY])
    # 日後新增的狀態一律走到這裡：沒有被明確列進白名單的狀態不給任何內容
    return {'state': state, 'message': '尚未開始',
            'poll_interval_ms': SCREEN_POLL_INTERVAL_MS}


def _public_result(election):
    """公告後可以公開的內容：名次、得票、當選或候補。

    直接讀 `result_json`（開票當下凍結的那份），不讀即時的候選人列——
    候選人列在公告之後仍可能因為資料修補而變動，公告的內容不能跟著變。
    """
    result = election.result_json or {}
    offices = []
    for code, data in sorted((result.get('offices') or {}).items()):
        offices.append({
            'office': code,
            'label': OFFICE_LABELS.get(code, code),
            'seats': data.get('seats'),
            'alternates': data.get('alternates'),
            'rows': [{
                'rank': row.get('rank'),
                'name': row.get('name'),
                'member_no': row.get('member_no'),
                'votes': row.get('votes'),
                'result': row.get('result'),
            } for row in data.get('ranking') or []],
        })
    return {'offices': offices, 'published_at': str(election.published_at or '')}


class AssocScreen(http.Controller):

    def _election_by_uuid(self, uuid):
        # 形狀檢查在 `tools.is_election_uuid`（vote.py 的五條公開路由共用同一支）
        if not is_election_uuid(uuid):
            raise request.not_found()
        election = request.env['assoc.election'].sudo().search([('uuid', '=', uuid)], limit=1)
        if not election:
            raise request.not_found()
        return election

    @http.route('/assoc/screen/<string:uuid>', type='http', auth='public', website=False)
    def screen_page(self, uuid, **kw):
        election = self._election_by_uuid(uuid)
        return request.render('assoc_election.screen_page', {
            'election_uuid': election.uuid,
            'poll_interval_ms': SCREEN_POLL_INTERVAL_MS,
            'title': election.name,
        })

    @http.route('/assoc/screen/<string:uuid>/poll', type='json', auth='public')
    def screen_poll(self, uuid, **kw):
        return _screen_payload(self._election_by_uuid(uuid))

    # ------------------------------------------------------------------
    # 跑馬燈：多公會共用一個畫面（大廳、官網）
    # ------------------------------------------------------------------
    @staticmethod
    def _company_ids(raw):
        """`?c=1,2` 只收正整數；其他一律當成沒指定（不要把壞輸入變成 500）。

        兩個踩過的地雷，這條路由是 `auth='public'`，壞輸入不該變成 500：
        - `isdigit()` 對上標數字 `'²'` 回 True，接著 `int('²')` 直接 ValueError。
          只有 `[0-9]` 才是安全的，所以改用明確的字元集合。
        - JSON 路由的參數可以是任何型別：`{"c": [1, 2]}` 送進來，
          `.split(',')` 就是 AttributeError。非字串一律當成沒指定。
        - **全是數字也可能炸**：Python 3.11 起 `int()` 對超過 4300 位的字串直接
          ValueError（CVE-2020-10735 的對策），所以要先看長度再轉。
        """
        if not isinstance(raw, str):
            return []
        ids = []
        for piece in raw.split(','):
            piece = piece.strip()
            if (piece and len(piece) <= COMPANY_ID_MAX_DIGITS
                    and all(char in '0123456789' for char in piece)):
                ids.append(int(piece))
        return ids[:TICKER_LIMIT]

    @http.route('/assoc/ticker', type='http', auth='public', website=False)
    def ticker_page(self, c=None, **kw):
        return request.render('assoc_election.ticker_page', {
            'companies': ','.join(str(one) for one in self._company_ids(c)),
            'poll_interval_ms': SCREEN_POLL_INTERVAL_MS,
        })

    @http.route('/assoc/ticker/poll', type='json', auth='public')
    def ticker_poll(self, c=None, **kw):
        items = []
        for election in request.env['assoc.election'].sudo()._ticker_elections(
                self._company_ids(c)):
            result = election.result_json or {}
            winners = []
            # 依職位代碼排序：dict 的順序來自 JSON 解析，理事與監事可能每次對調，
            # 跑馬燈上的名單就會莫名其妙變順序
            for _code, data in sorted((result.get('offices') or {}).items()):
                for row in data.get('ranking') or []:
                    if row.get('result') in ('elected', 'alternate'):
                        winners.append({'name': row.get('name'),
                                        'votes': row.get('votes'),
                                        'result': row.get('result')})
            items.append({
                'company': election.company_id.name,
                'name': election.name,
                'published_at': str(election.published_at or '')[:10],
                'winners': winners,
            })
        return {'items': items, 'poll_interval_ms': SCREEN_POLL_INTERVAL_MS}


class AssocArchive(http.Controller):
    """封存包與收據碼清單的下載（計畫 §4、§10）。"""

    def _election(self, eid):
        election = request.env['assoc.election'].browse(int(eid)).exists()
        if not election:
            raise request.not_found()
        # 先過 record rule（公會隔離、監票員逐場 rule），再談角色
        election.check_access('read')
        return election

    @http.route('/assoc/election/<int:eid>/archive', type='http', auth='user')
    def download_archive(self, eid, **kw):
        """監票封存包：**只有本場的監票員**下載得到，而且每次下載都留軌跡。"""
        election = self._election(eid)
        election._check_observer()
        raw = election._archive_blob()
        if not raw:
            raise request.not_found()
        # 軌跡掛在公會上而不是某些會員上：下載的是整場的資料，
        # 把它記成「某幾個人的個資被讀了」反而失真
        request.env['assoc.audit.log']._log(
            'archive_download', company=election.company_id, count=1,
            detail={'election_id': election.id, 'election': election.name,
                    'sha256': election.archive_sha256})
        return request.make_response(raw, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Length', len(raw)),
            ('Content-Disposition', content_disposition('封存包-%s.zip' % election.name)),
            ('Cache-Control', 'no-store'),
        ])

    @http.route('/assoc/election/<int:eid>/receipts.csv', type='http', auth='user')
    def download_receipts(self, eid, **kw):
        """收據碼清單：公告後供會員核對「我的碼在不在裡面」。

        限選務與公會管理員下載（它不含姓名，但一次拿到全部收據碼的人
        可以據此推算投票人數，公告前拿到就等於提前知道結果的規模）。
        """
        election = self._election(eid)
        election._check_officer()
        if election.state != 'published':
            raise request.not_found()
        raw = election.sudo()._csv_receipts()
        request.env['assoc.audit.log']._log(
            'archive_download', company=election.company_id, count=1,
            detail={'election_id': election.id, 'election': election.name,
                    'file': 'receipts.csv'})
        return request.make_response(raw, headers=[
            ('Content-Type', 'text/csv'),
            ('Content-Length', len(raw)),
            ('Content-Disposition', content_disposition('收據碼-%s.csv' % election.name)),
            ('Cache-Control', 'no-store'),
        ])
