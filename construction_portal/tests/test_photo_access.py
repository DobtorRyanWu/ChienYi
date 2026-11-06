# -*- coding: utf-8 -*-
"""M0.6 回歸測試 — 帶權限檢查的照片供圖端點（/construction/img）。

原始 bug（稽核 M-c / M0.6）：前台照片附件一律 public=True → 短網址
`/web/content/<id>` 繞過 record rule，任何登入者（甚至跨專案、跨承包商）可連號
枚舉抓取所有工地照片。修法：附件不再 public，前台顯圖改走
`/construction/img/<att_id>`，由本端點依「登入者對照片所屬專案的可見範圍」把關，
不在範圍一律 404（不洩漏存在性）。

本測試以 website.tools.MockRequest 驅動真實 controller 方法 + 真實成員關係，
斷言：非成員 → NotFound；成員 → 放行；附件→專案反解正確。純 TransactionCase。
"""

from werkzeug.exceptions import NotFound

from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    SUPERVISION_USER_VALS, contractor_project_vals, contractor_user_vals, make_contractor)

VIEWER = 'construction_supervision_base.group_portal_viewer'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPhotoAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        # 夾具：前台帳號是營造方帳號（範圍公司＝工程的承攬廠商）
        cls.contractor = make_contractor(cls.env, 'M0.6 照片測試營造')
        cls.project = cls.env['project.project'].create({
            'name': 'M0.6 照片權限測試工程',
            'code': 'M06-IMG',
            'state': 'construction',
            'company_id': cls.env.company.id,
            **contractor_project_vals(cls.contractor),
        })
        # 一張綁定到 supervision.photo 的附件（模擬 _portal_save_photos 產物）
        cls.att = cls.env['ir.attachment'].create({
            'name': 'test.png',
            'datas': b'aGVsbG8=',  # base64 "hello"
            'res_model': 'general.defect.improvement',
            'mimetype': 'image/png',
            'public': False,
        })
        cls.photo = cls.env['supervision.photo'].create({
            'project_id': cls.project.id,
            'attachment_id': cls.att.id,
        })
        cls.member = cls.env['res.users'].create({
            'name': 'm06_member', 'login': 'm06_member',
            'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])],
            **contractor_user_vals(cls.contractor),
        })
        cls.outsider = cls.env['res.users'].create({
            'name': 'm06_outsider', 'login': 'm06_outsider',
            'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])],
            **contractor_user_vals(cls.contractor),
        })
        cls.env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.member.id,
        })

    def test_resolve_photo_project(self):
        with MockRequest(self.env):
            proj = self.ctrl._resolve_photo_project(self.att)
        self.assertEqual(proj, self.project,
                         'M0.6：附件應反解回其 supervision.photo 的工程案件')

    def test_member_can_see_outsider_cannot(self):
        with MockRequest(self.env(user=self.member)):
            self.assertTrue(self.ctrl._user_can_see_project(self.project),
                            '專案成員應可見')
        with MockRequest(self.env(user=self.outsider)):
            self.assertFalse(self.ctrl._user_can_see_project(self.project),
                             'M0.6：非成員不應可見（跨專案枚舉破口）')

    def test_route_denies_outsider(self):
        """非成員打 /construction/img/<att> → NotFound（不洩漏照片）。"""
        with MockRequest(self.env(user=self.outsider)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_photo_serve(self.att.id)

    def test_route_serves_member(self):
        """成員打 /construction/img/<att> → 不 NotFound（放行到影像 pipeline）。"""
        with MockRequest(self.env(user=self.member)):
            try:
                resp = self.ctrl.portal_construction_photo_serve(self.att.id)
            except NotFound:
                self.fail('M0.6：專案成員不應被擋在照片端點外')
        self.assertIsNotNone(resp)

    def test_allowlist_rejects_generic_project_image(self):
        """掛在可見專案上、但非登記照片的影像附件 → 成員也 404。

        抗辯 finding：端點不得對「任意反解到可見專案的附件」放行，否則成為
        任意附件下載器。允許清單只認 supervision.photo/照片行/signboard/缺失 m2m。
        """
        rogue = self.env['ir.attachment'].create({
            'name': 'rogue.png', 'datas': b'aGVsbG8=',
            'res_model': 'project.project', 'res_id': self.project.id,
            'mimetype': 'image/png', 'public': False,
        })
        with MockRequest(self.env):
            self.assertIsNone(
                self.ctrl._resolve_photo_project(rogue),
                'M0.6：非登記照片附件不應被反解')
        with MockRequest(self.env(user=self.member)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_photo_serve(rogue.id)

    def test_non_image_attachment_denied(self):
        """非影像附件（即使綁定 supervision.photo）→ 404（image-only 端點）。"""
        pdf = self.env['ir.attachment'].create({
            'name': 'doc.pdf', 'datas': b'aGVsbG8=',
            'res_model': 'general.defect.improvement', 'mimetype': 'application/pdf',
            'public': False,
        })
        self.env['supervision.photo'].create({
            'project_id': self.project.id, 'attachment_id': pdf.id,
        })
        with MockRequest(self.env(user=self.member)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_photo_serve(pdf.id)


@tagged('post_install', '-at_install', 'construction_portal')
class TestDocumentAccess(TransactionCase):
    """M0.6（文件）— /construction/doc 帶權限下載端點，取代 public 文件枚舉。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        # 夾具：前台帳號代表監造方前台人員（_member_vals）；營造方版本見下面的 TestDocumentAccessContractor
        # （工程文件 supervision.document 歸工程層級，合約 §0b-10）。本類別驗的是 M0.6 允許清單與成員範圍。
        cls.contractor = make_contractor(cls.env, 'M0.6 文件測試營造')
        cls.project = cls.env['project.project'].create({
            'name': 'M0.6 文件權限測試工程', 'code': 'M06-DOC',
            'state': 'construction', 'company_id': cls.env.company.id,
            **contractor_project_vals(cls.contractor),
        })
        cls.att = cls.env['ir.attachment'].create({
            'name': 'contract.pdf', 'datas': b'aGVsbG8=',
            'res_model': 'supervision.document', 'type': 'binary',
            'mimetype': 'application/pdf', 'public': False,
        })
        cls.category = cls.env['supervision.document.category'].create({
            'name': 'M06 測試分類',
        })
        cls.doc = cls.env['supervision.document'].create({
            'name': '合約', 'project_id': cls.project.id,
            'document_category_id': cls.category.id,
            'upload_attachment_ids': [(4, cls.att.id)],
        })
        cls.member = cls.env['res.users'].create({
            'name': 'm06d_member', 'login': 'm06d_member',
            'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])],
            **cls._member_vals(),
        })
        cls.outsider = cls.env['res.users'].create({
            'name': 'm06d_outsider', 'login': 'm06d_outsider',
            'groups_id': [(6, 0, [cls.env.ref(VIEWER).id])],
            **cls._member_vals(),
        })
        cls.env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.member.id,
        })

    @classmethod
    def _member_vals(cls):
        """前台帳號是哪一方：本類別＝監造方前台人員。"""
        return SUPERVISION_USER_VALS

    def test_resolve_document_project(self):
        with MockRequest(self.env):
            self.assertEqual(self.ctrl._resolve_document_project(self.att),
                             self.project)

    def test_outsider_denied_member_served(self):
        with MockRequest(self.env(user=self.outsider)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_document_serve(self.att.id)
        with MockRequest(self.env(user=self.member)):
            try:
                resp = self.ctrl.portal_construction_document_serve(self.att.id)
            except NotFound:
                self.fail('M0.6：文件所屬專案成員不應被擋')
        self.assertIsNotNone(resp)

    def test_allowlist_rejects_non_document_attachment(self):
        """不屬文件庫的附件 → 成員也 404（不做泛用反解）。"""
        rogue = self.env['ir.attachment'].create({
            'name': 'rogue.pdf', 'datas': b'aGVsbG8=',
            'res_model': 'project.project', 'res_id': self.project.id,
            'mimetype': 'application/pdf', 'public': False,
        })
        with MockRequest(self.env):
            self.assertIsNone(self.ctrl._resolve_document_project(rogue))
        with MockRequest(self.env(user=self.member)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_document_serve(rogue.id)


@tagged('post_install', '-at_install', 'construction_portal')
class TestDocumentAccessContractor(TestDocumentAccess):
    """同 TestDocumentAccess，前台帳號換成營造方（範圍公司＝工程的承攬廠商）：自己承攬工程的工程文件
    下載得到、成員以外照樣 404（父類別的三支照跑）；別家營造廠就算是成員也看不到（合約 §0b-10）。"""

    # Odoo 18 的測試載入器預設只跑類別自己定義的方法（odoo/tests/loader.py），不開這個父類別的三支不會跑
    allow_inherited_tests_method = True

    @classmethod
    def _member_vals(cls):
        return contractor_user_vals(cls.contractor)

    def test_contractor_member_served_other_contractor_denied(self):
        """承攬營造廠的成員下載得到；別家營造廠（不在工程承攬廠商內）就算是成員也 404，ORM 也讀不到文件。"""
        if not self.env.ref('construction_company_dashboard.group_contractor_manager', raise_if_not_found=False):
            # ORM 層的營造方範圍規則在 construction_company_dashboard；沒裝就沒有可驗的東西
            self.skipTest('construction_company_dashboard 沒裝：營造方 ORM 範圍不能驗（不是通過）')
        other = make_contractor(self.env, 'M0.6 別家營造')
        stranger = self.env['res.users'].create({
            'name': 'm06d_stranger', 'login': 'm06d_stranger',
            'groups_id': [(6, 0, [self.env.ref(VIEWER).id])],
            **contractor_user_vals(other),
        })
        self.env['supervision.project.member'].create({
            'project_id': self.project.id, 'user_id': stranger.id,
        })
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual((self.att.res_model, self.att.res_id), ('supervision.document', self.doc.id),
                         '前提：附件的來源是工程文件')
        Doc = self.env['supervision.document']
        self.assertEqual(Doc.with_user(self.member).search([('id', '=', self.doc.id)]), self.doc,
                         '承攬營造廠的成員讀得到工程文件')
        self.assertFalse(Doc.with_user(stranger).search([('id', '=', self.doc.id)]),
                         '別家營造廠讀不到')
        with MockRequest(self.env(user=self.member)):
            self.assertIsNotNone(self.ctrl.portal_construction_document_serve(self.att.id))
        with MockRequest(self.env(user=stranger)):
            with self.assertRaises(NotFound):
                self.ctrl.portal_construction_document_serve(self.att.id)
