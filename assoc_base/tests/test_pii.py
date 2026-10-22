"""身分證字號：加密、索引、隱碼、檢查碼、空值 no-op、存取軌跡。"""

import base64
import os
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .common import guild_today
from odoo.tools import mute_logger
from odoo.tools import config

from .. import tools_pii

# 測試用假金鑰（不碰掛載的正式金鑰檔）
TEST_KEY = base64.b64encode(os.urandom(32)).decode()
VALID_ID = 'A123456789'      # 檢查碼正確
VALID_ID_2 = 'B234567894'
BAD_CHECKSUM = 'A123456788'


@tagged('post_install', '-at_install')
class TestPii(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_key = config.options.get('assoc_pii_key')
        config.options['assoc_pii_key'] = TEST_KEY
        cls.partner = cls.env['res.partner'].create({'name': '個資測試', 'company_id': cls.env.company.id})

    @classmethod
    def tearDownClass(cls):
        if cls._old_key is None:
            config.options.pop('assoc_pii_key', None)
        else:
            config.options['assoc_pii_key'] = cls._old_key
        super().tearDownClass()

    def _member(self, member_no, **vals):
        return self.env['assoc.member'].create(dict(
            {'partner_id': self.partner.copy({'name': member_no}).id, 'member_no': member_no}, **vals))

    def test_checksum(self):
        self.assertTrue(tools_pii.checksum_ok(VALID_ID, 'tw_id'))
        self.assertFalse(tools_pii.checksum_ok(BAD_CHECKSUM, 'tw_id'))
        self.assertEqual(tools_pii.detect_kind('A812345678'), 'arc_new')
        self.assertEqual(tools_pii.detect_kind('AB12345678'), 'arc_old')
        self.assertFalse(tools_pii.detect_kind('A12345678'))

    def test_mask_hides_middle(self):
        """遮末 4 碼時末碼是檢查碼，候選只剩約 10^3 組；本法遮中間 6 碼。"""
        self.assertEqual(tools_pii.mask(VALID_ID), 'A1******89')

    def test_normalize_accepts_fullwidth_and_lowercase(self):
        self.assertEqual(tools_pii.normalize('ａ123456789'), 'A123456789')
        self.assertEqual(tools_pii.normalize(' a123456789 '), 'A123456789')

    def test_write_stores_ciphertext_not_plaintext(self):
        member = self._member('P001', national_id=VALID_ID)
        member.invalidate_recordset()
        self.assertEqual(member.national_id, '', '讀回來一律空白')
        self.assertEqual(member.national_id_masked, 'A1******89')
        self.assertEqual(member.national_id_kind, 'tw_id')
        enc = member.national_id_enc
        self.assertTrue(enc.startswith('v1:'))
        self.assertNotIn(VALID_ID, enc)
        # 資料庫裡任何欄位都不該有明文
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT count(*) FROM assoc_member
             WHERE national_id_enc LIKE %s OR national_id_masked LIKE %s
        """, ['%' + VALID_ID + '%', '%' + VALID_ID + '%'])
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_hmac_is_stable_and_keyed(self):
        member = self._member('P002', national_id=VALID_ID)
        self.assertEqual(member.national_id_hmac, tools_pii.index_hmac(VALID_ID))
        other_key = base64.b64encode(os.urandom(32)).decode()
        config.options['assoc_pii_key'] = other_key
        try:
            self.assertNotEqual(member.national_id_hmac, tools_pii.index_hmac(VALID_ID),
                                '換金鑰就算不出同一個索引')
        finally:
            config.options['assoc_pii_key'] = TEST_KEY

    def test_aad_binds_to_record(self):
        """把 A 的密文搬到 B 名下 → 解不開（AAD 綁 member id）。"""
        a = self._member('P003', national_id=VALID_ID)
        b = self._member('P004', national_id=VALID_ID_2)
        stolen = a.national_id_enc
        # 一致性檢查在寫入當下就擋掉（密文解不開 → 四個欄位對不起來）
        with self.assertRaises(ValidationError):
            b.sudo().write({'national_id_enc': stolen})
        # 底層也要擋：直接用 B 的 AAD 解 A 的密文
        with self.assertRaises(UserError):
            tools_pii.decrypt(stolen, b._pii_aad())
        self.assertEqual(tools_pii.decrypt(stolen, a._pii_aad()), VALID_ID)

    def test_blank_is_noop(self):
        """匯出再匯入時空白儲存格會被寫成 False，不能因此清掉密文。"""
        member = self._member('P005', national_id=VALID_ID)
        enc = member.national_id_enc
        member.write({'national_id': ''})
        self.assertEqual(member.national_id_enc, enc)
        member.write({'national_id': False})
        self.assertEqual(member.national_id_enc, enc)

    def test_bad_checksum_rejected_without_echo(self):
        with self.assertRaises(UserError) as err:
            self._member('P006', national_id=BAD_CHECKSUM)
        self.assertNotIn(BAD_CHECKSUM, str(err.exception), '錯誤訊息不得回顯輸入值')

    def test_bad_format_rejected(self):
        with self.assertRaises(ValidationError):
            self._member('P007', national_id='12345')

    def test_duplicate_in_same_company_rejected(self):
        self._member('P008', national_id=VALID_ID)
        # 唯一鍵在 flush 時才爆；包 savepoint 才不會弄壞後續測試的 cursor
        with self.assertRaises(Exception), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self._member('P009', national_id=VALID_ID)
                self.env.flush_all()

    def test_reveal_and_clear_write_audit(self):
        member = self._member('P010', national_id=VALID_ID)
        log = self.env['assoc.audit.log']
        before = log.search_count([('action', '=', 'reveal_pii')])
        action = member.action_reveal_national_id()
        self.assertEqual(action['params']['message'], VALID_ID)
        self.assertEqual(log.search_count([('action', '=', 'reveal_pii')]), before + 1)

        member.action_clear_national_id()
        self.assertFalse(member.national_id_enc)
        self.assertFalse(member.national_id_masked)
        self.assertEqual(log.search_count([('action', '=', 'clear_national_id')]), 1)

    def test_enc_fields_are_system_only(self):
        """密文與索引只有 system 讀得到（職員看得到的只有隱碼）。"""
        staff = self.env['res.users'].create({
            'name': '職員', 'login': 'assoc_staff_pii_test',
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])]})
        info = self.env['assoc.member'].with_user(staff).fields_get(
            ['national_id_enc', 'national_id_hmac', 'national_id_masked'])
        self.assertNotIn('national_id_enc', info, '職員不該看得到密文欄位')
        self.assertNotIn('national_id_hmac', info, '職員不該看得到查詢索引')
        self.assertIn('national_id_masked', info, '隱碼是職員要用的')

    def test_broken_ciphertext_gives_user_error(self):
        """密文被改壞要回可讀的錯誤，不是 500（b64 解碼也要包在 try 裡）。"""
        member = self._member('P011', national_id=VALID_ID)
        with self.assertRaises(UserError):
            tools_pii.decrypt('v1:@@@not-base64@@@', member._pii_aad())
        with self.assertRaises(UserError):
            tools_pii.decrypt('v1:' + 'A' * 40, member._pii_aad())

    def test_reveal_checks_record_rule(self):
        """他公會的管理員不能讀別人的身分證（sudo 與非 sudo 共用快取，少了 check_access 就會漏）。"""
        other_company = self.env['res.company'].create({'name': '他公會（PII 測試）'})
        other_partner = self.env['res.partner'].create({
            'name': '他公會會員', 'company_id': other_company.id})
        other_member = self.env['assoc.member'].create({
            'partner_id': other_partner.id, 'member_no': 'X001',
            'company_id': other_company.id, 'national_id': VALID_ID_2})
        admin = self.env['res.users'].create({
            'name': '本公會管理員', 'login': 'assoc_admin_pii_test',
            'company_id': self.env.company.id, 'company_ids': [(6, 0, self.env.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_admin').id])]})
        with self.assertRaises(AccessError):
            other_member.with_user(admin).action_reveal_national_id()
        with self.assertRaises(AccessError):
            other_member.with_user(admin).action_clear_national_id()
        self.assertTrue(other_member.national_id_enc, '資料沒有被清掉')

    def test_system_fields_cannot_be_set_on_create(self):
        """create 不檢查欄位 groups，要自己擋（vals 與 context 的 default_ 都要）。"""
        Member = self.env['assoc.member']
        partner = self.partner.copy({'name': 'P012'})
        with self.assertRaises(AccessError):
            Member.create({'partner_id': partner.id, 'member_no': 'P012',
                           'national_id_masked': VALID_ID})
        member = Member.with_context(default_national_id_masked=VALID_ID).create({
            'partner_id': partner.id, 'member_no': 'P012'})
        self.assertFalse(member.national_id_masked, 'context 的 default_ 也要被清掉')

    def test_pii_fields_must_stay_consistent(self):
        """直接塞值（例如把明文塞進隱碼欄）會被一致性檢查擋下。"""
        member = self._member('P013', national_id=VALID_ID)
        with self.assertRaises(ValidationError):
            member.sudo().write({'national_id_masked': VALID_ID})
        with self.assertRaises(ValidationError):
            member.sudo().write({'national_id_hmac': 'v1:deadbeef'})

    def test_looks_like_id(self):
        """登入路徑用的寬鬆判斷：檢查碼錯也要算身分證（才不會落到核心去寫 log）。"""
        self.assertTrue(tools_pii.looks_like_id('a123456788'))
        self.assertTrue(tools_pii.looks_like_id('AB12345678'))
        self.assertFalse(tools_pii.looks_like_id('someone@example.com'))
        self.assertFalse(tools_pii.looks_like_id('officer_tp'))

    def test_voter_eligible_search(self):
        """非儲存 compute 一定要有 search：否則篩選會靜默回傳全部名冊。"""
        Member = self.env['assoc.member']
        today = guild_today()      # 產品釘公會時區；用 context_today 會在 UTC 16:00–24:00 差一天
        good = self._member('P014', fee_paid_opening=today)
        bad = self._member('P015', fee_paid_opening=today + timedelta(days=-1))
        found = Member.search([('is_voter_eligible', '=', True), ('member_no', 'in', ['P014', 'P015'])])
        self.assertEqual(found, good)
        found_false = Member.search([('is_voter_eligible', '=', False),
                                     ('member_no', 'in', ['P014', 'P015'])])
        self.assertEqual(found_false, bad)

    def test_voter_eligible_search_finds_members_with_no_fee_at_all(self):
        """沒繳過任何費（`fee_paid_until` 是 NULL）的人要出現在「無選舉權」裡。

        用 `['!', ...]` 取補集會漏掉他們：Odoo 把 '!' 編成 `NOT (...)`，
        而 `NULL >= today` 是 NULL，`NOT NULL` 還是 NULL，那一列會被 WHERE 丟掉。
        結果 compute 說「無選舉權」、search 卻找不到他——名冊與畫面對不上，
        而且**不會有任何錯誤訊息**。
        """
        Member = self.env['assoc.member']
        never = self._member('P016')                                   # 完全沒有繳費紀錄
        self.assertFalse(never.fee_paid_until)
        self.assertFalse(never.is_voter_eligible)
        scope = [('member_no', '=', 'P016')]
        self.assertIn(never, Member.search([('is_voter_eligible', '=', False)] + scope))
        self.assertNotIn(never, Member.search([('is_voter_eligible', '=', True)] + scope))

    def test_voter_eligible_search_and_compute_agree_on_the_whole_roster(self):
        """整份名冊逐筆比對：search 的兩邊聯集必須等於全部，且互不重疊。"""
        Member = self.env['assoc.member']
        everyone = Member.search([])
        yes = Member.search([('is_voter_eligible', '=', True)])
        no = Member.search([('is_voter_eligible', '=', False)])
        self.assertFalse(yes & no, '不能有人同時在兩邊')
        self.assertEqual(yes | no, everyone, '兩邊聯集要等於整份名冊')
        self.assertEqual(yes, everyone.filtered('is_voter_eligible'),
                         'search 與 compute 要給同一個答案')

    def test_inline_key_is_test_only(self):
        """金鑰寫在 odoo.conf 等於放進 git 備份範圍：只有測試模式能用注入。"""
        old = config.options.get('test_enable')
        config.options['test_enable'] = False
        try:
            with self.assertRaises(UserError):
                tools_pii.index_hmac(VALID_ID)
        finally:
            config.options['test_enable'] = old
