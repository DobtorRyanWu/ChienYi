"""出席紀錄的寫入守衛（計畫 P23、§16 通則 1–2）。

報到台對 attendance 有寫入 ACL，所以守衛必須擋得住「帶 context 的 RPC」。
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import GUARD_CHECKIN

from .common import MeetingCase


@tagged('post_install', '-at_install')
class TestAttendanceGuard(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.new_member('G001')
        cls.meeting = cls.new_meeting('守衛測試')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()

    def attendance(self):
        return self.attendance_of(self.meeting, self.member).with_user(self.desk_user)

    def test_truthy_context_does_not_pass_the_guard(self):
        """`call_kw` 會把前端送來的 context 直接套進 env，所以旗標是可偽造的。"""
        att = self.attendance()
        for context in ({'assoc_checkin': True}, {'assoc_checkin': 1},
                        {'assoc_checkin': 'yes'}, {'assoc_checkin': [1]}):
            with self.assertRaises(UserError, msg=str(context)):
                att.with_context(**context).write({'state': 'present'})

    def test_sentinel_passes(self):
        self.attendance().with_context(**{GUARD_CHECKIN: GUARD}).write({'state': 'present'})
        self.assertEqual(self.attendance().state, 'present')

    def test_credit_fields_need_their_own_sentinel(self):
        att = self.attendance()
        with self.assertRaises(UserError):
            att.with_context(**{GUARD_CHECKIN: GUARD}).write({'credit_points': 99})
        with self.assertRaises(UserError):
            att.with_context(assoc_credit=True).write({'credit_points': 99})

    def test_fields_outside_the_whitelist_are_never_writable(self):
        att = self.attendance()
        other = self.new_member('G002')
        with self.assertRaises(UserError):
            att.with_context(**{GUARD_CHECKIN: GUARD}).write({'member_id': other.id})

    def test_create_cannot_start_present(self):
        """只看 vals 的守衛擋不住 default_state（§16 通則 1）。"""
        member = self.new_member('G003')
        with self.assertRaises(UserError):
            self.env['assoc.meeting.attendance'].with_user(self.admin_user).with_context(
                default_state='present').create({
                    'meeting_id': self.meeting.id, 'member_id': member.id})

    def test_present_attendance_cannot_be_deleted(self):
        self.scan(self.meeting, self.member.sudo().barcode)
        with self.assertRaises(UserError):
            self.attendance_of(self.meeting, self.member).sudo().unlink()

    def test_meeting_with_attendees_cannot_be_deleted(self):
        """attendance 是 cascade：刪大會可以整批帶走出席紀錄，繞過出席守衛。"""
        self.scan(self.meeting, self.member.sudo().barcode)
        with self.assertRaises(UserError):
            self.meeting.sudo().unlink()

    def test_meeting_state_needs_the_sentinel(self):
        meeting = self.new_meeting('狀態守衛')
        with self.assertRaises(UserError):
            meeting.with_user(self.admin_user).with_context(assoc_meeting_state=True).write(
                {'state': 'in_session'})
        with self.assertRaises(UserError):
            meeting.with_user(self.admin_user).write({'kind': 'seminar'})

    def test_create_cannot_forge_credit_fields(self):
        """create 的白名單要列全：漏一個就是一條無軌跡的後門。

        直接建出 state='absent' 卻 credit_status='eligible' 的紀錄，
        前台就會憑它核發「茲證明全程參與」的積分證明。
        """
        member = self.new_member('G010')
        for forged in ({'credit_status': 'eligible'}, {'credit_points': 999},
                       {'checkin_method': 'manual'}, {'manual_reason': '偽造'},
                       {'credit_note': '偽造'}):
            with self.assertRaises(UserError, msg=str(forged)):
                self.env['assoc.meeting.attendance'].with_user(self.admin_user).create(
                    dict(forged, meeting_id=self.meeting.id, member_id=member.id))

    def test_scan_survives_non_string_input(self):
        """JSON 送得進來的不只字串：`.strip()` 對數字會 AttributeError → 500。"""
        for code in (12345, [1, 2], {'a': 1}, True):
            self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid', repr(code))


@tagged('post_install', '-at_install')
class TestAdminButtons(MeetingCase):
    """承辦在 UI 上按得到補登與積分調整（不用 wizard：暫存欄位 + 按鈕）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from datetime import timedelta
        cls.member = cls.new_member('B001')
        cls.seminar = cls.new_meeting('按鈕測試研討會', kind='seminar', credit_points=5)
        cls.seminar.with_user(cls.admin_user).action_open_checkin()
        cls.later = cls.seminar.date_end - timedelta(minutes=30)

    def test_manual_checkout_button(self):
        self.scan(self.seminar, self.member.sudo().barcode)
        att = self.attendance_of(self.seminar, self.member).with_user(self.admin_user)
        att.write({'input_checkout_at': self.later, 'input_reason': '家中急事先行離開'})
        att.button_manual_checkout()
        self.assertEqual(att.checkout_method, 'manual')
        self.assertEqual(att.credit_status, 'early_leave')
        self.assertFalse(att.input_checkout_at, '按完要清掉暫存輸入')

    def test_manual_checkout_button_needs_a_time(self):
        """原因有填、只缺時間——否則擋下來的是「原因必填」那道，驗不到這一道。"""
        self.scan(self.seminar, self.member.sudo().barcode)
        att = self.attendance_of(self.seminar, self.member).with_user(self.admin_user)
        att.write({'input_reason': '有填原因但沒填時間'})
        with self.assertRaises(UserError) as err:
            att.button_manual_checkout()
        self.assertIn('補登簽退時間', str(err.exception))

    def test_credit_override_button(self):
        self.scan(self.seminar, self.member.sudo().barcode)
        att = self.attendance_of(self.seminar, self.member).with_user(self.admin_user)
        att.write({'input_credit_status': 'eligible', 'input_credit_points': 5,
                   'input_reason': '認可公文 1140919'})
        att.button_credit_override()
        self.assertEqual(att.credit_status, 'eligible')
        self.assertTrue(att.credit_overridden)

    def test_recompute_credits_needs_admin_on_the_server(self):
        """view 的 groups= 只擋按鈕，擋不了 RPC。"""
        with self.assertRaises(AccessError):
            self.seminar.with_user(self.desk_user).action_recompute_credits()


@tagged('post_install', '-at_install')
class TestMeetingLockedFields(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.new_member('L001')
        cls.seminar = cls.new_meeting('鎖定欄位測試', kind='seminar', credit_points=4)
        cls.seminar.with_user(cls.admin_user).action_open_checkin()

    def test_date_begin_is_locked_after_checkin_opens(self):
        """遲到的判定就是 `date_begin + grace`，而散會會自動重算——
        不鎖的話，改一個欄位就能把 0 分變滿分。"""
        from datetime import timedelta
        with self.assertRaises(UserError):
            self.seminar.with_user(self.admin_user).date_begin = self.begin - timedelta(hours=2)

    def test_quorum_ratio_is_locked_after_checkin_opens(self):
        with self.assertRaises(UserError):
            self.seminar.with_user(self.admin_user).quorum_ratio = 0.01

    def test_approval_ref_stays_editable(self):
        """認可文號實務上常常是活動結束後才下來，不能鎖。"""
        self.seminar.with_user(self.admin_user).approval_ref = '工程會字第 1140919 號'
        self.assertEqual(self.seminar.approval_ref, '工程會字第 1140919 號')
