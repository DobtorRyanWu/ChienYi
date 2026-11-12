# -*- coding: utf-8 -*-
"""參觀帳號（models/visit_grant.py、models/ir_http.py、controllers/portal_visit.py、wizards/；淞源 2026-11-10 會議 C11）。

淞源：「給一個有期限的帳號，只開照片和指定的公文，其他都不要讓他看到」；老闆：預設七天。這裡鎖住：
① 授權內的照片與公文看得到（真實登入、真實 HTTP 請求）；
② 別的工程、沒指定的公文、其他前台頁面、RPC 都拿不到（預設拒絕：導回參觀首頁或 403／404）；
③ 過期當下就進不來，每日排程把帳號停用；沒設有效期的參觀帳號視為過期；
④ 既有前台角色不受影響（現場人員照常進得了一般頁面，進參觀頁會被導走）；
⑤ 參觀帳號本身沒有任何業務資料的讀取權、不能混其他角色、不替它建員工、RPC 不收密碼；
⑥ 後台精靈一次建好帳號＋有效期＋授權。
"""
import base64
import json
from datetime import timedelta

import odoo
from odoo import api
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.service import security
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.construction_supervision_base.utils.local_date import local_today

from ..models.ir_http import VISIT_HOME, visit_path_allowed
from ..models.visit_grant import DEFAULT_VISIT_DAYS, MAX_VISIT_DAYS, VISITOR_GROUP

ADMIN_GROUP = 'construction_supervision_base.group_supervisor_admin'
FIELD = 'construction_supervision_base.group_portal_user'
VIEWER = 'construction_supervision_base.group_portal_viewer'
DOC_MODEL = 'construction.official.doc'
PHOTO_MODEL = 'supervision.photo'
GRANT_MODEL = 'construction.visit.grant'
PASSWORD = 'Visit-Test-Pw-20261112'
# 1×1 PNG
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


class VisitFixture:
    """兩個工程、各一張照片與公文；一個參觀帳號只被授權工程一（可看照片、只指定公文 A）。"""

    @classmethod
    def _build_fixture(cls):
        env = cls.env
        cls.company = env.company
        Project = env['project.project']
        cls.p1 = Project.create({'name': 'VISIT 工程一', 'code': 'VISIT-P1', 'project_type': 'general',
                                 'state': 'construction', 'company_id': cls.company.id})
        cls.p2 = Project.create({'name': 'VISIT 工程二', 'code': 'VISIT-P2', 'project_type': 'general',
                                 'state': 'construction', 'company_id': cls.company.id})
        cls.photo1 = cls._photo(cls.p1, 'visit-p1.png')
        cls.photo2 = cls._photo(cls.p2, 'visit-p2.png')
        Doc = env[DOC_MODEL]
        cls.doc_a = Doc.create({'subject': 'VISIT 指定給他看的公文', 'company_id': cls.company.id,
                                'project_id': cls.p1.id, 'organization': 'VISIT 水利局'})
        cls.doc_b = Doc.create({'subject': 'VISIT 沒指定的公文', 'company_id': cls.company.id,
                                'project_id': cls.p1.id})
        cls.doc_p2 = Doc.create({'subject': 'VISIT 工程二的公文', 'company_id': cls.company.id,
                                 'project_id': cls.p2.id})
        cls.att_a = env['ir.attachment'].create({
            'name': 'visit-a.pdf', 'raw': b'%PDF-visit-a', 'res_model': DOC_MODEL, 'res_id': cls.doc_a.id})
        cls.att_b = env['ir.attachment'].create({
            'name': 'visit-b.pdf', 'raw': b'%PDF-visit-b', 'res_model': DOC_MODEL, 'res_id': cls.doc_b.id})
        cls.visitor = cls._visitor('visit_guest', local_today() + timedelta(days=3))
        cls.grant = env[GRANT_MODEL].create({
            'user_id': cls.visitor.id, 'project_id': cls.p1.id, 'allow_photos': True,
            'official_doc_ids': [(6, 0, cls.doc_a.ids)]})
        cls.worker = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'visit_worker', 'login': 'visit_worker', 'password': PASSWORD,
            'groups_id': [(6, 0, [env.ref(FIELD).id])], 'is_supervision_org': True,
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)]})
        env['supervision.project.member'].create({'project_id': cls.p1.id, 'user_id': cls.worker.id})

    @classmethod
    def _photo(cls, project, name):
        attachment = cls.env['ir.attachment'].create({
            'name': name, 'raw': PNG, 'mimetype': 'image/png', 'public': False, 'res_model': PHOTO_MODEL})
        return cls.env[PHOTO_MODEL].create({'project_id': project.id, 'attachment_id': attachment.id})

    @classmethod
    def _visitor(cls, login, valid_until):
        vals = {'name': login, 'login': login, 'password': PASSWORD,
                'groups_id': [(6, 0, [cls.env.ref(VISITOR_GROUP).id])],
                'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)]}
        if valid_until:
            vals['portal_valid_until'] = valid_until
        return cls.env['res.users'].with_context(no_reset_password=True).create(vals)


@tagged('post_install', '-at_install', 'construction_office')
class TestVisitAccountModel(VisitFixture, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._build_fixture()

    # ── ⑤ 帳號本身 ──────────────────────────────────────────────────────
    def test_visitor_has_no_business_read_access(self):
        self.assertTrue(self.visitor._is_visit_account())
        self.assertTrue(self.visitor.share, '參觀帳號是前台帳號')
        for model in (DOC_MODEL, 'construction.calendar.event', GRANT_MODEL, 'ir.attachment'):
            with self.assertRaises(AccessError, msg=model):
                self.env[model].with_user(self.visitor).search([])
        # 有些模型對所有前台帳號都開了讀取 ACL（例：工程、照片）：參觀帳號不是任何工程的成員，一筆都查不到
        for model, records in (('project.project', self.p1 | self.p2), (PHOTO_MODEL, self.photo1 | self.photo2)):
            Model = self.env[model].with_user(self.visitor)
            if Model.has_access('read'):
                self.assertFalse(Model.search([('id', 'in', records.ids)]), model)

    def test_visitor_gets_no_employee_and_rpc_needs_api_key(self):
        self.assertFalse(self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('user_id', '=', self.visitor.id)]), '不替參觀帳號建員工資料')
        self.assertTrue(self.visitor._rpc_api_keys_only())
        self.assertFalse(self.worker._rpc_api_keys_only(), '一般前台帳號不受影響')
        # 網頁登入（互動式）收密碼；程式介面（非互動式：XML-RPC／JSON-RPC）不收
        password = {'type': 'password', 'password': PASSWORD}
        self.env['res.users'].with_user(self.visitor)._check_credentials(password, {'interactive': True})
        with self.assertRaises(AccessDenied):
            self.env['res.users'].with_user(self.visitor)._check_credentials(password, {'interactive': False})
        self.env['res.users'].with_user(self.worker)._check_credentials(password, {'interactive': False})

    def test_visitor_cannot_be_mixed_with_other_roles(self):
        # ValidationError 是 UserError 的子類別；核心自己的「使用者類型衝突」檢查丟的也是 UserError 家族
        for xmlid in (VIEWER, FIELD, 'base.group_user'):
            with self.subTest(group=xmlid):
                with self.assertRaises(UserError), self.cr.savepoint():
                    self.visitor.write({'groups_id': [(4, self.env.ref(xmlid).id)]})
        with self.assertRaises(UserError), self.cr.savepoint():
            self.worker.write({'groups_id': [(4, self.env.ref(VISITOR_GROUP).id)]})

    def test_grant_constraints(self):
        Grant = self.env[GRANT_MODEL]
        with self.assertRaises(ValidationError), self.cr.savepoint():
            Grant.create({'user_id': self.worker.id, 'project_id': self.p1.id})      # 不是參觀帳號
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.grant.write({'official_doc_ids': [(4, self.doc_p2.id)]})            # 別的工程的公文
        with self.assertRaises(Exception), self.cr.savepoint():
            Grant.create({'user_id': self.visitor.id, 'project_id': self.p1.id})     # 同帳號同工程重複
            self.env.flush_all()

    # ── ③ 有效期 ────────────────────────────────────────────────────────
    def test_default_validity_and_expiry(self):
        today = local_today()
        fresh = self._visitor('visit_no_date', False)
        self.assertEqual(fresh.portal_valid_until, today + timedelta(days=DEFAULT_VISIT_DAYS), '沒填就帶預設天數')
        self.assertEqual(DEFAULT_VISIT_DAYS, 7, '老闆在會中說的預設天數')
        self.assertFalse(self.visitor._visit_expired())
        self.assertEqual(self.visitor._visit_grants(), self.grant)
        self.visitor.portal_valid_until = today
        self.assertFalse(self.visitor._visit_expired(), '有效期當天還能用')
        self.visitor.portal_valid_until = today - timedelta(days=1)
        self.assertTrue(self.visitor._visit_expired())
        self.assertFalse(self.visitor._visit_grants(), '過期就沒有授權')
        self.env.cr.execute('UPDATE res_users SET portal_valid_until = NULL WHERE id = %s', (fresh.id,))
        fresh.invalidate_recordset(['portal_valid_until'])
        self.assertTrue(fresh._visit_expired(), '沒設有效期視為過期')
        self.assertFalse(self.worker._visit_grants(), '不是參觀帳號沒有授權')

    def test_cron_deactivates_expired_visitors_only(self):
        today = local_today()
        expired = self._visitor('visit_expired', today - timedelta(days=1))
        no_date = self._visitor('visit_nodate2', today)
        self.env.cr.execute('UPDATE res_users SET portal_valid_until = NULL WHERE id = %s', (no_date.id,))
        no_date.invalidate_recordset(['portal_valid_until'])
        last_day = self._visitor('visit_lastday', today)
        self.worker.portal_valid_until = today - timedelta(days=5)      # 現場人員有到期日也不停用（既有規則）
        self.env['res.users']._cron_deactivate_expired_portal_users()
        self.assertEqual((expired.active, no_date.active, last_day.active, self.visitor.active, self.worker.active),
                         (False, False, True, True, True))

    # ── ⑥ 精靈 ──────────────────────────────────────────────────────────
    def test_wizard_creates_account_validity_and_grants(self):
        staff = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'visit_staff', 'login': 'visit_staff',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref(ADMIN_GROUP).id])],
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)]})
        Wizard = self.env['construction.visit.account.wizard'].with_user(staff)
        wizard = Wizard.create({
            'name': 'VISIT 水利局 王先生', 'login': 'visit-wang', 'project_ids': [(6, 0, (self.p1 | self.p2).ids)],
            'official_doc_ids': [(6, 0, (self.doc_a | self.doc_p2).ids)]})
        self.assertEqual(wizard.days, DEFAULT_VISIT_DAYS)
        wizard.action_create()
        user = wizard.created_user_id
        self.assertTrue(user._is_visit_account())
        self.assertEqual(user.sudo().portal_valid_until, local_today() + timedelta(days=DEFAULT_VISIT_DAYS))
        self.assertEqual(len(wizard.created_password), 12)
        self.assertEqual(wizard.state, 'done')
        grants = {grant.project_id: grant for grant in user._visit_grants()}
        self.assertEqual(set(grants), {self.p1, self.p2})
        self.assertEqual((grants[self.p1].official_doc_ids, grants[self.p2].official_doc_ids),
                         (self.doc_a, self.doc_p2), '公文分到各自的工程')
        self.assertTrue(all(grant.allow_photos for grant in grants.values()))
        # 密碼真的能登入
        self.env['res.users'].sudo().with_user(user)._check_credentials(
            {'type': 'password', 'password': wizard.created_password}, {'interactive': True})
        # 已建立的不能再按一次；帳號重複、天數不對要擋
        with self.assertRaises(UserError):
            wizard.action_create()
        with self.assertRaises(UserError):
            Wizard.create({'name': '重複', 'login': 'visit-wang', 'project_ids': [(6, 0, self.p1.ids)]}).action_create()
        for days in (0, MAX_VISIT_DAYS + 1):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                Wizard.create({'name': '天數', 'login': 'visit-days-%s' % days, 'days': days,
                               'project_ids': [(6, 0, self.p1.ids)]})

    def test_allowlist_is_exact_or_prefix_with_slash(self):
        allowed = (VISIT_HOME, VISIT_HOME + '/5/photos', '/web/assets/abc/web.assets_frontend.min.css',
                   '/web/session/logout', '/web/login')
        blocked = ('/construction', '/construction/5', '/construction/visitor', '/construction/visit-x', '/my',
                   '/web', '/web/dataset/call_kw', '/web/image/5', '/web/content/5', '/web/login_evil',
                   '/construction/img/5', '/construction/official-docs', '/mail/thread/data')
        for path in allowed:
            self.assertTrue(visit_path_allowed(path), path)
        for path in blocked:
            self.assertFalse(visit_path_allowed(path), path)


@tagged('post_install', '-at_install', 'construction_office')
class TestVisitAccountHttp(VisitFixture, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._build_fixture()

    def _login(self, user):
        """替 user 建一個已登入的 session（等同在登入頁輸入帳號密碼之後的狀態）。
        不能用 HttpCase.authenticate(login, password)：它走的是「非互動式」驗證，參觀帳號的非互動式驗證不收密碼
        （密碼本身收不收在 TestVisitAccountModel 驗）。"""
        self.authenticate(None, None)           # 新的匿名 session＋cookie
        session = self.session
        env = api.Environment(self.cr, user.id, {})
        session.uid = user.id
        session.login = user.login
        session.session_token = security.compute_session_token(session, env)
        session.context = dict(env['res.users'].context_get())
        odoo.http.root.session_store.save(session)

    def _get(self, path):
        return self.url_open(path, allow_redirects=False)

    def _location(self, response):
        return (response.headers.get('Location') or '').replace(self.base_url(), '')

    # ── ① 授權內的看得到 ────────────────────────────────────────────────
    def test_visitor_sees_granted_photos_and_docs(self):
        self._login(self.visitor)
        # 登入後系統把前台帳號帶去 /my：一路跟著導向走，最後落在參觀首頁
        landing = self.url_open('/my')
        self.assertTrue(landing.url.endswith(VISIT_HOME), landing.url)
        home = self._get(VISIT_HOME)
        self.assertEqual(home.status_code, 200)
        self.assertIn('VISIT 工程一', home.text)
        self.assertNotIn('VISIT 工程二', home.text)
        self.assertIn('%s/%s/photos' % (VISIT_HOME, self.p1.id), home.text)
        self.assertIn('%s/%s/docs' % (VISIT_HOME, self.p1.id), home.text)

        wall = self._get('%s/%s/photos' % (VISIT_HOME, self.p1.id))
        self.assertEqual(wall.status_code, 200)
        self.assertIn('%s/photo/%s/' % (VISIT_HOME, self.photo1.id), wall.text)
        self.assertNotIn('%s/photo/%s' % (VISIT_HOME, self.photo2.id), wall.text)
        image = self._get('%s/photo/%s/320x320' % (VISIT_HOME, self.photo1.id))
        self.assertEqual(image.status_code, 200)
        self.assertTrue(image.headers.get('Content-Type', '').startswith('image/'))
        self.assertEqual(self._get('%s/photo/%s' % (VISIT_HOME, self.photo1.id)).status_code, 200)

        docs = self._get('%s/%s/docs' % (VISIT_HOME, self.p1.id))
        self.assertEqual(docs.status_code, 200)
        self.assertIn('VISIT 指定給他看的公文', docs.text)
        self.assertNotIn('VISIT 沒指定的公文', docs.text)
        detail = self._get('%s/doc/%s' % (VISIT_HOME, self.doc_a.id))
        self.assertEqual(detail.status_code, 200)
        self.assertIn('VISIT 水利局', detail.text)
        download = self._get('%s/doc/%s/file/%s' % (VISIT_HOME, self.doc_a.id, self.att_a.id))
        self.assertEqual((download.status_code, download.content), (200, b'%PDF-visit-a'))

    # ── ② 授權外的拿不到 ────────────────────────────────────────────────
    def test_visitor_cannot_reach_anything_outside_the_grant(self):
        self._login(self.visitor)
        not_found = (
            '%s/%s/photos' % (VISIT_HOME, self.p2.id),                              # 別的工程的照片牆
            '%s/photo/%s' % (VISIT_HOME, self.photo2.id),                           # 別的工程的照片
            '%s/photo/%s/320x320' % (VISIT_HOME, self.photo2.id),
            '%s/%s/docs' % (VISIT_HOME, self.p2.id),                                # 別的工程的公文
            '%s/doc/%s' % (VISIT_HOME, self.doc_b.id),                              # 同工程但沒指定的公文
            '%s/doc/%s' % (VISIT_HOME, self.doc_p2.id),
            '%s/doc/%s/file/%s' % (VISIT_HOME, self.doc_b.id, self.att_b.id),       # 沒指定的公文的附件
            '%s/doc/%s/file/%s' % (VISIT_HOME, self.doc_a.id, self.att_b.id),       # 指定的公文＋別份公文的附件
            '%s/photo/%s' % (VISIT_HOME, 99999999),                                 # 不存在的
            '%s/doc/%s' % (VISIT_HOME, 99999999),
        )
        for path in not_found:
            self.assertEqual(self._get(path).status_code, 404, path)
        redirected = (
            '/my', '/my/home', '/construction', '/construction/%s' % self.p1.id,
            '/construction/%s/photos' % self.p1.id, '/construction/%s/official-docs' % self.p1.id,
            '/construction/official-docs', '/construction/official-doc/%s' % self.doc_a.id,
            '/construction/official-doc/%s/file/%s' % (self.doc_a.id, self.att_a.id),
            '/construction/img/%s' % self.photo1.attachment_id.id, '/construction/calendar',
            '/web/image/%s' % self.photo1.attachment_id.id, '/web/content/%s' % self.att_a.id,
            '/my/account', '/my/security',
        )
        for path in redirected:
            response = self._get(path)
            self.assertIn(response.status_code, (302, 303), path)
            self.assertEqual(self._location(response), VISIT_HOME, path)
        # 授權拿掉照片後，照片牆與照片都 404
        self.grant.allow_photos = False
        self.env.flush_all()
        self.assertEqual(self._get('%s/%s/photos' % (VISIT_HOME, self.p1.id)).status_code, 404)
        self.assertEqual(self._get('%s/photo/%s' % (VISIT_HOME, self.photo1.id)).status_code, 404)

    def test_visitor_rpc_and_posts_are_refused(self):
        self._login(self.visitor)
        payload = {'jsonrpc': '2.0', 'method': 'call', 'params': {
            'model': 'project.project', 'method': 'search_read', 'args': [[]], 'kwargs': {'fields': ['name']}}}
        response = self.url_open('/web/dataset/call_kw/project.project/search_read', data=json.dumps(payload),
                                 headers={'Content-Type': 'application/json'})
        body = response.json() if response.headers.get('Content-Type', '').startswith('application/json') else {}
        self.assertFalse(body.get('result'), 'RPC 不能回資料')
        self.assertTrue(response.status_code == 403 or 'error' in body, (response.status_code, body))
        # 對其他頁面送出表單（POST）：403，不是導走之後照做
        posted = self.url_open('/construction/%s/official-doc/create' % self.p1.id,
                               data={'subject': 'VISIT 不該建立的公文'}, allow_redirects=False)
        self.assertEqual(posted.status_code, 403)
        self.assertFalse(self.env[DOC_MODEL].search([('subject', '=', 'VISIT 不該建立的公文')]))

    # ── ③ 過期 ──────────────────────────────────────────────────────────
    def test_expired_visitor_is_logged_out_at_once(self):
        self._login(self.visitor)
        self.assertEqual(self._get(VISIT_HOME).status_code, 200)
        self.visitor.portal_valid_until = local_today() - timedelta(days=1)
        self.env.flush_all()
        for path in (VISIT_HOME, '%s/photo/%s' % (VISIT_HOME, self.photo1.id), '%s/doc/%s' % (VISIT_HOME, self.doc_a.id)):
            response = self._get(path)
            self.assertIn(response.status_code, (302, 303), path)
            self.assertTrue(self._location(response).startswith('/web/login'), (path, self._location(response)))

    # ── ④ 既有前台角色不受影響 ──────────────────────────────────────────
    def test_normal_portal_user_is_unaffected(self):
        self._login(self.worker)
        project_home = self._get('/construction/%s' % self.p1.id)
        self.assertEqual(project_home.status_code, 200, '現場人員照常進得了工程首頁')
        docs = self._get('/construction/%s/official-docs' % self.p1.id)
        self.assertEqual(docs.status_code, 200)
        visit = self._get(VISIT_HOME)
        self.assertIn(visit.status_code, (302, 303))
        self.assertEqual(self._location(visit), '/my', '不是參觀帳號：導回一般首頁')
        self.assertEqual(self._get('%s/photo/%s' % (VISIT_HOME, self.photo1.id)).status_code, 404)
        self.assertEqual(self._get('%s/doc/%s' % (VISIT_HOME, self.doc_a.id)).status_code, 404)
