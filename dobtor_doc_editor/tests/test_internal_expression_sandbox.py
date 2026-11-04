"""內部編輯者寫的運算式也要跑在加固沙箱裡（2026-11-04）。

背景（拷貝庫實跑重現）：
    - 預覽別名（controllers/doc_controller.py preview_content_json）用一般 SandboxedEnvironment，
      又把活的 record／user 傳進去。內部代操（group_doc_editor，不是系統管理者）寫別名
      `user.sudo().write({'groups_id': [(4, 系統管理群組)]})` 後按預覽，就變成系統管理者。
    - 套印 docx（fill_template）用 docxtpl 預設、沒有沙箱的 Jinja2，上傳的樣板可以走到 Python 內部。
匯出（doc.render.mixin._render_template）早就用 _DocSandboxedEnvironment＋_SafeRecordProxy，
這裡把預覽與套印改成同一套，所以預覽看到的也就是匯出會印出的值。
"""
import base64
import io
import json

from jinja2.exceptions import SecurityError

from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.dobtor_doc_editor.controllers.doc_controller import DocEditorController


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestInternalExpressionSandbox(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ctrl = DocEditorController()
        self.editor = new_test_user(
            self.env, login='doc_sandbox_editor',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        self.system = self.env.ref('base.group_system')
        self.partner = self.env['res.partner'].create({'name': '沙箱測試對象'})

    def _doc(self, **vals):
        return self.env['doc.document'].create(dict({
            'name': '沙箱測試文件',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'res_id': self.partner.id,
            'collaborator_ids': [(6, 0, [self.editor.id])]}, **vals))

    def test_rig_editor_is_not_system(self):
        self.assertFalse(self.editor.has_group('base.group_system'))

    def test_preview_alias_cannot_escalate(self):
        doc = self._doc(
            field_aliases={'esc': "user.sudo().write({'groups_id': [(4, %d)]})" % self.system.id,
                           'nm': 'object.name'},
            content_json=json.dumps({'main': [{'value': '{{ esc }} {{ nm }}'}]}))
        with MockRequest(self.env(user=self.editor)):
            result = self.ctrl.preview_content_json(doc.id)
        self.env.invalidate_all()
        self.assertFalse(self.editor.has_group('base.group_system'),
                         '別名運算式不可讓編輯者把自己升成系統管理者')
        # 正當的別名（取欄位值）照常算得出來
        self.assertIn('沙箱測試對象', json.dumps(result, ensure_ascii=False))

    def _docx(self, text):
        import docx
        d = docx.Document()
        d.add_paragraph(text)
        buf = io.BytesIO()
        d.save(buf)
        return base64.b64encode(buf.getvalue())

    def test_fill_template_is_sandboxed(self):
        doc = self._doc(template_docx=self._docx("{{ ''.__class__.__mro__ }}"))
        with MockRequest(self.env(user=self.editor)):
            with self.assertRaises(SecurityError):
                self.ctrl.fill_template(doc.id, context={}, output_format='docx')

    def test_fill_template_plain_variables_still_work(self):
        doc = self._doc(template_docx=self._docx('甲方：{{ party }}'))
        with MockRequest(self.env(user=self.editor)):
            result = self.ctrl.fill_template(doc.id, context={'party': '沙箱測試甲方'}, output_format='docx')
        self.assertTrue(result.get('success'), result)
        import docx
        text = '\n'.join(p.text for p in docx.Document(io.BytesIO(base64.b64decode(result['content']))).paragraphs)
        self.assertIn('沙箱測試甲方', text)
