from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.assoc_base.tools import qr_data_uri
from odoo.addons.assoc_meeting.controllers.desk import AssocDesk

from ..models.assoc_election import MAX_WATCHED_VOTERS, OFFICER_GROUP, VOTING_STATES
from ..models.assoc_election_voter import CLAIM_WINDOW_SECONDS
from ..tools import AssocVoteError

CLAIM_QR_SIZE_PX = 400


class AssocDeskElection(AssocDesk):
    """報到台的選舉功能：領票（產生 QR）、配對確認、作廢重發。

    選舉人資料一律 sudo 讀寫，守衛是「選舉人所屬大會 == 路由上的大會」，
    而大會本身已由 _desk_meeting 以報到台權限與公會隔離規則把關。
    """

    def _desk_qcontext(self, meeting):
        values = super()._desk_qcontext(meeting)
        values['can_reissue'] = request.env.user.has_group(OFFICER_GROUP)
        return values

    def _meeting_elections(self, meeting):
        return request.env['assoc.election'].sudo().search(
            [('meeting_id', '=', meeting.id), ('state', 'in', VOTING_STATES)])

    def _desk_voter(self, meeting, voter_id):
        try:
            voter_id = int(voter_id)
        except (TypeError, ValueError):
            raise NotFound()
        voter = request.env['assoc.election.voter'].sudo().browse(voter_id).exists()
        if not voter or voter.election_id.meeting_id != meeting:
            raise NotFound()
        return voter

    @http.route('/assoc/desk/<int:mid>/voters', type='json', auth='user')
    def desk_voters(self, mid, member_id=None, **kw):
        meeting = self._desk_meeting(mid)
        try:
            member_id = int(member_id)
        except (TypeError, ValueError):
            return []
        voters = request.env['assoc.election.voter'].sudo().search([
            ('election_id', 'in', self._meeting_elections(meeting).ids),
            ('member_id', '=', member_id),
        ])
        return [voter._desk_card() for voter in voters]

    @http.route('/assoc/desk/<int:mid>/issue', type='json', auth='user')
    def desk_issue(self, mid, voter_id=None, **kw):
        meeting = self._desk_meeting(mid)
        voter = self._desk_voter(meeting, voter_id)
        try:
            with request.env.cr.savepoint():
                token = voter._issue()
        except AssocVoteError as err:
            request.env.invalidate_all()
            return {'status': 'error', 'message': str(err), 'card': voter._desk_card()}
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        claim_url = f'{base_url}/assoc/vote/{voter.election_id.uuid}/claim#t={token}'
        return {
            'status': 'issued',
            'qr': qr_data_uri(request.env, claim_url, CLAIM_QR_SIZE_PX),
            'expires_in': CLAIM_WINDOW_SECONDS,
            'card': voter._desk_card(),
        }

    @http.route('/assoc/desk/<int:mid>/arm', type='json', auth='user')
    def desk_arm(self, mid, voter_id=None, pair_code=None, **kw):
        meeting = self._desk_meeting(mid)
        voter = self._desk_voter(meeting, voter_id)
        armed = voter._arm(pair_code if isinstance(pair_code, str) else '')
        return {'status': 'armed' if armed else 'rejected', 'card': voter._desk_card()}

    @http.route('/assoc/desk/<int:mid>/reissue', type='json', auth='user')
    def desk_reissue(self, mid, voter_id=None, reason=None, **kw):
        meeting = self._desk_meeting(mid)
        if not request.env.user.has_group(OFFICER_GROUP):
            raise AccessError(_('權限不足：作廢重發限選務人員'))
        voter = self._desk_voter(meeting, voter_id)
        try:
            with request.env.cr.savepoint():
                voter._reissue(reason if isinstance(reason, str) else '')
        except AssocVoteError as err:
            request.env.invalidate_all()
            return {'status': 'error', 'message': str(err), 'card': voter._desk_card()}
        return {'status': 'voided', 'card': voter._desk_card()}

    @http.route()
    def desk_poll(self, mid, voter_ids=None, **kw):
        result = super().desk_poll(mid, **kw)
        meeting = self._desk_meeting(mid)
        result['elections'] = [election._desk_stats() for election in self._meeting_elections(meeting)]
        ids = []
        for value in (voter_ids if isinstance(voter_ids, list) else [])[:MAX_WATCHED_VOTERS]:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        voters = request.env['assoc.election.voter'].sudo().browse(ids).exists().filtered(
            lambda voter: voter.election_id.meeting_id == meeting)
        result['voters'] = [voter._desk_card() for voter in voters]
        return result
