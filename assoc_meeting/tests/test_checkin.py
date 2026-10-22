from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAssocCheckin(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': '測試公會乙'})
        fee = fields.Date.today() + timedelta(days=365)

        def member(no, company, **vals):
            # partner 一定要帶 company_id（見 assoc_base 的 `_check_partner_company`）
            partner = cls.env['res.partner'].create(
                {'name': f'會員{no}', 'company_id': company.id})
            return cls.env['assoc.member'].create({
                'partner_id': partner.id, 'member_no': no, 'company_id': company.id,
                'fee_paid_opening': fee, **vals})

        cls.m1 = member('A001', cls.company_a)
        cls.m2 = member('A002', cls.company_a)
        cls.m3 = member('A003', cls.company_a)
        cls.m_inactive = member('A009', cls.company_a, active=False)
        cls.m_foreign = member('B001', cls.company_b)

        cls.meeting = cls.env['assoc.meeting'].create({
            'name': '測試大會', 'company_id': cls.company_a.id, 'date_begin': fields.Datetime.now()})
        cls.Att = cls.env['assoc.meeting.attendance']

        desk_group = cls.env.ref('assoc_meeting.group_meeting_desk')
        cls.desk_a = cls.env['res.users'].create({
            'name': '甲報到台', 'login': 'desk_a',
            'company_id': cls.company_a.id, 'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [desk_group.id])],
        })

    def _open(self):
        self.meeting.action_open_checkin()
        return self.meeting

    def _att(self, member):
        return self.Att.search([('meeting_id', '=', self.meeting.id), ('member_id', '=', member.id)])

    def test_roster_only_active_same_company_members(self):
        self._open()
        members = self.meeting.attendance_ids.member_id
        self.assertEqual(members, self.m1 | self.m2 | self.m3)
        # 重複執行不會重複建立
        self.meeting.action_build_roster()
        self.assertEqual(len(self.meeting.attendance_ids), 3)

    def test_scan_confirms_then_already(self):
        self._open()
        Att = self.Att.with_user(self.desk_a)
        meeting = self.meeting.with_user(self.desk_a)
        res = Att._checkin_by_barcode(meeting, self.m1.barcode)
        self.assertEqual(res['status'], 'confirmed')
        att = self._att(self.m1)
        self.assertEqual(att.state, 'present')
        self.assertEqual(att.checkin_method, 'qr_static')
        self.assertEqual(att.checkin_by_uid, self.desk_a)
        self.assertEqual(Att._checkin_by_barcode(meeting, self.m1.barcode)['status'], 'already')

    def test_scan_rejects_bad_input(self):
        self._open()
        Att = self.Att.with_user(self.desk_a)
        for barcode in ['', 'abc', "1' OR '1'='1", '9' * 25, self.m_foreign.barcode, self.m_inactive.barcode]:
            with self.subTest(barcode=barcode):
                self.assertEqual(Att._checkin_by_barcode(self.meeting, barcode)['status'], 'invalid')

    def test_scan_before_open(self):
        res = self.Att._checkin_by_barcode(self.meeting, self.m1.barcode)
        self.assertEqual(res['status'], 'not_open')

    def test_rotated_barcode_invalidates_old_card(self):
        self._open()
        old = self.m2.barcode
        self.m2.action_rotate_barcode()
        self.assertEqual(self.Att._checkin_by_barcode(self.meeting, old)['status'], 'invalid')
        self.assertEqual(self.Att._checkin_by_barcode(self.meeting, self.m2.barcode)['status'], 'confirmed')

    def test_manual_checkin_requires_reason(self):
        self._open()
        att = self._att(self.m3).with_user(self.desk_a)
        with self.assertRaises(UserError):
            att._checkin_manual('   ')
        self.assertEqual(att.state, 'absent')
        res = att._checkin_manual('未帶會員卡，已核對身分證')
        self.assertEqual(res['status'], 'confirmed')
        self.assertEqual(att.checkin_method, 'manual')

    def test_quorum_strictly_more_than_half(self):
        self._open()
        self.Att._checkin_by_barcode(self.meeting, self.m1.barcode)
        self.assertFalse(self.meeting.quorum_met)  # 1 > 1.5 不成立
        self.Att._checkin_by_barcode(self.meeting, self.m2.barcode)
        self.assertTrue(self.meeting.quorum_met)  # 2 > 1.5

    def test_attendance_state_write_belt(self):
        """安全帶：不經報到流程直接把出席狀態改成 present 會被擋。"""
        self._open()
        att = self._att(self.m1).with_user(self.desk_a)
        with self.assertRaises(UserError):
            att.write({'state': 'present', 'checkin_method': 'qr_static'})

    def test_stats_on_form_new_record(self):
        """表單 onchange 時紀錄是 NewId，統計仍要算到原始紀錄的出席人數。"""
        self._open()
        self.Att._checkin_by_barcode(self.meeting, self.m1.barcode)
        draft = self.meeting.new(origin=self.meeting)
        self.assertEqual((draft.member_count, draft.present_count), (3, 1))

    def test_desk_cannot_see_other_company_meeting(self):
        meeting_b = self.env['assoc.meeting'].create({
            'name': '乙公會大會', 'company_id': self.company_b.id, 'date_begin': fields.Datetime.now()})
        with self.assertRaises(AccessError):
            meeting_b.with_user(self.desk_a).check_access('read')
