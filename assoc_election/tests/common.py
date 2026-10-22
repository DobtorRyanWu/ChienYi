from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase

# 共用情境：A01–A06 具選舉權（A06 未報到），X99 會費過期不在名冊
ELIGIBLE_NOS = ('A01', 'A02', 'A03', 'A04', 'A05', 'A06')
PRESENT_NOS = ('A01', 'A02', 'A03', 'A04', 'A05')
FEE_VALID_DAYS = 365


class AssocElectionCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        today = fields.Date.today()

        def member(no, fee_paid_opening):
            # partner 一定要帶 company_id：沒帶等於建了一個跨公會可見的共用聯絡人，
            # 會被 assoc_base 的 `_check_partner_company` 擋下（M5 起）
            partner = cls.env['res.partner'].create(
                {'name': f'會員{no}', 'company_id': cls.company.id})
            return cls.env['assoc.member'].create({
                'partner_id': partner.id, 'member_no': no, 'company_id': cls.company.id,
                # `fee_paid_until` 是 M8 起的 stored compute（由期別一期期接出來），
                # 寫不進去；可編輯的是期初值
                'fee_paid_opening': fee_paid_opening})

        cls.members = {no: member(no, today + timedelta(days=FEE_VALID_DAYS)) for no in ELIGIBLE_NOS}
        cls.ineligible = member('X99', today - timedelta(days=1))

        cls.meeting = cls.env['assoc.meeting'].create({
            'name': '測試大會', 'company_id': cls.company.id, 'date_begin': fields.Datetime.now()})
        cls.meeting.action_open_checkin()
        Attendance = cls.env['assoc.meeting.attendance']
        for no in PRESENT_NOS:
            Attendance._checkin_by_barcode(cls.meeting, cls.members[no].barcode)

        # 選罷辦法 §6 要求選票載明屆次，`action_ready` 因此要求 `term_id`。
        # 放進共用工廠：所有繼承這個基底的測試都走得到同一條正當入口。
        cls.term = cls.env['assoc.term'].create({
            'company_id': cls.company.id, 'term_no': 12,
            'date_from': today, 'state': 'current'})
        cls.election = cls.env['assoc.election'].create({
            'name': '測試選舉', 'company_id': cls.company.id, 'meeting_id': cls.meeting.id,
            'term_id': cls.term.id,
            'director_seats': 3, 'director_alt': 1, 'supervisor_seats': 1, 'supervisor_alt': 0,
        })
        Candidate = cls.env['assoc.election.candidate']
        for no in ('A01', 'A02', 'A03', 'A04'):
            Candidate.create({'election_id': cls.election.id, 'office': 'director', 'member_id': cls.members[no].id})
        Candidate.create({'election_id': cls.election.id, 'office': 'supervisor', 'member_id': cls.members['A05'].id})
        cls.Voter = cls.env['assoc.election.voter']

    def _mid(self, no):
        return self.members[no].id

    def _open(self):
        self.election.action_ready()
        self.election.action_open()

    def _voter(self, no):
        return self.Voter.search([('election_id', '=', self.election.id), ('member_id', '=', self._mid(no))])

    def _ready_ticket(self, no):
        """領票 → 手機領取 → 選務輸入配對碼。回傳 (voter, token, nonce)。"""
        voter = self._voter(no)
        token = voter._issue()
        result = self.Voter._claim(self.election, token, None)
        self.assertEqual(result['status'], 'claimed')
        voter.invalidate_recordset()
        self.assertTrue(voter._arm(voter.pair_code))
        return voter, token, result['nonce']

    def _cast(self, no, director=(), supervisor=()):
        voter = self._ready_ticket(no)[0]
        return voter._cast({'director': list(director), 'supervisor': list(supervisor)})

    def _ballots(self):
        return self.env['assoc.election.ballot'].sudo().search([('election_id', '=', self.election.id)])


def seal_ballots(election):
    """測試裡的「封箱」。**`_assert_snapshot()` 要先繞開。**

    封箱的前提是「它是自己的一個請求」——快照晚於關票的 commit，
    所以看得到每一張在途票（第八輪把摘要寫在關票那一筆就是敗在這裡）。
    第十一輪 skeptic 指出這個前提原本**沒有任何程式在守**，現在由
    `action_seal_ballots()` 裡的 `_assert_snapshot()` 守住。

    代價是：`TransactionCase` 全部跑在同一個交易裡，關票那一筆在自己的快照裡
    天生不可見，於是每一支「跑到 counted」的測試都會被這道守衛擋下來。
    把繞開的方法集中在這裡，而不是在 13 個呼叫點各自 patch 一次（L9）——
    在每個地方各寫一次「正確用法」，就是還沒修好。

    真正證明這條路徑成立的是 HTTP E2E（`tools/e2e_golden_path.py`）：
    關票、封箱、開票是三個**真的**分開的請求。
    單交易裡這道守衛恆真，所以它只被一支測試指名驗（見 test_m10 的
    `test_sealing_must_be_its_own_request`）；那支不繞開。
    """
    with patch.object(type(election), '_assert_snapshot', lambda self: None):
        return election.action_seal_ballots()
