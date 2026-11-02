# -*- coding: utf-8 -*-
"""說明書發現問題的回歸（2026-11-02）。

- 版本訊息：message_post 傳純字串會被 escape，畫面顯示 `<p><strong>版本 v1</strong></p>`；
  改傳 Markup，動態值（版本說明）要跳脫。
- B25：「我的文件」預設只看自己建立的，代操作員看到 0 筆 → action 不再預設篩選。
"""
from markupsafe import Markup

from odoo.tests.common import TransactionCase, tagged

XSS = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestManualFixes20261102(TransactionCase):

    def _last_body(self, doc):
        return self.env['mail.message'].search(
            [('model', '=', doc._name), ('res_id', '=', doc.id)],
            order='id desc', limit=1).body

    def test_version_message_is_markup_and_escapes_label(self):
        doc = self.env['doc.document'].create({'name': '版本訊息測試', 'content_html': '<p>x</p>'})
        doc.action_save_version(label=XSS)
        body = self._last_body(doc)
        self.assertIsInstance(body, Markup)
        self.assertIn('<strong>版本 v1</strong>', body, '標籤要是真的標籤')
        self.assertNotIn('&lt;strong&gt;', body, '標籤不可被當文字跳脫')
        self.assertNotIn('<script>', body, '版本說明的 <script> 必須被跳脫')
        self.assertIn('&lt;script&gt;', body)

    def test_b25_action_has_no_default_my_docs_filter(self):
        action = self.env.ref('dobtor_doc_editor.action_doc_document_list')
        self.assertNotIn('search_default_my_docs', action.context or '')
        # 篩選本身仍在搜尋視圖裡，可手動勾
        arch = self.env['doc.document'].get_view(view_type='search')['arch']
        self.assertIn('name="my_docs"', arch)
