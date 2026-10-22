"""以身分證字號登入：等時、不外洩、失敗計數（計畫 P1、§11）。"""

from unittest.mock import patch

from odoo.exceptions import AccessDenied, ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base import tools_pii
from odoo.addons.assoc_base.tools import GUARD
from odoo.addons.assoc_portal.models.assoc_member import GUARD_LINK
from odoo.addons.assoc_portal.controllers import auth

from .common import PASSWORD, PortalCase, RecordingCrypt, VALID_ID, VALID_ID_2

CRYPT = 'odoo.addons.base.models.res_users.Users._crypt_context'
LEGACY_ROUNDS = 100000      # 遠低於現行預設，用來模擬存量雜湊


@tagged('post_install', '-at_install')
class TestLoginIdUnit(PortalCase):
    """不開 HTTP 的部分：對應邏輯與寬鬆樣式。"""

    def test_maps_only_single_active_share_user(self):
        Member = self.env['assoc.member']
        self.assertFalse(Member._user_by_national_id(VALID_ID), '還沒開通 → 對不到')
        user = self.grant()
        self.assertEqual(Member._user_by_national_id(VALID_ID), user)
        # 停用後不算
        self.member.with_user(self.admin_user).action_revoke_portal()
        self.assertFalse(Member._user_by_national_id(VALID_ID))

    def test_ambiguous_mapping_fails_closed(self):
        """同一身分證對到兩個帳號時要回空，不能挑一個。

        正常情況下 `init()` 的 partial unique index 讓這不可能發生，但那個索引是
        `IF NOT EXISTS` 建的——舊庫升級時漏建、或有人手動 DROP，就只剩這道判斷。
        這裡在交易內把索引拿掉來製造那個狀態（PostgreSQL 的 DDL 也跟著交易回滾）。
        """
        user = self.grant()
        self.env.cr.execute('DROP INDEX IF EXISTS assoc_member_one_account')
        twin = self.new_member('M6099', VALID_ID, company=self.other_company)
        twin_user = self.env['res.users'].sudo().create({
            'name': '雙胞胎', 'login': 'm6_twin', 'partner_id': twin.partner_id.id,
            'company_id': self.other_company.id,
            'company_ids': [(6, 0, self.other_company.ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]})
        twin.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = twin_user.id
        self.assertTrue(user.active and twin_user.active)
        self.assertFalse(self.env['assoc.member']._user_by_national_id(VALID_ID),
                         '對不到唯一一個帳號就要失敗，不能挑第一筆')

    def test_internal_user_is_not_matched(self):
        """只認 share 帳號：內部使用者不能用身分證登入。"""
        member = self.new_member('M6011', VALID_ID_2)
        internal = self.env['res.users'].create({
            'name': '內部', 'login': 'm6_internal',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        member.sudo().with_context(**{GUARD_LINK: GUARD}).user_id = internal.id
        self.assertFalse(self.env['assoc.member']._user_by_national_id(VALID_ID_2))

    def test_id_shaped_login_is_refused_at_creation(self):
        """帳號不可長得像身分證：那種帳號永遠登不進來（登入頁一律攔去身分證路徑），
        而且錯誤訊息是「帳號或密碼錯誤」，完全查不出原因。"""
        for login in ('C123456789', 'A12345678', 'A-123456780'):
            with self.assertRaises(ValidationError, msg=login):
                self.env['res.users'].sudo().create({
                    'name': '職員', 'login': login,
                    'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})

    def test_loose_pattern_covers_typos(self):
        self.assertTrue(tools_pii.looks_like_id('a123456788'))   # 檢查碼錯也要攔下
        self.assertTrue(tools_pii.looks_like_id('Ａ123456789'))  # 全形
        self.assertFalse(tools_pii.looks_like_id('someone@example.com'))


@tagged('post_install', '-at_install')
class TestLoginIdHttp(HttpCase, PortalCase):

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        # 第二位會員：用來驗「成功登入只清自己那一筆計數」
        self.member2 = self.new_member('M6099', VALID_ID_2, 'm6099@example.com')
        self.user2 = self.grant(self.member2)
        self.activate(self.member2)
        self.env.cr.flush()
        # 每個測試都從乾淨的冷卻計數開始（registry 記憶體，會跨測試累積）
        for attr in ('_login_failures', '_assoc_id_failures'):
            counter = getattr(self.env.registry, attr, None)
            if counter is not None:
                counter.clear()

    def _login(self, login, password):
        self.authenticate(None, None)
        page = self.url_open('/web/login')
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        return self.url_open('/web/login', data={
            'csrf_token': csrf, 'login': login, 'password': password, 'redirect': ''},
            allow_redirects=False)

    def test_login_with_national_id(self):
        response = self._login(VALID_ID, PASSWORD)
        self.assertEqual(response.status_code, 303, response.text[:300])

    def test_failure_page_never_echoes_mapped_login(self):
        """對應成功、但核心仍然失敗（例如帳號在那一瞬間被停用）時，
        失敗頁會回填 request.params['login']——那是換算後的 Email。"""
        with patch('odoo.addons.base.models.res_users.Users.authenticate',
                   side_effect=AccessDenied()):
            response = self._login(VALID_ID, PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.user.login, response.text, '不得回顯換算出的帳號')
        self.assertNotIn(VALID_ID, response.text)

    def test_wrong_password_shows_generic_error_without_echo(self):
        response = self._login(VALID_ID, 'wrong-password')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(VALID_ID, response.text, '失敗頁不得回顯身分證')
        self.assertNotIn(self.user.login, response.text, '也不得回顯換算出來的帳號')

    def test_national_id_never_reaches_core_log(self):
        with self.assertLogs('odoo.addons.base.models.res_users', level='INFO') as logs:
            self._login(VALID_ID, 'wrong-password')
            self._login(VALID_ID, PASSWORD)
        joined = '\n'.join(logs.output)
        self.assertNotIn(VALID_ID, joined, '核心 log 只能看到換算後的帳號或佔位字串')

    def test_over_long_login_never_reaches_normalisation(self):
        """長度先擋：`looks_like_id` 會對整個字串做 NFKC，10 MB 的 login 欄位就是一次免費的 CPU。"""
        target = 'odoo.addons.assoc_base.tools_pii.looks_like_id'
        real = tools_pii.looks_like_id
        with patch(target, side_effect=real) as spy:
            self._login('x' * (auth.MAX_LOGIN_LENGTH + 1), 'wrong')
            self.assertEqual(spy.call_count, 0, '超長輸入不該進正規化')
            self._login(VALID_ID, 'wrong')
            self.assertEqual(spy.call_count, 1, '正常長度仍要判斷（否則上一條斷言恆真）')

    def test_mistyped_id_never_reaches_core_log(self):
        """打錯的身分證（長度差一碼、0 打成 O、夾破折號）不符寬鬆樣式，
        落到核心就會被原樣寫進 INFO log 並回填登入頁。"""
        for typo in ('A12345678', 'A1234567800', 'A12345678O', 'A-123456780', '123456780'):
            with self.assertLogs('odoo.addons.base.models.res_users', 'INFO') as logs:
                response = self._login(typo, 'wrong')
            joined = '\n'.join(logs.output)
            self.assertNotIn(typo, joined, '%s 不該進核心 log' % typo)
            self.assertNotIn(typo, response.text, '%s 不該被回填登入頁' % typo)

    def test_exactly_one_hash_verification_per_attempt(self):
        """等時的實作判準：每次嘗試都恰好跑一次 verify（查無、空密碼、錯碼都一樣）。"""
        real_crypt = self.env['res.users']._crypt_context()
        calls = []

        with patch(CRYPT, return_value=RecordingCrypt(real_crypt, calls)):
            for login, password in ((VALID_ID, 'wrong'),        # 對得到帳號、密碼錯
                                    ('Z999999999', 'wrong'),    # 查無此人
                                    (VALID_ID, ''),             # 空密碼
                                    ('A123456788', 'wrong')):   # 檢查碼錯
                before = len(calls)
                self._login(login, password)
                self.assertEqual(len(calls) - before, 1,
                                 '%s 應該恰好一次 verify' % login)
                self.assertTrue(calls[-1].startswith('$pbkdf2-sha512$'),
                                '假雜湊也要是 pbkdf2（plaintext scheme 是 0 秒）')

    def _failure_keys(self, national_id):
        """計數表的 key 是（身分證索引, 來源 IP），這裡只認索引那半。"""
        index = tools_pii.index_hmac(national_id)
        failures = getattr(self.env.registry, '_assoc_id_failures', {})
        return [k for k in failures if isinstance(k, tuple) and k[0] == index]

    def _failure_count(self, national_id):
        keys = self._failure_keys(national_id)
        failures = self.env.registry._assoc_id_failures
        return sum(failures[k][0] for k in keys)

    def test_dummy_hash_follows_the_stored_rounds(self):
        """假雜湊必須跟真雜湊同輪數。

        只拿輪數當快取鍵、不帶進 `hash()` 的話，假雜湊永遠是設定檔的預設輪數；
        遇到舊輪數的存量雜湊就會出現「查得到會員比較快」的時間差
        （實測 100000 輪 0.082 秒 vs 600000 輪 0.473 秒）。
        """
        saved = dict(auth._dummy_hashes)
        self.addCleanup(lambda: (auth._dummy_hashes.clear(),
                                 auth._dummy_hashes.update(saved)))
        auth._dummy_hashes.clear()
        crypt = self.env['res.users']._crypt_context()
        legacy = crypt.hash(PASSWORD, rounds=LEGACY_ROUNDS)
        self.assertEqual(auth._hash_rounds(legacy), str(LEGACY_ROUNDS))
        self.env.cr.execute('UPDATE res_users SET password = %s WHERE id = %s',
                            [legacy, self.user.id])

        self._login(VALID_ID, 'wrong')          # 先讓伺服器看到這個站實際在用的輪數
        calls = []

        with patch(CRYPT, return_value=RecordingCrypt(crypt, calls)):
            self._login('Z999999999', 'wrong')   # 查無此人 → 應該用同輪數的假雜湊
        self.assertEqual(len(calls), 1)
        self.assertEqual(auth._hash_rounds(calls[0]), str(LEGACY_ROUNDS),
                         '假雜湊的輪數要跟著站上實際的雜湊走')

    def test_failed_attempt_counts_against_the_national_id(self):
        """核心的冷卻以 IP 計，任何人登入成功就整個清空——身分證要有自己的計數。"""
        self._login(VALID_ID, 'wrong')
        self.assertEqual(self._failure_count(VALID_ID), 1)
        keys = self._failure_keys(VALID_ID)
        self.assertEqual(len(keys), 1)
        self.assertTrue(keys[0][1], 'key 必須帶來源 IP：只用身分證當 key 的話，'
                                    '身分證是半公開資訊，任何人都能從任何地方把別人鎖住')
        self._login(VALID_ID, 'wrong')
        self.assertEqual(self._failure_count(VALID_ID), 2)
        self._login(VALID_ID_2, 'wrong')     # 另一個身分證也累積了一次
        self.assertEqual(self._failure_count(VALID_ID_2), 1)

        self._login(VALID_ID, PASSWORD)
        self.assertEqual(self._failure_count(VALID_ID), 0, '成功後清掉自己這一筆')
        self.assertEqual(self._failure_count(VALID_ID_2), 1,
                         '別人的計數不能被清掉（核心以 IP 計數就是這樣被重置的）')

    def test_locked_national_id_skips_hashing(self):
        import time
        self._login(VALID_ID, 'wrong')     # 先讓計數表存在（也拿到這次請求的 key）
        failures = self.env.registry._assoc_id_failures
        failures[self._failure_keys(VALID_ID)[0]] = (auth.ID_FAILURE_LIMIT, time.time())
        real_crypt = self.env['res.users']._crypt_context()
        calls = []

        with patch(CRYPT, return_value=RecordingCrypt(real_crypt, calls)):
            response = self._login(VALID_ID, PASSWORD)
        self.assertEqual(response.status_code, 200, '鎖住時就算密碼正確也不放行')
        self.assertEqual(calls, [], '鎖住時不做雜湊（否則每個請求都能逼出 CPU）')
