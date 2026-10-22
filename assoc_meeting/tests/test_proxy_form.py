"""委託書列印與條碼掃描（計畫 v14 M11）。

這個檔案守的是三件事，按重要性排：

1. **掃到委託書不可以鑄出 `desk_ref`。** `desk.py` 的 `_with_desk_context` 看到回應
   頂層有 `member_id` 就會鑄一個，而 `desk_ref(source='scan')` 是**禮品領取**的
   「卡被掃過」憑證——回了它，翻拍一張委託單就能換到受託人的禮品。
2. **碼的形狀不能與另外兩種撞。** 報到台掃碼分流唯一的判準就是形狀。
3. **重印要讓外面那張舊的失效**，否則回答不了「承辦掃的是哪一張」。
"""

import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_base import tools

from ..models.assoc_meeting import GUARD_STATE as GUARD_MEETING_STATE
from .common import MeetingCase


@tagged('post_install', '-at_install')
class TestProxyForm(MeetingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('F%03d' % no) for no in range(1, 5)}
        cls.meeting = cls.new_meeting('委託書測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()
        cls.Proxy = cls.env['assoc.meeting.proxy'].sudo()

    def make_proxy(self, principal=1, holder=2, **kw):
        return self.Proxy._new_proxy(
            self.meeting, self.members[principal], self.members[holder], **kw)

    # ------------------------------------------------------------------
    # 碼的形狀
    # ------------------------------------------------------------------
    def test_form_code_cannot_collide_with_the_other_two_codes(self):
        """24 位、`2` 開頭：動態碼與會員卡都吃不到。

        報到台的分流（`_checkin_by_code`）唯一的判準是形狀：
        動態碼固定 30 位 `1` 開頭、會員卡是 ≤20 位純數字。
        撞到任何一邊，掃委託書就會被當成報到或動態碼。
        """
        from odoo.addons.assoc_meeting.models.assoc_meeting_attendance import MAX_BARCODE_DIGITS
        codes = [tools.proxy_form_code(pid) for pid in (1, 42, 9999999999)]
        for code in codes:
            with self.subTest(code=code):
                self.assertEqual(len(code), tools.PROXY_CODE_DIGITS)
                self.assertTrue(tools.PROXY_CODE_RE.match(code))
                self.assertFalse(tools.PASS_TOKEN_RE.match(code), '不可以被動態碼吃掉')
                self.assertGreater(len(code), MAX_BARCODE_DIGITS, '不可以被靜態卡吃掉')
        # 會員卡是 64-bit 十進位，最長 20 位 → 永遠鑄不出 24 位
        self.assertLessEqual(len(str(2 ** 64 - 1)), MAX_BARCODE_DIGITS)

    def test_bad_codes_are_refused_without_saying_why(self):
        """壞碼一律查不到，而且**不區分失敗原因**。

        區分了就變成「這個 proxy id 存不存在」的探測工具
        （比照 `verify_pass_token`「MAC 不符一律 invalid」）。
        `None`／整數／全形數字都要安全回空集合，不可以丟例外——
        這個值來自掃碼槍，而掃碼槍送得進任何鍵盤打得出來的東西。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        wrong_last = code[:-1] + ('0' if code[-1] != '0' else '1')
        for bad in ('2' * 24, wrong_last, '', None, 12345, '２' * 24,
                    code[:-1], code + '0', code.replace('2', '1', 1)):
            with self.subTest(bad=repr(bad)):
                self.assertFalse(self.Proxy._by_form_code(bad))

    def test_reprint_invalidates_the_paper_already_out_there(self):
        """重印要讓舊碼失效。

        同一筆委託在外面同時有兩張可掃的紙，就回答不了「承辦掃的是哪一張」
        （與開通通知單的一次性 nonce 同一個理由）。
        """
        proxy = self.make_proxy()
        first = proxy._issue_form_code()
        self.assertEqual(self.Proxy._by_form_code(first), proxy)
        second = proxy._issue_form_code()
        self.assertFalse(self.Proxy._by_form_code(first), '舊碼必須失效')
        self.assertEqual(self.Proxy._by_form_code(second), proxy)
        # 列印留痕走稽核（append-only），不走欄位
        logs = self.env['assoc.audit.log'].sudo().search([
            ('action', '=', 'proxy_form_print')])
        self.assertEqual(len([lg for lg in logs if (lg.detail or {}).get('proxy_id') == proxy.id]),
                         2, '兩次列印要留兩筆軌跡')

    def test_plain_code_is_never_stored(self):
        """資料庫只存雜湊，而且必須是**帶伺服器秘密**的 HMAC。

        裸 sha256 在這裡不是單向的：亂數只有 13 位十進位（約 2^43）、`proxy_id`
        是明碼，離線搜尋空間就是 10^13。所以這支同時斷言「不是 sha256」——
        少了那一句，改回 sha256 也照樣綠。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        self.assertTrue(proxy.form_code_hash)
        self.assertNotIn(code, proxy.form_code_hash)
        self.assertEqual(proxy.form_code_hash, tools.proxy_form_hash(self.env, code))
        self.assertNotEqual(proxy.form_code_hash, tools.sha256_hex(code),
                            '無鹽 sha256 對 43 bit 的秘密回推得出來')

    def test_create_guard_covers_the_new_fields(self):
        """`default_form_code_hash` 這種 context 不可以預先塞一張可掃的紙。

        守衛驗**結果**不驗輸入（§16 通則 1）：`default_*` 與使用者自建的
        `ir.default` 都會改初值，只看 vals 的守衛擋不到。
        """
        Proxy = self.env['assoc.meeting.proxy'].sudo().with_context(
            default_form_code_hash='deadbeef', default_state='active')
        with self.assertRaises(UserError):
            Proxy.create({
                'meeting_id': self.meeting.id,
                'principal_member_id': self.members[3].id,
                'holder_member_id': self.members[4].id,
                'purpose': 'attend',
            })

    # ------------------------------------------------------------------
    # 掃碼分流：最重要的那一條
    # ------------------------------------------------------------------
    def test_scanning_a_proxy_form_mints_no_desk_ref(self):
        """**掃委託書不可以回 `member_id`，因此鑄不出 `desk_ref`。**

        `desk.py::_with_desk_context` 看到回應頂層有 `member_id` 就鑄一個
        `desk_ref(source='scan')`，而那是禮品領取的「卡被掃過」憑證。
        回了它，翻拍一張委託單就能換到受託人的禮品代領憑證。
        這是本里程碑最重要的一道守衛，所以斷言打在**回應的鍵**上，
        而不是只看有沒有 `desk_ref`（後者是上層才加的）。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        res = self.env['assoc.meeting.attendance'].sudo()._checkin_by_code(self.meeting, code)
        self.assertEqual(res['status'], 'proxy_found')
        self.assertNotIn('member_id', res, '回了 member_id 就會鑄出禮品憑證')
        self.assertNotIn('desk_ref', res)
        self.assertNotIn('member_id', res['proxy'])
        self.assertEqual(res['proxy']['holder_member_id'], self.members[2].id)

    def test_scanning_a_proxy_form_writes_nothing(self):
        """掃碼只是查詢加速器，不是授權：書面閘門不可以被掃碼翻開。"""
        proxy = self.make_proxy(channel='portal')
        code = proxy._issue_form_code()
        self.assertFalse(proxy.paper_received)
        self.env['assoc.meeting.attendance'].sudo()._checkin_by_code(self.meeting, code)
        proxy.invalidate_recordset()
        self.assertFalse(proxy.paper_received, '掃碼不可以翻書面旗標')
        self.assertEqual(proxy.state, 'requested')

    def test_proxy_code_is_routed_before_the_static_card(self):
        """委託書那一支要排在靜態卡之前。

        今天 24 > 20 不會被吃掉，但一旦有人放寬 `MAX_BARCODE_DIGITS`，
        排在後面就會被靜默吃掉——那時掃委託書會變成「查無此會員卡」。
        所以直接斷言：一個 24 位的碼絕不會走到靜態卡分支。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        Attendance = self.env['assoc.meeting.attendance'].sudo()
        calls = []
        original = type(Attendance)._scan_static

        def spy(self_, meeting, barcode):
            calls.append(barcode)
            return original(self_, meeting, barcode)

        from unittest.mock import patch
        with patch.object(type(Attendance), '_scan_static', spy):
            res = Attendance._checkin_by_code(self.meeting, code)
        self.assertEqual(res['status'], 'proxy_found')
        self.assertEqual(calls, [], '24 位的碼不可以走到靜態卡分支')

    def test_other_meeting_and_closed_states_are_distinguished(self):
        """掃到別場／已生效／已取消的委託書，各要有自己的回應。

        全部回 `invalid` 的話，承辦不知道該去哪裡處理；而這三種都是
        「碼是真的」，不會洩漏任何不該洩漏的東西。
        """
        other_meeting = self.new_meeting('另一場大會')
        other_meeting.with_user(self.admin_user).action_open_checkin()
        other = self.Proxy._new_proxy(other_meeting, self.members[3], self.members[4])
        code_other = other._issue_form_code()
        Attendance = self.env['assoc.meeting.attendance'].sudo()
        res = Attendance._checkin_by_code(self.meeting, code_other)
        self.assertEqual(res['status'], 'proxy_other_meeting')
        # **不可以回大會名稱**：`_by_form_code` 走 sudo，所以這裡讀得到別家公會的
        # 大會，回了名稱就是把 ORM 讀不到的資料經掃碼端點漏出去。
        self.assertNotIn('meeting_name', res)
        self.assertNotIn(other_meeting.name, json.dumps(res, ensure_ascii=False))

        cancelled = self.make_proxy(principal=1, holder=2)
        code_cancelled = cancelled._issue_form_code()
        cancelled._cancel('測試取消')
        res = Attendance._checkin_by_code(self.meeting, code_cancelled)
        self.assertEqual(res['status'], 'proxy_closed')
        self.assertEqual(res['reason'], '測試取消')

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def test_form_report_refuses_to_print_without_a_code(self):
        """報表只讀 `data` 裡的單號，自己不鑄、也不寫入。

        核心的 `/report/pdf/<報表>/<id>` 是 auth=user 且不驗 docids：
        單號若在報表裡鑄，任何內部使用者打那條網址就能拿到別人的單號，
        而且 GET 還會順手把已發出的那張紙作廢（開通通知單踩過同一個坑）。
        """
        proxy = self.make_proxy()
        Report = self.env['ir.actions.report'].sudo()
        with self.assertRaises(UserError):
            Report._render_qweb_pdf('assoc_meeting.report_proxy_form', proxy.ids, data={})
        with self.assertRaises(UserError):
            Report._render_qweb_pdf('assoc_meeting.report_proxy_form', proxy.ids,
                                    data={'code': '2' * 24})

    def test_form_report_refuses_when_code_and_id_disagree(self):
        """單號與網址上的 id 不一致要拒絕，不可以讓其中一個蓋過另一個。"""
        first = self.make_proxy(principal=1, holder=2)
        second = self.make_proxy(principal=3, holder=4)
        code = first._issue_form_code()
        Report = self.env['ir.actions.report'].sudo()
        with self.assertRaises(UserError):
            Report._render_qweb_pdf('assoc_meeting.report_proxy_form', second.ids,
                                    data={'code': code})

    def test_blank_form_prints_for_a_meeting_with_no_proxies(self):
        """空白單掛在大會上：零筆委託的場次也要印得出來（那正是它的用途）。"""
        Report = self.env['ir.actions.report'].sudo()
        empty = self.new_meeting('還沒有人委託的大會')
        html = Report._render_qweb_html('assoc_meeting.report_proxy_blank', empty.ids)[0]
        text = html.decode() if isinstance(html, bytes) else html
        self.assertIn(empty.name, text)
        self.assertIn('可貼會員編號條碼', text, '空白單要指示貼會員編號，不是會員卡條碼')
        self.assertNotIn('條碼黏貼處（會員卡）', text)

    def test_form_html_contains_a_data_uri_qr_not_a_barcode_url(self):
        """QR 一律 data URI。

        走 `/report/barcode?value=` 的話，wkhtmltopdf 會回呼那條網址，
        24 位單號就進了 access log。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        html = self.env['ir.actions.report'].sudo()._render_qweb_html(
            'assoc_meeting.report_proxy_form', proxy.ids, data={'code': code})[0]
        text = html.decode() if isinstance(html, bytes) else html
        self.assertIn('data:image/png;base64,', text)
        self.assertNotIn('/report/barcode', text)
        self.assertIn('三分之一', text, '§38 的兩條硬限制要印在紙上')


@tagged('post_install', '-at_install')
class TestProxyFormRoutes(HttpCase, MeetingCase):
    """報到台的兩條新路由，走**真的 HTTP**。

    為什麼一定要有這一段：三條守衛（`/proxy/receive` 的掃碼參照、
    它的 `requested` 狀態檢查、`/proxy/principal_lookup` 的掃碼參照）
    只存在於 controller 裡，而模型層的測試一行都碰不到它們——
    第一版就是這樣，那三條 mutant 全部 STILL GREEN。
    外部的 `tools/e2e/*` 腳本殺不掉它們（mutation 只跑 Odoo 測試）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('R%03d' % no) for no in range(1, 5)}
        cls.meeting = cls.new_meeting('委託書路由測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()
        cls.desk_user.write({'password': 'DeskPassw0rd!'})

    def setUp(self):
        super().setUp()
        self.authenticate('m7_desk', 'DeskPassw0rd!')

    def desk_rpc(self, path, params):
        response = self.url_open(
            '/assoc/desk/%s%s' % (self.meeting.id, path),
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
            headers={'Content-Type': 'application/json'})
        return response.json()['result']

    def make_proxy(self, principal, holder, **kw):
        return self.env['assoc.meeting.proxy'].sudo()._new_proxy(
            self.meeting, self.members[principal], self.members[holder], **kw)

    def scan_holder(self, holder):
        """掃受託人的卡，取得那張 `desk_ref`（這是兩條路由的前提）。"""
        res = self.desk_rpc('/scan', {'barcode': self.members[holder].sudo().barcode})
        self.assertTrue(res.get('desk_ref'), '掃到會員卡要鑄出參照碼')
        return res['desk_ref']

    # ------------------------------------------------------------------
    def test_receive_needs_a_fresh_scan_of_the_holder(self):
        """沒有受託人的掃碼參照就不能讓委託生效。

        少了這道，任何有 desk 群組的人可以用一行 RPC 讓任意一張委託書生效
        ——而書面閘門的整個意義就是「承辦當著人收到那張紙」。
        """
        proxy = self.make_proxy(1, 2, channel='portal')
        self.env.cr.flush()
        res = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id})
        self.assertEqual(res['status'], 'need_scan')
        proxy.invalidate_recordset()
        self.assertFalse(proxy.paper_received, '被擋下來就不該翻書面旗標')

    def test_receive_works_after_scanning_the_holder(self):
        """掃過受託人的卡之後，才輪到「確認已收紙本」那一鍵。

        這條同時補掉一個既有死路：前台送出的委託停在 `requested`，
        而報到台原本**沒有路**讓它生效（`action_receive_paper` 是 admin-only，
        `/proxy/register` 會撞委託人的唯一索引）。
        """
        proxy = self.make_proxy(1, 2, channel='portal')
        self.env.cr.flush()
        desk_ref = self.scan_holder(2)
        res = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertIn(res['status'], ('active', 'waiting'))
        proxy.invalidate_recordset()
        self.assertTrue(proxy.paper_received)

    def _paper_logs(self, proxy):
        return self.env['assoc.audit.log'].sudo().search([
            ('action', '=', 'proxy_paper_received')]).filtered(
                lambda log: (log.detail or {}).get('proxy_id') == proxy.id)

    def test_receive_on_a_waiting_proxy_is_idempotent_not_invalid(self):
        """候補中的委託重按確認鍵要**冪等**，不可以回 `invalid`。

        這裡的 `waiting` 是決定性的、不是碰運氣：只有受託人一個人報到，
        `3*(proxy+1) <= present` 就是 `3 <= 1`，必不成立。
        前一版斷言的是 `assertNotEqual(state, 'requested')`——那句話被 `waiting`
        滿足，於是「已生效／已取消不可以再翻」這個宣稱其實一次都沒驗到
        （第十三輪 skeptic）。`waiting` 是活的：開議時 `_activate_waiting_proxies()`
        還會再試一次，把它當成已取消擋掉，那張紙就永遠沒有用途。
        """
        proxy = self.make_proxy(1, 2, channel='portal')
        self.env.cr.flush()
        desk_ref = self.scan_holder(2)
        first = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertEqual(first['status'], 'waiting')
        proxy.invalidate_recordset()
        self.assertEqual(proxy.state, 'waiting')
        self.assertTrue(proxy.paper_received)
        again = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertEqual(again['status'], 'waiting', '候補中重按不可以變成 invalid')
        proxy.invalidate_recordset()
        self.assertTrue(proxy.paper_received, '書面旗標不可以被翻回去')
        self.assertEqual(len(self._paper_logs(proxy)), 1, '重按不可以再灌一筆軌跡')

    def test_receive_refuses_after_the_meeting_is_over(self):
        """散會之後不可以再翻不可逆的「已收書面」。

        `_try_activate` 的狀態閘在 `_mark_paper_received` **之後**才跑，
        所以少了這道，報到台在大會 closed 之後仍翻得動旗標＋寫一筆軌跡
        （第十四輪 skeptic）。這道只存在於 controller，模型層碰不到它。
        """
        proxy = self.make_proxy(1, 2, channel='portal')
        desk_ref = self.scan_holder(2)
        self.meeting.sudo().with_context(**{
            GUARD_MEETING_STATE: tools.GUARD}).write({'state': 'closed'})
        self.env.cr.flush()
        out = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertEqual(out['status'], 'meeting_closed')
        proxy.invalidate_recordset()
        self.assertFalse(proxy.paper_received, '散會後不可以翻旗標')
        self.assertFalse(self._paper_logs(proxy), '也不可以留下軌跡')

    def test_receive_refuses_a_proxy_that_is_already_active(self):
        """已生效的委託不可以再翻一次書面旗標（那會重跑一次生效流程）。

        先讓三個人報到，`3*1 <= 3` 才成立——這一支要的是 `active`，
        所以前置條件寫死，不靠預設狀態碰巧。
        """
        for no in (2, 3, 4):
            self.desk_rpc('/scan', {'barcode': self.members[no].sudo().barcode})
        proxy = self.make_proxy(1, 2, channel='portal')
        self.env.cr.flush()
        desk_ref = self.scan_holder(2)
        first = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertEqual(first['status'], 'active')
        again = self.desk_rpc('/proxy/receive', {'proxy_id': proxy.id, 'desk_ref': desk_ref})
        self.assertEqual(again['status'], 'invalid')
        self.assertEqual(len(self._paper_logs(proxy)), 1)

    def test_principal_lookup_needs_a_fresh_scan_too(self):
        """委託人查詢也要掃碼參照。

        少了它，這條路由就是一個「用會員編號問這個人在不在本次名冊」的
        列舉端點，而報到台對 `assoc.member` 沒有讀取權。
        """
        res = self.desk_rpc('/proxy/principal_lookup', {
            'code': self.members[1].member_no, 'holder_member_id': self.members[2].id})
        self.assertEqual(res['status'], 'need_scan')

    def test_principal_lookup_returns_no_barcode_and_no_member_id_key(self):
        """回應不可以含 `barcode`，也不可以用 `member_id` 當鍵名。

        `member_id` 會讓上層 `_with_desk_context` 鑄出 `desk_ref`
        （禮品領取的「卡被掃過」憑證）；`barcode` 本身就是報到用的持有者憑證。
        """
        desk_ref = self.scan_holder(2)
        res = self.desk_rpc('/proxy/principal_lookup', {
            'code': self.members[1].member_no, 'desk_ref': desk_ref,
            'holder_member_id': self.members[2].id})
        self.assertEqual(res['status'], 'found')
        self.assertEqual(res['principal_member_id'], self.members[1].id)
        self.assertNotIn('member_id', res)
        self.assertNotIn('barcode', json.dumps(res))
        self.assertNotIn('desk_ref', res)

    def test_principal_lookup_refuses_someone_off_the_roster(self):
        other_company = self.env['res.company'].create({'name': '別的公會（M11）'})
        outsider = self.new_member('R900', company=other_company)
        desk_ref = self.scan_holder(2)
        res = self.desk_rpc('/proxy/principal_lookup', {
            'code': outsider.member_no, 'desk_ref': desk_ref,
            'holder_member_id': self.members[2].id})
        self.assertEqual(res['status'], 'invalid')

    def test_scanning_a_form_over_http_mints_no_desk_ref(self):
        """整條 HTTP 路徑走一次：掃委託書的回應裡不可以出現 `desk_ref`。

        模型層的測試證明 `_scan_proxy` 不回 `member_id`；這一支證明
        **經過 `_with_desk_context` 之後**也還是沒有憑證——那才是攻擊者拿得到的東西。
        """
        proxy = self.make_proxy(1, 2, channel='portal')
        code = proxy._issue_form_code()
        self.env.cr.flush()
        res = self.desk_rpc('/scan', {'barcode': code})
        self.assertEqual(res['status'], 'proxy_found')
        self.assertNotIn('desk_ref', res)
        self.assertNotIn('member_id', res)


@tagged('post_install', '-at_install')
class TestProxyFormCrossGuild(MeetingCase):
    """第十三輪抗辯的修正。**最重要的一條是跨公會**。

    管理員動作的標準寫法是 `_check_admin()` → `ensure_one()` → `.sudo()`，
    而 `ensure_one()` 不讀任何欄位，所以 `record_rules.xml` 的公會 rule
    從頭到尾沒被觸發過。red-team 實跑：台北的管理員對新北的委託書按
    「已收書面」，把別家公會的出席列翻成 `proxy`——直接動到人民團體法的法定人數。
    七個模型各寫了一份只驗群組的 `_check_admin`，全部改走 `tools.check_guild_admin`。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = {no: cls.new_member('X%03d' % no) for no in range(1, 5)}
        cls.meeting = cls.new_meeting('跨公會測試大會')
        cls.meeting.with_user(cls.admin_user).action_open_checkin()
        cls.Proxy = cls.env['assoc.meeting.proxy'].sudo()
        cls.other_company = cls.env['res.company'].create({'name': '另一個公會（M11）'})
        cls.other_admin = cls.env['res.users'].create({
            'name': '別家公會管理員', 'login': 'm11_other_admin',
            'company_id': cls.other_company.id,
            'company_ids': [(6, 0, cls.other_company.ids)],
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_admin').id])],
        })

    def make_proxy(self, principal=1, holder=2, **kw):
        return self.Proxy._new_proxy(
            self.meeting, self.members[principal], self.members[holder], **kw)

    # ------------------------------------------------------------------
    # critical：跨公會
    # ------------------------------------------------------------------
    def test_another_guilds_admin_cannot_confirm_our_paper(self):
        """別家公會的管理員不可以對我們的委託書按「已收書面」。"""
        proxy = self.make_proxy(channel='portal')
        with self.assertRaises(AccessError):
            proxy.with_user(self.other_admin).action_receive_paper()
        proxy.invalidate_recordset()
        self.assertFalse(proxy.paper_received)

    def test_another_guilds_admin_cannot_cancel_our_proxy(self):
        """反向也要擋：取消同樣會改到別家公會的出席人數。"""
        proxy = self.make_proxy()
        with self.assertRaises(AccessError):
            proxy.with_user(self.other_admin).action_cancel('紅隊測試')
        proxy.invalidate_recordset()
        self.assertEqual(proxy.state, 'requested')

    def test_another_guilds_admin_cannot_create_a_proxy_on_our_meeting(self):
        """建立也要驗公會：`meeting_id` 是呼叫端給的，群組是全域的。

        **斷言要比對訊息**，不能只比對例外型別：拿掉 `assert_own_company` 之後
        這裡照樣會 `AccessError`——因為 `check_created` 接著讀欄位，
        記錄規則在那一刻才生效。只比型別的話，我指名的那道防線其實沒被驗到
        （L2⑮：紅的不代表那道防線有在守；這裡是它的反面）。
        """
        with self.assertRaisesRegex(AccessError, '只有公會管理員可以直接建立委託書'):
            self.env['assoc.meeting.proxy'].with_user(self.other_admin).create({
                'meeting_id': self.meeting.id,
                'principal_member_id': self.members[3].id,
                'holder_member_id': self.members[4].id,
                'purpose': 'attend',
            })

    def test_our_own_admin_still_works(self):
        """守衛不可以把正當動作一起擋掉（不然這組測試只證明了『全部擋光』）。"""
        proxy = self.make_proxy(channel='portal')
        proxy.with_user(self.admin_user).action_receive_paper()
        proxy.invalidate_recordset()
        self.assertTrue(proxy.paper_received)

    # ------------------------------------------------------------------
    # high：報表是公會 rule 的旁路
    # ------------------------------------------------------------------
    def _report_values(self, user, docids, code):
        return self.env['report.assoc_meeting.report_proxy_form'].with_user(
            user)._get_report_values(docids, {'code': code})

    def test_report_still_prints_when_docids_are_omitted(self):
        """**不帶 docids 必須印得出來**——那正是後台那顆按鈕走的路。

        這一支存在的理由是我自己踩過的坑：第十三輪為了擋 red-team 的旁路，
        我加了 `if not docids: raise`。核心
        `web/static/src/webclient/actions/reports/utils.js:15-23` 在
        `action.data` 非空時把 URL 組成 `?options=…&context=…`，
        `active_ids` **只進 context、不進路徑**，所以後台按鈕送出的請求
        `docids=None`。而 `action_print_proxy_form` 已經先 `_issue_form_code()`
        並 commit → 每按一次就是「會員手上那張紙作廢 ＋ 新的印不出來」。
        原本一支測試都沒有驗「正當入口還印得出來」（第十四輪 skeptic）。
        跨公會靠的是 `check_access('read')`，不是 docids。
        """
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        for docids in (None, [], proxy.ids):
            with self.subTest(docids=docids):
                values = self._report_values(self.admin_user, docids, code)
                self.assertEqual(values['docs'], proxy)
                self.assertIn(code[:4], values['code_grouped'])

    def test_report_still_refuses_a_code_that_disagrees_with_the_docids(self):
        """帶了 docids 而且與單號不符：要拒絕，不要讓其中一個蓋過另一個。"""
        proxy = self.make_proxy()
        other = self.make_proxy(3, 4)
        code = proxy._issue_form_code()
        with self.assertRaises(UserError):
            self._report_values(self.admin_user, other.ids, code)

    def test_report_refuses_another_guilds_proxy(self):
        """碼對、id 也對，但人不對：公會 rule 要在這裡生效。"""
        proxy = self.make_proxy()
        code = proxy._issue_form_code()
        # 先證明同公會的管理員印得出來，否則下一句可能只是「大家都印不出來」
        self.assertTrue(self._report_values(self.admin_user, proxy.ids, code))
        with self.assertRaises(AccessError):
            self._report_values(self.other_admin, proxy.ids, code)

    # ------------------------------------------------------------------
    # 單號本身
    # ------------------------------------------------------------------
    def test_form_code_refuses_an_out_of_range_id(self):
        """`proxy_id` 超出 10 位要 raise，不可以靜默產出 25 位的碼。

        `'%010d'` 對超長的值是加寬不是截斷 → 碼變 25 位 → `PROXY_CODE_RE` 不收，
        而呼叫端已經先覆寫了 hash：舊紙死了、新紙掃不出來，一個錯誤訊息都沒有。
        """
        with self.assertRaises(Exception):
            tools.proxy_form_code(10 ** 10)
        self.assertTrue(tools.PROXY_CODE_RE.match(tools.proxy_form_code(10 ** 10 - 1)))

    # ------------------------------------------------------------------
    # 掃碼分流與狀態
    # ------------------------------------------------------------------
    def test_scan_tells_waiting_apart_from_cancelled(self):
        """`waiting` 不可以被唸成「已取消或退回」。

        橫幅那句話是承辦唸給會員聽的，而唸完之後重新登錄會撞
        `assoc_proxy_principal` 這條 unique index，報到台就卡在那裡——
        而那張委託書其實自己會生效（開議時 `_activate_waiting_proxies()`）。
        """
        Attendance = self.env['assoc.meeting.attendance'].sudo()
        waiting = self.make_proxy(1, 2, channel='portal', paper_received=True)
        self.assertEqual(waiting._try_activate(), 'waiting', '0 人報到必然候補')
        waiting.invalidate_recordset()
        self.assertEqual(waiting.state, 'waiting')
        res = Attendance._checkin_by_code(self.meeting, waiting._issue_form_code())
        self.assertEqual(res['status'], 'proxy_waiting')

        cancelled = self.make_proxy(3, 4)
        code_cancelled = cancelled._issue_form_code()
        cancelled._cancel('測試取消')
        res = Attendance._checkin_by_code(self.meeting, code_cancelled)
        self.assertEqual(res['status'], 'proxy_closed',
                         '取消的才是 proxy_closed——兩者不可以同一個橫幅')

    def test_scan_tells_superseded_apart_from_cancelled(self):
        """`superseded`＝委託人本人已到場，也不是「取消或退回」。"""
        Attendance = self.env['assoc.meeting.attendance'].sudo()
        for no in (2, 3, 4):
            Attendance._checkin_by_code(self.meeting, self.members[no].sudo().barcode)
        proxy = self.make_proxy(1, 2, channel='portal', paper_received=True)
        self.assertEqual(proxy._try_activate(), 'active', '3 人報到，1/3 過得了')
        code = proxy._issue_form_code()
        # 委託人本人到場 → 委託自動失效
        Attendance._checkin_by_code(self.meeting, self.members[1].sudo().barcode)
        proxy.invalidate_recordset()
        self.assertEqual(proxy.state, 'superseded')
        res = Attendance._checkin_by_code(self.meeting, code)
        self.assertEqual(res['status'], 'proxy_superseded')

    # ------------------------------------------------------------------
    # 第十四輪抗辯的修正
    # ------------------------------------------------------------------
    def test_guard_refuses_an_empty_recordset(self):
        """對空 recordset 做公會比對，迴圈跑零圈就靜默通過＝不可能 FAIL 的閘。

        實際踩到：`assoc.gift.export._check_admin` 掛 `@api.model`，於是造冊
        那條路的公會檢查從頭到尾沒有執行過，而我把它算進了「七處都補上」。
        """
        empty = self.env['assoc.meeting.proxy']
        with self.assertRaises(AccessError):
            tools.assert_own_company(empty)
        with self.assertRaises(AccessError):
            tools.check_guild_admin(empty)

    def test_guard_still_checks_the_group_under_sudo(self):
        """`sudo()` 只翻 `su`、**不改 uid**，所以群組那一半在 sudo 下仍要驗。

        原本寫 `if env.su: return`，那對七處裡的六處是淨損失——它們原本在
        sudo 下照樣會驗群組，而 `proxy.write()` 的證物欄位只靠這一道把關。
        """
        proxy = self.make_proxy()
        desk = self.env['res.users'].create({
            'name': '報到台（第十四輪）', 'login': 'r14_desk',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_meeting.group_meeting_desk').id])],
        })
        sudoed = proxy.with_user(desk).sudo()
        self.assertTrue(sudoed.env.su)
        self.assertFalse(sudoed.env.user.has_group('assoc_base.group_assoc_admin'))
        with self.assertRaises(AccessError):
            tools.check_guild_admin(sudoed)

    def test_guard_refuses_a_record_whose_company_is_null(self):
        """`company_id` 的外鍵是 ON DELETE SET NULL：公會被刪就留下一筆
        對「每一家公會的管理員」都可寫的紀錄。falsy 要 fail-closed。
        """
        proxy = self.make_proxy(3, 4)
        # 先 flush 再下 raw SQL：`company_id` 是 stored related，
        # 待重算會把 NULL 蓋回去（實際踩到：斷言不成立）
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE assoc_meeting_proxy SET company_id = NULL WHERE id = %s', (proxy.id,))
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            tools.assert_own_company(proxy.with_user(self.admin_user))

    def test_a_member_card_that_happens_to_start_with_2_is_still_a_card(self):
        """會員卡條碼剛好以 2 開頭時，**不可以**被當成委託書。

        分流唯一的判準是形狀，而委託書那條 regex 要求恰好 24 位。
        放寬成 `^2[0-9]{0,23}$` 之後這張卡就會掉進委託書那一支——
        原本沒有任何測試瞄準它，只能靠「某位測試會員的 64-bit 條碼剛好以 2 開頭」
        （約 6%/人）碰運氣變紅，那是在擲骰（第十三輪 simplifier）。
        所以這裡把輸入寫成一組**刻意違反該性質**的值。
        """
        member = self.members[3]
        member.sudo().write({'barcode': '2' + '1' * 15})
        self.assertLess(len(member.sudo().barcode), 24)
        res = self.env['assoc.meeting.attendance'].sudo()._checkin_by_code(
            self.meeting, member.sudo().barcode)
        self.assertEqual(res['status'], 'confirmed')
