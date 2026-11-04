# -*- coding: utf-8 -*-
"""前台角色的 ORM 寫入權全部收回（2026-11-04）。

背景：前台三個角色（老闆 subscriber／主管 leader／現場 user）在 97 個模型上有
write/create/unlink 的 ACL，而多數模型沒有任何限制寫入範圍的 ir.rule（規則只管讀）。
營造廠帳號繞過前台頁面、直接打 /web/dataset/call_kw，就改得到全庫的照片、樣板、
工程主檔、通報單、估驗單——controller 守衛（_require_manage、_require_photo_deleter…）
整套被繞過。前台頁面本來就設計成「sudo＋controller 守衛」寫入（security.xml 檔頭），
所以收回 ORM 寫入權不影響前台；守衛從此是唯一的寫入閘。

三段：
A. 權限表：三個前台角色在任何模型上都沒有 write/create/unlink（以後誰加回 csv 列也會紅）
B. RPC：代表性的直接寫入會被擋（斷言打在使用者拿到的結果：AccessError、資料沒變）
C. 正當入口：原本靠使用者自己權限的前台動作，收回後仍然成功
   （審核動作、留言、閱覽者照舊不能留言、樣板頁只剩內部帳號能改）
"""

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

BOSS = 'construction_supervision_base.group_portal_subscriber'     # 老闆
LEADER = 'construction_supervision_base.group_portal_leader'       # 主管
FIELD = 'construction_supervision_base.group_portal_user'          # 現場人員
VIEWER = 'construction_supervision_base.group_portal_viewer'       # 定期閱覽者
OPERATOR = 'construction_supervision_base.group_operator'          # 內部代操作員
PORTAL_WRITER_GROUPS = (BOSS, LEADER, FIELD)
# 每個前台角色至少要讀得到這麼多個模型；少於這個數＝群組或權限表沒載入，
# A 段的「找不到寫入權」就會是空集合造成的恆真（不是真的收乾淨）
MIN_READ_ACL_PER_GROUP = 50
PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalOrmReadonly(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.project = env['project.project'].create({
            'name': '唯讀測試工程', 'code': 'RO-GEN', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        # 別人的工程：測試帳號都不是成員
        cls.other_project = env['project.project'].create({
            'name': '唯讀測試他案', 'code': 'RO-OTHER', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        # 別人的預約式工程（通報單用）
        cls.other_res_project = env['project.project'].create({
            'name': '唯讀測試他案預約式', 'code': 'RO-RSV', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id})
        env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'ROQA',
            'contractor_prefix': 'ROQR'})
        # 施工日誌要求工程已有啟用中的進度表
        env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.boss = cls._mk_user('ro_boss', [BOSS])
        cls.leader = cls._mk_user('ro_leader', [LEADER])
        cls.field = cls._mk_user('ro_field', [FIELD])
        cls.field_b = cls._mk_user('ro_field_b', [FIELD])
        cls.observer = cls._mk_user('ro_observer', [VIEWER])
        cls.operator = cls._mk_user('ro_operator', ['base.group_user', OPERATOR])
        for u in (cls.leader, cls.field, cls.field_b, cls.observer):
            env['supervision.project.member'].create({
                'project_id': cls.project.id, 'user_id': u.id})
        cls.global_type = env['self.inspection.type'].create({'name': '唯讀測試全域樣板'})

    @classmethod
    def _mk_user(cls, login, groups):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])]})

    def _photo(self, uploader, project):
        env_u = self.env(user=uploader)
        att = env_u['ir.attachment'].sudo().create({
            'name': 'ro.png', 'datas': PNG_B64, 'mimetype': 'image/png',
            'public': False, 'res_model': 'supervision.photo'})
        return env_u['supervision.photo'].sudo().create({
            'project_id': project.id, 'attachment_id': att.id})

    def _defect(self):
        return self.env['general.defect.improvement'].create({
            'project_id': self.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '唯讀測試缺失', 'defect_location': 'B1',
            'source_type': 'daily_check', 'state': 'notified'})

    # ═══ A. 權限表 ══════════════════════════════════════════════════════
    def test_a_rig_portal_groups_have_read_acl(self):
        """前提：三個前台角色的權限表有載入（否則 A 段是空集合恆真）。"""
        Access = self.env['ir.model.access'].sudo()
        for xmlid in PORTAL_WRITER_GROUPS:
            n = Access.search_count([('group_id', '=', self.env.ref(xmlid).id),
                                     ('perm_read', '=', True)])
            self.assertGreaterEqual(n, MIN_READ_ACL_PER_GROUP,
                                    '%s 只讀得到 %d 個模型，權限表沒載入？' % (xmlid, n))

    def test_a_portal_roles_have_no_orm_write_acl(self):
        groups = self.env['res.groups'].browse(
            [self.env.ref(x).id for x in PORTAL_WRITER_GROUPS])
        rows = self.env['ir.model.access'].sudo().search([
            ('group_id', 'in', groups.ids), '|', '|',
            ('perm_write', '=', True), ('perm_create', '=', True), ('perm_unlink', '=', True)])
        found = sorted('%s（%s）' % (r.model_id.model, r.group_id.name) for r in rows)
        if found:
            self.fail('前台角色不可有 ORM 寫入權（前台寫入一律走 sudo＋守衛），'
                      '還有 %d 列：%s' % (len(found), '、'.join(found[:20])))

    # ═══ B. RPC 直接寫入被擋 ════════════════════════════════════════════
    def test_b_boss_cannot_rpc_write_photo_of_other_project(self):
        photo = self._photo(self.operator, self.other_project)
        with self.assertRaises(AccessError):
            photo.with_user(self.boss).write({'description': '老闆改別案照片'})
        self.assertNotEqual(photo.description, '老闆改別案照片')

    def test_b_field_cannot_rpc_archive_others_photo(self):
        photo = self._photo(self.field_b, self.project)
        with self.assertRaises(AccessError):
            photo.with_user(self.field).write({'active': False})
        self.assertTrue(photo.active, '現場人員不可經 RPC 把別人的照片封存（隱藏）')

    def test_b_leader_cannot_rpc_write_global_inspection_type(self):
        with self.assertRaises(AccessError):
            self.global_type.with_user(self.leader).write({'name': '主管改全域樣板'})
        self.assertEqual(self.global_type.name, '唯讀測試全域樣板')

    def test_b_leader_cannot_rpc_write_slip_of_other_project(self):
        """通報單三個前台角色都有增改刪、而且沒有任何寫入規則：別案的也改得到。"""
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.other_res_project.id, 'location': '他案地點', 'slip_no': 1})
        with self.assertRaises(AccessError):
            slip.with_user(self.leader).write({'location': '主管改別案通報單'})
        self.assertEqual(slip.location, '他案地點')

    def test_b_field_cannot_rpc_close_defect(self):
        defect = self._defect()
        with self.assertRaises(AccessError):
            defect.with_user(self.field).write({'state': 'closed'})
        self.assertEqual(defect.state, 'notified', '現場人員不可經 RPC 繞過審核直接結案')

    def test_b_public_sudo_methods_not_callable_remotely(self):
        """RPC 能呼叫任何公開方法、呼叫前不查 ACL；方法裡自己 sudo 建資料，收回寫入權也擋不住。
        這三支內部 sudo 寫入、值又由呼叫端給，必須標 @api.private（照 /web/dataset/call_kw 的判斷）。"""
        from odoo.service.model import get_public_method
        cases = [('supervision.photo', 'create_from_portal'),          # 任意工程建照片
                 ('general.self.inspection', 'create_from_portal'),    # 任意工程建自主檢查
                 ('audit.trail', 'log_operation')]                     # 偽造稽核軌跡
        checked = 0
        for model, method in cases:
            if model not in self.env:
                continue
            with self.subTest(model=model, method=method):
                with self.assertRaises(AccessError):
                    get_public_method(self.env[model].with_user(self.field), method)
            checked += 1
        self.assertGreaterEqual(checked, 2, '前台兩支 create_from_portal 一定要驗到')

    # ═══ C. 正當入口仍然成功 ════════════════════════════════════════════
    def test_c_leader_review_action_still_works(self):
        """審核動作原本以本人身分執行（靠使用者自己的寫入權），收回後仍要成功、
        而且寫入者仍是本人（sudo() 不換使用者）。"""
        emp = self.env['hr.employee'].create({
            'name': 'ro_emp', 'company_id': self.env.company.id})
        log = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': emp.id, 'log_date': fields.Date.today()})
        self.assertEqual(log.state, 'draft', '前提：日誌從編輯中開始')
        with MockRequest(self.env(user=self.leader)):
            res = self.ctrl.portal_daily_log_mark_filled(self.project.id, log.id)
        self.assertIn('msg=reviewed', res.headers.get('Location', ''),
                      '主管標記已填應成功（收回寫入權後不可變成錯誤或 403）')
        self.assertEqual(log.state, 'filled')
        self.assertEqual(log.write_uid, self.leader, '寫入者要記成主管本人，不是系統')

    def test_c_review_action_records_the_reviewer(self):
        """缺失／自主檢查的單據來自 _document_check_access，核心回傳的是系統帳號的 record；
        審核動作要改回本人身分執行，審核人欄位才會記成主管本人而不是「系統」。"""
        defect = self._defect()
        defect.sudo().write({'state': 'improved'})
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.args = {}
            res = self.ctrl.portal_defect_verify(defect.id)
        self.assertIn('msg=reviewed', res.headers.get('Location', ''))
        self.assertEqual(defect.state, 'verified')
        self.assertEqual(defect.verifier_id, self.leader, '審核人要記成主管本人')

    def test_c_leader_can_still_submit_schedule_extension(self):
        """工期展延原本先用本人身分檢查「能不能寫工程」，寫入權收回後會一律被導回 /my。"""
        project = self.env['project.project'].create({
            'name': '唯讀測試展延工程', 'code': 'RO-EXT', 'project_type': 'general',
            'state': 'construction', 'company_id': self.env.company.id,
            'contract_start_date': fields.Date.to_date('2026-01-05'),
            'contract_end_date': fields.Date.to_date('2026-03-30')})
        self.env['supervision.project.member'].create({
            'project_id': project.id, 'user_id': self.leader.id})
        schedule = self.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()})
        self.assertEqual(schedule.state, 'draft', '前提：草稿版進度表')
        with MockRequest(self.env(user=self.leader)):
            res = self.ctrl.portal_schedule_extend_submit(
                project.id, schedule.id, current_extension='9')
        self.assertIn('success=1', res.headers.get('Location', ''),
                      '主管送出展延應成功：%s' % res.headers.get('Location', ''))
        self.assertEqual(schedule.current_extension, 9)

    def _post_comment(self, user, record, **kwargs):
        """走真的前台留言路由（本模組的 ConstructionThreadController → portal → mail）。
        回傳新留言；沒有留言權限（路由丟 NotFound）時回 None。"""
        from werkzeug.exceptions import NotFound
        from odoo.addons.construction_portal.controllers.portal import ConstructionThreadController
        self.env.flush_all()
        self.env.invalidate_all()
        Message = self.env['mail.message'].sudo()
        before = Message.search([('model', '=', record._name), ('res_id', '=', record.id)]).ids
        # @http.route() 的路由參數（type 等）要等 Odoo 產生路由表時才從上層合併，
        # 測試直接呼叫要用被包住的原函式（它裡面 super() 照樣走 portal → mail 的真實流程）
        post = ConstructionThreadController.mail_message_post.original_endpoint
        with MockRequest(self.env(user=user)):
            try:
                post(ConstructionThreadController(), record._name, record.id, {
                    'body': '唯讀測試留言', 'message_type': 'comment',
                    'subtype_xmlid': 'mail.mt_comment'}, **kwargs)
            except NotFound:
                return None
        return Message.search([('model', '=', record._name), ('res_id', '=', record.id),
                               ('id', 'not in', before)])

    def test_c_member_can_still_post_comment(self):
        defect = self._defect()
        for user in (self.boss, self.leader, self.field):
            message = self._post_comment(user, defect)
            self.assertEqual(len(message), 1, '%s 應可在前台留言' % user.login)
            self.assertEqual(message.author_id, user.partner_id)
            # 留言者要成為關注者，之後的回覆才會進他的通知中心
            self.assertIn(user.partner_id, defect.message_partner_ids,
                          '%s 留言後要自動關注這張缺失' % user.login)

    def test_c_token_holder_who_cannot_read_is_not_subscribed(self):
        """核心允許拿分享 token 的人留言；讀不到那筆的人不能因此變成關注者（否則之後的回覆會一直外洩）。"""
        inspection = self.env['general.self.inspection'].create({
            'project_id': self.other_project.id, 'name': 'RO-INSP',
            'inspection_type_id': self.global_type.id, 'sub_project_name': 'RO',
            'inspection_date': fields.Date.today()})
        token = inspection._portal_ensure_token()
        self.assertFalse(inspection.with_user(self.field).has_access('read'), '前提：現場人員不是他案成員')
        message = self._post_comment(self.field, inspection, token=token)
        self.assertEqual(len(message), 1, '前提：核心照樣讓持 token 的人留言')
        self.assertNotIn(self.field.partner_id, inspection.message_partner_ids,
                         '讀不到的人不可因留言變成關注者')

    def test_c_comment_models_exist(self):
        """留言名單用模型名稱比對；改名或移除時這份名單會靜默失效。"""
        from odoo.addons.construction_portal.models.mail_thread import PORTAL_COMMENT_MODELS
        optional = {'supervision.test.record'}   # construction_test 有裝才有
        missing = sorted(m for m in PORTAL_COMMENT_MODELS - optional if m not in self.env)
        self.assertFalse(missing, '留言名單裡的模型不存在：%s' % missing)

    def test_c_observer_still_cannot_post_comment(self):
        defect = self._defect()
        self.assertTrue(defect.with_user(self.observer).has_access('read'),
                        '前提：閱覽者讀得到這張缺失')
        self.assertFalse(self._post_comment(self.observer, defect), '閱覽者照舊不能留言')

    def test_c_non_member_cannot_post_comment(self):
        defect = self._defect()
        stranger = self._mk_user('ro_stranger', [FIELD])
        self.assertFalse(self._post_comment(stranger, defect), '不是成員的人不能留言')

    # ═══ D. 讀取範圍：日誌、通報單、檢試驗只看得到參與的工程（2026-11-04 補成員規則）══════
    def _assert_member_scope(self, record, member, outsider):
        self.env.invalidate_all()
        self.assertTrue(record.with_user(member).has_access('read'), '成員要讀得到 %s' % record._name)
        self.assertTrue(record.with_user(self.boss).has_access('read'), '老闆是公司範圍，要讀得到 %s' % record._name)
        self.assertFalse(record.with_user(outsider).has_access('read'),
                         '不是成員的前台帳號不可讀 %s' % record._name)
        self.assertNotIn(record, self.env[record._name].with_user(outsider).search([('id', '=', record.id)]))

    def _member_of(self, project):
        user = self._mk_user('ro_member_%s' % project.code.lower(), [FIELD])
        self.env['supervision.project.member'].create({'project_id': project.id, 'user_id': user.id})
        return user

    def test_d_daily_log_member_scope(self):
        self.env['progress.schedule'].create({
            'project_id': self.other_project.id,
            'change_date': fields.Date.today()}).write({'state': 'active'})
        emp = self.env['hr.employee'].create({'name': 'ro_emp_other', 'company_id': self.env.company.id})
        log = self.env['daily.log.sheet'].create({
            'supervision_project_id': self.other_project.id, 'company_id': self.env.company.id,
            'employee_id': emp.id, 'log_date': fields.Date.today()})
        self._assert_member_scope(log, self._member_of(self.other_project), self.field)

    def test_d_notification_slip_member_scope(self):
        slip = self.env['reservation.notification.slip'].create({
            'project_id': self.other_res_project.id, 'location': '他案地點', 'slip_no': 7})
        self._assert_member_scope(slip, self._member_of(self.other_res_project), self.field)

    def test_d_test_record_member_scope(self):
        if 'supervision.test.record' not in self.env:
            self.skipTest('construction_test 沒裝')
        standard = self.env['supervision.test.standard'].create({
            'name': '混凝土抗壓強度', 'material': '預拌混凝土', 'project_id': self.other_project.id})
        record = self.env['supervision.test.record'].create({
            'project_id': self.other_project.id, 'standard_id': standard.id})
        self._assert_member_scope(record, self._member_of(self.other_project), self.field)

    def _save_type(self, user, **post):
        with MockRequest(self.env(user=user)) as req:
            req.httprequest.files.get.return_value = None
            return self.ctrl.portal_inspection_type_save(**post)

    def test_c_portal_cannot_manage_inspection_types(self):
        """前台帳號在樣板頁只能看和下載（2026-11-04 使用者裁示）。"""
        for user in (self.boss, self.leader):
            with self.assertRaises(AccessError):
                self._save_type(user, type_id=str(self.global_type.id), name='前台改名')
            with self.assertRaises(AccessError):
                self._save_type(user, name='前台新增的樣板')
        self.assertEqual(self.global_type.name, '唯讀測試全域樣板')
        self.assertFalse(self.env['self.inspection.type'].search([('name', '=', '前台新增的樣板')]))
        with MockRequest(self.env(user=self.leader)):
            self.assertFalse(self.ctrl._can_manage_inspection_types(),
                             '樣板頁不可對前台帳號顯示編輯按鈕')

    def test_c_internal_operator_can_still_manage_inspection_types(self):
        self._save_type(self.operator, type_id=str(self.global_type.id), name='代操改名')
        self.assertEqual(self.global_type.name, '代操改名')
        with MockRequest(self.env(user=self.operator)):
            self.assertTrue(self.ctrl._can_manage_inspection_types())
