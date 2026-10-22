from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.assoc_election.tools import AssocVoteError

from .common import ELIGIBLE_NOS, AssocElectionCase

CLAIM_EXPIRED_SECONDS = 100


@tagged('post_install', '-at_install')
class TestIssueClaimArm(AssocElectionCase):

    def setUp(self):
        super().setUp()
        self._open()

    def _age_issue(self, voter, seconds):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE assoc_election_voter SET issued_at = issued_at - make_interval(secs => %s) WHERE id = %s",
            [seconds, voter.id])
        voter.invalidate_recordset()

    def test_roster_is_eligible_members_only(self):
        self.assertEqual(self.election.voter_ids.member_id,
                         self.env['assoc.member'].browse([self._mid(no) for no in ELIGIBLE_NOS]))

    def test_issue_requires_checkin_and_open_election(self):
        with self.assertRaises(AssocVoteError) as ctx:
            self._voter('A06')._issue()
        self.assertEqual(ctx.exception.code, 'absent')
        self.election.action_start_closing()
        with self.assertRaises(AssocVoteError):
            self._voter('A01')._issue()

    def test_claim_then_rescan_same_device_is_idempotent(self):
        voter = self._voter('A01')
        token = voter._issue()
        first = self.Voter._claim(self.election, token, None)
        self.assertEqual(first['status'], 'claimed')
        again = self.Voter._claim(self.election, token, first['nonce'])
        self.assertEqual(again['status'], 'already_mine')
        voter.invalidate_recordset()
        self.assertFalse(voter.claim_conflict)
        self.assertRegex(voter.pair_code, r'^\d{4}$')

    def test_second_device_marks_conflict_and_blocks_arm(self):
        voter = self._voter('A01')
        token = voter._issue()
        self.Voter._claim(self.election, token, None)
        second = self.Voter._claim(self.election, token, 'another-device-nonce')
        self.assertEqual(second['status'], 'conflict')
        voter.invalidate_recordset()
        self.assertTrue(voter.claim_conflict)
        self.assertFalse(voter._arm(voter.pair_code))

    def test_same_device_resubmit_recovers_ticket(self):
        """第一次領取其實成功、但回應沒送達：同一裝置（沒有票券 cookie）重送要補發原票券，不能變成衝突。"""
        voter = self._voter('A01')
        token = voter._issue()
        first = self.Voter._claim(self.election, token, None, 'device-A')
        again = self.Voter._claim(self.election, token, None, 'device-A')
        self.assertEqual(again['status'], 'already_mine')
        self.assertEqual(again['nonce'], first['nonce'])
        voter.invalidate_recordset()
        self.assertFalse(voter.claim_conflict)
        self.assertEqual(self.Voter._claim(self.election, token, None, 'device-B')['status'], 'conflict')

    def test_non_ascii_cookie_is_ignored_not_crash(self):
        voter = self._voter('A01')
        token = voter._issue()
        self.Voter._claim(self.election, token, None, 'device-A')
        self.assertEqual(self.Voter._claim(self.election, token, 'éé', 'ëë')['status'], 'conflict')

    def test_writein_search_escapes_wildcards(self):
        self.assertFalse(self.election._search_roster('%%', 10))
        self.assertFalse(self.election._search_roster('__', 10))
        self.assertEqual(sorted(self.election._search_roster('會員A0', 10).mapped('member_no')), list(ELIGIBLE_NOS))

    def test_expired_claim_and_stale_replay(self):
        voter = self._voter('A01')
        token = voter._issue()
        self._age_issue(voter, CLAIM_EXPIRED_SECONDS)
        self.assertEqual(self.Voter._claim(self.election, token, None)['status'], 'invalid')
        # 已被領取、過了時間窗後重放：統一錯誤，不污染衝突訊號
        other = self._voter('A02')
        other_token = other._issue()
        self.Voter._claim(self.election, other_token, None)
        self._age_issue(other, CLAIM_EXPIRED_SECONDS)
        self.assertEqual(self.Voter._claim(self.election, other_token, 'stranger')['status'], 'invalid')
        other.invalidate_recordset()
        self.assertFalse(other.claim_conflict)

    def test_claim_rejected_after_closing(self):
        voter = self._voter('A01')
        token = voter._issue()
        self.election.action_start_closing()
        self.assertEqual(self.Voter._claim(self.election, token, None)['status'], 'invalid')

    def test_arm_preconditions(self):
        voter = self._voter('A01')
        self.assertFalse(voter._arm('1234'), '尚未領票')
        token = voter._issue()
        self.assertFalse(voter._arm('1234'), '尚未被手機領取')
        self.Voter._claim(self.election, token, None)
        voter.invalidate_recordset()
        wrong = f'{(int(voter.pair_code) + 1) % 10000:04d}'
        self.assertFalse(voter._arm(wrong))
        self.assertFalse(voter._arm('12a4'))
        self.election.action_start_closing()
        self.assertTrue(voter._arm(voter.pair_code), '停止領票後已領取者仍可配對')
        self.assertFalse(voter._arm(voter.pair_code), '不可重複配對')

    def test_regenerate_unclaimed_qr_invalidates_old_token(self):
        voter = self._voter('A01')
        old = voter._issue()
        new = voter._issue()
        self.assertEqual(self.Voter._claim(self.election, old, None)['status'], 'invalid')
        self.assertEqual(self.Voter._claim(self.election, new, None)['status'], 'claimed')
        with self.assertRaises(AssocVoteError):
            voter._issue()

    def test_reissue_resets_ticket_and_logs(self):
        voter, token, _nonce = self._ready_ticket('A01')
        voter._reissue('手機遺失')
        voter.invalidate_recordset()
        self.assertEqual(voter.state, 'voided')
        self.assertFalse(voter.session_nonce or voter.claim_hash or voter.armed_at or voter.issued_at or voter.pair_code)
        self.assertEqual(self.Voter._claim(self.election, token, None)['status'], 'invalid')
        new_token = voter._issue()
        self.assertEqual(self.Voter._claim(self.election, new_token, None)['status'], 'claimed')
        log = self.election.log_ids.filtered(lambda entry: entry.action == 'reissue')
        self.assertEqual(log.payload, {'member_no': 'A01', 'reason': '手機遺失'})

    def test_reissue_guards(self):
        voter = self._voter('A01')
        with self.assertRaises(AssocVoteError):
            voter._reissue('未領票不能重發')
        voter._issue()
        with self.assertRaises(AssocVoteError):
            voter._reissue('   ')
        self._cast('A02')
        with self.assertRaises(AssocVoteError):
            self._voter('A02')._reissue('已投票不能重發')

    def test_time_windows_ignore_session_timezone(self):
        """Odoo 的 Datetime 是 naive UTC；連線時區換成台北時，時間窗與寫入時間都不能偏 8 小時。"""
        self.env.cr.execute("SET LOCAL TimeZone = 'Asia/Taipei'")
        voter = self._voter('A01')
        token = voter._issue()
        self.assertEqual(self.Voter._claim(self.election, token, None)['status'], 'claimed')
        voter.invalidate_recordset()
        self.assertTrue(voter._arm(voter.pair_code))
        voter._cast({'director': [], 'supervisor': []})
        voter.invalidate_recordset()
        for fname in ('claimed_at', 'armed_at', 'voted_at'):
            with self.subTest(field=fname):
                self.assertLess(abs((voter[fname] - voter.issued_at).total_seconds()), 60)

    def test_write_belts(self):
        voter = self._voter('A01')
        with self.assertRaises(UserError):
            voter.write({'state': 'issued'})
        with self.assertRaises(UserError):
            voter.unlink()
        with self.assertRaises(UserError):
            self.election.write({'name': '開始投票後改名'})
        with self.assertRaises(UserError):
            self.election.write({'state': 'draft'})
        with self.assertRaises(UserError):
            self.election.write({'observer_user_ids': [(6, 0, [])]})
        with self.assertRaises(UserError):
            self.env['assoc.election.candidate'].create(
                {'election_id': self.election.id, 'office': 'director', 'member_id': self._mid('A06')})

    def test_ticket_fields_hidden_from_officer(self):
        """選務人員讀得到名冊狀態，但讀不到 nonce／配對碼：否則可以冒用會員的手機投票。"""
        officer = self.env['res.users'].create({
            'name': '選務甲', 'login': 'officer_a',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_officer').id])],
        })
        self._ready_ticket('A01')
        voter = self._voter('A01').with_user(officer)
        self.assertEqual(voter.read(['state'])[0]['state'], 'issued')
        for fname in ('session_nonce', 'pair_code', 'claim_hash', 'claim_device_hash', 'receipt_code'):
            with self.subTest(field=fname), self.assertRaises(AccessError):
                voter.read([fname])

    def test_other_company_officer_cannot_read_roster(self):
        company_b = self.env['res.company'].create({'name': '測試公會乙'})
        officer_b = self.env['res.users'].create({
            'name': '乙選務', 'login': 'officer_b',
            'company_id': company_b.id, 'company_ids': [(6, 0, [company_b.id])],
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_officer').id])],
        })
        with self.assertRaises(AccessError):
            self._voter('A01').with_user(officer_b).read(['state'])
        with self.assertRaises(AccessError):
            self.election.with_user(officer_b).read(['name'])
