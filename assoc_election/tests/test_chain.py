import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_election.models.assoc_election import GUARD_STATE

from .common import AssocElectionCase


@tagged('post_install', '-at_install')
class TestChain(AssocElectionCase):

    def test_transitions_recorded_and_verified(self):
        observer = self.env['res.users'].create({
            'name': '監票甲', 'login': 'observer_a',
            'groups_id': [(6, 0, [self.env.ref('assoc_election.group_election_observer').id])],
        })
        election = self.election
        election.observer_user_ids = [(6, 0, [observer.id])]
        election.action_ready()
        election.action_open()
        election.action_start_closing()
        election.action_close()
        logs = election.log_ids.sorted('seq')
        self.assertEqual(logs.mapped('seq'), [1, 2, 3, 4])
        self.assertEqual([log.payload['to'] for log in logs], ['ballot_ready', 'open', 'closing', 'closed'])
        self.assertEqual(logs[1].payload['observers'][0]['login'], 'observer_a')
        self.assertEqual(logs.filtered('is_head'), logs[-1])
        self.assertTrue(election._verify_chain())
        json.dumps(logs.mapped('payload'))

    def test_tampered_payload_breaks_chain(self):
        self._open()
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE assoc_election_log SET payload = jsonb_set(payload, '{to}', '"closed"')
             WHERE election_id = %s AND seq = 1
        """, [self.election.id])
        self.env['assoc.election.log'].invalidate_model()
        self.assertFalse(self.election._verify_chain())

    def test_truncated_tail_detected(self):
        self._open()
        self.env.flush_all()
        self.env.cr.execute("""
            DELETE FROM assoc_election_log WHERE election_id = %s
               AND seq = (SELECT max(seq) FROM assoc_election_log WHERE election_id = %s)
        """, [self.election.id, self.election.id])
        self.env['assoc.election.log'].invalidate_model()
        self.assertFalse(self.election._verify_chain())

    def test_log_is_append_only(self):
        self.election.action_ready()
        log = self.election.log_ids
        with self.assertRaises(UserError):
            log.write({'action': 'reissue'})
        with self.assertRaises(UserError):
            log.unlink()

    def test_state_written_around_state_machine_breaks_verification(self):
        """鏈本身自洽，但紀錄的狀態被帶 context 直接改掉：驗證要失敗。"""
        self._open()
        self.assertTrue(self.election._verify_chain())
        self.election.with_context(**{GUARD_STATE: GUARD}).write({'state': 'closed'})
        self.assertFalse(self.election._verify_chain())
