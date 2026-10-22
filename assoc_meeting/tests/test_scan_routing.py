"""掃碼分流（計畫 §6）：靜態會員卡、動態報到碼、其他一律 invalid。"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.assoc_base.tools import PASS_WINDOW_SECONDS, pass_token

from .common import MeetingCase


@tagged('post_install', '-at_install')
class TestScanRouting(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.new_member('S001')
        cls.meeting = cls.new_meeting('掃碼分流測試')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()

    def test_static_card_checks_in(self):
        result = self.scan(self.meeting, self.member.sudo().barcode)
        self.assertEqual(result['status'], 'confirmed')
        att = self.attendance_of(self.meeting, self.member)
        self.assertEqual(att.state, 'present')
        self.assertEqual(att.checkin_method, 'qr_static')

    def test_dynamic_code_checks_in(self):
        code = pass_token(self.env, self.member.sudo())
        self.assertEqual(len(code), 30)
        result = self.scan(self.meeting, code)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(self.attendance_of(self.meeting, self.member).checkin_method, 'qr_dynamic')

    def test_expired_dynamic_code_is_not_a_checkin(self):
        """MAC 對得上但時窗過了 → pass_expired（不是 invalid，也不寫入）。"""
        old = fields.Datetime.now() - timedelta(seconds=PASS_WINDOW_SECONDS * 10)
        code = pass_token(self.env, self.member.sudo(), at=old.timestamp())
        result = self.scan(self.meeting, code)
        self.assertEqual(result['status'], 'pass_expired')
        self.assertEqual(self.attendance_of(self.meeting, self.member).state, 'absent')

    def test_tampered_dynamic_code_is_invalid(self):
        """MAC 不符一律 invalid：不能透露「這個會員存在但碼過期了」。"""
        code = pass_token(self.env, self.member.sudo())
        tampered = code[:19] + ('0' * 11 if code[19:] != '0' * 11 else '1' * 11)
        self.assertEqual(self.scan(self.meeting, tampered)['status'], 'invalid')

    def test_fullwidth_digits_are_invalid_not_500(self):
        """全形數字不能走到 `hmac.compare_digest`——它對非 ASCII 字串丟 TypeError → 500。

        危險的形狀不是「整串全形」（那個在查會員時就落空了），而是
        **真的會員 id ＋ 全形 MAC**：`int()` 吃全形（`int('２２２')` == 222），
        所以前綴會被解析成真的會員，一路走到 MAC 比對。
        擋住它的是 `PASS_TOKEN_RE` 的 `[0-9]`；換成 `\d` 就會整條路由 500。
        """
        fullwidth = '１２３４５６７８９０'
        self.assertTrue(fullwidth.isdigit(), '全形數字在 Python 眼裡也是數字')
        self.assertEqual(self.scan(self.meeting, fullwidth)['status'], 'invalid')
        self.assertEqual(self.scan(self.meeting, '1' + '２' * 29)['status'], 'invalid')
        # 真會員 id + 合法時窗 + 全形 MAC
        import time
        from odoo.addons.assoc_base.tools import PASS_WINDOW_SECONDS
        window = int(time.time()) // PASS_WINDOW_SECONDS
        crafted = '1%010d%08d%s' % (self.member.id, window, '２' * 11)
        self.assertEqual(len(crafted), 30)
        self.assertEqual(self.scan(self.meeting, crafted)['status'], 'invalid')

    def test_other_shapes_are_invalid(self):
        for code in ('', '   ', 'ABC123', '9' * 21, '1' * 31, None):
            self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid', code)

    def test_cross_company_card_is_invalid(self):
        other_company = self.env['res.company'].create({'name': '他公會（M7 掃碼）'})
        stranger = self.new_member('X001', company=other_company)
        self.assertEqual(self.scan(self.meeting, stranger.sudo().barcode)['status'], 'invalid')

    def test_dynamic_code_of_member_not_on_roster_is_invalid(self):
        outsider = self.new_member('S099')
        # 名冊是開放報到時凍結的，之後入會的人不在名冊上
        code = pass_token(self.env, outsider.sudo())
        self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid')

    def test_scan_cannot_check_someone_into_another_meeting(self):
        """查詢一定要帶 meeting_id。

        只用「哪個名冊都不在」的會員測是不夠的——那種人本來就查不到，
        拿掉 meeting_id 條件測試照樣會過。要用**在別場名冊上**的人才驗得到：
        少了那個條件，他會被簽進別場（甚至別的公會那場）。
        """
        other_meeting = self.new_meeting('另一場大會')
        other_meeting.with_user(self.admin_user).action_open_checkin()
        guest = self.new_member('S077')
        other_meeting.with_user(self.admin_user).action_build_roster()
        self.assertTrue(self.attendance_of(other_meeting, guest), '他在另一場的名冊上')
        self.assertFalse(self.attendance_of(self.meeting, guest), '但不在這一場')

        for code, label in ((guest.sudo().barcode, '靜態卡'),
                            (pass_token(self.env, guest.sudo()), '動態碼')):
            self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid', label)
            self.assertEqual(self.attendance_of(other_meeting, guest).state, 'absent',
                             '%s：不能把他簽進別場' % label)

    def test_scan_cannot_check_in_another_company_member(self):
        other_company = self.env['res.company'].create({'name': '他公會（名冊）'})
        stranger = self.new_member('X077', company=other_company)
        their_meeting = self.env['assoc.meeting'].sudo().create({
            'name': '他公會大會', 'kind': 'assembly',
            'company_id': other_company.id, 'date_begin': self.begin})
        their_meeting.action_build_roster()
        self.assertTrue(self.attendance_of(their_meeting, stranger))
        for code, label in ((stranger.sudo().barcode, '靜態卡'),
                            (pass_token(self.env, stranger.sudo()), '動態碼')):
            self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid', label)
            self.assertEqual(self.attendance_of(their_meeting, stranger).state, 'absent', label)

    def test_require_dynamic_pass_refuses_static_card(self):
        meeting = self.new_meeting('只收動態碼', require_dynamic_pass=True)
        meeting.with_user(self.admin_user).action_open_checkin()
        self.assertEqual(self.scan(meeting, self.member.sudo().barcode)['status'],
                         'static_not_allowed')
        self.assertEqual(self.scan(meeting, pass_token(self.env, self.member.sudo()))['status'],
                         'confirmed')

    def test_not_open_meeting_refuses_everything(self):
        meeting = self.new_meeting('還沒開放')
        self.assertEqual(self.scan(meeting, self.member.sudo().barcode)['status'], 'not_open')

    def test_rotating_the_card_kills_the_dynamic_code(self):
        """動態碼的 MAC 綁會員卡條碼：換發卡片時兩種碼一起失效。"""
        code = pass_token(self.env, self.member.sudo())
        self.member.sudo().action_rotate_barcode()
        self.assertEqual(self.scan(self.meeting, code)['status'], 'invalid')

    def test_desk_info_flags_missing_photo(self):
        """沒有照片時台面要看得出來（動態碼防不了即時轉傳，照片是唯一的人工關卡）。"""
        result = self.scan(self.meeting, self.member.sudo().barcode)
        self.assertEqual(result['photo'], '')
