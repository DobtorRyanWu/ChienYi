"""會員自助登記參選（M14-A）。

守的是三件事，按重要性排：

1. **只動得了自己那一筆**——`_register_self` 收的 member 由 `_me()` 解出，
   而 `_withdraw_self` 必須比對 `candidate.member_id == member`；
   少了它，帶別人的 `candidate_id` 就能把對手退選掉。
2. **時限與資格的閘門在模型層**，不在 controller：share 使用者對 `assoc.*`
   沒有 ACL、路由一律 sudo，閘門寫在 controller 的話多一條路由就漏一次。
3. **既有的後台建檔沒有被弄壞**——自助登記刻意不帶哨兵 context，
   走的是與承辦建檔同一條 create。
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_election.tests.common import AssocElectionCase
from odoo.addons.assoc_portal.tests.common import PASSWORD, PortalCase, index_cards, visible_card_urls


@tagged('post_install', '-at_install')
class TestSelfRegister(AssocElectionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Candidate = cls.env['assoc.election.candidate']
        # 另開一場，不要去動基底那場（它已經有候選人、別的測試靠它）
        cls.open_election = cls.env['assoc.election'].create({
            'name': '開放自助登記的選舉', 'company_id': cls.company.id,
            'meeting_id': cls.meeting.id, 'term_id': cls.term.id,
            'director_seats': 3, 'director_alt': 1,
            'supervisor_seats': 1, 'supervisor_alt': 0,
            'registration_deadline': fields.Datetime.now() + timedelta(days=7),
        })

    def _logs(self, action):
        return self.env['assoc.audit.log'].sudo().search([('action', '=', action)])

    # ------------------------------------------------------------------
    # 正路
    # ------------------------------------------------------------------
    def test_member_can_register_and_it_leaves_a_trail(self):
        before = len(self._logs('candidate_self_register'))
        cand = self.Candidate._register_self(
            self.open_election, self.members['A01'], 'director')
        self.assertEqual(cand.state, 'registered', '自助登記只能建到「已登記」，不是「已確認」')
        self.assertEqual(cand.member_id, self.members['A01'])
        self.assertEqual(len(self._logs('candidate_self_register')), before + 1)

    def test_member_can_withdraw_their_own_registration(self):
        cand = self.Candidate._register_self(
            self.open_election, self.members['A01'], 'director')
        cand._withdraw_self(self.members['A01'])
        self.assertEqual(cand.state, 'withdrawn')
        self.assertTrue(self._logs('candidate_self_withdraw'))

    def test_backend_creation_still_works(self):
        """**回歸**：自助登記不帶哨兵，走的是與承辦建檔同一條 create。

        這一支紅＝我把既有的後台路徑弄壞了，而那條路是公會真正在用的。
        """
        cand = self.Candidate.create({
            'election_id': self.open_election.id,
            'office': 'supervisor', 'member_id': self.members['A02'].id})
        self.assertEqual(cand.state, 'registered')

    # ------------------------------------------------------------------
    # 閘門
    # ------------------------------------------------------------------
    def test_cannot_withdraw_someone_elses_registration(self):
        """**最重要的一條**：帶別人的 candidate_id 不可以把對手退選掉。"""
        victim = self.Candidate._register_self(
            self.open_election, self.members['A01'], 'director')
        with self.assertRaises(UserError):
            victim._withdraw_self(self.members['A02'])
        victim.invalidate_recordset()
        self.assertEqual(victim.state, 'registered', '別人的登記不可以被動到')

    def test_registration_closes_at_the_deadline(self):
        self.open_election.write({
            'registration_deadline': fields.Datetime.now() - timedelta(minutes=1)})
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.open_election, self.members['A01'], 'director')

    def test_withdraw_also_closes_at_the_deadline(self):
        """退選與登記用同一個時間判斷（`_registration_open`），不可以只擋一邊。"""
        cand = self.Candidate._register_self(
            self.open_election, self.members['A01'], 'director')
        self.open_election.write({
            'registration_deadline': fields.Datetime.now() - timedelta(minutes=1)})
        with self.assertRaises(UserError):
            cand._withdraw_self(self.members['A01'])
        cand.invalidate_recordset()
        self.assertEqual(cand.state, 'registered')

    def test_election_without_a_deadline_is_not_open_to_self_service(self):
        """沒填截止日＝這場不開放線上登記（預設關著，不是預設開著）。"""
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.election, self.members['A06'], 'director')

    def test_cannot_register_after_the_roster_is_frozen(self):
        """**斷言要比對訊息**，不能只比型別。

        拿掉 `_register_self` 的 draft 檢查之後，`create` 裡既有的 `_check_editable`
        照樣丟 `UserError`（訊息是後台用語「名冊已凍結，候選人不可再變更」），
        所以只比型別的話我指名的那道防線其實沒被驗到——mutation 實測存活
        （M-B：綠或紅都可能是別的東西滿足了斷言）。會員看到的應該是「不能再登記」。
        """
        self.open_election.action_ready()
        self.assertNotEqual(self.open_election.state, 'draft')
        with self.assertRaisesRegex(UserError, '不能再登記'):
            self.Candidate._register_self(
                self.open_election, self.members['A06'], 'director')

    def test_ineligible_member_is_refused(self):
        """會費過期的人不能參選（與選舉權同一個判準）。"""
        self.assertFalse(self.ineligible.is_voter_eligible)
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.open_election, self.ineligible, 'director')

    def test_office_not_being_elected_is_refused(self):
        """沒有席次的職位不能登記——用的是選票頁同一支 `_active_offices()`。"""
        self.open_election.write({'supervisor_seats': 0, 'supervisor_alt': 0})
        self.assertNotIn('supervisor', self.open_election._active_offices())
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.open_election, self.members['A01'], 'supervisor')

    def test_unknown_office_is_refused(self):
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.open_election, self.members['A01'], 'chairman')

    def test_confirmed_registration_cannot_be_withdrawn_by_the_member(self):
        """承辦確認過之後名單可能已對外公布，退選要走後台留軌跡。"""
        cand = self.Candidate._register_self(
            self.open_election, self.members['A01'], 'director')
        cand.write({'state': 'confirmed'})
        with self.assertRaises(UserError):
            cand._withdraw_self(self.members['A01'])
        cand.invalidate_recordset()
        self.assertEqual(cand.state, 'confirmed')

    def test_self_registration_does_not_carry_the_sentinel(self):
        """`_register_self` **刻意不帶哨兵**，所以 `check_created` 仍然守得住。

        帶了哨兵的話，前端送來的 `default_state='write_in'` 會原封流進 create
        ——「名單外得票」繞過凍結名冊的選舉權檢查，正是 §16 通則 1 擋的那件事。
        """
        Candidate = self.Candidate.with_context(default_state='write_in')
        with self.assertRaises(Exception):
            Candidate._register_self(self.open_election, self.members['A01'], 'director')
        self.assertFalse(self.Candidate.search([
            ('election_id', '=', self.open_election.id),
            ('member_id', '=', self.members['A01'].id)]))

    def test_duplicate_registration_is_refused(self):
        self.Candidate._register_self(self.open_election, self.members['A01'], 'director')
        with self.assertRaises(UserError):
            self.Candidate._register_self(
                self.open_election, self.members['A01'], 'director')

    def test_another_guilds_member_is_refused_without_saying_so(self):
        """跨公會：訊息不可以說「這是別家公會的」——那就成了存在性探測器。"""
        other = self.env['res.company'].create({'name': '另一個公會（M14）'})
        partner = self.env['res.partner'].create({'name': '他會會員', 'company_id': other.id})
        outsider = self.env['assoc.member'].create({
            'partner_id': partner.id, 'member_no': 'Z01', 'company_id': other.id,
            'fee_paid_opening': fields.Date.today() + timedelta(days=365)})
        with self.assertRaises(UserError) as caught:
            self.Candidate._register_self(self.open_election, outsider, 'director')
        self.assertNotIn('公會', str(caught.exception).replace('公會辦公室', ''))


@tagged('post_install', '-at_install')
class TestSelfRegisterRoutes(HttpCase, PortalCase):
    """三條路由走**真的 HTTP**。

    為什麼一定要有這一段：`_withdraw_self` 只驗「這筆是不是你的」，
    **不驗「是不是這一場的」**——後者只存在於 controller
    （`assoc_election_register`／`withdraw` 的 `candidate.election_id != election`），
    模型層的測試一行都碰不到它。委託書那一輪就是這樣讓三條 mutant 假存活。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `PortalCase.new_member` 不設繳費，而參選資格看 `is_voter_eligible`
        # ——不補這一行，所有登記都會被資格閘正確地擋下來（實際踩到）
        cls.member.write({'fee_paid_opening': fields.Date.today() + timedelta(days=365)})
        cls.meeting = cls.env['assoc.meeting'].create({
            'name': 'M14 選舉測試大會', 'kind': 'assembly',
            'company_id': cls.company.id, 'date_begin': fields.Datetime.now()})
        cls.meeting.action_open_checkin()

        term = cls.env['assoc.term'].create({
            'company_id': cls.company.id, 'term_no': 12,
            'date_from': fields.Date.today(), 'state': 'current'})

        def election(name):
            return cls.env['assoc.election'].create({
                'name': name, 'company_id': cls.company.id, 'meeting_id': cls.meeting.id,
                'term_id': term.id,
                'director_seats': 3, 'director_alt': 1,
                'supervisor_seats': 1, 'supervisor_alt': 0,
                'registration_deadline': fields.Datetime.now() + timedelta(days=7)})
        cls.election_a = election('M14 甲場')
        cls.election_b = election('M14 乙場')

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)

    def _csrf(self):
        page = self.url_open('/my/assoc/elections')
        return page.text.split('name="csrf_token" value="')[1].split('"')[0]

    def _candidates(self):
        return self.env['assoc.election.candidate'].sudo().search(
            [('member_id', '=', self.member.id)])

    def test_my_home_has_the_elections_card(self):
        """「參選登記」入口跟其他會員入口一樣排在 /my（裝了這個橋接模組才有）。"""
        home = self.url_open('/my')
        self.assertIn('/my/assoc/elections', visible_card_urls(home.text))
        icon = index_cards(home.text)['/my/assoc/elections'][1]
        self.assertTrue(icon and icon.startswith('/assoc_portal_election/static/src/img/'), icon)
        self.assertEqual(self.url_open(icon).status_code, 200, icon)

    def test_page_renders_and_lists_the_open_election(self):
        page = self.url_open('/my/assoc/elections')
        self.assertEqual(page.status_code, 200)
        self.assertIn('M14 甲場', page.text)
        self.assertIn('登記參選', page.text)

    def test_register_over_http_creates_the_candidate(self):
        self.url_open('/my/assoc/elections/%s/register' % self.election_a.id,
                      data={'csrf_token': self._csrf(), 'office': 'director'})
        cand = self._candidates()
        self.assertEqual(len(cand), 1)
        self.assertEqual(cand.election_id, self.election_a)
        self.assertEqual(cand.state, 'registered')

    def test_withdraw_refuses_a_candidate_from_another_election(self):
        """**這一條只有 HTTP 測得到**：把乙場的 candidate_id 送到甲場的退選路由。

        模型層的 `_withdraw_self` 會放行（那確實是本人的登記），
        擋住它的是 controller 把 candidate 綁回 URL 上那一場。
        """
        self.url_open('/my/assoc/elections/%s/register' % self.election_b.id,
                      data={'csrf_token': self._csrf(), 'office': 'director'})
        cand = self._candidates()
        self.assertEqual(len(cand), 1)
        response = self.url_open(
            '/my/assoc/elections/%s/withdraw' % self.election_a.id,
            data={'csrf_token': self._csrf(), 'candidate_id': cand.id})
        self.assertEqual(response.status_code, 404)
        cand.invalidate_recordset()
        self.assertEqual(cand.state, 'registered', '不可以被別場的退選路由動到')

    def test_withdraw_over_http_works_on_the_right_election(self):
        """反向控制：證明上一支紅的是「綁錯場次」，不是「退選根本壞掉」。"""
        self.url_open('/my/assoc/elections/%s/register' % self.election_a.id,
                      data={'csrf_token': self._csrf(), 'office': 'director'})
        cand = self._candidates()
        self.url_open('/my/assoc/elections/%s/withdraw' % self.election_a.id,
                      data={'csrf_token': self._csrf(), 'candidate_id': cand.id})
        cand.invalidate_recordset()
        self.assertEqual(cand.state, 'withdrawn')
