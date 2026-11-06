# -*- coding: utf-8 -*-
"""前台 /construction/inspection/get-items 只回使用者看得到的樣板（11-06 抗辯 F9；合約 §0b-23，線 H）。

原本 ``self.inspection.type.sudo().browse(type_id)`` 直接讀任意樣板的檢查項目與標準：RPC 讀樣板被拒、
詳情頁 303 的別工程專屬樣板，get-items 照樣回 13 個項目。修法：先過 ``_get_visible_inspection_type``
（全域樣板＋可存取工程的樣板，與樣板列表／詳情頁同一個判定）。看不到與不存在回同一個空結果。
"""
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    SUPERVISION_USER_VALS, contractor_project_vals, contractor_user_vals, make_contractor)

LEADER = 'construction_supervision_base.group_portal_leader'
EMPTY = {'items': [], 'stages': [], 'timings': [], 'measures': []}


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalGetItemsScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        cls.contractor = make_contractor(env, 'H 樣板營造')
        Project = env['project.project']
        cls.project = Project.create({'name': 'H 樣板工程（可見）', 'code': 'H-GI-A', 'project_type': 'general',
                                      'state': 'construction', 'company_id': env.company.id,
                                      **contractor_project_vals(cls.contractor)})
        cls.other = Project.create({'name': 'H 樣板工程（別家）', 'code': 'H-GI-B', 'project_type': 'general',
                                    'state': 'construction', 'company_id': env.company.id})
        Users = env['res.users'].with_context(no_reset_password=True)
        group = env.ref(LEADER)
        cls.contractor_leader = Users.create({'name': 'h_gi_c', 'login': 'h_gi_c',
                                              'groups_id': [(6, 0, group.ids)],
                                              **contractor_user_vals(cls.contractor)})
        cls.supervision_leader = Users.create({'name': 'h_gi_s', 'login': 'h_gi_s',
                                               'groups_id': [(6, 0, group.ids)], **SUPERVISION_USER_VALS})
        for user in (cls.contractor_leader, cls.supervision_leader):
            env['supervision.project.member'].create({'project_id': cls.project.id, 'user_id': user.id})
        Type, Item = env['self.inspection.type'], env['self.inspection.type.item']
        cls.t_global = Type.create({'name': 'H 全域樣板'})
        cls.t_own = Type.create({'name': 'H 本工程樣板', 'project_id': cls.project.id})
        cls.t_other = Type.create({'name': 'H 別工程樣板', 'project_id': cls.other.id})
        for itype in (cls.t_global, cls.t_own, cls.t_other):
            Item.create({'type_id': itype.id, 'name': f'{itype.name} 項目', 'check_standard': 'H 標準',
                         'sequence': 10})

    def _items(self, user, itype):
        with MockRequest(self.env(user=user)):
            return self.ctrl.portal_construction_inspection_get_items(type_id=itype.id)

    def test_other_project_template_returns_nothing(self):
        for user in (self.contractor_leader, self.supervision_leader):
            with self.subTest(user=user.login):
                # 前提：這個帳號直接讀不到別工程的樣板（詳情頁走的同一個判定）
                with MockRequest(self.env(user=user)):
                    self.assertIsNone(self.ctrl._get_visible_inspection_type(self.t_other.id))
                self.assertEqual(self._items(user, self.t_other), EMPTY)

    def test_visible_templates_unchanged(self):
        """正當用法：全域樣板與本工程樣板照常回項目（名稱、標準）。"""
        for user in (self.contractor_leader, self.supervision_leader):
            for itype in (self.t_global, self.t_own):
                with self.subTest(user=user.login, itype=itype.name):
                    result = self._items(user, itype)
                    self.assertEqual([i['name'] for i in result['items']], [f'{itype.name} 項目'])
                    self.assertEqual(result['items'][0]['standard'], 'H 標準')

    def test_missing_template_same_as_hidden(self):
        missing = self.env['self.inspection.type'].browse(self.t_other.id + 100000)
        self.assertEqual(self._items(self.contractor_leader, missing), EMPTY)
