from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AssocElectionCase, seal_ballots


@tagged('post_install', '-at_install')
class TestCountShuffle(AssocElectionCase):

    def setUp(self):
        super().setUp()
        self._open()

    def _distinct_xmin(self):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT count(DISTINCT xmin::text) FROM assoc_election_ballot WHERE election_id = %s",
            [self.election.id])
        return self.env.cr.fetchone()[0]

    def test_shuffle_collapses_xmin_and_keeps_digest(self):
        voters = ('A01', 'A02', 'A03', 'A04', 'A05')
        tickets = {no: self._ready_ticket(no)[0] for no in voters}
        for index, no in enumerate(voters):
            # 每張票各自一個子交易（各自的 xmin），模擬真實世界每位選舉人一個請求交易
            with self.cr.savepoint():
                tickets[no]._cast({'director': [self._mid('A01'), self._mid(voters[index % 4])],
                                   'supervisor': [self._mid('A05')]})
        self.assertEqual(self._distinct_xmin(), len(voters), '洗牌前 xmin 可以對回每一位選舉人的交易')
        ids_before = set(self._ballots().ids)
        digest_before = self.election._compute_ballots_digest()

        self.election.action_start_closing()
        self.election.action_close()
        seal_ballots(self.election)   # 關票後、開票前的封箱
        moved = self.election._shuffle_ballots(self.election._assert_ballot_count())

        self.assertEqual(moved, len(voters) * 2)
        self.assertEqual(self._distinct_xmin(), 1, '洗牌後所有選票同一個 xmin')
        self.assertTrue(ids_before.isdisjoint(set(self._ballots().ids)), '洗牌後 id 全部換新')
        self.assertEqual(self.election._compute_ballots_digest(), digest_before, '摘要與列順序無關')

    def test_count_in_same_transaction_as_close_is_refused(self):
        """同一交易內開票看不到關票前才 commit 的選票，票數斷言會照樣通過——所以必須用快照檢查擋下。"""
        self._cast('A01', director=[self._mid('A01')])
        self.election.action_start_closing()
        self.election.action_close()
        self.assertTrue(self.election.close_xid)
        with self.assertRaises(UserError):
            self.election._assert_snapshot()
        with self.assertRaises(UserError):
            self.election.action_count()

    def test_snapshot_requires_closed_state(self):
        with self.assertRaises(UserError):
            self.election._assert_snapshot()
