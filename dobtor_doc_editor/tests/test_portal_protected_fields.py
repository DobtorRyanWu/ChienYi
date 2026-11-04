"""前台協作者不能改「會被當程式執行、或決定對哪筆資料執行」的欄位（2026-11-04）。

背景（拷貝庫實跑重現）：前台帳號被加成協作者後，ACL 1100＋規則「是協作者」讓它能經 RPC 寫：
    - field_aliases：預覽（controllers/doc_controller.py preview_content_json）用 SandboxedEnvironment
      執行別名運算式，又傳入可操作的 user／object → user.sudo().write(groups_id=base.group_system) 自升管理者
    - template_docx：套印（fill_template）用 docxtpl 預設、沒有沙箱的 Jinja2 → 伺服器執行程式
    - model_id／res_id／template_id：換掉運算式執行的對象與別名來源
    - collaborator_ids：自己決定誰能編輯
內文、頁首頁尾、名稱、版面設定照常可改（前台編輯器存檔只寫這些）。
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.dobtor_doc_editor.models.doc_document import PORTAL_PROTECTED_FIELDS


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestPortalProtectedFields(TransactionCase):

    def setUp(self):
        super().setUp()
        self.portal = new_test_user(
            self.env, login='doc_protect_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal')
        self.internal = new_test_user(
            self.env, login='doc_protect_internal',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        self.doc = self.env['doc.document'].create({
            'name': '協作文件', 'content_html': '<p>原文</p>',
            'collaborator_ids': [(6, 0, [self.portal.id])]})
        self.partner_model = self.env['ir.model']._get('res.partner')

    def test_rig_portal_is_collaborator_and_can_edit_content(self):
        """正當入口：協作者照常改內文與名稱（前台編輯器存檔的欄位）。"""
        self.assertTrue(self.portal.share)
        self.doc.with_user(self.portal).write({
            'name': '協作者改名', 'content_html': '<p>協作者改內文</p>',
            'content_json': '{"main": []}', 'margin_top': 50})
        self.assertEqual(self.doc.name, '協作者改名')
        self.assertEqual(self.doc.margin_top, 50)

    def test_portal_cannot_write_protected_fields(self):
        attempts = {
            'field_aliases': {'名稱': 'user.sudo().write({})'},
            'template_docx': 'UEsDBA==',
            'model_id': self.partner_model.id,
            'model_name': 'res.users',   # res_id 的參照模型（related 存檔，可直接寫）
            'res_id': self.portal.partner_id.id,
            'collaborator_ids': [(4, self.internal.id)],
        }
        for field, value in attempts.items():
            with self.subTest(field=field):
                with self.assertRaises(AccessError):
                    self.doc.with_user(self.portal).write({field: value})
        self.assertFalse(self.doc.field_aliases)
        self.assertFalse(self.doc.template_docx)
        self.assertFalse(self.doc.model_id)
        self.assertEqual(self.doc.collaborator_ids, self.portal)

    def test_protected_fields_exist(self):
        """名單用欄位名稱比對；欄位改名時名單會靜默失效。"""
        missing = sorted(f for f in PORTAL_PROTECTED_FIELDS if f not in self.env['doc.document']._fields)
        self.assertFalse(missing, '保護名單裡的欄位不存在：%s' % missing)

    def test_internal_editor_unaffected(self):
        self.doc.write({'collaborator_ids': [(4, self.internal.id)]})
        self.doc.with_user(self.internal).write({'field_aliases': {'名稱': 'object.name'},
                                                  'model_id': self.partner_model.id})
        self.assertEqual(self.doc.model_id, self.partner_model)
