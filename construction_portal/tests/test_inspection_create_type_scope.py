# -*- coding: utf-8 -*-
"""前台建立自主檢查時，POST 進來的 inspection_type_id 要過「樣板可見性」（2026-11-16）。

審查員在 11-16 的權限審查標出（未實測）：/construction/inspection/create 把 POST 的
inspection_type_id 原樣交給 sudo 建立，action_load_default_items 再把該樣板的項目
（檢查項目名稱、設計標準）複製進這張檢查——前台帳號本來讀不到的別案專屬樣板內容，
就這樣經建立者自己的檢查讀到。同族的 /inspection/get-items 早就先過 _get_visible_inspection_type。
修法：建立（一般式與預約式）用同一個判定；POST 了看不到的樣板就拒絕、不建立、導回表單頁。
（不能當成沒選：一般式的 inspection_type_id 必填，會撞資料庫約束變成 400＋SQL ERROR。）
"""

from odoo import fields, http
from odoo.tests import HttpCase, tagged

from odoo.addons.construction_portal.tests.dash_fixtures import SUPERVISION_USER_VALS

FIELD_GROUP = 'construction_supervision_base.group_portal_user'    # 現場人員
SECRET_ITEM = '別案專屬機密檢查項目'
OWN_ITEM = '本案樣板檢查項目'
PASSWORD = 'type-scope-pw'


@tagged('post_install', '-at_install', 'construction_portal')
class TestInspectionCreateTypeScope(HttpCase):

    def setUp(self):
        super().setUp()
        env = self.env
        mk_project = lambda name, code: env['project.project'].create({
            'name': name, 'code': code, 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id})
        self.project = mk_project('建立樣板範圍本案', 'ICT-OWN')
        self.other_project = mk_project('建立樣板範圍他案', 'ICT-OTHER')
        self.user = env['res.users'].create({
            'name': '建立樣板範圍現場', 'login': 'ict_field', 'password': PASSWORD,
            'groups_id': [(6, 0, [env.ref(FIELD_GROUP).id])], **SUPERVISION_USER_VALS})
        env['supervision.project.member'].create({'project_id': self.project.id, 'user_id': self.user.id})
        Type, Item = env['self.inspection.type'], env['self.inspection.type.item']
        self.own_type = Type.create({'name': '建立樣板範圍本案樣板', 'project_id': self.project.id})
        self.other_type = Type.create({'name': '建立樣板範圍他案樣板', 'project_id': self.other_project.id})
        self.global_type = Type.create({'name': '建立樣板範圍全域樣板'})
        Item.create({'type_id': self.other_type.id, 'name': SECRET_ITEM,
                     'stage_id': self.other_type.stage_ids[:1].id})
        Item.create({'type_id': self.own_type.id, 'name': OWN_ITEM, 'stage_id': self.own_type.stage_ids[:1].id})
        Item.create({'type_id': self.global_type.id, 'name': '全域樣板檢查項目',
                     'stage_id': self.global_type.stage_ids[:1].id})

    def _create_inspection(self, itype):
        """以前台帳號 POST 建立；回新建的一般式自主檢查（只有一張才算成功）。"""
        self.authenticate(self.user.login, PASSWORD)
        self.last_response = response = self.url_open('/construction/inspection/create', data={
            'csrf_token': http.Request.csrf_token(self),
            'project_id': self.project.id,
            'inspection_type_id': itype.id,
            'inspection_date': fields.Date.today().isoformat(),
            'sub_project_name': '樣板範圍測試',
        })
        self.assertEqual(response.status_code, 200)
        return self.env['general.self.inspection'].search([('project_id', '=', self.project.id)])

    def test_other_project_type_is_rejected_and_nothing_is_created(self):
        """洞本身：POST 別案專屬樣板的 id 要被拒絕——不建立檢查（所以不會有項目被複製進來），
        導回表單頁並帶 error（不是 400）；資料庫約束的 SQL ERROR 也不可出現。"""
        inspection = self._create_inspection(self.other_type)
        self.assertFalse(inspection, '看不到的樣板不可建立檢查；建出來的檢查項目：%s'
                         % inspection.checklist_ids.mapped('check_item'))
        self.assertIn('error=inspection_type', self.last_response.url)

    def test_own_and_global_types_still_load_their_items(self):
        """正當入口不可壞：本案專屬樣板與全域樣板照常帶入項目。"""
        inspection = self._create_inspection(self.own_type)
        self.assertEqual(len(inspection), 1, '測資前提：建立了一張檢查')
        self.assertEqual(inspection.inspection_type_id, self.own_type)
        self.assertIn(OWN_ITEM, inspection.checklist_ids.mapped('check_item'))
        inspection.sudo().unlink()
        inspection = self._create_inspection(self.global_type)
        self.assertEqual(len(inspection), 1, '測資前提：建立了一張檢查')
        self.assertEqual(inspection.inspection_type_id, self.global_type)
        self.assertIn('全域樣板檢查項目', inspection.checklist_ids.mapped('check_item'))

    def test_no_create_path_reads_type_id_straight_from_post(self):
        """守衛：一般式與預約式兩條建立路徑都走 _posted_visible_type_id，沒人再直接 int(post[...])。
        預約式需要一整套通報單夾具；兩條路徑共用同一個 helper，這裡用原始碼檢查補上它。"""
        import os
        path = os.path.join(os.path.dirname(__file__), '..', 'controllers', 'portal_inspection.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertNotIn("int(post.get('inspection_type_id'", source)
        self.assertEqual(source.count("self._posted_visible_type_id(post)"), 2)
        self.assertEqual(source.count("if type_id is None:"), 2, '兩條路徑都要拒絕看不到的樣板')
