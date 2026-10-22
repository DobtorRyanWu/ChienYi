"""研討會簽退與積分（計畫 §8）。

時間一律用台北時區的情境跑一次：Odoo 的 Datetime 存 naive UTC，
而簽退時窗是「結束前 10 分鐘到結束後 2 小時」——差 8 小時的話時窗恆真或恆假。
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import CHECKOUT_CLOSE_MIN

from .common import MeetingCase

NOW = 'odoo.sql_db.Cursor.now'


@tagged('post_install', '-at_install')
class TestSeminarCredit(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.new_member('C001')
        cls.other = cls.new_member('C002')
        cls.seminar = cls.new_meeting('技師研討會', kind='seminar', credit_points=6)
        cls.seminar.with_user(cls.admin_user).action_open_checkin()
        cls.end = cls.seminar.date_end

    def scan_at(self, moment, member=None, meeting=None):
        """在指定的伺服器時間掃一次碼。"""
        meeting = meeting or self.seminar
        member = member or self.member
        with patch(NOW, return_value=moment):
            return self.scan(meeting, member.sudo().barcode)

    def test_checkin_then_checkout_is_eligible(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        self.assertEqual(att.state, 'present')
        result = self.scan_at(self.end - timedelta(minutes=5))
        self.assertEqual(result['status'], 'checked_out')
        self.assertTrue(att.checkout_at)
        self.seminar.with_user(self.admin_user).action_close_meeting()
        self.assertEqual(att.credit_status, 'eligible')
        self.assertEqual(att.credit_points, 6)

    def test_scanning_again_after_checkout_says_already_out(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        self.scan_at(self.end - timedelta(minutes=5))
        self.assertEqual(self.scan_at(self.end)['status'], 'already_out')

    def test_checkout_before_the_window_does_not_write(self):
        """散場前的誤掃不能變成提前離場：只顯示訊息、不寫入。"""
        self.scan_at(self.begin + timedelta(minutes=5))
        result = self.scan_at(self.begin + timedelta(minutes=30))
        self.assertEqual(result['status'], 'checkout_early')
        self.assertFalse(self.attendance_of(self.seminar, self.member).checkout_at)

    def test_checkout_after_the_upper_bound_is_closed(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        result = self.scan_at(self.end + timedelta(minutes=CHECKOUT_CLOSE_MIN + 1))
        self.assertEqual(result['status'], 'checkout_closed')
        self.assertFalse(self.attendance_of(self.seminar, self.member).checkout_at)

    def test_late_checkin_loses_the_credit(self):
        self.scan_at(self.begin + timedelta(minutes=self.seminar.checkin_grace_min + 1))
        self.scan_at(self.end - timedelta(minutes=5))
        self.seminar.with_user(self.admin_user).action_close_meeting()
        att = self.attendance_of(self.seminar, self.member)
        self.assertEqual(att.credit_status, 'late')
        self.assertEqual(att.credit_points, 0)

    def test_no_checkout_loses_the_credit(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        self.seminar.with_user(self.admin_user).action_close_meeting()
        self.assertEqual(self.attendance_of(self.seminar, self.member).credit_status, 'no_checkout')

    def test_absent_member_is_absent(self):
        self.seminar.with_user(self.admin_user).action_close_meeting()
        self.assertEqual(self.attendance_of(self.seminar, self.other).credit_status, 'absent')

    def test_manual_checkout_can_record_early_leave(self):
        """真的提前離場由管理員事後補登，不是掃碼當下寫。"""
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        att.with_user(self.admin_user).action_manual_checkout(
            self.begin + timedelta(minutes=40), '家中急事先行離開')
        self.assertEqual(att.credit_status, 'early_leave')
        self.assertEqual(att.credit_points, 0)
        self.assertEqual(att.checkout_method, 'manual')

    def test_manual_checkout_outside_the_range_is_refused(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        for moment in (self.begin - timedelta(minutes=1),
                       self.end + timedelta(minutes=CHECKOUT_CLOSE_MIN + 1)):
            with self.assertRaises(UserError):
                att.with_user(self.admin_user).action_manual_checkout(moment, '理由')

    def test_manual_checkout_needs_a_reason_and_admin(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        with self.assertRaises(UserError):
            att.with_user(self.admin_user).action_manual_checkout(self.end, '')
        with self.assertRaises(AccessError):
            att.with_user(self.desk_user).action_manual_checkout(self.end, '理由')

    def test_checkout_beyond_the_upper_bound_fails_closed(self):
        """簽退時間超出上限時判定為未簽退。

        正常路徑到不了這個狀態（補登會擋、掃碼只提示不寫入），這條規則防的是
        「用別的方式進到資料庫的資料」——例如事後改過 `date_end`、從備份還原、
        或有人直接下 SQL。判定要 fail-closed，不能因為「有 checkout_at」就給全程。
        """
        from odoo.addons.assoc_base.tools import GUARD
        from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import GUARD_CHECKIN
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        att.with_context(**{GUARD_CHECKIN: GUARD}).write({
            'checkout_at': self.end + timedelta(minutes=CHECKOUT_CLOSE_MIN + 30),
            'checkout_method': 'manual'})
        att._recompute_credit()
        self.assertEqual(att.credit_status, 'no_checkout')
        self.assertEqual(att.credit_points, 0)

    def test_override_survives_recompute(self):
        """人工調整過的紀錄，之後重算要跳過——否則承辦的更正會被關會時蓋掉。"""
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        att.with_user(self.admin_user).action_credit_override('eligible', 6, '認可公文 1140918')
        self.seminar.with_user(self.admin_user).action_close_meeting()
        self.assertEqual(att.credit_status, 'eligible')
        self.assertEqual(att.credit_points, 6)
        self.assertTrue(att.credit_overridden)

    def test_override_writes_audit(self):
        self.scan_at(self.begin + timedelta(minutes=5))
        att = self.attendance_of(self.seminar, self.member)
        Audit = self.env['assoc.audit.log'].sudo()
        before = Audit.search_count([('action', '=', 'credit_override')])
        att.with_user(self.admin_user).action_credit_override('eligible', 6, '認可公文')
        self.assertEqual(Audit.search_count([('action', '=', 'credit_override')]), before + 1)

    def test_assembly_has_no_checkout(self):
        """大會沒有簽退：第二次掃碼只會回 already。"""
        assembly = self.new_meeting('大會（無簽退）')
        assembly.with_user(self.admin_user).action_open_checkin()
        self.scan(assembly, self.member.sudo().barcode)
        self.assertEqual(self.scan(assembly, self.member.sudo().barcode)['status'], 'already')

    def test_seminar_requires_an_end_time(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['assoc.meeting'].create({
                'name': '沒有結束時間', 'kind': 'seminar',
                'company_id': self.company.id, 'date_begin': self.begin})

    def test_locked_settings_after_checkin_opens(self):
        with self.assertRaises(UserError):
            self.seminar.with_user(self.admin_user).credit_points = 9


@tagged('post_install', '-at_install')
class TestSeminarCreditTimezone(MeetingCase):
    """時區：驗的是**資料庫 session 的 TimeZone**，不是使用者的 tz。

    原本這裡是一個只覆寫 setUpClass 的子類別，想「整組在台北時區再跑一次」。
    兩個問題：
    1. Odoo 的 loader 只收 `test_case_class.__dict__` 裡的 test method，
       不含繼承來的——那個子類別實際收集到 **0 個測試**，從來沒通電。
    2. 全專案沒有任何程式讀 `user.tz`（時間一律 naive UTC + `cr.now()`），
       所以就算跑了也不可能有不同結果。

    真正會被時區咬到的是 raw SQL：裸 `now()` 寫進 naive 欄位會依連線的 TimeZone
    偏移（Asia/Taipei 下差 8 小時），所以委託生效那段一律寫
    `(now() AT TIME ZONE 'UTC')`。這裡就驗那件事。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('TZ%03d' % no) for no in range(1, 5)}
        cls.meeting = cls.new_meeting('時區測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()

    def test_proxy_checkin_time_is_utc_under_taipei_session(self):
        for no in (1, 2, 3):
            self.scan(self.meeting, self.members[no].sudo().barcode)
        self.env.cr.execute("SET LOCAL TimeZone = 'Asia/Taipei'")
        proxy = self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[4], self.members[1], paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active')
        att = self.attendance_of(self.meeting, self.members[4])
        drift = abs((att.checkin_at - fields.Datetime.now()).total_seconds())
        self.assertLess(drift, 120,
                        '代簽時間偏了 %.0f 秒：raw SQL 用了裸 now() 而不是 '
                        "(now() AT TIME ZONE 'UTC')" % drift)
