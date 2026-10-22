"""動態報到碼與報到台參照碼（計畫 §6）。"""

import time
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..tools import (PASS_WINDOW_SECONDS, desk_ref, pass_token, verify_desk_ref,
                     verify_pass_token)


@tagged('post_install', '-at_install')
class TestPassToken(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env['res.partner'].create({
            'name': '動態碼測試', 'company_id': cls.env.company.id})
        cls.member = cls.env['assoc.member'].create({
            'partner_id': partner.id, 'member_no': 'PT001'})

    def test_token_is_thirty_ascii_digits(self):
        code = pass_token(self.env, self.member)
        self.assertEqual(len(code), 30)
        self.assertTrue(code.isascii() and code.isdigit())
        self.assertTrue(code.startswith('1'), '固定開頭，掃碼槍打錯字時能快速判掉')

    def test_valid_token_resolves_to_member(self):
        member, state = verify_pass_token(self.env, pass_token(self.env, self.member))
        self.assertEqual((member, state), (self.member, 'ok'))

    def test_previous_window_still_accepted(self):
        old = pass_token(self.env, self.member, at=time.time() - PASS_WINDOW_SECONDS)
        self.assertEqual(verify_pass_token(self.env, old)[1], 'ok', '最長 60 秒')

    def test_older_token_is_expired(self):
        old = pass_token(self.env, self.member, at=time.time() - 3 * PASS_WINDOW_SECONDS)
        member, state = verify_pass_token(self.env, old)
        self.assertEqual(state, 'expired')
        self.assertEqual(member, self.member, '過期要能顯示是誰，請他重新整理')

    def test_tampered_mac_is_invalid_not_expired(self):
        code = pass_token(self.env, self.member)
        tampered = code[:19] + ('0' * 11 if code[19:] != '0' * 11 else '1' * 11)
        member, state = verify_pass_token(self.env, tampered)
        self.assertEqual(state, 'invalid')
        self.assertFalse(member, 'MAC 不符不得透露這個會員存在')

    def test_rotating_card_invalidates_token(self):
        code = pass_token(self.env, self.member)
        self.member.action_rotate_barcode()
        self.assertEqual(verify_pass_token(self.env, code)[1], 'invalid')

    def test_full_width_digits_are_rejected(self):
        code = pass_token(self.env, self.member)
        full_width = code.replace('1', '１', 1)
        self.assertEqual(verify_pass_token(self.env, full_width)[1], 'invalid')

    def test_static_barcode_is_not_a_pass_token(self):
        self.assertEqual(verify_pass_token(self.env, self.member.sudo().barcode)[1], 'invalid')

    def test_inactive_member_token_rejected(self):
        code = pass_token(self.env, self.member)
        self.member.active = False
        self.assertEqual(verify_pass_token(self.env, code)[1], 'invalid')

    def test_desk_ref_round_trip(self):
        ref = desk_ref(self.env, self.env.uid, 7, self.member.id)
        self.assertTrue(verify_desk_ref(self.env, ref, self.env.uid, 7, self.member.id))
        self.assertFalse(verify_desk_ref(self.env, ref, self.env.uid, 8, self.member.id),
                         '換一場大會就不算')
        self.assertFalse(verify_desk_ref(self.env, ref, self.env.uid + 1, 7, self.member.id),
                         '換一個報到台人員就不算')
        self.assertFalse(verify_desk_ref(self.env, 'x' * 32, self.env.uid, 7, self.member.id))

    def test_desk_ref_expires(self):
        old = desk_ref(self.env, self.env.uid, 7, self.member.id, at=time.time() - 1200)
        self.assertFalse(verify_desk_ref(self.env, old, self.env.uid, 7, self.member.id))


@tagged('post_install', '-at_install')
class TestDeskRef(TransactionCase):
    """報到台參照碼：比對前要先收斂型別與字元集。

    `hmac.compare_digest` 對非 ASCII 字串丟 TypeError、對非字串丟別的型別錯誤，
    一路傳上去就是 500（動態報到碼那邊是靠 PASS_TOKEN_RE 擋掉同一件事）。
    """

    def test_valid_ref_round_trips(self):
        value = desk_ref(self.env, 1, 2, 3)
        self.assertTrue(verify_desk_ref(self.env, value, 1, 2, 3))

    def test_wrong_party_or_desk_does_not_match(self):
        value = desk_ref(self.env, 1, 2, 3)
        self.assertFalse(verify_desk_ref(self.env, value, 9, 2, 3))
        self.assertFalse(verify_desk_ref(self.env, value, 1, 2, 9))

    def test_malformed_input_returns_false_not_500(self):
        for value in ('中文中文中文中文中文中文中文中文', 12345, None, [], {'a': 1},
                      True, 'z' * 32, 'abc', b'0' * 32):
            self.assertFalse(verify_desk_ref(self.env, value, 1, 2, 3), repr(value))
