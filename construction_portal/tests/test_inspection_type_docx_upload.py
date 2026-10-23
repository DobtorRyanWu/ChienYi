# -*- coding: utf-8 -*-
"""前台帳號不可上傳自主檢查樣板 docx 的回歸測試。

背景（2026-10-23 三方抗辯）：樣板 docx 會交給 construction_template 套印，套印引擎 docxtpl
用的是沒有沙箱的 jinja2.Environment（容器內 docxtpl/template.py:485）。能上傳樣板＝能讓伺服器
執行樣板裡的運算式，而所有庫都跑在同一台主機上，所以不能交給營造廠（portal）帳號。
內部帳號（監造／代操）照常可以上傳。
"""
from werkzeug.datastructures import MultiDict

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

LEADER = 'construction_supervision_base.group_portal_leader'      # 主管
OPERATOR = 'construction_supervision_base.group_operator'         # 內部代操作員


class _Docx:
    filename = 'evil.docx'

    def read(self):
        return b'PK fake docx'


@tagged('post_install', '-at_install', 'construction_portal')
class TestInspectionTypeDocxUpload(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.project = cls.env['project.project'].create({
            'name': '樣板上傳測試工程', 'code': 'TPL-DOCX-P', 'state': 'construction',
            'company_id': cls.env.company.id})
        cls.leader = cls._mk_user('docx_leader', [LEADER])
        cls.operator = cls._mk_user('docx_operator', ['base.group_user', OPERATOR])
        cls.env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': cls.leader.id})
        cls.type = cls.env['self.inspection.type'].create({
            'name': '樣板上傳測試', 'code': 'DOCX', 'project_id': cls.project.id})

    @classmethod
    def _mk_user(cls, login, groups):
        return cls.env['res.users'].create({
            'name': login, 'login': login,
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
        })

    def _save_with_upload(self, user):
        with MockRequest(self.env(user=user)) as req:
            req.httprequest.files = MultiDict([('template_file', _Docx())])
            return self.ctrl.portal_inspection_type_save(type_id=str(self.type.id), name=self.type.name)

    def test_rig(self):
        self.assertTrue(self.leader.share)
        self.assertFalse(self.operator.share)
        self.assertFalse(self.type.template_file)

    def test_portal_cannot_upload_template_docx(self):
        with self.assertRaises(AccessError):
            self._save_with_upload(self.leader)
        self.assertFalse(self.type.template_file, '前台主管不應換得掉樣板 docx')

    def test_internal_can_upload_template_docx(self):
        # 正當入口：內部代操仍可上傳
        self._save_with_upload(self.operator)
        self.assertEqual(self.type.template_filename, 'evil.docx')
