# -*- coding: utf-8 -*-
"""呼叫端給的關聯 id 不能拿來以 sudo 讀資料（合約 §0b-23，線 H；models/relational_input_guard.py）。

情境比照 jt：兩家監造公司共用一庫（各自的內部帳號只有自己的公司），再加一個前台營造帳號。
核心的工程／工項多公司規則讓 A 公司的人讀不到 B 公司的工程，於是「把 B 的工程 id 填進 A 的精靈」
在修之前會以 sudo 帶出 B 的工程名稱（11-06 抗辯 F2 同形）。

鎖住：
1. 守衛欄位清單：印出規模、與手寫期望比（含反例：不是每個關聯欄位都守）。
2. create／onchange／write／x2many 指令／預設值（context、ir.default）／值的各種格式 → 讀不到就 AccessError，
   訊息指出是哪個欄位；每支附「正當用法仍然成功」的對照（L4⑤）。
3. write 只查改變了的值（現值是別人設的、本人讀不到，寫回同一個 id 照常成功）。
4. env.su 不查；呼叫端偽造複製憑證無效。
5. 資料夾上傳精靈（F5／skeptic F1）：別人單據上的附件、別人上傳的附件不能被搬走；自己剛上傳的照常。
6. mail.resend.partner（F6）：讀不到的通知不能拿來帶出收件人。
"""
import logging

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_supervision_base.models.relational_input_guard import (
    COPY_CTX, guarded_fields_of)

_logger = logging.getLogger(__name__)

SUPERVISOR_ADMIN = 'construction_supervision_base.group_supervisor_admin'   # 工程後台使用者
PORTAL_LEADER = 'construction_supervision_base.group_portal_leader'         # 前台主管
GUARD_MSG = '沒有讀取權限的紀錄'
XML_STUB = 'eA=='

# 手寫期望（至少要有這些；清單是 registry 算出來的，這裡防「算法壞掉變少」）
EXPECTED_GUARDED = {
    ('tender.import.wizard', 'project_id'): {'project_name'},
    ('supervision.folder.upload.wizard', 'folder_id'): {'folder_path'},
    ('mail.resend.partner', 'notification_id'): {'partner_id', 'failure_reason'},
    ('ir.attachment', 'folder_id'): {'folder_path'},
    ('project.task', 'project_id'): {'company_id'},
}
# 反例：不以 sudo 計算的關聯欄位不守（防「算法壞掉變成每個關聯欄位都守」）
EXPECTED_NOT_GUARDED = {
    ('supervision.folder.upload.wizard', 'attachment_ids'),   # 沒有任何 sudo 欄位依賴它
    ('mail.resend.partner', 'partner_id'),                    # name／email 是 related_sudo=False
}


class GuardCase(TransactionCase):
    """兩家監造公司（jt 情境）＋前台營造帳號的共用夾具。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Company = env['res.company']
        cls.co_sa = Company.create({'name': 'H 監造 A', 'company_type': 'supervision'})
        cls.co_sb = Company.create({'name': 'H 監造 B', 'company_type': 'supervision'})
        cls.co_c = Company.create({'name': 'H 營造 C', 'company_type': 'contractor'})
        cls.sup_a = cls._user('h_sup_a', [SUPERVISOR_ADMIN], cls.co_sa, cls.co_sa)
        cls.sup_b = cls._user('h_sup_b', [SUPERVISOR_ADMIN], cls.co_sb, cls.co_sb)
        cls.portal_c = cls._user('h_portal_c', [PORTAL_LEADER], cls.co_c, cls.co_c | cls.co_sa,
                                 extra={'is_contractor_org': True, 'dash_scope_company_id': cls.co_c.id})
        Project = env['project.project']
        cls.p_a = Project.create({'name': 'H 工程 A', 'code': 'H-GUARD-A', 'company_id': cls.co_sa.id,
                                  'state': 'construction', 'contractor_company_ids': [(6, 0, cls.co_c.ids)]})
        cls.p_b = Project.create({'name': 'H 工程 B', 'code': 'H-GUARD-B', 'company_id': cls.co_sb.id,
                                  'state': 'construction'})
        cls.p_b2 = Project.create({'name': 'H 工程 B2', 'code': 'H-GUARD-B2', 'company_id': cls.co_sb.id,
                                   'state': 'construction'})
        env['supervision.project.member'].create({'project_id': cls.p_a.id, 'user_id': cls.portal_c.id})
        Task = env['project.task']
        cls.t_a = Task.create(cls._task_vals('H 工項 A', cls.p_a))
        cls.t_b = Task.create(cls._task_vals('H 工項 B', cls.p_b))
        Att = env['ir.attachment']
        # 掛在 B 工程上的附件（A 的人讀不到：附件權限跟著它掛的單據）
        cls.att_pb = Att.create({'name': 'h_pb.txt', 'raw': b'B secret', 'res_model': 'project.project',
                                 'res_id': cls.p_b.id})
        cls.att_pa = Att.create({'name': 'h_pa.txt', 'raw': b'A data', 'res_model': 'project.project',
                                 'res_id': cls.p_a.id})
        # 沒掛單據、建立者是系統的附件：只有建立者與系統管理員讀得到
        cls.att_orphan = Att.create({'name': 'h_orphan.txt', 'raw': b'orphan secret'})

    @classmethod
    def _user(cls, login, groups, company, companies, extra=None):
        vals = {'name': login, 'login': login, 'company_id': company.id,
                'company_ids': [(6, 0, companies.ids)],
                'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])]}
        vals.update(extra or {})
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)

    @staticmethod
    def _task_vals(name, project):
        return {'name': name, 'project_id': project.id, 'item_no': '1', 'unit': '式',
                'planned_qty': 1.0, 'unit_price': 1.0}

    def _as(self, user, model):
        # 允許公司＝帳號自己的全部公司（跟登入後的預設一樣）
        return self.env[model].with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def assertGuardBlocks(self, fname, func, *args, **kwargs):
        """斷言被「這個守衛」以 AccessError 擋下，而且訊息指名欄位（不是別的權限檢查碰巧先擋，M-B）。"""
        with self.assertRaises(AccessError) as caught:
            func(*args, **kwargs)
        message = str(caught.exception)
        self.assertIn(GUARD_MSG, message, f'應是關聯 id 守衛擋下，實際訊息：{message}')
        self.assertIn(f'（{fname}）', message, f'訊息要指名欄位 {fname}：{message}')
        return message


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestGuardedFieldList(GuardCase):

    def test_guarded_field_list_matches_expectation(self):
        listing = {}
        for name in sorted(self.env.registry):
            guarded = guarded_fields_of(self.env[name])
            if guarded:
                listing[name] = guarded
        n_fields = sum(len(g) for g in listing.values())
        _logger.info('relational_input_guard：%s 個模型有守衛欄位，共 %s 個欄位', len(listing), n_fields)
        for (model, fname), computed in EXPECTED_GUARDED.items():
            self.assertIn(fname, listing.get(model, {}), f'{model}.{fname} 應在守衛欄位清單')
            self.assertTrue(computed <= set(listing[model][fname]),
                            f'{model}.{fname} 應帶出 {computed}，清單是 {listing[model][fname]}')
        for model, fname in EXPECTED_NOT_GUARDED:
            self.assertNotIn(fname, listing.get(model, {}), f'{model}.{fname} 不以 sudo 計算，不應在清單')
        self.assertGreater(len(listing), len({m for m, _f in EXPECTED_GUARDED}))

    def test_list_is_cached_per_registry(self):
        model = self.env['tender.import.wizard']
        self.assertTrue(self.env.registry.ready)
        self.assertIs(guarded_fields_of(model), guarded_fields_of(model), '準備好的 registry 上只算一次')


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestRelationalInputGuard(GuardCase):

    def test_rig_targets_are_unreadable(self):
        """夾具前提：A 的人直接讀 B 的工程、工項、附件都被擋；讀自己的照常（否則下面的測試證明不了什麼）。"""
        for record in (self.p_b, self.t_b, self.att_pb, self.att_orphan):
            with self.assertRaises(AccessError):
                record.with_user(self.sup_a).with_context(allowed_company_ids=self.co_sa.ids).read(['display_name'])
        self.assertEqual(self._as(self.sup_a, 'project.project').browse(self.p_a.id).name, 'H 工程 A')
        self.assertEqual(self._as(self.sup_b, 'project.project').browse(self.p_b.id).name, 'H 工程 B')

    # ── create ───────────────────────────────────────────────────────────
    def test_create_with_unreadable_project_is_blocked_both_companies(self):
        for user, foreign, own in ((self.sup_a, self.p_b, self.p_a), (self.sup_b, self.p_a, self.p_b)):
            Wizard = self._as(user, 'tender.import.wizard')
            self.assertGuardBlocks('project_id', Wizard.create, {'project_id': foreign.id, 'xml_file': XML_STUB})
            wizard = Wizard.create({'project_id': own.id, 'xml_file': XML_STUB})
            self.assertEqual(wizard.project_name, own.name, '正當用法：自己的工程照常帶出名稱')

    def test_value_formats_do_not_bypass(self):
        Wizard = self._as(self.sup_a, 'tender.import.wizard')
        for value in (str(self.p_b.id), (self.p_b.id, 'x'), [self.p_b.id], float(self.p_b.id)):
            self.assertGuardBlocks('project_id', Wizard.create, {'project_id': value, 'xml_file': XML_STUB})
        spec = {'project_id': {}, 'project_name': {}}
        self.assertGuardBlocks('project_id', Wizard.onchange, {'project_id': {'id': self.p_b.id}},
                               ['project_id'], spec)

    def test_portal_contractor_blocked(self):
        """前台營造帳號：讀不到的工程填進精靈的 onchange（不需要建立權）→ 擋。"""
        Wizard = self._as(self.portal_c, 'tender.import.wizard')
        spec = {'project_id': {}, 'project_name': {}}
        self.assertGuardBlocks('project_id', Wizard.onchange, {'project_id': self.p_b.id}, ['project_id'], spec)

    # ── onchange ─────────────────────────────────────────────────────────
    def test_onchange_new_record(self):
        Wizard = self._as(self.sup_a, 'tender.import.wizard')
        spec = {'project_id': {}, 'project_name': {}}
        self.assertGuardBlocks('project_id', Wizard.onchange, {'project_id': self.p_b.id}, ['project_id'], spec)
        result = Wizard.onchange({'project_id': self.p_a.id}, ['project_id'], spec)
        self.assertEqual(result['value'].get('project_name'), 'H 工程 A', '正當用法：onchange 照常帶出')

    def test_caller_controlled_defaults(self):
        """核心在 create／onchange 裡才補預設值：context 的 default_<欄位> 與 ir.default 都是呼叫端控制得到的。"""
        spec = {'project_id': {}, 'project_name': {}}
        Wizard = self._as(self.sup_a, 'tender.import.wizard')
        foreign = Wizard.with_context(default_project_id=self.p_b.id)
        self.assertGuardBlocks('project_id', foreign.create, {'xml_file': XML_STUB})
        self.assertGuardBlocks('project_id', foreign.onchange, {}, [], spec)
        own = Wizard.with_context(default_project_id=self.p_a.id)
        self.assertEqual(own.create({'xml_file': XML_STUB}).project_name, 'H 工程 A')
        # ir.default（使用者自己的預設值）
        field = self.env['ir.model.fields']._get('tender.import.wizard', 'project_id')
        self.env['ir.default'].create({'field_id': field.id, 'user_id': self.sup_a.id,
                                       'json_value': str(self.p_b.id)})
        self.assertGuardBlocks('project_id', Wizard.onchange, {}, [], spec)

    # ── write：只查改變了的值 ────────────────────────────────────────────
    def test_write_checks_only_changed_values(self):
        Wizard = self._as(self.sup_a, 'tender.import.wizard')
        wizard = Wizard.create({'project_id': self.p_a.id, 'xml_file': XML_STUB})
        self.assertGuardBlocks('project_id', wizard.write, {'project_id': self.p_b.id})
        # 現值是別人設的（這裡用 SQL 模擬）、本人讀不到：寫回同一個 id 照常成功，換成另一個讀不到的照擋
        self.env.cr.execute('UPDATE tender_import_wizard SET project_id = %s WHERE id = %s', [self.p_b.id, wizard.id])
        wizard.invalidate_recordset(['project_id'])
        wizard.write({'project_id': self.p_b.id, 'xml_file': XML_STUB})
        self.assertGuardBlocks('project_id', wizard.write, {'project_id': self.p_b2.id})
        wizard.write({'project_id': self.p_a.id})
        self.assertEqual(wizard.project_name, 'H 工程 A', '正當用法：改成自己的工程照常')

    # ── x2many 指令 ──────────────────────────────────────────────────────
    def test_x2many_commands(self):
        # 工程管理員：對工項有寫入權（正當用法那兩行才寫得進去；被擋的那幾行訊息指名欄位，不是 ACL 先擋）
        manager = self._user('h_sup_pm_x2m', [SUPERVISOR_ADMIN, 'project.group_project_manager'],
                             self.co_sa, self.co_sa)
        project = self._as(manager, 'project.project').browse(self.p_a.id)
        cases = {
            'LINK 讀不到的工項': [Command.link(self.t_b.id)],
            'SET 混進讀不到的工項': [Command.set([self.t_a.id, self.t_b.id])],
            'UPDATE 讀不到的工項': [Command.update(self.t_b.id, {})],
        }
        for label, commands in cases.items():
            with self.subTest(label):
                self.assertGuardBlocks('task_ids', project.write, {'task_ids': commands})
        # CREATE／UPDATE 的巢狀 vals 遞迴到子模型：工項的 parent_id 是守衛欄位
        nested = self._task_vals('H 巢狀', self.p_a)
        nested['parent_id'] = self.t_b.id
        self.assertGuardBlocks('parent_id', project.write, {'task_ids': [Command.create(nested)]})
        self.assertGuardBlocks('parent_id', project.write,
                               {'task_ids': [Command.update(self.t_a.id, {'parent_id': self.t_b.id})]})
        # 正當用法：已經掛著的照常（SET 同一組）、新建自己的工項照常
        project.write({'task_ids': [Command.set(project.task_ids.ids)]})
        project.write({'task_ids': [Command.create(self._task_vals('H 新工項', self.p_a))]})
        self.assertIn('H 新工項', project.task_ids.mapped('name'))

    def test_onchange_nested_commands(self):
        Project = self._as(self.sup_a, 'project.project')
        spec = {'task_ids': {'fields': {'parent_id': {}, 'name': {}}}}
        values = {'task_ids': [Command.create({'name': 'H 巢狀 onchange', 'parent_id': self.t_b.id})]}
        self.assertGuardBlocks('parent_id', Project.browse(self.p_a.id).onchange, values, ['task_ids'], spec)

    # ── 伺服器端在另一個模型的 create 裡順手建的紀錄 ───────────────────────
    def test_server_side_nested_create_is_not_blocked(self):
        """工程 create 替新工程建分析帳戶，分析方案一般帳號沒有讀取 ACL：值是伺服器挑的，照常建得出工程
        （全模組回歸 TestRpcCreateProject 實測被擋過）。同一組值由呼叫端直接給 → 照擋（證明放行的理由只有「巢狀」）。"""
        creator = self._user('h_sup_pm', [SUPERVISOR_ADMIN, 'project.group_project_manager'], self.co_sa, self.co_sa)
        Plan = self._as(creator, 'account.analytic.plan')
        plan = self.env['account.analytic.plan'].search([], limit=1)
        self.assertTrue(plan, '夾具：庫裡要有分析方案')
        with self.assertRaises(AccessError):
            Plan.search([('id', '=', plan.id)])
        project = self._as(creator, 'project.project').create(
            {'name': 'H 巢狀建立', 'code': 'H-NESTED', 'company_id': self.co_sa.id, 'allow_timesheets': True})
        self.assertTrue(project.sudo().account_id, '前提：建工程時附帶建了分析帳戶（否則這支沒測到巢狀）')
        self.assertGuardBlocks('plan_id', self._as(creator, 'account.analytic.account').create,
                               {'name': 'H 直接建', 'plan_id': project.sudo().account_id.plan_id.id,
                                'company_id': self.co_sa.id})

    # ── env.su 與憑證 ────────────────────────────────────────────────────
    def test_sudo_is_not_checked(self):
        wizard = self._as(self.sup_a, 'tender.import.wizard').sudo().create(
            {'project_id': self.p_b.id, 'xml_file': XML_STUB})
        self.assertEqual(wizard.project_name, 'H 工程 B')

    def test_caller_cannot_forge_copy_token(self):
        Wizard = self._as(self.sup_a, 'tender.import.wizard')
        for value in (True, 1, 'yes', {'x': 1}):
            self.assertGuardBlocks('project_id', Wizard.with_context(**{COPY_CTX: value}).create,
                                   {'project_id': self.p_b.id, 'xml_file': XML_STUB})


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestFolderUploadWizardGuard(GuardCase):
    """資料夾上傳精靈原本以 sudo 改寫勾選附件的歸屬（res_model／res_id），先確認本人有寫入權。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder_a = cls.env['supervision.folder'].create({'name': 'H 資料夾 A', 'project_id': cls.p_a.id})
        cls.folder_b = cls.env['supervision.folder'].create({'name': 'H 資料夾 B', 'project_id': cls.p_b.id})

    def _upload(self, user, folder, attachments):
        wizard = self._as(user, 'supervision.folder.upload.wizard').create({
            'project_id': folder.project_id.id, 'folder_id': folder.id,
            'attachment_ids': [Command.set(attachments.ids)]})
        return wizard.action_upload()

    def _owner(self, attachment):
        self.env.flush_all()
        self.env.cr.execute('SELECT res_model, res_id FROM ir_attachment WHERE id = %s', [attachment.id])
        return self.env.cr.fetchone()

    def test_cannot_take_over_others_attachments(self):
        for user, folder, victim in ((self.sup_a, self.folder_a, self.att_pb),
                                     (self.sup_a, self.folder_a, self.att_orphan),
                                     (self.sup_b, self.folder_b, self.att_pa)):
            with self.subTest(user=user.login, victim=victim.name):
                before = self._owner(victim)
                with self.assertRaises(AccessError):
                    self._upload(user, folder, victim)
                self.assertEqual(self._owner(victim), before, '被擋下時附件歸屬不可改變')

    def test_own_new_upload_still_works(self):
        """正當用法：本人剛上傳（還沒掛單據）的檔照常放進資料夾。"""
        own = self._as(self.sup_a, 'ir.attachment').create({
            'name': 'h_own.txt', 'raw': b'mine', 'res_model': 'supervision.folder.upload.wizard', 'res_id': 0})
        self._upload(self.sup_a, self.folder_a, own)
        self.assertEqual(self._owner(own), ('supervision.folder', self.folder_a.id))
        self.assertEqual(own.sudo().folder_id, self.folder_a)

    def test_portal_contractor_cannot_use_wizard(self):
        own = self._as(self.portal_c, 'ir.attachment').sudo().create({'name': 'h_c.txt', 'raw': b'c'})
        with self.assertRaises(AccessError):
            self._upload(self.portal_c, self.folder_a, own | self.att_pa)


@tagged('post_install', '-at_install', 'construction_supervision_base')
class TestResendPartnerGuard(GuardCase):
    """mail.resend.partner 的 partner_id／failure_reason 是 related notification_id.*（sudo）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.partner_b = env['res.partner'].create({'name': 'H 收件人 B', 'email': 'h_b@example.com',
                                                   'company_id': cls.co_sb.id})
        message = env['mail.message'].create({'model': 'res.partner', 'res_id': cls.partner_b.id,
                                              'body': 'H', 'message_type': 'comment'})
        Notif = env['mail.notification']
        cls.notif_b = Notif.create({'mail_message_id': message.id, 'res_partner_id': cls.partner_b.id,
                                    'notification_type': 'email', 'notification_status': 'exception'})
        cls.notif_own = Notif.create({'mail_message_id': message.id, 'res_partner_id': cls.sup_a.partner_id.id,
                                      'notification_type': 'email', 'notification_status': 'exception'})

    def test_unreadable_notification_is_blocked(self):
        Notif = self._as(self.sup_a, 'mail.notification')
        try:
            Notif.browse(self.notif_b.id).read(['res_partner_id'])
            readable = True
        except AccessError:
            readable = False
        if readable:
            # 新安裝的 mail 模組：mail.notification 對內部帳號不限讀取（ir_rule_mail_notifications_group_user
            # perm_read=False）→ 第一段讀得到，守衛不適用；收件人姓名是第二段，已知殘餘（reports/H.md）
            self.skipTest('此庫 mail.notification 對內部帳號不限讀取：第一段守衛不適用（已知殘餘）')
        Partner = self._as(self.sup_a, 'mail.resend.partner')
        self.assertGuardBlocks('notification_id', Partner.create, {'notification_id': self.notif_b.id})
        own = Partner.create({'notification_id': self.notif_own.id})
        self.assertEqual(own.partner_id, self.sup_a.partner_id, '正當用法：自己的通知照常')
