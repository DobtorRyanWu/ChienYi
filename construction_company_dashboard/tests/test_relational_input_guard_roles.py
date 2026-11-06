# -*- coding: utf-8 -*-
"""11-06 抗辯 F1–F3、F5、F6、F9 的攻擊，對每一種帳號都要擋（合約 §0b-23，線 H；守衛在
construction_supervision_base/models/relational_input_guard.py）。

帳號：營造廠主管（mgr_a，啟用兩步驟驗證）、前台營造帳號（portal_a）、控台讀取帳號（console）、
監造方（sup，監造公司 S）、另一家監造公司的監造方（sup2，監造公司 S2——jt 這種兩家監造公司共用一庫）。
攻擊目標是「該帳號直接讀不到」的紀錄（每支先驗這個前提）；每支附「正當用法仍然成功」的對照（L4⑤）。

斷言：被擋＝AccessError。監造方與非暫存模型的 onchange 另外比對訊息（指名欄位：證明是這道守衛擋的，M-B）；
受限帳號在暫存模型上的建立，線 I 的暫存模型白名單也可能先擋，所以只斷言被擋。
"""
import base64

from odoo import Command, fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

from .test_scope_rules import SUPERVISOR_ADMIN, DashScopeCase

GUARD_MSG = '沒有讀取權限的紀錄'
PHOTO_SPEC = {'attachment_id': {}, 'image': {}}
FORGED_NOTE = 'H dashboard forged audit entry'
SPOOF_VALUES = (True, 1, 'yes')


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestRelationalInputGuardRoles(DashScopeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # jt 情境：第二家監造公司與它的工程、帳號
        cls.co_s2 = env['res.company'].create({'name': 'DASH 監造 S2', 'company_type': 'supervision'})
        cls.sup2 = cls._user('dash_h_sup2', ['base.group_user', SUPERVISOR_ADMIN], company=cls.co_s2,
                             companies=cls.co_s2)
        cls.p_s2 = env['project.project'].create({
            'name': 'DASH-S2 公司儀表板測試工程', 'code': 'DASH-S2', 'project_type': 'general',
            'state': 'construction', 'company_id': cls.co_s2.id})
        cls.task_s2 = env['project.task'].create({'name': 'S2 工項', 'project_id': cls.p_s2.id, 'item_no': '1',
                                                  'unit': '式', 'planned_qty': 1.0, 'unit_price': 1.0})
        for project, number in ((cls.p_a, 'H-CN-A'), (cls.p_b, 'H-CN-B'), (cls.p_s2, 'H-CN-S2')):
            project.contract_no = number
        cls.est_b = cls.docs[('payment.estimate', cls.co_b)][:1]
        cls.est_line_b = cls.lines[('payment.estimate.line', cls.co_b)][:1]
        cls.est_line_a = cls.lines[('payment.estimate.line', cls.co_a)][:1]
        cls.sheet_b = cls.docs[('daily.log.sheet', cls.co_b)][:1]
        cls.photo_a = cls.docs[('supervision.photo', cls.co_a)].filtered(lambda p: p.project_id == cls.p_a)[:1]
        cls.photo_b = cls.docs[('supervision.photo', cls.co_b)].filtered(lambda p: p.project_id == cls.p_b)[:1]
        for photo in cls.photo_a | cls.photo_b:
            photo.attachment_id.res_id = photo.id
        cls.att_s2 = env['ir.attachment'].create({'name': 'S2 契約.pdf', 'raw': b'S2-CONTRACT',
                                                  'res_model': 'project.project', 'res_id': cls.p_s2.id})

    # ── 共用 ────────────────────────────────────────────────────────────
    def _model(self, user, model):
        return self._env_of(user)[model]

    def _readable(self, user, record):
        self.env.invalidate_all()
        try:
            record.with_env(self._env_of(user)).read(['display_name'])
            return True
        except AccessError:
            return False

    def assertBlocked(self, func, *args, field=None, **kwargs):
        self.env.invalidate_all()
        self.env.registry.clear_cache()
        with self.assertRaises(AccessError) as caught:
            func(*args, **kwargs)
        if field:
            message = str(caught.exception)
            self.assertIn(GUARD_MSG, message, f'應是關聯 id 守衛擋下：{message}')
            self.assertIn(f'（{field}）', message, message)

    # ── F3：一般模型新紀錄的 onchange ───────────────────────────────────
    def test_f3_onchange_related_blocked_for_every_role(self):
        spec_est = {'project_id': {}, 'contract_no': {}, 'contract_amount': {}}
        spec_sched = {'project_id': {}, 'start_date': {}, 'approved_duration': {}}
        spec_log = {'supervision_project_id': {}, 'project_id': {}, 'contract_duration': {}}
        cases = ((self.mgr_a, self.p_b, self.p_a), (self.portal_a, self.p_b, self.p_a),
                 (self.console, self.p_a, None), (self.sup2, self.p_a, self.p_s2), (self.sup, self.p_s2, self.p_a))
        for user, foreign, own in cases:
            with self.subTest(user=user.login):
                self.assertFalse(self._readable(user, foreign), f'前提：{user.login} 直接讀不到 {foreign.code}')
                Est = self._model(user, 'payment.estimate')
                self.assertBlocked(Est.onchange, {'project_id': foreign.id}, ['project_id'], spec_est,
                                   field='project_id')
                self.assertBlocked(self._model(user, 'progress.schedule').onchange, {'project_id': foreign.id},
                                   ['project_id'], spec_sched, field='project_id')
                self.assertBlocked(self._model(user, 'daily.log.sheet').onchange,
                                   {'supervision_project_id': foreign.id}, ['supervision_project_id'], spec_log,
                                   field='supervision_project_id')
                if own:
                    self.env.invalidate_all()
                    value = Est.onchange({'project_id': own.id}, ['project_id'], spec_est)['value']
                    self.assertEqual(value.get('contract_no'), own.contract_no, '正當用法：自己看得到的工程照常帶出')

    # ── F10：「模型＋id」型欄位（第二輪抗辯 red-team A：mail.activity／rating.rating 的 res_name 以 sudo 依
    #        (res_model, res_id) 算，onchange 帶任意紀錄 id 逐筆讀到別筆的顯示名稱）────────────────────
    def test_f10_reference_display_name_blocked_for_every_role(self):
        project_model = self.env['ir.model']._get('project.project')
        spec = {'res_model_id': {}, 'res_model': {}, 'res_id': {}, 'res_name': {}}
        cases = ((self.mgr_a, self.p_b, self.p_a), (self.portal_a, self.p_b, self.p_a),
                 (self.console, self.p_a, None), (self.sup2, self.p_a, self.p_s2), (self.sup, self.p_s2, self.p_a))
        for model_name in ('mail.activity', 'rating.rating'):
            for user, foreign, own in cases:
                with self.subTest(model=model_name, user=user.login):
                    self.assertFalse(self._readable(user, foreign), f'前提：{user.login} 直接讀不到 {foreign.code}')
                    Model = self._model(user, model_name)
                    # 前台帳號沒有這兩個模型的 ACL：只斷言被擋；內部帳號另比訊息（證明是守衛擋的）
                    field = None if user.share else 'res_id'
                    for given in ({'res_model': 'project.project', 'res_id': foreign.id},
                                  {'res_model_id': project_model.id, 'res_id': foreign.id},
                                  {'res_model_id': project_model.id, 'res_model': 'project.project',
                                   'res_id': foreign.id}):
                        self.assertBlocked(Model.onchange, given, ['res_id'], spec, field=field)
                    self.assertBlocked(Model.with_context(default_res_model_id=project_model.id,
                                                          default_res_id=foreign.id).onchange, {}, [], spec,
                                       field=field)
                    if own and not user.share:
                        self.env.invalidate_all()
                        value = Model.onchange({'res_model_id': project_model.id, 'res_model': 'project.project',
                                                'res_id': own.id}, ['res_id'], spec)['value']
                        self.assertEqual(value.get('res_name'), own.display_name, '正當用法：自己看得到的工程照常帶出名稱')
        # 既有待辦：改成讀不到的工程被擋；目標沒變的寫入照常
        activity = self.env['mail.activity'].create({
            'res_model_id': project_model.id, 'res_id': self.p_a.id, 'user_id': self.sup.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id, 'summary': 'F10'})
        mine = activity.with_env(self._env_of(self.sup))
        self.assertBlocked(mine.write, {'res_id': self.p_s2.id}, field='res_id')
        mine.write({'summary': 'F10 改摘要'})
        self.assertEqual(activity.summary, 'F10 改摘要')

    # ── F11：_inherits 子模型帶著父模型的守衛欄位（第三輪抗辯 red-team：product.document 繼承 ir.attachment，
    #        onchange 帶讀不到的資料夾讀到資料夾路徑）─────────────────────────────────────────────
    def test_f11_inherits_child_carries_parent_guard(self):
        from odoo.addons.construction_supervision_base.models.relational_input_guard import guarded_fields_of
        child = 'product.document'
        if child not in self.env:
            self.skipTest('這個庫沒有 product.document')
        self.assertIn('folder_id', guarded_fields_of(self.env['ir.attachment']), '前提：父模型的資料夾是守衛欄位')
        self.assertIn('folder_id', guarded_fields_of(self.env[child]), '子模型也要有')
        Folder = self.env['supervision.folder']
        folder_b = Folder.create({'name': 'F11 乙工程資料夾', 'project_id': self.p_b.id})
        folder_a = Folder.create({'name': 'F11 甲工程資料夾', 'project_id': self.p_a.id})
        spec = {'folder_id': {}, 'folder_path': {}}
        self.assertFalse(self._readable(self.mgr_a, folder_b), '前提：營造廠主管讀不到乙工程的資料夾')
        self.assertBlocked(self._model(self.mgr_a, child).onchange, {'folder_id': folder_b.id}, ['folder_id'], spec,
                           field='folder_id')
        self.assertBlocked(self._model(self.mgr_a, 'ir.attachment').onchange, {'folder_id': folder_b.id},
                           ['folder_id'], spec, field='folder_id')
        # 正當用法：自己看得到的資料夾照常帶出路徑
        if self._readable(self.mgr_a, folder_a):
            self.env.invalidate_all()
            value = self._model(self.mgr_a, child).onchange({'folder_id': folder_a.id}, ['folder_id'], spec)['value']
            self.assertEqual(value.get('folder_path'), folder_a.complete_name)

    # ── F2：精靈的 related（sudo）──────────────────────────────────────
    def test_f2_wizard_related_blocked(self):
        today = fields.Date.today()
        for user, foreign in ((self.mgr_a, self.p_b), (self.console, self.p_a), (self.sup2, self.p_a)):
            with self.subTest(user=user.login):
                strict = 'project_id' if user == self.sup2 else None
                self.assertBlocked(self._model(user, 'estimate.import.wizard').create,
                                   {'project_id': foreign.id, 'estimate_date': today}, field=strict)
                self.assertBlocked(self._model(user, 'tender.import.wizard').create,
                                   {'project_id': foreign.id, 'xml_file': 'eA=='}, field=strict)
        # 工項、估驗明細、日誌：營造廠主管讀不到 B 的；S2 監造方讀不到 S 的工項
        line_spec = {'estimate_line_id': {}, 'unit_price': {}, 'description': {}}
        task_spec = {'task_id': {}, 'planned_qty': {}, 'name': {}}
        for user in (self.mgr_a, self.console):
            with self.subTest(user=user.login):
                self.assertFalse(self._readable(user, self.est_line_b))
                self.assertBlocked(self._model(user, 'estimate.manual.amount.wizard.line').onchange,
                                   {'estimate_line_id': self.est_line_b.id}, ['estimate_line_id'], line_spec)
                self.assertBlocked(self._model(user, 'estimate.fill.available.wizard.line').onchange,
                                   {'estimate_line_id': self.est_line_b.id}, ['estimate_line_id'],
                                   {'estimate_line_id': {}, 'description': {}})
                self.assertBlocked(self._model(user, 'daily.log.unlock.wizard').onchange,
                                   {'sheet_id': self.sheet_b.id}, ['sheet_id'], {'sheet_id': {}, 'log_date': {}})
                self.assertBlocked(self._model(user, 'daily.log.add.items.wizard.line').onchange,
                                   {'task_id': self.tasks[self.p_b].id}, ['task_id'], task_spec)
        self.assertFalse(self._readable(self.sup2, self.tasks[self.p_a]))
        self.assertBlocked(self._model(self.sup2, 'daily.log.add.items.wizard.line').onchange,
                           {'task_id': self.tasks[self.p_a].id}, ['task_id'], task_spec, field='task_id')
        # 正當用法：監造方對自己的工項／估驗明細照常
        self.env.invalidate_all()
        value = self._model(self.sup, 'daily.log.add.items.wizard.line').onchange(
            {'task_id': self.tasks[self.p_a].id}, ['task_id'], task_spec)['value']
        self.assertEqual(value.get('planned_qty'), self.tasks[self.p_a].planned_qty)
        self.env.invalidate_all()
        value = self._model(self.sup, 'estimate.manual.amount.wizard.line').onchange(
            {'estimate_line_id': self.est_line_a.id}, ['estimate_line_id'], line_spec)['value']
        self.assertEqual(value.get('unit_price'), self.est_line_a.unit_price)

    # ── F1：照片 onchange 帶出附件全文 ─────────────────────────────────
    def test_f1_photo_onchange_matches_direct_read(self):
        targets = (self.photo_a.attachment_id, self.photo_b.attachment_id, self.att_s2)
        for user in (self.mgr_a, self.portal_a, self.console, self.sup, self.sup2):
            for att in targets:
                with self.subTest(user=user.login, att=att.name):
                    self.env.invalidate_all()
                    try:
                        direct = att.with_env(self._env_of(user)).read(['datas'])[0]['datas']
                        direct = direct.decode() if isinstance(direct, bytes) else direct
                    except AccessError:
                        direct = None
                    Photo = self._model(user, 'supervision.photo')
                    if direct is None:
                        self.assertBlocked(Photo.onchange, {'attachment_id': att.id}, ['attachment_id'],
                                           PHOTO_SPEC, field='attachment_id')
                    else:
                        self.env.invalidate_all()
                        image = Photo.onchange({'attachment_id': att.id}, ['attachment_id'], PHOTO_SPEC)['value']['image']
                        image = image.decode() if isinstance(image, bytes) else image
                        self.assertEqual(image, direct, '正當用法：讀得到的附件照常帶出，內容一致')
        # 具體期望（夾具前提）：營造廠主管讀得到自家照片、讀不到 B 的；S2 讀不到 S 工程的附件
        self.assertTrue(self._readable(self.mgr_a, self.photo_a.attachment_id))
        self.assertFalse(self._readable(self.mgr_a, self.photo_b.attachment_id))
        self.assertFalse(self._readable(self.sup, self.att_s2))

    # ── F5：資料夾上傳精靈 ────────────────────────────────────────────
    def test_f5_folder_wizard_cannot_move_attachments(self):
        folder = self.env['supervision.folder'].create({'name': 'DASH H 資料夾', 'project_id': self.p_a.id})
        victims = self.photo_a.attachment_id | self.photo_b.attachment_id
        self.env.flush_all()
        self.env.cr.execute('SELECT id, res_model, res_id FROM ir_attachment WHERE id = ANY(%s) ORDER BY id',
                            [victims.ids])
        before = self.env.cr.fetchall()
        for user in (self.mgr_a, self.sup2):
            for victim in victims:
                with self.subTest(user=user.login, victim=victim.id):
                    Wizard = self._model(user, 'supervision.folder.upload.wizard')
                    with self.assertRaises(AccessError):
                        Wizard.create({'project_id': self.p_a.id, 'folder_id': folder.id,
                                       'attachment_ids': [Command.set(victim.ids)]}).action_upload()
        self.env.flush_all()
        self.env.cr.execute('SELECT id, res_model, res_id FROM ir_attachment WHERE id = ANY(%s) ORDER BY id',
                            [victims.ids])
        self.assertEqual(self.env.cr.fetchall(), before, '附件歸屬不可改變')
        # 正當用法：監造方把自己剛上傳的檔放進資料夾
        own = self._model(self.sup, 'ir.attachment').create({'name': 'DASH H own.txt', 'raw': b'own'})
        self._model(self.sup, 'supervision.folder.upload.wizard').create({
            'project_id': self.p_a.id, 'folder_id': folder.id,
            'attachment_ids': [Command.set(own.ids)]}).action_upload()
        self.assertEqual(own.sudo().folder_id, folder)

    # ── F4：操作軌跡偽造 ─────────────────────────────────────────────
    def test_f4_audit_trail_forge_blocked(self):
        if 'audit.trail' not in self.env:
            self.skipTest('construction_audit 未安裝')
        model = self.env['ir.model']._get('project.project')
        for user in (self.mgr_a, self.portal_a, self.console, self.sup2):
            for value in SPOOF_VALUES:
                with self.subTest(user=user.login, value=value):
                    Trail = self._model(user, 'audit.trail').with_context(audit_trail_create=value)
                    # AccessError 是 UserError 的子類別：被別的防線先擋也算擋（Odoo 的 assertRaises 不收 tuple）
                    with self.assertRaises(UserError):
                        Trail.create({'model_id': model.id, 'res_id': self.p_a.id, 'operation_type': 'state_change',
                                      'user_id': self.sup.id, 'old_state': 'draft', 'new_state': 'approved',
                                      'note': FORGED_NOTE})
        self.env.flush_all()
        self.env.cr.execute('SELECT count(*) FROM audit_trail WHERE note = %s', [FORGED_NOTE])
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    # ── F6：通知收件人 ───────────────────────────────────────────────
    def test_f6_resend_partner_blocked(self):
        partner = self.env['res.partner'].create({'name': 'DASH H 收件人', 'email': 'dash_h@example.com',
                                                  'company_id': self.co_s2.id})
        message = self.env['mail.message'].create({'model': 'res.partner', 'res_id': partner.id, 'body': 'H',
                                                   'message_type': 'comment'})
        notif = self.env['mail.notification'].create({
            'mail_message_id': message.id, 'res_partner_id': partner.id,
            'notification_type': 'email', 'notification_status': 'exception'})
        checked = 0
        for user in (self.mgr_a, self.sup):
            with self.subTest(user=user.login):
                # 前提要用守衛自己的「讀得到」判準（搜得到這一筆，reports/H.md §2-1），不能用 _readable：
                # 它讀 display_name，通知的 display_name 會讀收件人——收件人在別家公司時 res.partner 的公司規則
                # 讓它讀不到，於是「通知本身讀得到」被誤判成讀不到（乾淨庫實測：監造方搜得到通知、讀 display_name
                # 被 res.partner 拒），守衛第一段本來就不適用卻被要求擋下
                self.env.invalidate_all()
                if self._model(user, 'mail.notification').search_count([('id', '=', notif.id)]):
                    # 新安裝的 mail 模組對內部帳號不限讀取通知 → 第一段守衛不適用（已知殘餘，reports/H.md）
                    continue
                checked += 1
                self.assertBlocked(self._model(user, 'mail.resend.partner').create, {'notification_id': notif.id},
                                   field='notification_id' if user == self.sup else None)
        if not checked:
            # 沒有任何一個帳號讀不到這則通知＝這支什麼都沒驗，要看得出來（不可默默變綠，M-C）
            self.skipTest('此庫 mail.notification 對內部帳號不限讀取：第一段守衛不適用（已知殘餘）')

    # ── F9：前台 get-items ──────────────────────────────────────────
    def test_f9_portal_get_items_hidden_template(self):
        Type, Item = self.env['self.inspection.type'], self.env['self.inspection.type.item']
        t_b = Type.create({'name': 'DASH H B 專屬樣板', 'project_id': self.p_b.id})
        t_a = Type.create({'name': 'DASH H A 專屬樣板', 'project_id': self.p_a.id})
        for itype in (t_a, t_b):
            Item.create({'type_id': itype.id, 'name': f'{itype.name} 項目', 'sequence': 10})
        ctrl = ConstructionPortal()
        for user in (self.mgr_a, self.portal_a):
            with self.subTest(user=user.login):
                with MockRequest(self._env_of(user)):
                    hidden = ctrl.portal_construction_inspection_get_items(type_id=t_b.id)
                    shown = ctrl.portal_construction_inspection_get_items(type_id=t_a.id)
                self.assertEqual(hidden['items'], [], '別家工程的樣板項目不可回傳')
                self.assertEqual([i['name'] for i in shown['items']], [f'{t_a.name} 項目'], '正當用法：自家工程樣板照常')

    # ── 基準照片內容（夾具健全性）───────────────────────────────────
    def test_rig_photo_payload_is_real(self):
        datas = self.photo_a.attachment_id.datas
        self.assertTrue(datas and base64.b64decode(datas), '夾具照片要有內容，F1 的比對才有意義')
