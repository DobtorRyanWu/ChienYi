"""會員前台「大會專區」整合頁（`/my/assoc/meetings*`）。

**為什麼放在橋接模組而不是 `assoc_portal`**：這一頁的重點是「同一場大會的事
收攏成一頁」，而選舉那一塊是 `assoc_portal_election` 用 xpath 掛進
`#assoc_meeting_hub_extra` 的。只在 `assoc_portal` 測就只測得到空 anchor，
測不到整合後的樣子——而整合正是這一頁存在的理由。

**為什麼不是只留 `tools/e2e/e2e_m14_hub.py`**：那支要人工跑、對示範庫做破壞性
寫入再自己收尾（第一次就留了殘料），而且進不了 `-u --test-enable`，mutation
harness 也碰不到。沒有人會每次改動都記得跑它——等於這一頁沒有網。
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.assoc_base.tools import GUARD
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_portal.tests.common import PASSWORD, PortalCase


@tagged('post_install', '-at_install')
class TestMeetingHub(HttpCase, PortalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member.write({'fee_paid_opening': fields.Date.today() + timedelta(days=365)})
        # 這兩位必須在 `action_open_checkin()` **之前**建立：名冊是當下一次建好的，
        # 之後才出現的會員沒有出席列，連帶也當不了委託的任何一方
        cls.other_member = cls.new_member('M14X', None, 'm14x@example.com')
        cls.third_member = cls.new_member('M14Y', None, 'm14y@example.com')
        cls.meeting = cls.env['assoc.meeting'].create({
            'name': 'M14 專區測試大會', 'kind': 'assembly', 'place': '測試會場',
            'company_id': cls.company.id, 'date_begin': fields.Datetime.now()})
        # 名冊（出席列）是專區的入口 guard，所以一定要先開放報到把它建出來
        cls.meeting.action_open_checkin()
        # 別公會的場次。**一定要開放報到並建好名冊**：停在 draft 的話那個 404 是
        # `meeting_id.state != 'draft'` 擋下的，不是名冊——測試會證明到另一件事，
        # 而「別公會有名冊的大會會不會外洩」就完全沒有被驗到（M-B）。
        cls.foreign_member = cls.new_member(
            'M14Z', None, 'm14z@example.com', company=cls.other_company)
        cls.foreign_meeting = cls.env['assoc.meeting'].create({
            'name': 'M14 他公會大會', 'kind': 'assembly',
            'company_id': cls.other_company.id, 'date_begin': fields.Datetime.now()})
        cls.foreign_meeting.action_open_checkin()

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)

    def _election(self, name, deadline=True):
        term = self.env['assoc.term'].search(
            [('company_id', '=', self.company.id), ('term_no', '=', 12)], limit=1)
        if not term:
            term = self.env['assoc.term'].create({
                'company_id': self.company.id, 'term_no': 12,
                'date_from': fields.Date.today(), 'state': 'current'})
        return self.env['assoc.election'].create({
            'name': name, 'company_id': self.company.id, 'meeting_id': self.meeting.id,
            'term_id': term.id,
            'director_seats': 3, 'director_alt': 1,
            'supervisor_seats': 1, 'supervisor_alt': 0,
            'registration_deadline': (
                fields.Datetime.now() + timedelta(days=7) if deadline else False),
        })

    def _hub(self, meeting=None):
        return self.url_open('/my/assoc/meetings/%s' % (meeting or self.meeting).id)

    # ------------------------------------------------------------------
    # 頁面本身
    # ------------------------------------------------------------------
    def test_list_shows_the_meetings_i_am_on_the_roster_for(self):
        page = self.url_open('/my/assoc/meetings')
        self.assertEqual(page.status_code, 200)
        self.assertIn('M14 專區測試大會', page.text)
        self.assertNotIn('M14 他公會大會', page.text)

    def test_hub_collects_every_section_on_one_page(self):
        """整合的定義就是這四塊同時在。少一塊就不是這一頁了。"""
        self._election('M14 專區選舉')
        page = self._hub()
        self.assertEqual(page.status_code, 200)
        for section in ('我的出席', '委託', '我的禮品', '這一場的選舉'):
            self.assertIn(section, page.text, '專區少了「%s」區塊' % section)

    # ------------------------------------------------------------------
    # 入口 guard：名冊是唯一判準（跨公會也靠它）
    # ------------------------------------------------------------------
    def test_meeting_i_am_not_on_the_roster_for_is_not_found(self):
        """別公會的大會：**已開放報到、名冊也建好了**，擋住我的只能是名冊。"""
        self.assertEqual(self.foreign_meeting.state, 'checkin_open')
        self.assertTrue(
            self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', self.foreign_meeting.id)]),
            '別公會那場要有名冊，否則擋住我的是「籌備中」不是名冊（M-B）')
        self.assertFalse(
            self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', self.foreign_meeting.id),
                ('member_id', '=', self.member.id)]),
            '而我不可以在那份名冊上')
        self.assertEqual(self._hub(self.foreign_meeting).status_code, 404)
        self.assertNotIn('M14 他公會大會', self.url_open('/my/assoc/meetings').text)

    def test_unknown_meeting_is_not_found(self):
        self.assertEqual(self.url_open('/my/assoc/meetings/999999').status_code, 404)

    def test_roster_row_removed_closes_the_door(self):
        """反向控制：證明上面兩條紅的是「名冊」，不是「那一筆剛好不存在」。

        同一場大會，只把我的出席列拿掉，專區就必須關上——否則擋住別公會的
        其實是別的東西，而我會以為名冊這道有在守（L2⑮）。
        """
        self.assertEqual(self._hub().status_code, 200)
        self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', self.meeting.id),
            ('member_id', '=', self.member.id)]).unlink()
        self.env.cr.flush()
        self.assertEqual(self._hub().status_code, 404)

    # ------------------------------------------------------------------
    # 別人的資料不可以出現在我的專區
    # ------------------------------------------------------------------
    def test_hub_does_not_leak_another_members_proxy(self):
        """與我無關的委託（別人委託別人）不可以出現在我的頁面上。

        `mine`／`held` 兩個查詢各自綁 `principal_member_id`／`holder_member_id`；
        少掉任何一邊，整場大會的委託關係就全部攤在每個人的頁面上
        （誰委託誰是會員之間的事，不是公開資訊）。
        """
        proxy = self.env['assoc.meeting.proxy'].with_user(self.admin_user).create({
            'meeting_id': self.meeting.id,
            'principal_member_id': self.other_member.id,
            'holder_member_id': self.third_member.id,
            'purpose': 'attend'})
        self.assertTrue(proxy, '沒建出委託的話這條測試是空的（M-C）')
        self.env.cr.flush()
        page = self._hub()
        self.assertEqual(page.status_code, 200)
        self.assertIn('尚未委託他人', page.text)
        self.assertIn('沒有人委託你', page.text)
        self.assertNotIn(self.other_member.name, page.text)
        self.assertNotIn(self.third_member.name, page.text)

    def test_hub_lists_only_my_own_gift_rows(self):
        """禮品名單是逐會員建的，專區只能列出我自己那幾列。

        斷言用**出現次數**而不是「有沒有出現」：全公會每個人都有同一個品項的
        權利列，所以漏掉 `member_id` 條件時品項名稱照樣出現、只是出現 N 次
        ——用 `in` 判斷的話兩種情況長得一模一樣（M-B）。
        """
        campaign = self.env['assoc.gift.campaign'].sudo().create({
            'name': 'M14 專區禮品', 'company_id': self.company.id,
            'meeting_id': self.meeting.id, 'eligibility': 'active_members'})
        item = self.env['assoc.gift.item'].sudo().create({
            'campaign_id': campaign.id, 'name': 'M14專區紀念品',
            'delivery': 'pickup', 'unit_value': 100})
        campaign.action_ready()
        Entitlement = self.env['assoc.gift.entitlement'].sudo()
        mine = Entitlement.search([('item_id', '=', item.id),
                                   ('member_id', '=', self.member.id)])
        everyone = Entitlement.search([('item_id', '=', item.id)])
        self.assertEqual(len(mine), 1)
        self.assertGreater(len(everyone), len(mine),
                           '別的會員也要有權利列，否則漏條件與不漏條件沒有差別（M-C）')
        self.env.cr.flush()
        page = self._hub()
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.text.count('M14專區紀念品'), 1,
                         '品項出現的次數要等於我自己的權利列數')

    def test_seminar_hub_shows_the_checkout_and_credit_block(self):
        """研討會分支（簽退／積分）——改動裡唯一一段沒有被任何測試渲染過的樣板。

        `_my_attendances` 不分 kind，所以研討會也會進「我的大會」。
        """
        seminar = self.env['assoc.meeting'].create({
            'name': 'M14 研討會', 'kind': 'seminar', 'company_id': self.company.id,
            'date_begin': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(hours=3),
            'credit_points': 3, 'credit_hours': 3.0})
        seminar.action_open_checkin()
        self.env.cr.flush()
        page = self._hub(seminar)
        self.assertEqual(page.status_code, 200)
        self.assertIn('簽退', page.text)
        self.assertIn('積分判定', page.text)

    # ------------------------------------------------------------------
    # 還沒對外公告的東西不可以出現
    # ------------------------------------------------------------------
    def test_draft_meeting_with_a_prebuilt_roster_is_not_exposed(self):
        """`action_build_roster` 在 draft 就跑得動（按鈕只對 closed 隱藏）。

        承辦一補建名冊，還沒公告的開會時間與地點就會落到每位會員的頁面上。
        """
        draft = self.env['assoc.meeting'].create({
            'name': 'M14 還沒公告的大會', 'kind': 'assembly', 'place': '還沒公告的場地',
            'company_id': self.company.id, 'date_begin': fields.Datetime.now()})
        draft.action_build_roster()
        self.assertTrue(
            self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', draft.id), ('member_id', '=', self.member.id)]),
            '名冊要真的建起來，否則這條測試是空的（M-C）')
        self.env.cr.flush()
        page = self.url_open('/my/assoc/meetings')
        self.assertNotIn('M14 還沒公告的大會', page.text)
        self.assertNotIn('還沒公告的場地', page.text)
        self.assertEqual(self._hub(draft).status_code, 404)

    def test_hub_hides_proxies_the_holder_should_not_see(self):
        """`rejected` 是公會對委託人的處置，不給受託人看（既有頁面同口徑）。"""
        proxy = self.env['assoc.meeting.proxy'].with_user(self.admin_user).create({
            'meeting_id': self.meeting.id,
            'principal_member_id': self.other_member.id,
            'holder_member_id': self.member.id, 'purpose': 'attend'})
        body = self._hub().text
        self.assertIn(self.other_member.name, body,
                      'requested 的委託本來就要看得到，否則下面那半是空的（M-C）')
        proxy._reject('名額已滿')
        self.env.cr.flush()
        self.assertEqual(proxy.state, 'rejected')
        self.assertNotIn(self.other_member.name, self._hub().text)

    def test_hook_cannot_override_the_identity_values(self):
        """鉤子不可以蓋掉 controller 剛依登入者綁好的值。

        **守衛改成「擋下來」而不是「悄悄忽略」**：第三輪之前這裡只排 merge 順序，
        鉤子回 `member` 會被靜默丟掉；現在非 `hub_` 的鍵一律 raise，因為
        核心 `ir_qweb` 對 `user_id`／`res_company`／`debug` 用的是 `setdefault`，
        光排順序擋不住那三個。所以這一支現在斷言的是 **500 而不是 200**。
        """
        from odoo.addons.assoc_portal.controllers.portal import AssocPortal
        original = AssocPortal._meeting_hub_extra
        try:
            AssocPortal._meeting_hub_extra = lambda self, member, meeting: {
                'member': None, 'attendance': None, 'gifts': None,
                'mine': None, 'held': None}
            self.assertEqual(self._hub().status_code, 500)
        finally:
            AssocPortal._meeting_hub_extra = original
        self.assertEqual(self._hub().status_code, 200, '還原後要恢復正常')

    def test_expired_draft_election_is_not_exposed(self):
        """截止日已過的草稿不可以列出來——畫面上根本沒有登記入口。

        觸發路徑不需要任何人犯錯：`registration_deadline` 若沒有 `copy=False`，
        「複製上屆選舉」就會把舊的截止日一起帶過來。
        """
        election = self._election('M14 截止日已過的草稿')
        election.registration_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env.cr.flush()
        self.assertNotIn('M14 截止日已過的草稿', self._hub().text)

    def test_registration_deadline_is_not_copied(self):
        copy = self._election('M14 上屆選舉').copy()
        self.assertFalse(copy.registration_deadline,
                         '複製出來的草稿不可以帶著舊截止日，否則它一出生就對全名冊可見')

    def test_other_company_election_on_my_meeting_is_not_exposed(self):
        """公會條件要自己帶一份，不要外包給兩條 @api.constrains。"""
        rogue = self.env['assoc.election'].sudo().create({
            'name': 'M14 他公會的選舉', 'company_id': self.company.id,
            'meeting_id': self.meeting.id, 'registration_deadline':
            fields.Datetime.now() + timedelta(days=7)})
        self.assertIn('M14 他公會的選舉', self._hub().text, '先證明它本來看得到（M-C）')
        # constrains 只在自己那張表被寫時才重跑，所以換公會不會被它擋下
        self.env.cr.execute('UPDATE assoc_election SET company_id = %s WHERE id = %s',
                            [self.other_company.id, rogue.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        self.assertNotIn('M14 他公會的選舉', self._hub().text)

    def test_hub_shows_my_candidacy_not_someone_elses(self):
        """`hub_my_candidacies` 的鍵是 `(election_id, office)`，**不含 member_id**。

        所以漏掉 `member_id` 條件時字典不會變大、只會**被別人覆蓋**（同一個鍵，
        最後一筆贏），職位那一行於是改印別人的狀態——頁面看起來完全正常。
        這就是 L3 那條「`{鍵: 值}` 天生覆寫」的形狀，用「有沒有出現」是驗不到的。
        """
        election = self._election('M14 只有別人登記的選舉')
        self.env['assoc.election.candidate'].sudo().with_context(
            assoc_state_machine=GUARD).create({
                'election_id': election.id, 'office': 'director',
                'member_id': self.other_member.id, 'state': 'registered'})
        self.env.cr.flush()
        body = self._hub()
        self.assertEqual(body.status_code, 200)
        self.assertIn('M14 只有別人登記的選舉', body.text, '場次本身要列出來（M-C）')
        self.assertNotIn('已登記', body.text,
                         '別人的「已登記」不可以印在我的職位狀態上')
        self.assertIn('未登記', body.text, '我自己沒登記，印的就該是未登記')

    def _counted_write_in(self, name='M14 開票中的選舉'):
        """把一場選舉推到「已開票、未公告」，並給自己一筆 `write_in`。

        這正是 `_tally` 在開票那一筆做的事（`published` 是之後另一個請求）。
        """
        election = self._election(name)
        self.env['assoc.election.candidate'].sudo().with_context(
            assoc_state_machine=GUARD).create({
                'election_id': election.id, 'office': 'director',
                'member_id': self.member.id, 'state': 'write_in'})
        self.env.cr.execute("UPDATE assoc_election SET state = 'counted' WHERE id = %s",
                            [election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        return election

    def test_counted_election_does_not_reveal_vote_derived_state(self):
        """開票完成、公告之前，不可以透露「名單外得票」這種得票衍生的狀態。"""
        self._counted_write_in()
        body = self._hub().text
        self.assertIn('M14 開票中的選舉', body, '場次本身還是要列出來（M-C）')
        self.assertNotIn('名單外得票', body)

    def test_elections_page_also_hides_the_vote_derived_state(self):
        """**同一道守衛要蓋到兩頁**。

        第一版只裝在大會專區，而專區的「前往登記」連結指過去的那一頁
        （`/my/assoc/elections`）原封不動印同一份資料——紅隊實跑複現。
        守衛要裝在兩頁共用的那一支 helper 上，不是其中一條路徑上。
        """
        self._counted_write_in('M14 另一頁也要擋的選舉')
        page = self.url_open('/my/assoc/elections')
        self.assertEqual(page.status_code, 200)
        self.assertIn('M14 另一頁也要擋的選舉', page.text, '場次本身要列出來（M-C）')
        self.assertNotIn('名單外得票', page.text)

    def test_counted_election_still_shows_a_confirmed_candidacy(self):
        """反向控制：濾掉的只能是 `write_in` 那一列，不是整場選舉。

        整場濾掉的話，一位已被公會確認的候選人在開票後會看到「未登記」
        ——頁面上印了一句假話。
        """
        election = self._election('M14 開票中但我已確認')
        self.env['assoc.election.candidate'].sudo().with_context(
            assoc_state_machine=GUARD).create({
                'election_id': election.id, 'office': 'director',
                'member_id': self.member.id, 'state': 'confirmed'})
        self.env.cr.execute("UPDATE assoc_election SET state = 'counted' WHERE id = %s",
                            [election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        self.assertIn('已確認', self._hub().text)

    def test_write_in_stays_hidden_even_after_publication(self):
        """公告後**也**不顯示：對外公告的只有當選與候補。

        「我至少拿到 1 票」在公告之後一樣不是公告過的事實，所以判準要寫成
        「濾掉這個值」而不是「濾掉 counted 這個狀態」——狀態式只擋得住一個時間窗。
        """
        election = self._counted_write_in('M14 公告後也要擋的選舉')
        self.env.cr.execute("UPDATE assoc_election SET state = 'published' WHERE id = %s",
                            [election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        self.assertNotIn('名單外得票', self.url_open('/my/assoc/elections').text)
        self.assertNotIn('名單外得票', self._hub().text)

    def _published(self, name='M14 已公告的選舉'):
        """把一場選舉推到 published 並塞進真實形狀的 result_json。"""
        election = self._election(name)
        self.env.cr.execute(
            "UPDATE assoc_election SET state = 'published', result_json = %s WHERE id = %s",
            ['{"offices": {"director": {"ranking": ['
             '{"member_id": 1, "member_no": "A1", "name": "當選的人", "votes": 5,'
             ' "rank": 1, "result": "elected"},'
             '{"member_id": 2, "member_no": "A2", "name": "候補的人", "votes": 3,'
             ' "rank": 2, "result": "alternate"},'
             '{"member_id": 3, "member_no": "A3", "name": "落選的人", "votes": 1,'
             ' "rank": 3, "result": "none"}]}}}', election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        return election

    def test_published_block_renders_elected_and_alternate(self):
        """**整個改動裡唯一會印出開票結果的那一段**，要真的渲染一次。

        之前沒有任何測試、E2E 或真實請求走進過它：E2E 是用 psql 撈 JSON 比鍵，
        不是渲染頁面；而唯一有已公告選舉的那場大會屬於別公會。
        """
        self._published()
        body = self._hub().text
        self.assertIn('當選的人', body)
        self.assertIn('候補的人', body, '公開跑馬燈印當選與候補，會員自己的頁面不能更少')
        self.assertNotIn('落選的人', body)

    def test_results_are_not_shown_before_they_are_published(self):
        """公告之前不可以把當選名單貼出來——`counted` 是開票完、還沒公告。"""
        election = self._published('M14 開票完還沒公告')
        self.env.cr.execute("UPDATE assoc_election SET state = 'counted' WHERE id = %s",
                            [election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        body = self._hub().text
        self.assertIn('M14 開票完還沒公告', body, '場次本身要列出來（M-C）')
        self.assertNotIn('當選的人', body)
        self.assertNotIn('候補的人', body)
        self.assertIn('已停止投票', body)

    def test_published_block_never_shows_vote_counts(self):
        """只印姓名，不印票數與名次。"""
        self._published('M14 不可以印票數')
        body = self._hub().text
        self.assertNotIn('>5<', body)
        self.assertNotIn('得票', body)

    def test_cancelled_election_is_not_listed_on_the_elections_page(self):
        """取消的場次被印成「登記已截止」是錯的訊息（它不是截止，是整場取消）。"""
        election = self._election('M14 取消掉的選舉')
        self.assertIn('M14 取消掉的選舉', self.url_open('/my/assoc/elections').text,
                      '先證明它本來看得到（M-C）')
        election.action_cancel()
        self.env.cr.flush()
        self.assertNotIn('M14 取消掉的選舉', self.url_open('/my/assoc/elections').text)

    def test_many_elections_do_not_hide_the_ones_that_need_action(self):
        """塞滿場次之後，**開放登記的**與**正在投票的**都還要看得到。

        上一版的測試是假閘：它把 `wanted` 建成**最後一筆**（id 最大），於是對
        任何 `desc` 排序都必然綠——驗的是實作而不是命題。這一版反過來，
        把要看到的那兩場建成**最舊**的。
        """
        wanted = self._election('M14 我要登記的那一場')
        voting = self._election('M14 正在投票的那一場')
        voting.action_ready()
        voting.action_open()
        for index in range(25):
            self._election('M14 塞位選舉 %d' % index)
        self.env.cr.flush()
        body = self._hub().text
        self.assertIn('M14 我要登記的那一場', body)
        self.assertIn('前往登記', body)
        self.assertIn('M14 正在投票的那一場', body)
        self.assertIn('報到台領票', body, '正在投票那場的領票說明不可以被擠掉')
        self.assertTrue(wanted.exists())

    def test_hook_may_only_add_hub_prefixed_keys(self):
        """守衛在**消費端**，而且驗整個回傳值。

        **鍵要挑「漏過去也不會讓樣板炸掉」的那種**：用 `member: None` 斷言 500
        證明不了守衛有沒有跑——拿掉守衛之後樣板自己會因為 None 炸掉，一樣 500，
        兩種情況長得一模一樣（M-B，mutation #15 當場存活抓到的就是這個）。
        這裡用一個樣板根本不讀的鍵：守衛在就是 500，守衛不在就是正常 200。
        """
        from odoo.addons.assoc_portal.controllers.portal import AssocPortal
        original = AssocPortal._meeting_hub_extra
        try:
            AssocPortal._meeting_hub_extra = lambda self, member, meeting: {
                'harmless_but_not_hub': 1}
            self.assertEqual(self._hub().status_code, 500,
                             '非 hub_ 的鍵要被擋下來，即使它本身無害')
        finally:
            AssocPortal._meeting_hub_extra = original
        self.assertEqual(self._hub().status_code, 200, '還原後要恢復正常')

    def test_candidacy_status_is_hidden_once_counting_starts(self):
        """開票後不顯示個人登記狀態——**而且要明說**，不可以落到「未登記」。

        `_tally` 把「已退選但拿到票」的人改成 `write_in`，所以光是濾掉那個**值**，
        那位會員的標籤就會從「已退選」變成「未登記」——有沒有那一列本身帶著
        「有沒有人投我」這個 bit（紅隊用真的 `_tally()` 實跑複現）。
        """
        election = self._election('M14 開票中不顯示狀態')
        self.env['assoc.election.candidate'].sudo().with_context(
            assoc_state_machine=GUARD).create({
                'election_id': election.id, 'office': 'director',
                'member_id': self.member.id, 'state': 'confirmed'})
        body = self._hub().text
        self.assertIn('已確認', body, '開票前要看得到自己的狀態（M-C）')
        self.env.cr.execute("UPDATE assoc_election SET state = 'counted' WHERE id = %s",
                            [election.id])
        self.env.cr.flush()
        self.env.invalidate_all()
        body = self._hub().text
        self.assertIn('M14 開票中不顯示狀態', body, '場次本身還是要列出來')
        self.assertIn('開票後不再顯示個人登記狀態', body)
        self.assertNotIn('已確認', body)
        self.assertNotIn('未登記', body, '不可以落到「未登記」——那是假話')

    def test_withdrawn_and_write_in_look_identical_after_counting(self):
        """退選者有沒有被投票，開票後在頁面上**必須長得一模一樣**。

        這是上一版真正漏掉的：濾掉 `write_in` 這個值之後，
        「退選+有票」與「退選+沒票」兩種情況的畫面不同 → 1 bit 洩漏。
        """
        def page_for(state):
            election = self._election('M14 退選比對 %s' % state)
            self.env['assoc.election.candidate'].sudo().with_context(
                assoc_state_machine=GUARD).create({
                    'election_id': election.id, 'office': 'director',
                    'member_id': self.member.id, 'state': state})
            self.env.cr.execute(
                "UPDATE assoc_election SET state = 'counted' WHERE id = %s", [election.id])
            self.env.cr.flush()
            self.env.invalidate_all()
            body = self._hub().text
            section = body.split('M14 退選比對 %s' % state, 1)[-1][:400]
            return section

        withdrawn = page_for('withdrawn')        # 退選、沒人投他
        write_in = page_for('write_in')          # 退選、有人投他（_tally 改的）
        self.assertEqual(withdrawn, write_in,
                         '兩種情況的畫面不同就等於洩漏「有沒有人投我」')
