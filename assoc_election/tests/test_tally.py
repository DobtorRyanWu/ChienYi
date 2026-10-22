import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.assoc_election.tools import canonical_json, sha256_hex

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_election.models.assoc_election import GUARD_STATE

from .common import AssocElectionCase, seal_ballots


@tagged('post_install', '-at_install')
class TestTally(AssocElectionCase):

    def setUp(self):
        super().setUp()
        self._open()

    def _close_and_count(self):
        """測試交易內無法通過快照檢查（同一交易），直接跑後面三段。"""
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()

    def _ranking(self, office):
        return {row['member_no']: row for row in self.election.result_json['offices'][office]['ranking']}

    def test_results_write_in_and_invalid_counts(self):
        m = self._mid
        self._cast('A01', director=[m('A01'), m('A02'), m('A03')], supervisor=[m('A05')])
        self._cast('A02', director=[m('A01'), m('A02'), m('A06')], supervisor=[m('A05')])
        self._cast('A03', director=[m('A01'), m('A03')], supervisor=[])
        self._cast('A04', director=[m('A02')], supervisor=[m('A04')])
        self._cast('A05', director=[m('A01'), m('A01'), m('A02')], supervisor=[m('A05')])
        self._close_and_count()

        election = self.election
        self.assertEqual(election.state, 'counted')
        director = self._ranking('director')
        self.assertEqual({no: (row['votes'], row['result']) for no, row in director.items()}, {
            'A01': (4, 'elected'), 'A02': (4, 'elected'), 'A03': (2, 'elected'),
            'A06': (1, 'alternate'), 'A04': (0, 'none'),
        })
        supervisor = self._ranking('supervisor')
        self.assertEqual({no: (row['votes'], row['result']) for no, row in supervisor.items()}, {
            'A05': (3, 'elected'), 'A04': (1, 'none'),
        })
        offices = election.result_json['offices']
        self.assertEqual((offices['director']['valid_ballots'], offices['director']['invalid_ballots']), (5, 0))
        self.assertEqual(offices['supervisor']['invalid_reasons'], {'blank': 1})

        write_in = election.candidate_ids.filtered(lambda c: c.member_id.member_no == 'A06')
        self.assertEqual((write_in.state, write_in.votes, write_in.result), ('write_in', 1, 'alternate'))
        self.assertEqual(election.result_digest, sha256_hex(canonical_json(election.result_json)))
        self.assertEqual(election._compute_results()[1], election.result_digest, '重算結果必須一致')
        self.assertTrue(election._verify_chain())

    def test_boundary_tie_requires_observer_entropy(self):
        m = self._mid
        self._cast('A01', director=[m('A01'), m('A02'), m('A03')])
        self._cast('A02', director=[m('A01'), m('A02'), m('A04')])
        self._cast('A03', director=[m('A01'), m('A02')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        with self.assertRaises(UserError):
            self.election._tally()
        self.election.write({'tie_entropy': '骰子 3-6-2'})  # 關票後唯一可寫的欄位
        first = self.election._compute_results()[1]
        self.assertEqual(self.election._compute_results()[1], first, '同一亂數必須得到同一結果')
        self.election._tally()
        director = self._ranking('director')
        self.assertEqual({director['A03']['result'], director['A04']['result']}, {'elected', 'alternate'})

    def test_ballot_count_mismatch_stops_count(self):
        self._cast('A01', director=[self._mid('A01')])
        self.env['assoc.election.ballot'].sudo().create(
            {'election_id': self.election.id, 'office': 'director', 'choices': [self._mid('A01')], 'status': 'valid'})
        self.election.action_start_closing()
        self.election.action_close()
        with self.assertRaises(UserError):
            self.election._assert_ballot_count()

    def test_publish_refuses_tampered_result_even_with_recomputed_digest(self):
        """帶 context 繞過安全帶、連結果摘要一起改：公告前從選票重算與稽核鏈核對都要抓到。"""
        self._cast('A01', director=[self._mid('A01')], supervisor=[self._mid('A05')])
        self._close_and_count()
        original_json, original_digest = self.election.result_json, self.election.result_digest
        tampered = json.loads(json.dumps(original_json))
        tampered['offices']['director']['ranking'][0]['votes'] += 10
        self.election.with_context(**{GUARD_STATE: GUARD}).write(
            {'result_json': tampered, 'result_digest': sha256_hex(canonical_json(tampered))})
        self.assertFalse(self.election._verify_chain())
        with self.assertRaises(UserError):
            self.election.action_publish()
        self.election.with_context(**{GUARD_STATE: GUARD}).write(
            {'result_json': original_json, 'result_digest': original_digest})
        self.assertTrue(self.election._verify_chain())
        self.election.action_publish()
        self.assertEqual(self.election.state, 'published')

    def test_ballot_and_result_use_frozen_snapshot(self):
        """投票中對調兩位會員的姓名與會員編號：選票頁顯示與開票結果都必須維持凍結時的對應。"""
        m1, m2 = self.members['A01'], self.members['A02']
        before = self.election._ballot_offices()
        name1, name2 = m1.partner_id.name, m2.partner_id.name
        m1.partner_id.name, m2.partner_id.name = name2, name1
        for member, number in ((m1, 'TMP'), (m2, 'A01'), (m1, 'A02')):  # 逐步 flush，避免撞唯一約束
            member.member_no = number
            self.env.flush_all()
        self.assertEqual(self.election._ballot_offices(), before)
        self._cast('A03', director=[m1.id])
        self._close_and_count()
        row = self._ranking('director')['A01']
        self.assertEqual((row['member_id'], row['name'], row['votes']), (m1.id, name1, 1))



    def test_result_fields_locked_after_count(self):
        self._cast('A01', director=[self._mid('A01')])
        self._close_and_count()
        with self.assertRaises(UserError):
            self.election.write({'result_digest': 'x'})
        with self.assertRaises(UserError):
            self.election.write({'tie_entropy': '開票後不可再改'})


@tagged('post_install', '-at_install')
class TestCandidateGuards(AssocElectionCase):

    def test_write_in_state_not_settable_manually(self):
        Candidate = self.env['assoc.election.candidate']
        with self.assertRaises(UserError):
            Candidate.create({'election_id': self.election.id, 'office': 'director',
                              'member_id': self._mid('A06'), 'state': 'write_in'})
        with self.assertRaises(UserError):
            self.election.candidate_ids[0].write({'state': 'write_in'})

    def test_ineligible_candidate_blocks_freeze_in_any_state(self):
        """會費未繳的會員不管候選人狀態是什麼（就算繞過守衛設成名單外得票）都不能凍結，否則開票會 KeyError 卡死。"""
        self.env['assoc.election.candidate'].with_context(**{GUARD_STATE: GUARD}).create({
            'election_id': self.election.id, 'office': 'director', 'member_id': self.ineligible.id,
            'state': 'write_in'})
        with self.assertRaises(UserError):
            self.election.action_ready()

    def test_rules_locked_after_freeze_but_observers_assignable(self):
        observer = self.env['res.users'].create({
            'name': '監票乙', 'login': 'observer_guard',
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_observer').id])],
        })
        self.election.action_ready()
        with self.assertRaises(UserError):
            self.election.write({'director_seats': 2})
        with self.assertRaises(UserError):
            self.election.write({'mark_limit_mode': 'half_floor'})
        self.election.write({'observer_user_ids': [(4, observer.id)]})
        self.assertIn(observer, self.election.observer_user_ids)

    def test_withdrawn_candidate_with_votes_marked_write_in(self):
        withdrawn = self.election.candidate_ids.filtered(lambda c: c.member_id == self.members['A04'])
        withdrawn.write({'state': 'withdrawn'})
        self._open()
        self.assertNotIn(self._mid('A04'), [c['member_id'] for c in self.election._ballot_offices()[0]['candidates']])
        self._cast('A01', director=[self._mid('A04')])
        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        self.election._shuffle_ballots(self.election._assert_ballot_count())
        self.election._tally()
        self.assertEqual((withdrawn.state, withdrawn.votes, withdrawn.member_no), ('write_in', 1, 'A04'))
