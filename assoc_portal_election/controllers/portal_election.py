"""前台自助登記參選的三條路由。

**兩個動作都是 POST**：它們有副作用（建立／退選候選人列），用 GET 的話瀏覽器預抓、
按上一頁、或任何爬蟲都會動到名單——委託書列印那條路已經踩過同一個坑。

資格與時限的判斷**不在這裡**，在 `assoc.election.candidate._register_self`／
`_withdraw_self`。這裡只做一件事：解出登入者是哪一位會員（`_me()`），
以及把會員看不到的選舉過濾掉。
"""

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.assoc_base.tools import ASSOC_TZ
from odoo.addons.assoc_portal.controllers.portal import AssocPortal, _me

# **刻意不設 limit。** 第二輪為了防示範庫的殘料加了 `limit=20`，理由寫的是
# 「現在開放登記的必然是最新建的那一場，所以砍最舊的是安全的」——那句話是假的：
# `id` 與「要不要行動」無關。第三輪實跑證明，塞 20 筆之後**正在投票的那一場**
# 與**開放登記的那一場**雙雙從頁面消失，連「請到報到台領票」整段都不見，而畫面
# 上零痕跡。隔壁的 `_visible_elections` 本來就沒有 limit，一場大會正常也只有一筆
# 選舉（席次是同一筆上的欄位）——要防的是殘料，不是真實資料。


class AssocPortalElection(http.Controller):

    def _visible_elections(self, member):
        """參選登記頁看得到的選舉：本公會、而且**現在**開放自助登記的場次。

        判準與大會專區共用 `_election_visibility_domain()`——兩頁各寫一份的結果是
        「截止日已過的草稿」專區藏、這一頁露，而那正是專區註解自己寫的
        「沒有任何正當理由出現」。上一輪共用了候選狀態的守衛，卻沒共用這一個。
        """
        return request.env['assoc.election'].sudo().search(
            [('company_id', '=', member.company_id.id)]
            + _election_visibility_domain(),
            order='registration_deadline desc, id desc')

    def _my_candidacies(self, member, elections):
        return _my_candidacies(member, elections)

    @http.route('/my/assoc/elections', type='http', auth='user', website=True)
    def assoc_elections(self, **kw):
        member = _me()
        elections = self._visible_elections(member)
        Candidate = request.env['assoc.election.candidate'].sudo()
        return request.render('assoc_portal_election.member_elections', {
            'member': member,
            # 樣板要用它把截止時間釘死在公會時區（裸印 Datetime 是 naive UTC）
            'assoc_tz': ASSOC_TZ,
            'elections': elections,
            'is_open': {e.id: Candidate._registration_open(e) for e in elections},
            'offices': {e.id: e._active_offices() for e in elections},
            'office_labels': dict(
                request.env['assoc.election.candidate']._fields['office'].selection),
            'mine': {(c.election_id.id, c.office): c
                     for c in self._my_candidacies(member, elections)},
            'error': kw.get('error'),
            'ok': kw.get('ok'),
        })

    def _election_for(self, member, eid):
        election = request.env['assoc.election'].sudo().browse(eid).exists()
        # 硬帶公會條件：少了它，換個 id 就讀得到別家公會的場次
        if not election or election.company_id != member.company_id:
            raise request.not_found()
        return election

    @http.route('/my/assoc/elections/<int:eid>/register', type='http', auth='user',
                methods=['POST'], website=False)
    def assoc_election_register(self, eid, **post):
        member = _me()
        election = self._election_for(member, eid)
        try:
            request.env['assoc.election.candidate']._register_self(
                election, member, post.get('office') or '')
        except UserError as err:
            return request.redirect('/my/assoc/elections?error=%s' % _quote(str(err)))
        return request.redirect('/my/assoc/elections?ok=registered')

    @http.route('/my/assoc/elections/<int:eid>/withdraw', type='http', auth='user',
                methods=['POST'], website=False)
    def assoc_election_withdraw(self, eid, **post):
        member = _me()
        election = self._election_for(member, eid)
        candidate = request.env['assoc.election.candidate'].sudo().browse(
            _as_id(post.get('candidate_id'))).exists()
        # 綁回這場選舉：少了這一句，帶別場的 candidate_id 就會被 `_withdraw_self`
        # 當成合法輸入（它只驗「是不是你的」，不驗「是不是這一場的」）
        if not candidate or candidate.election_id != election:
            raise request.not_found()
        try:
            candidate._withdraw_self(member)
        except UserError as err:
            return request.redirect('/my/assoc/elections?error=%s' % _quote(str(err)))
        return request.redirect('/my/assoc/elections?ok=withdrawn')


def _election_visibility_domain():
    """兩個前台頁面共用的「這場選舉該不該讓會員看到」。

    判準寫成「截止日**還沒到**」而不是「有設截止日」：後者讓截止日已過的草稿
    照樣列出來，而那時畫面上根本沒有登記入口，沒有任何正當理由出現。
    已取消的不列——`_registration_open` 對非 draft 回 False，於是取消的場次會被
    印成「登記已截止」，那是錯的訊息（它不是截止，是整場取消了）。
    """
    return [
        ('state', 'not in', ('cancelled',)),
        '|', ('state', '!=', 'draft'),
        ('registration_deadline', '>=', fields.Datetime.now()),
    ]


# 開票（`counted`）之後個人登記狀態一律不顯示。`_tally` 在開票那一筆會把
# 「已退選但拿到票」的人改成 `write_in`——所以**濾掉 `write_in` 這一列**本身就帶著
# 那個 bit：那位會員的標籤會從「已退選」變成「未登記」，他重新整理一次就知道
# 有沒有人投他。把「值」藏起來不夠，**「有沒有那一列」也不可以帶資訊**。
# 公告之後同樣不顯示：對外公告的只有當選與候補，「我至少拿到 1 票」不在其中。
CANDIDACY_VISIBLE_STATES = ('draft', 'ballot_ready', 'open', 'closing', 'closed')


def _my_candidacies(member, elections):
    """這位會員在這些選舉裡的候選列，**而且是現在可以給他看的那些**。

    兩個前台頁面共用這一支——守衛裝在其中一頁、另一頁原封不動印同一份資料，
    是這個改動第一版的實際錯誤（紅隊實跑複現）。

    **整場濾掉而不是濾掉某個值**：見上方 `CANDIDACY_VISIBLE_STATES` 的理由。
    代價是開票後連「已確認」也不顯示——所以樣板**不可以**因此印「未登記」
    （那是假話），要印一句明確的「開票後不再顯示」。
    """
    visible = elections.filtered(lambda e: e.state in CANDIDACY_VISIBLE_STATES)
    if not visible:
        return request.env['assoc.election.candidate'].sudo().browse()
    return request.env['assoc.election.candidate'].sudo().search([
        ('election_id', 'in', visible.ids),
        ('member_id', '=', member.id),
    ])


def _as_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _quote(text):
    from urllib.parse import quote
    return quote(text[:120])


class AssocPortalMeetingElections(AssocPortal):
    """把「這一場的選舉」掛進大會專區。

    走 `assoc_portal` 留的鉤子而不是改它的檔案：那個模組不依賴 assoc_election
    （計畫 D8），沒裝這個橋接模組時大會專區就不該出現選舉區塊。
    """

    def _meeting_hub_extra(self, member, meeting):
        values = super()._meeting_hub_extra(member, meeting)
        Election = request.env['assoc.election'].sudo()
        Candidate = request.env['assoc.election.candidate'].sudo()
        # **草稿的場次不列**，除外的是「**現在**開放自助登記」的那些（會員必須看得到
        # 才登記得了）。還在籌備的選舉對會員而言不存在，列出來只是提前曝光承辦
        # 還沒公告的名單與職位。已取消的不列。
        #
        # 判準要寫成「截止日還沒到」而不是「有設截止日」——後者讓**截止日已過的
        # 草稿**照樣列出來，而那時畫面上根本沒有登記入口，沒有任何正當理由出現。
        # 公會條件硬帶一份：跨公會今天是靠兩條 `@api.constrains` 間接擋住的
        # （出席列同公會、選舉與大會同公會），而 constrains 只在自己那張表被寫時
        # 才重跑。隔壁的 `_visible_elections`（:26-29）就是這樣寫的，不要只有一邊有。
        elections = Election.search(
            [('company_id', '=', member.company_id.id),
             ('meeting_id', '=', meeting.id)] + _election_visibility_domain(),
            order='id')
        values.update({
            'hub_elections': elections,
            'hub_registration_open': {
                e.id: Candidate._registration_open(e) for e in elections},
            'hub_my_candidacies': {
                (c.election_id.id, c.office): c
                for c in _my_candidacies(member, elections)},
            'hub_election_labels': dict(Election._fields['state'].selection),
            'hub_office_labels': dict(Candidate._fields['office'].selection),
        })
        return values
