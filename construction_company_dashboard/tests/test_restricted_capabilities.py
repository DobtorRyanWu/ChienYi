# -*- coding: utf-8 -*-
"""受限帳號收回能力（合約 §0b-24～26；線 I）。

受限帳號＝營造方（後台營造廠主管、前台營造帳號）＋控台讀取帳號。營造廠主管與控台讀取帳號隱含 base.group_user，
11-06 抗辯實打它們繼承了內部帳號的：精靈建立權（related 以 sudo 算 → 讀範圍外資料；精靈動作以 sudo 寫）、
全部自訂方法的呼叫路徑、公開頻道、內部備註、全體共用篩選。這裡鎖住「拿掉之後」：

1. 精靈：業務精靈建不了（規則拒＋實際 create 被拒），只看得到自己建的；帳號自助四種照常。對照：監造方照常。
2. 自訂方法閘門（判定）：自訂模組實作的公開方法拒，ORM 讀取 API、寫建刪名稱、儀表板方法、只由官方模組實作的方法放行；
   伺服器動作只能執行官方模組定義的。
3. 公開頻道：不自動加入、既有成員資格移除、讀不到改不了；私訊照常。對照：監造方照常。
4. 內部備註：讀不到；一般訊息、追蹤紀錄照常。對照：監造方看得到自己的內部備註。
5. 共用篩選：只能建寫刪自己的。對照：監造方照常建全體篩選。
6. 回填歸屬：讀不到／寫不了的工程不能代為重算。對照：自家工程照常。
7. 歸屬約束：監造方改照片的工程、營造廠移出工程後替舊單據補照片都成功；營造方仍不能把歸屬寫成別家。
8. 訊息搜尋：受限帳號 search_count([]) 不因讀不到的來源單據（行事曆）而出錯。
9. 控台讀取帳號在前台：看不到任何工程、sudo 查出的紀錄以本人身分再過規則。

HTTP 層（call_kw、call_button、XML-RPC、JSON-RPC 真的被閘門攔下）在 test_method_gate_http.py。
"""
from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.addons.construction_company_dashboard.models.method_gate import (
    GATE_NOTE, check_method_call, custom_implementations, gate_verdict, is_custom_module,
)
from odoo.addons.construction_company_dashboard.models.rule_scope import DENY_NOTE_CONSOLE, DENY_NOTE_CONTRACTOR
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

from .test_scope_rules import DENIED, MANAGER_GROUP, PNG_B64, SUPERVISOR_ADMIN, DashScopeCase

# 帳號自助精靈（測試這邊獨立寫一份；合約 §0b-24）
EXPECT_SELF_SERVICE = frozenset({
    'auth_totp.wizard', 'res.users.identitycheck', 'res.users.apikeys.description', 'change.password.own'})
# 一定是自訂模組實作的公開方法（抗辯實打用過的）與一定只由官方模組實作的（帳號自助）
CUSTOM_METHODS = (
    ('supervision.folder.upload.wizard', 'action_upload'),   # sudo 改掛附件（skeptic F1、red-team F5）
    ('project.project', 'action_view_photos'),
    ('project.project', 'action_dash_refill_attribution'),
    ('project.project', 'geo_search'),                       # 第三方 base_geoengine 也算自訂
)
CORE_ONLY_METHODS = (
    ('res.users', 'action_totp_enable_wizard'), ('res.users', 'preference_change_password'),
    ('res.users', 'api_key_wizard'), ('res.users', 'action_revoke_all_devices'),
    ('res.users.identitycheck', 'run_check'), ('auth_totp.wizard', 'enable'),
)
# 自訂模組覆寫了、但名稱照放行的（ORM 讀取 API、寫建刪）：前提是它們確實被自訂模組覆寫（否則這組斷言恆真）
OVERRIDDEN_BUT_ALLOWED = (('project.project', 'fields_get'), ('project.project', 'write'),
                          ('project.project', 'create'), ('res.users', 'write'))
EXPECT_DASHBOARD_METHODS = (
    ('project.project', 'get_dash_company_kpis'), ('project.project', 'action_dash_drilldown'),
    ('project.project', 'get_project_dashboard_data'), ('project.project', 'get_progress_chart_data'),
    ('project.project', 'dash_console_overview'),
)
SECRET_B32 = 'JBSWY3DPEHPK3PXQ'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestRestrictedCapabilities(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.restricted = (cls.mgr_a, cls.portal_a, cls.console)
        cls.folder_a = env['supervision.folder'].create({'name': 'DASH 資料夾 A', 'project_id': cls.p_a.id})
        cls.photo_b = cls.docs[('supervision.photo', cls.co_b)].filtered(lambda p: p.project_id == cls.p_b)
        cls.estimate_b = cls.docs[('payment.estimate', cls.co_b)].filtered(lambda e: e.project_id == cls.p_b)

    def _env(self, user):
        return self._env_of(user)

    # ── 1. 精靈 ───────────────────────────────────────────────────────────
    def test_business_wizards_denied_self_service_kept(self):
        """有建立 ACL 的每個暫存模型：業務精靈規則拒，帳號自助四種不拒；監造方對照不受影響。"""
        Access = self.env['ir.model.access']
        transient = [n for n in sorted(self.env.registry) if self.env[n]._transient and not self.env[n]._abstract]
        for user in self.restricted:
            env = self._env(user)
            creatable = [n for n in transient if Access.with_user(user).check(n, 'create', raise_exception=False)]
            self.assertTrue(creatable, f'{user.login}：應列得出有建立 ACL 的精靈（否則下面恆真）')
            for name in creatable:
                domain = env['ir.rule']._compute_domain(name, 'create')
                if name in EXPECT_SELF_SERVICE:
                    self.assertNotEqual(domain, DENIED, f'{user.login} {name}：帳號自助精靈不可被拒')
                else:
                    self.assertEqual(domain, DENIED, f'{user.login} {name}：業務精靈要拒建')
            # 內部帳號（營造廠主管、控台讀取）的業務精靈很多（抗辯實測 48 種），前台營造帳號只有照片下載兩種
            business = [n for n in creatable if n not in EXPECT_SELF_SERVICE]
            self.assertTrue(business, f'{user.login}：應有業務精靈可驗')
        sup_env = self._env(self.sup)
        self.assertNotEqual(sup_env['ir.rule']._compute_domain('supervision.folder.upload.wizard', 'create'), DENIED)

    def test_folder_upload_wizard_rejected_supervision_ok(self):
        """skeptic F1／red-team F5：營造廠主管建資料夾上傳精靈（勾別家照片的附件）被拒，附件沒被改；監造方照常。"""
        att = self.photo_b.attachment_id
        before = (att.res_model, att.res_id)
        vals = {'project_id': self.p_a.id, 'folder_id': self.folder_a.id, 'attachment_ids': [(6, 0, att.ids)]}
        # 帶別家附件：關聯 id 守衛（線 H，所有帳號）與精靈拒建（本線）都會擋，這裡只驗「被擋、附件沒被改」
        for user in (self.mgr_a, self.console):
            with self.assertRaises(AccessError):
                self._env(user)['supervision.folder.upload.wizard'].create(vals)
        self.assertEqual((att.res_model, att.res_id), before, '附件歸屬不可被改')
        # 單獨驗本線的精靈拒建（守衛沒有東西可擋），訊息是範圍規則的。不能用「不帶關聯值的 create」：folder_id 必填，
        # create() 先 INSERT 再查權限，INSERT 就撞 NOT NULL（乾淨庫實測 NotNullViolation）。改成：以受限帳號本人為建立者
        # 放進一筆精靈（sudo 只用來越過必填與守衛），再跑 create() 在 INSERT 之後對新紀錄做的同一道檢查
        # （odoo/models.py _create 的 records.check_access('create')）。建立者是本人，「精靈只看自己建的」那條擋不到它，
        # 擋下的只會是精靈拒建
        for user, note in ((self.mgr_a, DENY_NOTE_CONTRACTOR), (self.console, DENY_NOTE_CONSOLE)):
            own = self._env(user)['supervision.folder.upload.wizard'].sudo().create(
                {'project_id': self.p_a.id, 'folder_id': self.folder_a.id})
            self.assertEqual(own.create_uid, user, '前提：建立者是受限帳號本人')
            with self.assertRaises(AccessError) as ctx:
                own.with_env(self._env(user)).check_access('create')
            self.assertIn(note, str(ctx.exception), f'{user.login}：精靈拒建應來自範圍規則')
        wizard = self._env(self.sup)['supervision.folder.upload.wizard'].create(
            {'project_id': self.p_a.id, 'folder_id': self.folder_a.id})
        self.assertEqual(wizard.folder_path, self.folder_a.complete_name, '監造方照常建精靈')

    def test_wizard_related_read_attack_blocked(self):
        """red-team F2：建估驗精靈指向別家估驗、讀 related 單價 → 建立就被拒；監造方照常讀得到。"""
        line_b = self.lines[('payment.estimate.line', self.co_b)].filtered(lambda l: l.estimate_id == self.estimate_b)[:1]
        self.assertTrue(line_b, '前提：B 的估驗有明細')
        env = self._env(self.mgr_a)
        with self.assertRaises(AccessError):
            env['estimate.manual.amount.wizard'].create({'estimate_id': self.estimate_b.id})
        sup_env = self._env(self.sup)
        wizard = sup_env['estimate.manual.amount.wizard'].create({'estimate_id': self.estimate_b.id})
        line = sup_env['estimate.manual.amount.wizard.line'].create(
            {'wizard_id': wizard.id, 'estimate_line_id': line_b.id})
        self.assertEqual(line.unit_price, line_b.unit_price, '監造方照常讀到明細單價')
        # 別人（監造方）建的精靈：受限帳號讀不到（related 以 sudo 算，讀得到就等於讀到別家單價）
        with self.assertRaises(AccessError):
            env['estimate.manual.amount.wizard.line'].browse(line.id).read(['unit_price'])
        self.assertEqual(env['estimate.manual.amount.wizard.line'].search_count([('id', '=', line.id)]), 0)

    def test_self_service_wizards_still_creatable(self):
        """帳號自助精靈：營造廠主管、控台讀取帳號照常建立（啟用兩步驟驗證完整流程見 test_account_setup）。"""
        for user in (self.mgr_a, self.console):
            env = self._env(user)
            env['res.users.apikeys.description'].create({'name': 'DASH 金鑰'})
            env['res.users.identitycheck'].create({'password': 'x'})
            env['change.password.own'].create({'new_password': 'x', 'confirm_password': 'x'})
            env['auth_totp.wizard'].create({'user_id': user.id, 'secret': SECRET_B32})

    # ── 2. 自訂方法閘門（判定） ─────────────────────────────────────────────
    def test_gate_custom_methods_denied_for_restricted_only(self):
        for model, method in CUSTOM_METHODS:
            for user in self.restricted:
                self.assertTrue(gate_verdict(self._env(user), model, method), f'{user.login} {model}.{method} 要被拒')
            self.assertEqual(gate_verdict(self._env(self.sup), model, method), [],
                             f'監造方 {model}.{method} 不受閘門影響')

    def test_gate_allows_read_api_writes_dashboard_and_core_methods(self):
        for model, method in OVERRIDDEN_BUT_ALLOWED:
            # 前提：確實被自訂模組覆寫（不然「放行」不代表名單有作用）
            self.assertTrue(custom_implementations(self.env.registry[model], method), f'{model}.{method} 前提')
        for model, method in OVERRIDDEN_BUT_ALLOWED + EXPECT_DASHBOARD_METHODS + CORE_ONLY_METHODS:
            self.assertTrue(hasattr(type(self.env[model]), method), f'{model}.{method} 不存在（名單過時）')
            for user in self.restricted:
                self.assertEqual(gate_verdict(self._env(user), model, method), [],
                                 f'{user.login} {model}.{method} 應放行')

    def test_gate_allows_release_notices_only_those_two(self):
        """更新公告（construction_release 只裝在部分庫）：啟動時讀公告、按「知道了」放行；同模型其他自訂方法照擋。"""
        if 'construction.release' not in self.env.registry:
            self.skipTest('construction_release 沒裝：本庫沒有更新公告')
        for method in ('get_startup_notices', 'mark_announcements_read'):
            for user in self.restricted:
                self.assertEqual(gate_verdict(self._env(user), 'construction.release', method), [],
                                 f'{user.login} construction.release.{method} 應放行')
        # 反證：同模型其他自訂公開方法仍被擋（放行只限這兩支）
        others = [name for name in dir(type(self.env['construction.release']))
                  if not name.startswith('_') and name not in ('get_startup_notices', 'mark_announcements_read')
                  and callable(getattr(type(self.env['construction.release']), name, None))
                  and custom_implementations(self.env.registry['construction.release'], name)]
        self.assertTrue(others, '前提：construction.release 還有別的自訂公開方法')
        self.assertTrue(gate_verdict(self._env(self.mgr_a), 'construction.release', others[0]),
                        f'construction.release.{others[0]} 應被閘門擋')

    def test_gate_custom_module_by_source(self):
        """自訂＝來源不在 Odoo 官方 addons 目錄：本專案、第三方都算；官方不算。"""
        for module in ('construction_photo', 'construction_company_dashboard', 'base_geoengine'):
            self.assertTrue(is_custom_module(module), module)
        for module in ('base', 'web', 'mail', 'auth_totp', 'project'):
            self.assertFalse(is_custom_module(module), module)

    def test_gate_denial_message_and_warning(self):
        env = self._env(self.mgr_a)
        with self.assertLogs('odoo.addons.construction_company_dashboard.models.method_gate', 'WARNING') as logs:
            with self.assertRaises(AccessError) as ctx:
                check_method_call(env, 'supervision.folder.upload.wizard', 'action_upload', 'test')
        self.assertIn(GATE_NOTE, str(ctx.exception))
        self.assertIn('請洽監造單位', str(ctx.exception))
        self.assertIn('dash_mgr_a', logs.output[0])
        self.assertIn('supervision.folder.upload.wizard.action_upload', logs.output[0])
        # 監造方：不丟、不記
        check_method_call(self._env(self.sup), 'supervision.folder.upload.wizard', 'action_upload', 'test')

    def _server_action(self, name, module=None):
        action = self.env['ir.actions.server'].create({
            'name': name, 'model_id': self.env.ref('base.model_ir_filters').id, 'state': 'code',
            'code': "action = {'type': 'ir.actions.act_window_close'}"})
        if module:
            self.env['ir.model.data'].create({'module': module, 'name': f'dash_test_{action.id}',
                                              'model': 'ir.actions.server', 'res_id': action.id})
        return action

    def test_server_actions_from_custom_modules_denied(self):
        """伺服器動作也是呼叫自訂方法的路：受限帳號只能執行官方模組定義的；監造方照常。"""
        custom = self._server_action('DASH 自訂模組的動作', 'construction_general')
        ad_hoc = self._server_action('DASH 畫面上建的動作')
        official = self._server_action('DASH 官方模組的動作（夾具）', 'base')
        # 動作掛在受限帳號有寫入 ACL 的模型上（核心對沒設群組的動作只查這個）
        ctx = {'active_model': 'ir.filters'}
        for user in (self.mgr_a, self.console):
            env = self._env(user)
            for action in (custom, ad_hoc):
                with self.assertRaises(AccessError, msg=f'{user.login} {action.name}') as cm:
                    env['ir.actions.server'].browse(action.id).with_context(**ctx).run()
                self.assertIn(GATE_NOTE, str(cm.exception))
            self.assertEqual(env['ir.actions.server'].browse(official.id).with_context(**ctx).run(),
                             {'type': 'ir.actions.act_window_close'}, f'{user.login}：官方模組的動作照舊')
        sup_env = self._env(self.sup)
        self.assertEqual(sup_env['ir.actions.server'].browse(custom.id).with_context(**ctx).run(),
                         {'type': 'ir.actions.act_window_close'}, '監造方照常')

    # ── 3. 公開頻道 ───────────────────────────────────────────────────────
    def _public_channel(self, name):
        return self.env['discuss.channel'].create({
            'name': name, 'channel_type': 'channel',
            'group_ids': [(6, 0, self.env.ref('base.group_user').ids)]})

    def _is_member(self, channel, user):
        return bool(self.env['discuss.channel.member'].search_count(
            [('channel_id', '=', channel.id), ('partner_id', '=', user.partner_id.id)]))

    def test_restricted_not_auto_joined_and_removed(self):
        channel = self._public_channel('DASH 全員頻道')
        self.assertTrue(self._is_member(channel, self.sup), '前提：監造方自動加入')
        for user in (self.mgr_a, self.console):
            self.assertFalse(self._is_member(channel, user), f'{user.login} 不可自動加入公開頻道')
        # 新建的營造廠主管也不會被加入
        new_mgr = self._user('dash_mgr_new', [MANAGER_GROUP], company=self.co_s,
                             companies=self.co_s | self.co_a, scope=self.co_a)
        self.assertFalse(self._is_member(channel, new_mgr))
        # 既有成員資格（升級前就在裡面）：升級時移除；私訊不動；監造方不動
        self.env['discuss.channel.member'].create({'channel_id': channel.id, 'partner_id': self.mgr_a.partner_id.id})
        chat = self._env(self.mgr_a)['discuss.channel'].channel_get([self.mgr_a.partner_id.id])
        removed = self.env['res.users']._dash_remove_restricted_channel_memberships()
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(self._is_member(channel, self.mgr_a), '升級時移出公開頻道')
        self.assertTrue(self._is_member(chat, self.mgr_a), '私訊照舊')
        self.assertTrue(self._is_member(channel, self.sup), '監造方照舊')

    def test_employee_becoming_manager_leaves_public_channels(self):
        channel = self._public_channel('DASH 轉任頻道')
        eng = self._user('dash_conv_eng', ['base.group_user', 'construction_supervision_base.group_engineering_manager'],
                         company=self.co_s, companies=self.co_s)
        emp = self._user('dash_conv_emp', ['base.group_user'], company=self.co_s, companies=self.co_s | self.co_a,
                         scope=None)
        self.assertTrue(self._is_member(channel, emp), '前提：一般員工自動加入')
        emp.sudo().write({'dash_scope_company_id': self.co_a.id})
        emp.with_user(eng).action_set_contractor_manager()
        self.assertFalse(self._is_member(channel, emp), '改設為營造廠主管後移出公開頻道')

    def test_public_channel_hidden_and_read_only(self):
        channel = self._public_channel('DASH 內部頻道')
        msg = channel.with_user(self.sup).message_post(body='DASH 監造內部討論', message_type='comment',
                                                        subtype_xmlid='mail.mt_comment')
        for user in self.restricted:
            env = self._env(user)
            self.assertNotIn(channel.id, env['discuss.channel'].search([]).ids, f'{user.login} 看不到公開頻道')
            with self.assertRaises(AccessError):
                env['discuss.channel'].browse(channel.id).read(['name'])
            with self.assertRaises(AccessError):
                env['discuss.channel'].browse(channel.id).write({'description': 'x'})
            self.assertFalse(env['mail.message'].search([('id', '=', msg.id)]), f'{user.login} 讀不到頻道訊息')
            self.assertFalse(env['discuss.channel.member'].search([('channel_id', '=', channel.id)]),
                             f'{user.login} 讀不到成員名單')
            if user.has_group('base.group_user'):
                with self.assertRaises(AccessError):
                    env['discuss.channel'].create({'name': 'DASH 營造方開的公開頻道', 'channel_type': 'channel'})
                with self.assertRaises(AccessError):
                    env['discuss.channel.member'].create(
                        {'channel_id': channel.id, 'partner_id': user.partner_id.id})
        sup_env = self._env(self.sup)
        self.assertIn(channel.id, sup_env['discuss.channel'].search([]).ids, '監造方照常看得到')
        self.assertTrue(sup_env['mail.message'].search([('id', '=', msg.id)]))

    # ── 4. 內部備註 ───────────────────────────────────────────────────────
    def test_internal_notes_hidden_comments_and_tracking_kept(self):
        project = self.p_a.with_user(self.sup)
        note = project.message_post(body='DASH 內部評語', message_type='comment', subtype_xmlid='mail.mt_note')
        comment = project.message_post(body='DASH 一般訊息', message_type='comment', subtype_xmlid='mail.mt_comment')
        log = self.p_a._message_log(body='DASH 追蹤紀錄')
        self.assertTrue(note.subtype_id.internal and log.is_internal, '前提：備註與追蹤紀錄都是內部的')
        domain = [('model', '=', 'project.project'), ('res_id', '=', self.p_a.id)]
        mgr_env = self._env(self.mgr_a)
        seen = set(mgr_env['mail.message'].search(domain).ids)
        self.assertIn(comment.id, seen, '一般訊息照常')
        self.assertIn(log.id, seen, '追蹤紀錄照常')
        self.assertNotIn(note.id, seen, '內部備註看不到')
        with self.assertRaises(AccessError):
            mgr_env['mail.message'].browse(note.id).read(['body'])
        # 監造方（兩個方向：自己的內部備註仍看得到）
        self.assertTrue({note.id, comment.id, log.id} <= set(self._env(self.sup)['mail.message'].search(domain).ids))

    def test_message_search_without_domain_does_not_crash(self):
        """red-team F10：受限帳號 search_count([]) 不可因讀不到的來源單據（行事曆 _get_mail_message_access 讀欄位）出錯。"""
        if 'calendar.event' not in self.env:
            self.skipTest('沒裝 calendar：這個情境不存在')
        event = self.env['calendar.event'].create({'name': 'DASH 監造內部會議', 'start': fields.Datetime.now(),
                                                   'stop': fields.Datetime.now() + timedelta(hours=1)})
        event.message_post(body='DASH 會議訊息', message_type='comment', subtype_xmlid='mail.mt_comment')
        for user in self.restricted:
            env = self._env(user)
            count = env['mail.message'].search_count([])
            self.assertIsInstance(count, int)
            self.assertFalse(env['mail.message'].search([('model', '=', 'calendar.event'), ('res_id', '=', event.id)]))

    # ── 5. 共用篩選 ───────────────────────────────────────────────────────
    def test_shared_filters_only_own(self):
        shared = self.env['ir.filters'].create({'name': 'DASH 全體篩選', 'model_id': 'project.project',
                                                'user_id': False, 'domain': '[]'})
        for user in (self.mgr_a, self.console):
            env = self._env(user)
            with self.assertRaises(AccessError, msg=user.login):
                env['ir.filters'].create({'name': 'DASH 營造方全體預設', 'model_id': 'project.project',
                                          'user_id': False, 'is_default': True, 'domain': "[('id', '=', 0)]"})
            with self.assertRaises(AccessError, msg=user.login):
                env['ir.filters'].browse(shared.id).write({'domain': "[('id', '=', 0)]"})
            with self.assertRaises(AccessError, msg=user.login):
                env['ir.filters'].browse(shared.id).unlink()
            own = env['ir.filters'].create({'name': 'DASH 自己的', 'model_id': 'project.project', 'user_id': user.id})
            own.write({'domain': '[]'})
            own.unlink()
            self.assertIn(shared.id, env['ir.filters'].search([]).ids, '全體篩選照常讀得到（套用）')
        self.assertEqual(shared.domain, '[]')
        self._env(self.sup)['ir.filters'].create({'name': 'DASH 監造方全體', 'model_id': 'project.project',
                                                  'user_id': False, 'domain': '[]'})

    # ── 6. 回填歸屬 ───────────────────────────────────────────────────────
    def test_refill_requires_write_access(self):
        co_s2 = self.env['res.company'].create({'name': 'DASH 監造 S2', 'company_type': 'supervision'})
        sup2 = self._user('dash_sup2', ['base.group_user', SUPERVISOR_ADMIN], company=co_s2, companies=co_s2)
        self.assertTrue(sup2._is_supervision_side(), '前提：另一家監造公司的監造方')
        with self.assertRaises(AccessError):
            self._env(sup2)['project.project'].browse(self.p_a.id).action_dash_refill_attribution()
        res = self._env(self.sup)['project.project'].browse(self.p_a.id).action_dash_refill_attribution()
        self.assertEqual(res['tag'], 'display_notification', '自家工程照常重算')

    # ── 7. 歸屬約束不擋監造方 ─────────────────────────────────────────────
    def _photo_vals_uploaded_by(self, user, project):
        """照片的最少欄位，附件由 user 自己上傳（實際流程）。共用夾具 _doc_vals 的附件是系統帳號建的、
        沒掛單據——只有建立者讀得到，監造方把它掛上照片會被關聯 id 守衛擋（合約 §0b-23）。"""
        att = self._env(user)['ir.attachment'].create({
            'name': 'dash_sup.png', 'datas': PNG_B64, 'mimetype': 'image/png', 'public': False,
            'res_model': 'supervision.photo'})
        return {'project_id': project.id, 'attachment_id': att.id}

    def test_supervision_moves_photo_to_other_project(self):
        """skeptic F2 觸發 1：沒掛單據的照片（歸 A）改到只有 B 的工程 → 成功、依新工程重算成 B；
        改到不含 A 的多家工程 → 留空；改到仍含 A 的工程 → 保留 A。"""
        co_d = self.env['res.company'].create({'name': 'DASH 營造 D', 'company_type': 'contractor'})
        p_bd = self._project('DASH-PBD', 'general', [(6, 0, (self.co_b | co_d).ids)])
        Photo = self._env(self.sup)['supervision.photo']
        photo = Photo.create(dict(self._photo_vals_uploaded_by(self.sup, self.p_shared), contractor_company_id=self.co_a.id))
        photo.write({'project_id': self.p_a.id})
        self.assertEqual(photo.contractor_company_id, self.co_a, '仍含 A → 保留')
        photo.write({'project_id': self.p_b.id})
        self.assertEqual(photo.contractor_company_id, self.co_b, '只有 B → 依新工程重算成 B')
        photo.write({'contractor_company_id': self.co_b.id, 'project_id': p_bd.id})
        self.assertEqual(photo.contractor_company_id, self.co_b, '同時指定 → 照指定')
        photo2 = Photo.create(dict(self._photo_vals_uploaded_by(self.sup, self.p_a), contractor_company_id=self.co_a.id))
        photo2.write({'project_id': p_bd.id})
        self.assertFalse(photo2.contractor_company_id, '多家且不含 A → 留空（由監造方補）')
        # 監造方明確寫一家不在工程內的營造廠：照樣擋
        with self.assertRaises(ValidationError):
            photo2.write({'contractor_company_id': self.co_a.id})

    def test_supervision_adds_photo_after_contractor_removed(self):
        """skeptic F2 觸發 2：營造廠 A 移出共用工程後，監造方替 A 的舊缺失補照片 → 成功、照片跟著缺失歸 A；
        有人重存同一個工程，舊單據的歸屬不被改給剩下的那一家。"""
        defect = self.docs[('general.defect.improvement', self.co_a)].filtered(lambda d: d.project_id == self.p_shared)
        log = self.docs[('daily.log.sheet', self.co_a)].filtered(lambda d: d.supervision_project_id == self.p_shared)
        self.p_shared.write({'contractor_company_ids': [(3, self.co_a.id)]})
        Photo = self._env(self.sup)['supervision.photo']
        photo = Photo.create(dict(self._photo_vals_uploaded_by(self.sup, self.p_shared), general_defect_id=defect.id))
        self.assertEqual(photo.contractor_company_id, self.co_a, '照片跟著缺失')
        defect.with_user(self.sup).write({'project_id': self.p_shared.id})
        log.with_user(self.sup).write({'supervision_project_id': self.p_shared.id})
        self.assertEqual(defect.contractor_company_id, self.co_a, '寫回同一個工程不重算')
        self.assertEqual(log.contractor_company_id, self.co_a)
        # 新單據明確寫已移出的營造廠：照樣擋
        with self.assertRaises(ValidationError):
            self.env['general.defect.improvement'].create(dict(
                self._doc_vals('general.defect.improvement', self.p_shared), contractor_company_id=self.co_a.id))

    def test_contractor_still_cannot_move_document_to_other_contractor(self):
        """營造方（前台 sudo）把自家單據改到沒承攬的工程：照舊被約束擋下（不能藉改工程把資料移給別家）。"""
        defect = self.docs[('general.defect.improvement', self.co_a)].filtered(lambda d: d.project_id == self.p_shared)
        with self.assertRaises(ValidationError):
            self.env(user=self.portal_a)['general.defect.improvement'].sudo().browse(defect.id).write(
                {'project_id': self.p_b.id})
        self.assertEqual(defect.contractor_company_id, self.co_a)

    # ── 9. 控台讀取帳號在前台 ─────────────────────────────────────────────
    def test_console_reader_restricted_in_portal(self):
        ctrl = ConstructionPortal()
        photos = self.env['supervision.photo'].sudo().browse(self.docs[('supervision.photo', self.co_a)].ids)
        with MockRequest(self.env(user=self.console)):
            self.assertTrue(ctrl._dash_is_contractor(), '控台讀取帳號走受限帳號那條路')
            self.assertFalse(ctrl._user_can_see_project(self.p_a), '前台看不到任何工程')
            self.assertFalse(ctrl._dash_visible(photos), 'sudo 查出的照片以本人身分再過規則 → 看不到')
        self.assertEqual(self.env['project.project'].with_user(self.console)._get_portal_projects_domain(
            self.console.partner_id), DENIED)
        # 對照：監造方照常
        with MockRequest(self.env(user=self.sup)):
            self.assertFalse(ctrl._dash_is_contractor())
            self.assertTrue(ctrl._user_can_see_project(self.p_a))
            self.assertEqual(ctrl._dash_visible(photos), photos)
