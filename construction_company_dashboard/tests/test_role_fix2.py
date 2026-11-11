# -*- coding: utf-8 -*-
"""S2 fix2（使用者 11-11 追加，2026-11-11）：U（對話 @ 內部同事，暫定）、W（意見回饋開給角色帳號）、Z（先不強制兩步驟驗證，暫定）。

* U：唯讀帳號（監造方角色帳號、既有營造廠主管型）在私訊裡 @ 對話外的人：讀得到的內部同事加進 partner_ids、收站內通知
  （對方偏好 email 也改站內），讀不到的內部使用者、前台帳號、沒有帳號的聯絡人照舊拿掉；後台人員照核心。@ 建議名單同一個判斷。
  **使用者 11-11 暫定**，之後會再改（restricted_mail.py 檔頭九）。
* W：監造方角色帳號的意見回饋＝同方別的舊前台帳號（入口、建單、看自己的單）；寫入例外都只限本人的單：前台建單（sudo 建本人的單）、
  留言、驗證（S2 fix3 更正「只有建單這一條」；留言與驗證的測試在 test_role_fix3）。
* Z：DASH_REQUIRE_TOTP＝False（使用者 11-11 暫定：先不強制）——沒開 TOTP 的營造廠主管、四種角色帳號與開了 TOTP 的同一帳號
  讀取範圍、手機能力、通知都相同。強制時（常數 patch 成 True）的舊行為由 test_scope_rules／test_role_phone 等標了
  require_totp 的測試保住。（原本的 X「沒開 TOTP 照發通知」被 Z 取代，已拿掉。）
"""
import json
import unittest
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, tagged

from .test_role_phone import (
    CONTRACTOR_MARKER, LEVEL_BOSS, LEVEL_MANAGER, ROLE_BOSS, ROLE_MANAGER, ROLE_SUPERVISION, SIDE_CONTRACTOR,
    SIDE_SUPERVISION, RolePhoneCase, _mail_sender_config,
)
from .test_scope_rules import MANAGER_GROUP, SUPERVISOR_ADMIN, TOTP_FIXTURE_SECRET, require_totp

MODULE = 'construction_company_dashboard'
TICKET = 'construction.service.ticket'
DISCUSS = 'discuss.channel'


# ── U：對話裡 @ 內部同事（使用者 11-11 暫定）────────────────────────────────
@tagged('post_install', '-at_install', MODULE)
class TestRoleMentionColleagueHttp(HttpCase):
    """真 HTTP（/mail/message/post、call_kw message_post、@ 建議名單、session 旗標）。"""

    PASSWORD = 'Role-mention-pass1'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        _mail_sender_config(env)
        cls.co_a = env['res.company'].create({'name': 'U 營造 A', 'company_type': 'contractor'})
        cls.co_s = env['res.company'].create({'name': 'U 監造 S', 'company_type': 'supervision'})
        cls.co_far = env['res.company'].create({'name': 'U 監造 遠', 'company_type': 'supervision'})
        Users = env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, companies, totp=False, **extra):
            # email 要有：核心的對話收件人 SQL 只取 email 不是空的聯絡人（mail/models/discuss/discuss_channel.py:566
            # `partner.email != %s`，NULL 比較為假），沒有 email 的人被 @ 也不會被通知
            record = Users.create(dict({
                'name': login, 'login': login, 'password': cls.PASSWORD, 'email': f'{login}@example.invalid',
                'groups_id': [(6, 0, [env.ref(g).id for g in groups])],
                'company_id': companies[:1].id, 'company_ids': [(6, 0, companies.ids)]}, **extra))
            if totp:
                record.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
            return record

        cls.sb = user('u_role_sb', [ROLE_SUPERVISION, ROLE_BOSS], cls.co_s, totp=True)
        cls.mgr = user('u_mgr', [MANAGER_GROUP], cls.co_s | cls.co_a, totp=True, dash_scope_company_id=cls.co_a.id)
        cls.sup = user('u_sup', ['base.group_user', SUPERVISOR_ADMIN], cls.co_s)
        a_parent = {'parent_id': cls.co_a.partner_id.id}
        # 兩個唯讀帳號各自的範圍：監造方讀得到「允許公司是 S」的帳號，營造廠主管讀得到「隸屬營造廠 A」的聯絡人
        cls.member = user('u_member', ['base.group_user'], cls.co_s, **a_parent)
        cls.colleague = user('u_colleague', ['base.group_user'], cls.co_s, **a_parent)
        cls.colleague.write({'notification_type': 'email'})   # 偏好 email（建帳號時預設站內，事後改）
        assert cls.colleague.notification_type == 'email'
        cls.far = user('u_far', ['base.group_user'], cls.co_far)
        cls.portal = user('u_portal', ['base.group_portal'], cls.co_s, **a_parent)
        cls.nouser = env['res.partner'].create({'name': 'u_nouser', 'email': 'u-nouser@example.invalid',
                                                'company_id': cls.co_s.id, **a_parent})

    def _login(self, user):
        # 已啟用 TOTP 的帳號：HttpCase.authenticate 是非互動式登入，核心只收 API 金鑰（同 TestRoleMailHttp._login）
        with patch.object(type(self.env['res.users']), '_rpc_api_keys_only', lambda self: False):
            self.authenticate(user.login, self.PASSWORD)

    def _json(self, route, params):
        response = self.url_open(route, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def _rpc(self, model, method, args, kwargs=None):
        return self._json(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def _post(self, author, channel, partners, route, tag):
        body = f'U-MENTION {author.login} {route} {tag}'
        self._login(author)
        post = {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment', 'partner_ids': partners.ids}
        if route == 'http':
            result = self._json('/mail/message/post', {'thread_model': DISCUSS, 'thread_id': channel.id, 'post_data': post})
        else:
            result = self._rpc(DISCUSS, 'message_post', [channel.id], post)
        self.assertNotIn('error', result, f'{author.login} {route}：發得出去：{result.get("error")}')
        self.env.invalidate_all()
        message = self.env['mail.message'].sudo().search([('model', '=', DISCUSS), ('res_id', '=', channel.id),
                                                          ('body', 'ilike', body)])
        self.assertEqual(len(message), 1)
        return message

    def _readable(self, author, partner):
        return bool(self.env['res.partner'].with_user(author).search_count([('id', '=', partner.id)]))

    def test_restricted_mention_colleague_inbox_only(self):
        for author in (self.sb, self.mgr):
            # 前提：同事、前台帳號、沒有帳號的聯絡人都讀得到（才隔離得出「內部使用者」那一道）；遠處的人讀不到
            for partner in (self.member.partner_id, self.colleague.partner_id, self.portal.partner_id, self.nouser):
                self.assertTrue(self._readable(author, partner), f'前提：{author.login} 讀得到 {partner.name}')
            self.assertFalse(self._readable(author, self.far.partner_id), f'前提：{author.login} 讀不到 u_far')
            channel = self.env[DISCUSS].with_user(author).channel_get([self.member.partner_id.id])
            targets = (self.member.partner_id | self.colleague.partner_id | self.far.partner_id
                       | self.portal.partner_id | self.nouser)
            for route in ('http', 'rpc'):
                with self.subTest(author=author.login, route=route):
                    message = self._post(author, channel, targets, route, 'restricted')
                    notes = message.notification_ids
                    self.assertIn(self.colleague.partner_id, message.partner_ids, '讀得到的內部同事加進 partner_ids')
                    self.assertTrue(notes.filtered(lambda n: n.res_partner_id == self.colleague.partner_id
                                                   and n.notification_type == 'inbox'),
                                    '同事收到站內通知（偏好 email 也改站內）')
                    self.assertIn(self.member.partner_id, message.partner_ids, '成員照舊')
                    for other in (self.far.partner_id, self.portal.partner_id, self.nouser):
                        self.assertNotIn(other, message.partner_ids, f'{other.name} 不加進 partner_ids')
                        self.assertFalse(notes.filtered(lambda n, o=other: n.res_partner_id == o), f'{other.name} 沒有通知')
                    self.assertFalse(self.env['mail.mail'].sudo().search_count([('mail_message_id', '=', message.id)]),
                                     '整則訊息沒有 mail.mail')
                    self.assertFalse(notes.filtered(lambda n: n.notification_type != 'inbox'), '沒有 email／簡訊型通知')
                    self.assertNotIn(self.colleague.partner_id, channel.sudo().channel_member_ids.partner_id,
                                     '同事不加入對話成員')

    def test_staff_mention_unchanged(self):
        """後台人員在私訊 @ 對話外的人：照核心（partner_ids 不收窄、照對方偏好通知、沒有帳號的寄 email）。"""
        channel = self.env[DISCUSS].with_user(self.sup).channel_get([self.member.partner_id.id])
        message = self._post(self.sup, channel, self.far.partner_id | self.colleague.partner_id | self.nouser,
                             'http', 'staff')
        notes = message.notification_ids
        for partner in (self.far.partner_id, self.colleague.partner_id, self.nouser):
            self.assertIn(partner, message.partner_ids, f'後台人員：{partner.name} 照核心留在 partner_ids')
        self.assertTrue(notes.filtered(lambda n: n.res_partner_id == self.far.partner_id
                                       and n.notification_type == self.far.notification_type), 'u_far 照偏好通知')
        emailed = notes.filtered(lambda n: n.notification_type == 'email').res_partner_id
        self.assertIn(self.colleague.partner_id, emailed, '偏好 email 的同事照核心收 email')
        self.assertIn(self.nouser, emailed, '沒有帳號的聯絡人照核心收 email')

    def test_mention_suggestions_and_session_flag(self):
        for author, expect in ((self.sb, True), (self.mgr, True), (self.sup, False)):
            channel = self.env[DISCUSS].with_user(author).channel_get([self.member.partner_id.id])
            self._login(author)
            info = self._json('/web/session/get_session_info', {})['result']
            self.assertEqual(info.get('dash_mention_colleagues'), expect, f'{author.login}：session 旗標')
            found = set()
            for term in ('u_colleague', 'u_far', 'u_portal', 'u_nouser', 'u_member'):
                result = self._rpc('res.partner', 'get_mention_suggestions_from_channel', [],
                                   {'channel_id': channel.id, 'search': term})
                self.assertNotIn('error', result, f'{author.login}：建議名單 {term}')
                found |= {row['id'] for row in (result['result'].get('res.partner') or [])}
            self.assertIn(self.member.partner_id.id, found, f'{author.login}：成員照舊在建議名單')
            self.assertEqual(self.colleague.partner_id.id in found, expect,
                             f'{author.login}：對話外的內部同事（唯讀帳號才有；後台人員照核心只列成員）')
            for other in (self.far.partner_id, self.portal.partner_id, self.nouser):
                self.assertNotIn(other.id, found, f'{author.login}：{other.name} 不在建議名單')


# ── W：意見回饋開給監造方角色帳號（使用者 11-11）─────────────────────────────
@tagged('post_install', '-at_install', MODULE)
class TestRoleFeedback(RolePhoneCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if TICKET not in cls.env:
            raise unittest.SkipTest('construction_helpdesk 沒裝（意見回饋只在裝了它的庫）')
        from odoo.addons.construction_helpdesk.controllers.portal_feedback import HelpdeskPortal
        cls.fb = HelpdeskPortal()
        cls.category = cls.env['construction.service.category'].create({'name': 'S2W 類別'})
        cls.p_other = cls._project('S2-PO', 'general', 'construction')   # 監造主管不是成員：看不到

    def _create(self, user, tag, **post):
        status, value = self._call(user, self.fb.portal_feedback_create, category_id=str(self.category.id),
                                   subject=f'S2W {user.login} {tag}', description='S2W 內容', **post)
        self.env.invalidate_all()
        ticket = self.env[TICKET].sudo().search([('subject', '=', f'S2W {user.login} {tag}')])
        return status, value, ticket

    def test_supervision_role_feedback_like_old_portal(self):
        others = self.env[TICKET].with_user(self.staff).sudo().create({
            'subject': 'S2W 別人的單', 'description': 'x', 'category_id': self.category.id, 'channel': 'portal'})
        for pair in ((SIDE_SUPERVISION, LEVEL_BOSS), (SIDE_SUPERVISION, LEVEL_MANAGER)):
            for user in (self.old[pair], self.new[pair]):
                with self.subTest(login=user.login):
                    status, value, ticket = self._create(
                        user, 'own', from_project=str(self.p.id), create_uid=str(self.staff.id), contact_name='冒名')
                    self.assertEqual((status, 'message=created' in value), ('redirect', True), f'建單成功：{value}')
                    self.assertEqual(len(ticket), 1)
                    self.assertEqual(ticket.create_uid, user, '擁有者是本人（不能替別人建）')
                    self.assertEqual(ticket.contact_name, user.name, '聯絡人是本人（表單送來的值不採用）')
                    self.assertEqual(ticket.project_name, self.p.name)
                    Ticket = self.env[TICKET].with_user(user)
                    self.assertEqual(Ticket.search([('id', 'in', (ticket | others).ids)]), Ticket.browse(ticket.id),
                                     '讀得到自己的、讀不到別人的')
                    self.assertEqual(self._call(user, self.fb.portal_feedback_detail, ticket.id)[0], 'render')
                    status, value = self._call(user, self.fb.portal_feedback_detail, others.id)
                    self.assertTrue(status == 'redirect' and value.endswith('/construction/feedback'), '別人的單導回列表')
                    self.assertEqual(self._call(user, self.fb.portal_feedback_list)[0], 'render')
                    # 看不到的工程：不帶工程名稱（不能指定範圍外的工程）
                    if pair[1] == LEVEL_MANAGER:
                        _status, _value, hidden = self._create(user, 'hidden', from_project=str(self.p_other.id))
                        self.assertFalse(hidden.project_name, '範圍外的工程不帶進客服單')
        # RPC／ORM 直接建、改：角色帳號照舊全拒（後台唯讀；寫入例外只走前台路由：建單、留言、驗證，都只限本人的單）
        role = self.new[(SIDE_SUPERVISION, LEVEL_BOSS)]
        with self.assertRaises(AccessError):
            self.env[TICKET].with_user(role).create({'subject': 'S2W RPC', 'description': 'x',
                                                     'category_id': self.category.id})
        own = self.env[TICKET].sudo().search([('create_uid', '=', role.id)], limit=1)
        self.assertTrue(own, '前提：角色帳號有自己建的單（前台建單成功）')
        with self.assertRaises(AccessError):
            own.with_user(role).write({'subject': 'S2W 改'})

    @require_totp   # 範圍不合格的角色帳號（強制兩步驟驗證時沒開 TOTP 的）；S2 fix2-Z 起預設不強制
    def test_contractor_and_blocked_roles_still_closed(self):
        blocked = self._role('s2w_fresh_sb', SIDE_SUPERVISION, ROLE_BOSS, totp=False)
        for user in (self.old[(SIDE_CONTRACTOR, LEVEL_BOSS)], self.new[(SIDE_CONTRACTOR, LEVEL_BOSS)],
                     self.new[(SIDE_CONTRACTOR, LEVEL_MANAGER)], blocked):
            with self.subTest(login=user.login):
                status, value, ticket = self._create(user, 'closed')
                self.assertFalse(ticket, '營造方、沒開 TOTP 的角色帳號照舊建不了')
                if user._is_role_account():
                    # 角色帳號：建單路由一開頭就導回（帶 error=denied），不是讀到一半被讀取規則擋成 403
                    # （mutation W2 第一輪存活：拿掉這道之後讀類別照樣被 rule_scope 擋，只有回應的樣子不同）
                    self.assertEqual((status, 'error=denied' in value), ('redirect', True), f'{status} {value[:80]}')
                else:
                    # 舊的營造方前台帳號照舊在讀類別時被讀取規則擋（403）
                    self.assertEqual(status, 'denied', value[:80])


# ── Z：先不強制兩步驟驗證（使用者 11-11 暫定）───────────────────────────────
@tagged('post_install', '-at_install', MODULE)
class TestNoTotpRequired(RolePhoneCase):
    """常數為 False（現況）：同一個帳號沒開 TOTP 與開了 TOTP，讀取範圍、手機能力、通知都相同（同一組斷言跑兩種狀態）。"""

    _z_day = 0

    def _member(self, user):
        # 主管是成員制：要是工程成員才看得到（開不開 TOTP 都一樣；不加的話「有工程」這個前提量不到）
        for project in self.projects:
            self.env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        return user

    def _contractor_manager(self, login):
        return self._member(self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'groups_id': [(6, 0, [self.env.ref(CONTRACTOR_MARKER).id])],
            'company_id': self.co_s.id, 'company_ids': [(6, 0, (self.co_s | self.co_a).ids)],
            'dash_scope_company_id': self.co_a.id}))

    def _state(self, user, tag):
        """讀取範圍、手機能力、通知（同一組量法）。"""
        self.env.registry.clear_cache()
        self.env.invalidate_all()
        env = self.env(user=user)
        type(self)._z_day += 1   # 每一次量一張不同日期的日誌（同一天同一個填表人只能一張；14 天內不鎖定）
        log = self._log(days_ago=self._z_day)
        message = log.with_user(self.staff).message_post(
            body=f'S2Z {user.login} {tag}', message_type='comment', subtype_xmlid='mail.mt_comment',
            partner_ids=user.partner_id.ids)
        return {
            'scope_ok': user._dash_scope_ok(),
            'totp_missing': user._dash_totp_missing(),
            'kind_none': env['ir.rule']._dash_scope_kind() is None,
            'level': user._portal_role_level(),
            'manage': user._portal_can_manage(),
            'write': user._portal_can_write(),
            'review': user._portal_review_visible(),
            'projects': set(env['project.project'].search([('id', 'in', self.projects.ids)]).ids),
            'logs': bool(env['daily.log.sheet'].search_count([('id', '=', log.id)])),
            'estimates_readable': env['payment.estimate'].check_access_rights('read', raise_exception=False),
            'notified': user.partner_id in message.sudo().notification_ids.res_partner_id,
            'reads_message': bool(env['mail.message'].search_count([('id', '=', message.id)])),
        }

    def test_no_totp_same_as_totp(self):
        users = [self._contractor_manager('s2z_mgr')] + [
            self._member(self._role(f's2z_{side}_{level}', side, ROLE_BOSS if level == LEVEL_BOSS else ROLE_MANAGER,
                                    totp=False))
            for side, level in ((SIDE_CONTRACTOR, LEVEL_BOSS), (SIDE_CONTRACTOR, LEVEL_MANAGER),
                                (SIDE_SUPERVISION, LEVEL_BOSS), (SIDE_SUPERVISION, LEVEL_MANAGER))]
        for user in users:
            with self.subTest(login=user.login):
                self.assertFalse(user.sudo().totp_enabled, '前提：沒開 TOTP')
                without = self._state(user, 'without')
                user.sudo().write({'totp_secret': TOTP_FIXTURE_SECRET})
                with_totp = self._state(user, 'with')
                self.assertTrue(with_totp['scope_ok'] and with_totp['projects'], f'前提：開了 TOTP 有範圍、有工程 {with_totp}')
                self.assertEqual(without, with_totp, '沒開 TOTP 與開了 TOTP 相同（使用者 11-11 暫定：先不強制）')
                self.assertFalse(without['kind_none'], '有角色群組的帳號 kind 絕不能是 None')

    @require_totp
    def test_require_totp_restores_old_behavior(self):
        """常數 patch 成 True：沒開 TOTP＝範圍不合格（什麼都看不到、kind 不是 None、手機沒能力、不收業務通知）。"""
        for user in (self._contractor_manager('s2z_req_mgr'),
                     self._role('s2z_req_sb', SIDE_SUPERVISION, ROLE_BOSS, totp=False)):
            with self.subTest(login=user.login):
                state = self._state(user, 'required')
                self.assertTrue(state['totp_missing'] and not state['scope_ok'], state)
                self.assertFalse(state['kind_none'], 'kind 不是 None')
                self.assertEqual((state['projects'], state['logs'], state['notified'], state['reads_message']),
                                 (set(), False, False, False), state)
                self.assertFalse(state['level'] or state['manage'] or state['write'], '手機沒能力')
