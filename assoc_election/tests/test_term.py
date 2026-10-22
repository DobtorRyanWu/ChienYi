"""屆次（選罷辦法 §6 I：選舉票應載明團體名稱、選舉屆次、職稱及年月日）。

§6 的「載明」對**紙本與電子票一視同仁**，不是只有紙本票才要——這一點在
2026-10-15 讀 §6 原文時才確認，而電子選票頁當時只印了團體名稱與選舉名稱。
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_election.models.assoc_election import GUARD_STATE

from .common import AssocElectionCase


@tagged('post_install', '-at_install')
class TestTerm(AssocElectionCase):

    def _ready_payload(self):
        """凍結名冊那一筆的鏈 payload。"""
        log = self.election.log_ids.filtered(
            lambda one: one.action == 'state_change' and one.payload.get('to') == 'ballot_ready')
        self.assertEqual(len(log), 1)
        return log.payload

    # ---- 正當入口 ----

    def test_the_legitimate_path_still_freezes_the_roster(self):
        """**加了「必須有屆次」這道閘之後，正常流程仍然走得通。**

        L4⑤：加「必須帶 X」的前置條件時，要先對每一條正當入口實跑一次，
        並補一支「正當入口仍然成功」的測試——否則只驗了拒絕、沒驗放行。
        M11 就是在這裡踩過一次（`if not docids: raise` 打死了後台列印按鈕）。
        """
        self.election.action_ready()
        self.assertEqual(self.election.state, 'ballot_ready')
        self.assertEqual(self.election.term_no, 12)
        self.assertTrue(self.election._verify_chain())

    def test_freezing_the_roster_writes_the_term_row(self):
        """凍結名冊時要**寫**屆次那一列（no-op UPDATE），否則守衛擋不住 write skew。

        為什麼是寫、不是鎖，以及兩種先後順序的實證，在 `test_term_concurrency.py`
        （兩條真連線，`assoc_concurrency` 標籤；L2⑫：單交易測試在結構上看不到競態）。
        這一支只驗「那一句有沒有執行、而且真的寫到屆次那一列」：攔 `cr.execute` 記下
        SQL、參數與受影響的列數——與 `tools/check_verify_script.py` 對 `checks.append`
        做靜態斷言同一類判準。先抓原件再包（L2②：wrapper 裡呼叫 `cr.execute` 會無限
        遞迴）。只比 SQL 前綴的話，寫錯列（`WHERE id = 別的`）或寫零列
        （`… AND false`）也會綠（第六、七輪 skeptic），所以參數與列數都要比。
        **第一版改用 `xmax` 判斷，實跑發現 fixture 建完 term 之後 xmax 就已經
        不是 0**（前置斷言直接紅），所以那把尺量不到我要量的東西。
        """
        statements = []
        original = self.env.cr.execute

        def recording(query, params=None):
            result = original(query, params) if params is not None else original(query)
            statements.append((str(query), params, self.env.cr.rowcount))
            return result

        self.patch(self.env.cr, 'execute', recording)
        self.election.action_ready()
        writes = [query for query, params, rowcount in statements
                  if query.upper().lstrip().startswith('UPDATE ASSOC_TERM ')
                  and params == (self.term.id,) and rowcount == 1]
        self.assertTrue(
            writes,
            'action_ready 沒有寫到屆次那一列：改屆次與凍結名冊可以同時成立'
            '（只下 FOR UPDATE 在 REPEATABLE READ 下擋不住「凍結先提交」；'
            '實際下過的 SQL 共 %d 句）' % len(statements))

    def test_the_frozen_term_goes_into_the_chain(self):
        """屆次要進**凍結名冊**那一筆，不是開票那一筆。

        L1⑫：承諾的時點比承諾的內容更要緊。屆次印在選票上，所以它必須在
        第一張票發出去之前就定下來——`ballot_ready` 在 `open` 之前，
        而監票員抄的鏈頭在 `open` 當下。放到 `counted` 就什麼也證明不了。
        """
        self.election.action_ready()
        self.assertEqual(self._ready_payload().get('term_no'), 12)
        # payload 進得了 json.dumps（datetime 混進去會讓整條鏈寫不出來）
        json.dumps(self._ready_payload())

    # ---- 閘門 ----

    def test_freezing_without_a_term_is_refused(self):
        self.election.term_id = False
        with self.assertRaises(UserError) as caught:
            self.election.action_ready()
        # **比訊息，不是比「有沒有提到屆次」**：下面那道「屆次必須大於 0」的
        # fail-closed 也會講屆次，於是拿掉這一道照樣有例外、照樣含「屆次」兩個字
        # ——測試會紅，看起來像它有在守，其實擋住的是另一道（L2⑮）。
        self.assertIn('請先指定', str(caught.exception))
        self.assertEqual(self.election.state, 'draft', '擋下來之後不可以留下半套狀態')
        self.assertFalse(self.election.voter_ids, '名冊也不可以先建出來')

    def test_a_term_from_another_company_is_refused(self):
        """`domain` 只管表單，RPC 直接寫一個看不到的 id 繞得過去——要 fail-closed。"""
        other = self.env['res.company'].create({'name': '別的公會'})
        self.election.term_id = self.env['assoc.term'].create({
            'company_id': other.id, 'term_no': 3, 'date_from': fields.Date.today()})
        with self.assertRaises(UserError) as caught:
            self.election.action_ready()
        self.assertIn('同一個公會', str(caught.exception))
        self.assertEqual(self.election.state, 'draft')

    def test_term_no_cannot_be_written_without_the_state_machine(self):
        """`term_no` 是快照，只能由狀態機寫。

        可以用 RPC 改的話，選票上印的屆次就與鏈上那一筆對不起來——
        而 §6 的要件正是「選票載明屆次」，兩個數字不一致時沒有人說得出
        哪一個才算數。
        """
        for context in ({}, {GUARD_STATE: True}, {GUARD_STATE: 1}):
            with self.assertRaises(UserError, msg=str(context)):
                self.election.with_context(**context).write({'term_no': 99})
        self.assertEqual(self.election.term_no, 0)
        self.election.with_context(**{GUARD_STATE: GUARD}).write({'term_no': 7})
        self.assertEqual(self.election.term_no, 7)

    def test_creating_an_election_with_a_term_no_is_refused(self):
        """create 驗結果不驗輸入（§16 通則 1）：`default_term_no` 也要擋。"""
        with self.assertRaises(UserError):
            self.env['assoc.election'].with_context(default_term_no=99).create({
                'name': '偷帶屆次', 'company_id': self.company.id,
                'meeting_id': self.meeting.id, 'term_id': self.term.id})

    # ---- 屆次本身 ----

    def test_term_no_is_unique_per_company(self):
        from psycopg2 import IntegrityError
        with self.assertRaises(IntegrityError), self.env.cr.savepoint(flush=False):
            self.env['assoc.term'].create({
                'company_id': self.company.id, 'term_no': 12,
                'date_from': fields.Date.today()})

    def test_term_no_must_be_positive(self):
        from psycopg2 import IntegrityError
        with self.assertRaises(IntegrityError), self.env.cr.savepoint(flush=False):
            self.env['assoc.term'].create({
                'company_id': self.company.id, 'term_no': 0,
                'date_from': fields.Date.today()})

    def test_term_no_is_locked_once_an_election_froze_it(self):
        """被凍結之後改屆次，會讓後台顯示的與鏈上的、紙上的互相矛盾。"""
        self.election.action_ready()
        with self.assertRaises(UserError):
            self.term.term_no = 13
        self.assertEqual(self.term.term_no, 12)
        # 草稿階段改得動（還沒有任何票、沒有任何鏈紀錄引用它）
        draft_term = self.env['assoc.term'].create({
            'company_id': self.company.id, 'term_no': 20, 'date_from': fields.Date.today()})
        draft_term.term_no = 21
        self.assertEqual(draft_term.name, '第 21 屆')

    def test_a_plain_staff_user_can_open_the_term_form(self):
        """職員（沒有選務權）打得開屆次表單。

        `assoc.term` 的讀權開給 `group_assoc_staff`，而「本屆的選舉」那一頁
        讀的 `assoc.election` 只給選務／監票／公會管理員——那個 One2many
        沒有 `groups=` 的話，出納或報到台帳號**一點開屆次就 AccessError**
        （抗辯以 `finance_tp` 實查複現）。Odoo 只會因為 `groups=` 把欄位整個
        拿掉，不會因為讀不到就略過。
        """
        staff = self.env['res.users'].create({
            'name': '只是職員', 'login': 'plain_staff_term_test',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])]})
        officer = self.env['res.users'].create({
            'name': '選務', 'login': 'officer_term_test',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [
                self.env.ref('assoc_base.group_assoc_staff').id,
                self.env.ref('assoc_election.group_election_officer').id])]})
        view = self.env.ref('assoc_base.assoc_term_view_form')
        Term = self.env['assoc.term']
        # **斷言打在 view 的 arch 上，不是 `web_read`。** `groups=` 是 view 層的
        # 機制：伺服器在送出 arch 時就把那一段拿掉，於是前端根本不會去要那個
        # 欄位。拿明寫的 spec 直接 `web_read` 是在模擬一個「view 沒給、客戶端
        # 硬要」的請求，驗到的是 ACL 而不是這道修正（第一版就是這樣寫錯的）。
        officer_arch = Term.with_user(officer).get_view(view.id, 'form')['arch']
        self.assertIn('election_ids', officer_arch,
                      '先證明這一頁本來在，否則下面那半段恆真（M-C）')
        staff_arch = Term.with_user(staff).get_view(view.id, 'form')['arch']
        self.assertNotIn('election_ids', staff_arch,
                         '職員拿到的表單不可以含有他讀不到的 assoc.election')
        # 真的打開（用 view 會給的欄位）不會炸
        self.election.action_ready()
        self.assertTrue(self.term.with_user(staff).web_read({'name': {}, 'term_no': {}}))

    def test_a_cancelled_draft_does_not_lock_the_term(self):
        """建了又取消、從來沒凍結過名冊的選舉，不可以永久鎖死這一屆。

        判準是 `term_no` 快照（只有 `action_ready` 寫得出來），不是
        `state != 'draft'`——後者把 `cancelled` 也算進去，而那種選舉沒有鏈、
        沒有票、`term_no` 仍是 0，鎖它的錯誤訊息（「已經有選舉凍結名冊」）
        也與事實不符。
        """
        self.election.action_cancel()
        self.assertEqual(self.election.state, 'cancelled')
        self.assertEqual(self.election.term_no, 0, '取消的草稿不會有快照')
        self.term.term_no = 13          # 不可以被擋
        self.assertEqual(self.term.term_no, 13)

    def test_default_term_length_is_three_years(self):
        """技師法 §31 的 3 年只是 `date_to` 的預設值，不驗證。"""
        term = self.env['assoc.term'].new({
            'company_id': self.company.id, 'term_no': 30, 'date_from': '2026-01-01'})
        term._onchange_date_from()
        self.assertEqual(fields.Date.to_string(term.date_to), '2028-12-31')
        # 已經填好的迄日不可以被覆寫
        kept = self.env['assoc.term'].new({
            'company_id': self.company.id, 'term_no': 31,
            'date_from': '2026-01-01', 'date_to': '2027-06-30'})
        kept._onchange_date_from()
        self.assertEqual(fields.Date.to_string(kept.date_to), '2027-06-30')

    # ---- §6 四要件 ----

    def test_ballot_header_gives_the_term_and_the_date_only(self):
        """§6 四要件裡，`_ballot_header()` 負責的是**屆次與年月日**。

        另外兩個刻意不在裡面：「團體名稱」由共用版型的 heading 印（領取頁與
        錯誤頁也要印它），「職稱」逐職位在 `_ballot_offices()` 的 label。

        這支也守住**不要再回沒人讀的鍵**：原本還回 `organization` 與 `term_no`，
        兩個都沒有任何呼叫端（樣板印的是 `election.company_id.name`），於是
        docstring 宣稱的「§6 的要件只能有一個來源」對團體名稱一開始就名不副實
        （第二輪 simplifier 與 red-team 各自指到）。
        年月日取不取大會日由 `test_ballot_date_is_the_meeting_day_not_today` 守
        ——那一支用的是**日期與今天不同**的 fixture，這裡的大會就是今天，
        所以在這裡斷言 date_label 等於今天是量不到那件事的。
        """
        self.election.action_ready()
        header = self.election._ballot_header()
        self.assertEqual(header['term_label'], '第 12 屆')
        self.assertEqual(set(header), {'term_label', 'date_label'},
                         '多一個沒人讀的鍵，下一個人就會以為它有用')
        # 職稱：§6 的第四個要件
        self.assertEqual({office['label'] for office in self.election._ballot_offices()},
                         {'理事', '監事'})

    def test_ballot_date_is_the_meeting_day_not_today(self):
        """§6 的年月日取**大會日**，不是列印／瀏覽當下。

        共用 fixture 的大會就是今天，所以「改成取現在時間」這個錯誤在那一場上
        **看不出來**——同一天，印出來的字串一模一樣。要另開一場日期不同的大會
        才量得到（L2③：先證明這個 rig 真的會改變結果）。
        """
        past = self.env['assoc.meeting'].create({
            'name': '去年的大會', 'company_id': self.company.id,
            'date_begin': fields.Datetime.now() - timedelta(days=400)})
        election = self.env['assoc.election'].create({
            'name': '去年那一場', 'company_id': self.company.id,
            'meeting_id': past.id, 'term_id': self.term.id})
        expected = fields.Datetime.context_timestamp(
            past.with_context(tz='Asia/Taipei'), past.date_begin).strftime('%Y-%m-%d')
        self.assertNotEqual(expected, fields.Date.to_string(fields.Date.today()),
                            '這個 fixture 的日期必須與今天不同，否則測試恆真')
        self.assertEqual(election._ballot_header()['date_label'], expected)


@tagged('post_install', '-at_install')
class TestBallotPageSection6(HttpCase, AssocElectionCase):
    """選罷辦法 §6 的四要件要真的出現在**使用者看到的那一頁**上。

    斷言打在頁面內容而不是 `_ballot_header()` 的回傳值：樣板的 `t-if` 有一半
    的判斷在 QWeb 裡，Python 的測試一條都碰不到它們（M-B：斷言要打在使用者
    看得到的結果上）。
    """

    def test_the_ballot_page_shows_all_four_elements(self):
        self._open()
        voter, _token, nonce = self._ready_ticket('A01')
        self.opener.cookies.set('ax_nonce', nonce,
                                path='/assoc/vote/%s' % self.election.uuid)
        page = self.url_open('/assoc/vote/%s/ballot' % self.election.uuid)
        self.assertEqual(page.status_code, 200)
        html = page.text
        # **基準要來自頁面以外**。原本這裡拿 `_ballot_header()` 的回傳值去比
        # 頁面，那是自我參照：`_ballot_header()` 回傳垃圾時頁面印同一份垃圾，
        # 測試照樣綠（M-B：斷言被「別的東西」滿足）。改成各自獨立算。
        expected_date = fields.Datetime.context_timestamp(
            self.meeting.with_context(tz='Asia/Taipei'),
            self.meeting.date_begin).strftime('%Y-%m-%d')
        # 團體名稱由共用版型印（不經 `_ballot_header()`，見那一支的 docstring）
        self.assertIn(self.company.name, html, '§6：團體名稱')
        self.assertIn('第 12 屆', html, '§6：選舉屆次')
        self.assertIn(expected_date, html, '§6：年月日')
        for label in ('理事', '監事'):
            self.assertIn(label, html, '§6：職稱')
        # **這一行讓下面那支否定斷言有意義**：領取頁斷言「沒有 section6 區塊」，
        # 而那個斷言在 attribute 改名之後會變成恆真——除非有人在這裡證明
        # 選票頁真的有它（M-B：要單獨證明一道，先確認量尺還在）。
        self.assertIn('data-ax="section6"', html, '§6 的區塊要在選票頁上')
        self.assertEqual(voter.state, 'issued', '頁面是唯讀的，不可以順手改狀態')

    def test_the_claim_page_does_not_carry_the_meeting_date(self):
        """§6 的要件只印在**選票頁**，不印在匿名可達的領取頁。

        `/assoc/vote/<uuid>/claim` 只要有 uuid 就打得到，而 uuid 就是公開
        大螢幕的網址。§6 要求載明的是選舉票本身，沒有理由讓每一頁都把
        大會日期送出去。
        """
        self._open()
        page = self.url_open('/assoc/vote/%s/claim' % self.election.uuid)
        self.assertEqual(page.status_code, 200)
        expected_date = fields.Datetime.context_timestamp(
            self.meeting.with_context(tz='Asia/Taipei'),
            self.meeting.date_begin).strftime('%Y-%m-%d')
        self.assertNotIn(expected_date, page.text,
                         '大會日期沒有理由出現在匿名可達的領取頁')
        # **不可以斷言「『第 12 屆』不在頁面上」**：領取頁的版型本來就印
        # `election.name`，而正式資料的選舉就叫「第 12 屆理監事選舉」
        # （`tools/seed_demo.py`）——這個斷言之所以綠，只是因為共用 fixture
        # 把選舉取名「測試選舉」，正式命名下它會假紅（第二輪 simplifier）。
        # 要守的是「§6 那個區塊不在這一頁」，所以斷言打在區塊上。
        self.assertNotIn('data-ax="section6"', page.text,
                         '§6 的區塊只屬於選票頁')

    def test_a_ballot_without_a_term_says_so_instead_of_leaving_a_blank(self):
        """升級當下還在投票的場次拿不到屆次——那要**說出來**，不是留白。

        `term_no` 只有 `action_ready` 寫得進去，而它只吃草稿，所以升級時已經
        在 `open` 的選舉永遠補不回屆次（migration 會警告，實查正式庫副本有
        12 場）。那時 §6 的要件少一個，而**空白與「這場沒登記」長得一樣**：
        選民與監票員看到空白只會以為版面壞了（第二輪 red-team）。
        """
        self._open()
        # 模擬升級當下那 12 場：名冊已凍結、票已開發，而屆次欄位是 0
        self.election.with_context(**{GUARD_STATE: GUARD}).write({'term_no': 0})
        _voter, _token, nonce = self._ready_ticket('A01')
        self.opener.cookies.set('ax_nonce', nonce,
                                path='/assoc/vote/%s' % self.election.uuid)
        page = self.url_open('/assoc/vote/%s/ballot' % self.election.uuid)
        self.assertEqual(page.status_code, 200)
        self.assertIn('（本場未登記選舉屆次）', page.text)
        self.assertNotIn('第 12 屆', page.text, '屆次清掉了就不可以還印著舊值')
