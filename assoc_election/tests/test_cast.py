from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.assoc_election.tools import AssocVoteError

from .common import AssocElectionCase


@tagged('post_install', '-at_install')
class TestCast(AssocElectionCase):

    def setUp(self):
        super().setUp()
        self._open()

    def test_cast_records_anonymous_ballots(self):
        m = self._mid
        receipt = self._cast('A01', director=[m('A01'), m('A02')], supervisor=[m('A05')])
        voter = self._voter('A01')
        self.assertEqual(voter.state, 'voted')
        self.assertEqual(voter.receipt_code, receipt)
        self.assertTrue(voter.session_nonce, '投後保留 nonce，手機才能重看收據')
        self.assertEqual(sorted(self._ballots().mapped('office')), ['director', 'supervisor'])
        Ballot = self.env['assoc.election.ballot']
        self.assertFalse(Ballot._log_access)
        self.assertNotIn('create_uid', Ballot._fields)
        identity_models = {'assoc.election.voter', 'assoc.member', 'res.users', 'res.partner'}
        self.assertFalse([f for f in Ballot._fields.values() if f.type == 'many2one' and f.comodel_name in identity_models])

    def test_double_submit_rejected(self):
        voter = self._ready_ticket('A01')[0]
        voter._cast({'director': [self._mid('A01')], 'supervisor': []})
        with self.assertRaises(AssocVoteError) as ctx:
            voter._cast({'director': [self._mid('A02')], 'supervisor': []})
        self.assertEqual(ctx.exception.code, 'ticket')
        self.assertEqual(len(self._ballots()), 2)

    def test_over_mark_rejected_without_writing(self):
        voter = self._ready_ticket('A01')[0]
        with self.assertRaises(AssocVoteError) as ctx:
            voter._cast({'director': [self._mid(no) for no in ('A01', 'A02', 'A03', 'A04')], 'supervisor': []})
        self.assertEqual(ctx.exception.code, 'over_mark')
        self.assertFalse(self._ballots())
        self.assertEqual(voter.state, 'issued')

    def test_duplicate_marks_count_once_before_limit(self):
        """§11：同一被選舉人圈兩次以一票計，先去重再驗上限。"""
        voter = self._ready_ticket('A01')[0]
        m = self._mid
        voter._cast({'director': [m('A01'), m('A01'), m('A02'), m('A03')], 'supervisor': []})
        director = self._ballots().filtered(lambda b: b.office == 'director')
        self.assertEqual(director.choices, sorted([m('A01'), m('A02'), m('A03')]))
        self.assertEqual(director.status, 'valid')

    def test_write_in_member_from_roster(self):
        voter = self._ready_ticket('A01')[0]
        voter._cast({'director': [self._mid('A06')], 'supervisor': []})  # A06 不是候選人，但在名冊內
        self.assertEqual(self._ballots().filtered(lambda b: b.office == 'director').status, 'valid')

    def test_member_outside_roster_rejected(self):
        voter = self._ready_ticket('A01')[0]
        with self.assertRaises(AssocVoteError):
            voter._cast({'director': [self.ineligible.id], 'supervisor': []})
        self.assertFalse(self._ballots())

    def test_blank_ballot_is_invalid_blank(self):
        self._cast('A01', director=[], supervisor=[])
        ballots = self._ballots()
        self.assertEqual(set(ballots.mapped('status')), {'invalid'})
        self.assertEqual(set(ballots.mapped('invalid_reason')), {'blank'})

    def test_tampered_payload_rejected(self):
        voter = self._ready_ticket('A01')[0]
        payloads = [
            {'director': []},                                   # 少一個職位
            {'director': [], 'supervisor': [], 'treasurer': []},  # 多一個職位
            'director',
            {'director': 'A01', 'supervisor': []},
            {'director': ['abc'], 'supervisor': []},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(AssocVoteError):
                voter._cast(payload)
        self.assertFalse(self._ballots())

    def test_unarmed_ticket_rejected(self):
        voter = self._voter('A01')
        self.Voter._claim(self.election, voter._issue(), None)
        with self.assertRaises(AssocVoteError) as ctx:
            voter._cast({'director': [], 'supervisor': []})
        self.assertEqual(ctx.exception.code, 'not_armed')

    def test_closing_still_accepts_votes_closed_does_not(self):
        early = self._ready_ticket('A01')[0]
        late = self._ready_ticket('A02')[0]
        self.election.action_start_closing()
        early._cast({'director': [], 'supervisor': []})
        self.election.action_close()
        with self.assertRaises(AssocVoteError) as ctx:
            late._cast({'director': [], 'supervisor': []})
        self.assertEqual(ctx.exception.code, 'closed')


@tagged('post_install', '-at_install')
class TestMarkLimits(AssocElectionCase):

    def test_max_marks_rules(self):
        """§4：單記法 1、連記法＝應選名額、限制連記法＝應選名額之半（至少 1）。"""
        election = self.election
        cases = [
            ('full', 3, 3), ('full', 1, 1), ('half_floor', 3, 1), ('half_floor', 5, 2), ('half_floor', 1, 1),
        ]
        for mode, seats, expected in cases:
            with self.subTest(mode=mode, seats=seats):
                election.write({'mark_limit_mode': mode, 'director_seats': seats})
                self.assertEqual(election._max_marks('director'), expected)

    def test_limited_voting_requires_resolution(self):
        self.election.write({'mark_limit_mode': 'half_floor'})
        with self.assertRaises(UserError):
            self.election.action_ready()
        self.election.write({'limit_resolution_note': '第 3 案，出席 30 人、同意 12 人'})
        self.election.action_ready()
        self.assertEqual(self.election.state, 'ballot_ready')
