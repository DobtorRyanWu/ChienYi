# -*- coding: utf-8 -*-
"""S2 fix3（2026-11-11；第二輪審查＋使用者 11-11 追加）。

* 1（U-email）：被 @ 的對話外內部同事**沒有 email** 也收到站內通知（核心對話收件人 SQL 只取有 email 的聯絡人，
  mail/models/discuss/discuss_channel.py:566；dev 內部帳號 11 個有 10 個沒 email）。夾具的同事一律不設 email——
  fix2 的夾具都有 email，所以假綠（L2⑫：測試的幾何跟真實資料不同）。
* 2（U-1＋skeptic F5）：可 @ 的同事只有一份定義（restricted_mail._dash_colleagues）：同一個搜尋字，後端建議名單＝送出時會保留的集合。
* 3（skeptic F4）：編輯自己的對話訊息（/mail/message/update_content）也照建立時收窄 partner_ids（成員＋可 @ 的同事）。
* 4（W2，使用者 11-11）：範圍合格的監造方角色帳號在自己的意見回饋單上留言＝同方別的舊前台帳號（作者本人、通知對象相同、
  不寄給不是追蹤者的人、可以附檔）；別人的單、RPC 直接 message_post 照舊被擋。
* 5（skeptic F3＝red-team F2）：意見回饋的「驗證」路由（問題已解決／仍有問題）角色帳號與舊帳號相同：本人的單可以、別人的單不行。
* 9（使用者 11-11「關」）：受限內部帳號（營造廠主管、後台角色帳號、控台讀取）走 XML-RPC／JSON-RPC 只收 API key、不收密碼；
  瀏覽器登入（/web/login，互動式）照常只要密碼（不要求任何人開兩步驟驗證）；一般內部帳號用密碼打 RPC 照常。
"""
import datetime
import json
import re
import unittest
import xmlrpc.client

from odoo import fields, http
from odoo.tests.common import HttpCase, tagged

from odoo.addons.construction_portal.tests.dash_fixtures import SUPERVISION_USER_VALS
from .test_role_phone import (
    LEVEL_BOSS, P_BOSS, ROLE_BOSS, ROLE_SUPERVISION, SIDE_SUPERVISION, RolePhoneCase, _mail_sender_config,
)
from .test_scope_rules import CONSOLE_GROUP, MANAGER_GROUP, SUPERVISOR_ADMIN, login_as_browser

MODULE = 'construction_company_dashboard'
DISCUSS = 'discuss.channel'
TICKET = 'construction.service.ticket'
# 夾具 login／名稱的共同字首（第 2 項用同一個搜尋字比對建議名單與送出時保留的集合）。不用底線：ilike 的 _ 是萬用字元
FIX3_PREFIX = 'u3mzq'
# 建議名單的筆數上限：要大於夾具裡符合字首的人數，兩邊才比得出「同一個集合」（核心預設 8）
SUGGESTION_LIMIT = 50
RPC_FAULT_ACCESS_DENIED = 3       # 核心 base/controllers/rpc.py
API_KEY_DAYS = 1


def _json(case, route, params):
    response = case.url_open(route, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                             headers={'Content-Type': 'application/json'})
    return response.json()


def _call_kw(case, model, method, args, kwargs=None):
    return _json(case, f'/web/dataset/call_kw/{model}/{method}', {
        'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})


# ── 1、2、3：對話 @ 內部同事（使用者 11-11 暫定）─────────────────────────────
@tagged('post_install', '-at_install', MODULE)
class TestMentionColleagueNoEmailHttp(HttpCase):

    PASSWORD = 'Role-fix3-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        _mail_sender_config(env)
        cls.co_a = env['res.company'].create({'name': 'U3 營造 A', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'U3 監造 S', 'company_type': 'supervision'})
        cls.co_far = env['res.company'].create({'name': 'U3 監造 遠', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(name, groups, companies, email=False, **extra):
            login = FIX3_PREFIX + name
            return Users.create(dict({
                'name': login, 'login': login, 'password': cls.PASSWORD, 'email': email,
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': companies[:1].id, 'company_ids': [(6, 0, companies.ids)]}, **extra))

        # 作者要有 email：RPC（非 sudo）的 message_post 沒有寄件人 email 會丟 UserError（mail_thread._message_compute_author）
        cls.sb = user('role_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s, email='u3m-sb@example.invalid')
        cls.mgr = user('mgr', [MANAGER_GROUP], cls.co_s | cls.co_a, email='u3m-mgr@example.invalid',
                       dash_scope_company_id=cls.co_a.id)
        a_parent = {'parent_id': cls.co_a.partner_id.id}
        # 被 @ 的人一律沒有 email（與 dev 的內部帳號相同）
        cls.member = user('member', ['base.group_user'], cls.co_s, **a_parent)
        cls.colleague = user('colleague', ['base.group_user'], cls.co_s, **a_parent)
        cls.colleague_mailpref = user('colleague_mailpref', ['base.group_user'], cls.co_s, **a_parent)
        cls.colleague_mailpref.write({'notification_type': 'email'})   # 偏好 email、卻沒有 email
        cls.far = user('far', ['base.group_user'], cls.co_far)
        cls.portal = user('portal', ['base.group_portal'], cls.co_s, **a_parent)
        cls.nouser = env['res.partner'].create({'name': FIX3_PREFIX + 'nouser', 'company_id': cls.co_s.id, **a_parent})
        for record in (cls.member, cls.colleague, cls.colleague_mailpref, cls.far, cls.portal):
            assert not record.partner_id.email, f'前提：{record.login} 沒有 email'
        cls.colleagues = cls.colleague.partner_id | cls.colleague_mailpref.partner_id

    def _login(self, user):
        login_as_browser(self, user.login, self.PASSWORD)

    def _channel(self, author):
        return self.env[DISCUSS].with_user(author).channel_get([self.member.partner_id.id])

    def _post(self, author, channel, partners, route, tag):
        body = f'U3M {author.login} {route} {tag}'
        self._login(author)
        post = {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment', 'partner_ids': partners.ids}
        if route == 'http':
            result = _json(self, '/mail/message/post', {'thread_model': DISCUSS, 'thread_id': channel.id, 'post_data': post})
        else:
            result = _call_kw(self, DISCUSS, 'message_post', [channel.id], post)
        self.assertNotIn('error', result, f'{author.login} {route}：發得出去：{result.get("error")}')
        self.env.invalidate_all()
        message = self.env['mail.message'].sudo().search([('model', '=', DISCUSS), ('res_id', '=', channel.id),
                                                          ('body', 'ilike', body)])
        self.assertEqual(len(message), 1)
        return message

    def _readable(self, author, partner):
        return bool(self.env['res.partner'].with_user(author).search_count([('id', '=', partner.id)]))

    def test_colleague_without_email_gets_inbox(self):
        """第 1 項：同事沒有 email（偏好站內、偏好 email 各一）照樣收到站內通知；mail.mail 0、沒有 email 型通知。"""
        for author in (self.sb, self.mgr):
            for partner in self.member.partner_id | self.colleagues | self.portal.partner_id | self.nouser:
                self.assertTrue(self._readable(author, partner), f'前提：{author.login} 讀得到 {partner.name}')
            self.assertFalse(self._readable(author, self.far.partner_id), f'前提：{author.login} 讀不到 far')
            channel = self._channel(author)
            targets = (self.member.partner_id | self.colleagues | self.far.partner_id | self.portal.partner_id
                       | self.nouser)
            for route in ('http', 'rpc'):
                with self.subTest(author=author.login, route=route):
                    message = self._post(author, channel, targets, route, 'noemail')
                    notes = message.notification_ids
                    for colleague in self.colleagues:
                        self.assertIn(colleague, message.partner_ids, f'{colleague.name}：加進 partner_ids')
                        self.assertEqual(notes.filtered(lambda n, c=colleague: n.res_partner_id == c).mapped(
                            'notification_type'), ['inbox'], f'{colleague.name}：沒有 email 也收到站內通知（恰好一則）')
                    for other in (self.far.partner_id, self.portal.partner_id, self.nouser):
                        self.assertNotIn(other, message.partner_ids, f'{other.name} 不加進 partner_ids')
                        self.assertFalse(notes.filtered(lambda n, o=other: n.res_partner_id == o), f'{other.name} 沒有通知')
                    self.assertFalse(notes.filtered(lambda n: n.res_partner_id == author.partner_id), '作者自己沒有通知')
                    self.assertFalse(self.env['mail.mail'].sudo().search_count([('mail_message_id', '=', message.id)]),
                                     '整則訊息沒有 mail.mail')
                    self.assertFalse(notes.filtered(lambda n: n.notification_type != 'inbox'), '沒有 email／簡訊型通知')
                    self.assertFalse(self.colleagues & channel.sudo().channel_member_ids.partner_id, '同事不加入對話成員')

    def test_suggestions_equal_kept_set(self):
        """第 2 項：同一個搜尋字，後端 @ 建議名單＝送出時 partner_ids 會保留的集合（_dash_colleagues 一份）。"""
        everyone = self.env['res.partner'].sudo().search(
            ['|', ('name', 'ilike', FIX3_PREFIX), ('email', 'ilike', FIX3_PREFIX)])
        self.assertEqual(len(everyone), 8, '前提：夾具的 8 個聯絡人（2 位作者、成員、2 位同事、far、前台、沒有帳號）')
        self.assertLess(len(everyone), SUGGESTION_LIMIT, '前提：上限夠大，兩邊比的是完整集合')
        for author in (self.sb, self.mgr):
            with self.subTest(author=author.login):
                channel = self._channel(author)
                self._login(author)
                result = _call_kw(self, 'res.partner', 'get_mention_suggestions_from_channel', [],
                                  {'channel_id': channel.id, 'search': FIX3_PREFIX, 'limit': SUGGESTION_LIMIT})
                self.assertNotIn('error', result, result.get('error'))
                suggested = {row['id'] for row in (result['result'].get('res.partner') or [])}
                message = self._post(author, channel, everyone, 'http', 'equal')
                kept = set(message.partner_ids.ids)
                self.assertTrue(self.colleagues.ids and set(self.colleagues.ids) <= kept, '前提：同事在裡面')
                self.assertEqual(suggested, kept, f'{author.login}：建議名單＝送出時保留的集合')

    def test_author_reloads_own_mention_message(self):
        """第 1 項的連帶（S2 fix3 驗收真瀏覽器時發現）：作者 @ 了同事之後，自己重新載入這個私訊照常。
        dev 的「mail.notifications: group_user」規則是 noupdate 的舊資料、perm_read＝True（核心 XML 是 False）：內部帳號只讀得到
        通知到自己的 mail.notification，核心組訊息給網頁（_filtered_for_web_client）讀別人的通知就 AccessError。這裡在交易內把規則
        設成 dev 的狀態，不管跑在哪個庫都量得到。"""
        self.env.ref('mail.ir_rule_mail_notifications_group_user').sudo().write({'perm_read': True})
        for author in (self.sb, self.mgr):
            with self.subTest(author=author.login):
                channel = self._channel(author)
                message = self._post(author, channel, self.colleague.partner_id, 'http', 'reload')
                self.assertTrue(message.notification_ids.filtered(lambda n: n.res_partner_id == self.colleague.partner_id),
                                '前提：同事有站內通知（作者讀不到這一筆）')
                result = _json(self, '/discuss/channel/messages', {'channel_id': channel.id})
                self.assertNotIn('error', result, f'作者重新載入私訊照常：{str(result.get("error"))[:300]}')
                ids = {row['id'] for row in (result['result']['data'].get('mail.message') or [])}
                self.assertIn(message.id, ids, '自己那則訊息載得出來')

    def test_edit_message_narrows_partner_ids(self):
        """第 3 項：編輯自己的對話訊息帶前台帳號、讀不到的內部帳號 → 被拿掉；可 @ 的同事留著。"""
        for author in (self.sb, self.mgr):
            with self.subTest(author=author.login):
                channel = self._channel(author)
                message = self._post(author, channel, self.member.partner_id, 'http', 'edit')
                wanted = self.portal.partner_id | self.far.partner_id | self.nouser | self.colleague.partner_id
                result = _json(self, '/mail/message/update_content', {
                    'message_id': message.id, 'body': f'U3M 改過 {author.login}', 'attachment_ids': [],
                    'partner_ids': wanted.ids})
                self.assertNotIn('error', result, f'編輯照常：{result.get("error")}')
                self.env.invalidate_all()
                self.assertIn('改過', message.body, '前提：內容真的改了')
                for other in (self.portal.partner_id, self.far.partner_id, self.nouser):
                    self.assertNotIn(other, message.partner_ids, f'{other.name}：編輯時也被拿掉')
                self.assertIn(self.colleague.partner_id, message.partner_ids, '可 @ 的同事留著')
                # ORM 直接寫（非 sudo）：要嘛被擋，要嘛照樣收窄
                try:
                    message.with_user(author).write({'partner_ids': [(4, self.portal.partner_id.id)]})
                except Exception:  # noqa: BLE001 — 被擋也是對的
                    pass
                self.env.invalidate_all()
                self.assertNotIn(self.portal.partner_id, message.sudo().partner_ids, 'ORM 寫入也照樣收窄')


# ── 4、5：意見回饋的留言與驗證（使用者 11-11）─────────────────────────────────
@tagged('post_install', '-at_install', MODULE)
class TestRoleFeedbackCommentHttp(HttpCase):
    """舊前台監造老闆與監造老闆角色帳號在自己的單上留言（真 HTTP /mail/message/post＋附檔）：收件人相同。"""

    PASSWORD = 'Role-fb3-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        if TICKET not in env:
            raise unittest.SkipTest('construction_helpdesk 沒裝（意見回饋只在裝了它的庫）')
        _mail_sender_config(env)
        cls.co_s = env['res.company'].create({'name': 'W3 監造 S', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, **extra):
            return Users.create(dict({
                'name': login, 'login': login, 'password': cls.PASSWORD, 'email': f'{login}@example.invalid',
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': cls.co_s.id, 'company_ids': [(6, 0, cls.co_s.ids)]}, **extra))

        cls.old = user('w3_old_sb', [P_BOSS], **SUPERVISION_USER_VALS)
        cls.new = user('w3_new_sb', [ROLE_SUPERVISION, ROLE_BOSS])
        cls.staff = user('w3_staff', ['base.group_user', SUPERVISOR_ADMIN])
        cls.category = env['construction.service.category'].create({'name': 'W3 類別'})
        cls.follower_ext = env['res.partner'].create({'name': 'W3 追蹤的外部聯絡人', 'email': 'w3-f@example.invalid'})
        cls.outsider = env['res.partner'].create({'name': 'W3 不相干的外部聯絡人', 'email': 'w3-o@example.invalid'})
        cls.others = cls._ticket(cls.staff, 'W3 別人的單')

    @classmethod
    def _ticket(cls, owner, subject):
        ticket = cls.env[TICKET].with_user(owner).sudo().with_context(mail_create_nosubscribe=True).create({
            'subject': subject, 'description': 'x', 'category_id': cls.category.id, 'channel': 'portal'})
        ticket.message_subscribe(partner_ids=(cls.staff.partner_id | cls.follower_ext).ids)
        return ticket

    def _upload(self, ticket, name):
        """前台留言框的附檔：先以「暫存」上傳（核心 attachment_uploader_hook 在有留言框時帶 is_pending）。"""
        response = self.url_open('/mail/attachment/upload', data={
            'thread_id': ticket.id, 'thread_model': TICKET, 'is_pending': 'true',
            'csrf_token': http.Request.csrf_token(self)}, files={'ufile': (name, b'W3 FILE', 'text/plain')})
        rows = (response.json().get('data') or {}).get('ir.attachment') or []
        self.assertEqual(len(rows), 1, f'上傳附件：{response.text[:200]}')
        return rows[0]

    def _comment(self, user, ticket, tag, with_file=True):
        login_as_browser(self, user.login, self.PASSWORD)
        body = f'W3 留言 {user.login} {tag}'
        post = {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment',
                'partner_ids': [self.follower_ext.id, self.outsider.id]}
        params = {'thread_model': TICKET, 'thread_id': ticket.id, 'post_data': post}
        if with_file:
            row = self._upload(ticket, f'w3-{user.login}-{tag}.txt')
            post['attachment_ids'] = [row['id']]
            params['attachment_tokens'] = [row.get('access_token')]
        result = _json(self, '/mail/message/post', params)
        self.env.invalidate_all()
        return result, self.env['mail.message'].sudo().search([('body', 'ilike', body)])

    def test_own_ticket_comment_like_old_portal(self):
        results = {}
        for user in (self.old, self.new):
            with self.subTest(login=user.login):
                ticket = self._ticket(user, f'W3 {user.login} 自己的單')
                followers_before = ticket.sudo().message_partner_ids
                result, message = self._comment(user, ticket, 'own')
                self.assertNotIn('error', result, f'{user.login}：在自己的單上留言照常：{result.get("error")}')
                self.assertEqual(len(message), 1)
                self.assertEqual(message.author_id, user.partner_id, '作者是本人')
                self.assertEqual((message.model, message.res_id), (TICKET, ticket.id))
                self.assertFalse(message.is_internal or message.subtype_id.internal, '一般留言（不是內部備註）')
                self.assertEqual(len(message.attachment_ids), 1, '附檔照常')
                self.assertEqual((message.attachment_ids.res_model, message.attachment_ids.res_id), (TICKET, ticket.id))
                self.assertNotIn(self.outsider, message.partner_ids, '不是追蹤者的外部聯絡人被拿掉')
                recipients = {(n.res_partner_id.id, n.notification_type) for n in message.notification_ids}
                self.assertIn(self.staff.partner_id.id, {pid for pid, _type in recipients}, '追蹤者（客服）收到')
                self.assertNotIn(self.outsider.id, {pid for pid, _type in recipients})
                self.assertEqual(ticket.sudo().message_partner_ids, followers_before, '留言者不自動成為追蹤者（同舊帳號）')
                # 留言後重新載入這張單的訊息（詳情頁的對話）照常——dev 的通知規則狀態見 TestMentionColleagueNoEmailHttp
                # test_author_reloads_own_mention_message（這裡的留言通知了客服，作者讀不到那幾筆通知）
                self.env.ref('mail.ir_rule_mail_notifications_group_user').sudo().write({'perm_read': True})
                reload = _json(self, '/mail/thread/messages', {'thread_model': TICKET, 'thread_id': ticket.id})
                self.assertNotIn('error', reload, f'{user.login}：留言後重新載入照常：{str(reload.get("error"))[:300]}')
                self.assertIn(message.id, {row['id'] for row in (reload['result']['data'].get('mail.message') or [])})
                results[user.login] = recipients
        self.assertEqual(results[self.old.login], results[self.new.login], '舊前台帳號與角色帳號：通知對象相同')

    def test_others_ticket_and_rpc_rejected(self):
        for user in (self.old, self.new):
            with self.subTest(login=user.login):
                result, message = self._comment(user, self.others, 'others', with_file=False)
                self.assertIn('error', result, f'{user.login}：別人的單不能留言')
                self.assertFalse(message, '沒有建出訊息')
        # 角色帳號：RPC 直接 message_post 照舊被擋（後台唯讀；只有前台留言這一條路）
        own = self._ticket(self.new, 'W3 角色帳號 RPC')
        login_as_browser(self, self.new.login, self.PASSWORD)
        result = _call_kw(self, TICKET, 'message_post', [own.id], {
            'body': 'W3 RPC 留言', 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment'})
        self.assertIn('error', result, 'RPC 直接 message_post 被擋')
        self.assertFalse(self.env['mail.message'].sudo().search([('body', 'ilike', 'W3 RPC 留言')]))


@tagged('post_install', '-at_install', MODULE)
class TestRoleFeedbackVerify(RolePhoneCase):
    """第 5 項：驗證路由（問題已解決／仍有問題）——本人的單可以、別人的單不行；角色帳號與同方別舊帳號相同。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if TICKET not in cls.env:
            raise unittest.SkipTest('construction_helpdesk 沒裝（意見回饋只在裝了它的庫）')
        from odoo.addons.construction_helpdesk.controllers.portal_feedback import HelpdeskPortal
        cls.fb = HelpdeskPortal()
        cls.category = cls.env['construction.service.category'].create({'name': 'S2V 類別'})

    def _waiting(self, owner, subject):
        ticket = self.env[TICKET].with_user(owner).sudo().create({
            'subject': subject, 'description': 'x', 'category_id': self.category.id, 'channel': 'portal'})
        ticket.with_context(helpdesk_system_write=True).sudo().write({'state': 'waiting_verify'})
        return ticket

    def test_verify_own_only(self):
        pair = (SIDE_SUPERVISION, LEVEL_BOSS)
        outcomes = {}
        for user in (self.old[pair], self.new[pair]):
            with self.subTest(login=user.login):
                resolved = self._waiting(user, f'S2V {user.login} 已解決')
                again = self._waiting(user, f'S2V {user.login} 仍有問題')
                others = self._waiting(self.staff, f'S2V 別人的單 {user.login}')
                status, value = self._call(user, self.fb.portal_feedback_verify, resolved.id, result='resolved')
                self.assertEqual((status, value.endswith('message=resolved')), ('redirect', True), value)
                status, value = self._call(user, self.fb.portal_feedback_verify, again.id, result='not_resolved')
                self.assertEqual((status, value.endswith('message=not_resolved')), ('redirect', True), value)
                status, value = self._call(user, self.fb.portal_feedback_verify, others.id, result='resolved')
                self.assertEqual((status, value.endswith('/construction/feedback')), ('redirect', True),
                                 f'別人的單導回列表：{value}')
                self.env.invalidate_all()
                self.assertEqual((resolved.state, resolved.confirm_user_id, resolved.customer_confirmed),
                                 ('done', user, True), '本人的單：結案、確認者是本人')
                self.assertEqual(again.state, 'processing', '本人的單：回到處理中')
                self.assertEqual((others.state, others.confirm_user_id.id), ('waiting_verify', False), '別人的單沒有被改')
                outcomes[user.login] = (resolved.state, again.state, others.state)
        self.assertEqual(len(set(outcomes.values())), 1, f'舊帳號與角色帳號相同：{outcomes}')


# ── 9：受限內部帳號的程式介面只收 API key（使用者 11-11「關」）───────────────────
@tagged('post_install', '-at_install', MODULE)
class TestRestrictedRpcApiKeyOnlyHttp(HttpCase):

    PASSWORD = 'Rpc-key-only-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.co_a = env['res.company'].create({'name': 'K9 營造 A', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'K9 監造 S', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, companies, **extra):
            return Users.create(dict({
                'name': login, 'login': login, 'password': cls.PASSWORD,
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': companies[:1].id, 'company_ids': [(6, 0, companies.ids)]}, **extra))

        # 都不開 TOTP（使用者 11-11：不要求任何人開兩步驟驗證）
        cls.restricted = (
            user('k9_role_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s),
            user('k9_mgr', [MANAGER_GROUP], cls.co_s | cls.co_a, dash_scope_company_id=cls.co_a.id),
            user('k9_console', [CONSOLE_GROUP], cls.co_s),
        )
        cls.staff = user('k9_staff', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s)
        for record in cls.restricted + (cls.staff,):
            assert not record.totp_enabled, f'前提：{record.login} 沒開 TOTP'

    def _xml_read(self, uid, secret):
        return self.xmlrpc_object.execute_kw(self.env.cr.dbname, uid, secret, 'res.users', 'read', [[uid], ['login']])

    def _jsonrpc(self, uid, secret):
        return _json(self, '/jsonrpc', {'service': 'object', 'method': 'execute_kw', 'args': [
            self.env.cr.dbname, uid, secret, 'res.users', 'read', [[uid], ['login']]]})

    def _browser_login(self, user):
        self.url_open('/web/session/logout')
        page = self.url_open('/web/login')
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        response = self.url_open('/web/login', data={'login': user.login, 'password': self.PASSWORD,
                                                     'csrf_token': csrf.group(1) if csrf else ''}, allow_redirects=False)
        info = _json(self, '/web/session/get_session_info', {}).get('result') or {}
        return response.headers.get('Location', ''), info.get('uid')

    def test_password_rpc_rejected_api_key_and_browser_ok(self):
        db = self.env.cr.dbname
        for user in self.restricted:
            with self.subTest(login=user.login):
                self.assertTrue(user._dash_is_restricted_internal(), '前提：受限內部帳號')
                # 密碼：authenticate 回 False、execute_kw 是 AccessDenied（XML-RPC、JSON-RPC 都一樣）
                self.assertFalse(self.xmlrpc_common.authenticate(db, user.login, self.PASSWORD, {}),
                                 'XML-RPC 用密碼登入被拒')
                with self.assertRaises(xmlrpc.client.Fault) as ctx:
                    self._xml_read(user.id, self.PASSWORD)
                self.assertEqual(ctx.exception.faultCode, RPC_FAULT_ACCESS_DENIED, ctx.exception.faultString[:200])
                body = self._jsonrpc(user.id, self.PASSWORD)
                self.assertIn('error', body, 'JSON-RPC 用密碼被拒')
                self.assertIn('AccessDenied', json.dumps(body['error'])[:2000])
                # API key：照常
                key = self.env['res.users.apikeys'].with_user(user)._generate(
                    'rpc', 'K9 測試', fields.Datetime.now() + datetime.timedelta(days=API_KEY_DAYS))
                self.assertEqual(self.xmlrpc_common.authenticate(db, user.login, key, {}), user.id, 'API key 登入照常')
                self.assertEqual(self._xml_read(user.id, key)[0]['login'], user.login, 'API key 讀取照常')
                self.assertEqual(self._jsonrpc(user.id, key).get('result', [{}])[0].get('login'), user.login)
                # 瀏覽器（互動式）用密碼登入：照常，不要求兩步驟驗證
                location, uid = self._browser_login(user)
                self.assertTrue(location and '/web/login' not in location, f'瀏覽器登入導向（不是打回登入頁）：{location!r}')
                self.assertEqual(uid, user.id, '瀏覽器登入建立了本人的 session')
        # 一般內部帳號：用密碼打 RPC 照常（不受影響）
        self.assertEqual(self.xmlrpc_common.authenticate(db, self.staff.login, self.PASSWORD, {}), self.staff.id)
        self.assertEqual(self._xml_read(self.staff.id, self.PASSWORD)[0]['login'], self.staff.login)
        self.assertEqual(self._jsonrpc(self.staff.id, self.PASSWORD).get('result', [{}])[0].get('login'),
                         self.staff.login)
