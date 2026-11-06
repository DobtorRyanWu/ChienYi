"""doc.document 範本自動填充測試（Sprint 16 補：選範本後內容空白 bug）。"""

from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestTemplateAutofill(TransactionCase):
    """確認用 template_id 建立 doc.document 時，content_html 會從 template 帶過來。

    背景：
        模型中 template_id 只是 Many2one，沒有任何 hook 把 template.content_html
        複製到新 doc.document.content_html，導致用戶選範本後開啟編輯器仍空白。
        Sprint 16 在 create() 加 hook 解決，本測試鎖死該行為。
    """

    def setUp(self):
        super().setUp()
        self.Doc = self.env['doc.document']
        self.Template = self.env['doc.template']
        self.tpl = self.Template.create({
            'name': '測試範本',
            'category': 'report',
            'page_format': 'A4',
            'content_html': '<h1>範本標題</h1><p>範本固定內容。</p>',
        })

    def test_create_with_template_copies_content_html(self):
        """建立文件時指定 template_id（不指定 content_html）→ content_html 應 = 範本內容。"""
        doc = self.Doc.create({
            'name': '從範本建立的文件',
            'template_id': self.tpl.id,
        })
        self.assertIn('範本標題', doc.content_html or '')
        self.assertIn('範本固定內容', doc.content_html or '')
        self.assertEqual(doc.template_id, self.tpl)

    def test_create_with_template_copies_page_format(self):
        """page_format 預設應從 template 帶過來（除非建立時已指定）。"""
        doc = self.Doc.create({
            'name': '頁面格式測試',
            'template_id': self.tpl.id,
        })
        self.assertEqual(doc.page_format, 'A4')

    def test_create_with_template_and_explicit_content_does_not_overwrite(self):
        """若建立時同時指定 content_html，不應被範本內容覆寫。"""
        doc = self.Doc.create({
            'name': '已有內容的文件',
            'template_id': self.tpl.id,
            'content_html': '<p>使用者已輸入的內容</p>',
        })
        self.assertIn('使用者已輸入', doc.content_html or '')
        self.assertNotIn('範本標題', doc.content_html or '')

    def test_create_without_template(self):
        """不指定 template_id 應如常運作（不應 throw）。"""
        doc = self.Doc.create({
            'name': '無範本文件',
        })
        # 沒指定 template_id 時 content_html 預設可空
        self.assertFalse(doc.template_id)

    def test_create_with_template_id_false(self):
        """template_id 顯式給 False（清空）→ 不應觸發 autofill，照常建立。"""
        doc = self.Doc.create({
            'name': '無範本文件 explicit False',
            'template_id': False,
        })
        self.assertFalse(doc.template_id)
        self.assertFalse((doc.content_html or '').strip())

    def test_onchange_template_fills_empty_content(self):
        """後台 Form view 選範本：onchange 應把 content_html 帶入（內容為空時）。"""
        new_doc = self.Doc.new({'name': '新建中'})
        new_doc.template_id = self.tpl
        new_doc._onchange_template_id()
        self.assertIn('範本標題', new_doc.content_html or '')

    def test_onchange_template_overwrites_existing_content_on_switch(self):
        """切換 template_id 時 onchange 應直接覆寫 content_html。

        Sprint 16 修正：原先「保護使用者已輸入」的邏輯反而讓「使用者切換範本」
        時看不到新範本內容（編輯器仍顯示舊範本）。改為顯式切換 = 顯式意圖
        要新範本，直接覆寫。"""
        tpl_b = self.Template.create({
            'name': '另一個範本',
            'category': 'letter',
            'page_format': 'A4',
            'content_html': '<h1>新範本標題</h1><p>新範本內容。</p>',
        })
        # 模擬：使用者先選 self.tpl，content_html 已是 self.tpl 內容（或編輯過）
        new_doc = self.Doc.new({
            'name': '新建中',
            'content_html': '<p>之前選的或使用者寫的</p>',
        })
        # 切換到 tpl_b
        new_doc.template_id = tpl_b
        new_doc._onchange_template_id()
        # 應該被新範本覆寫
        self.assertIn('新範本標題', new_doc.content_html or '')
        self.assertNotIn('之前選的或使用者寫的', new_doc.content_html or '')

    # ─── 2026-11-06：範本內容要真的進到編輯器 ──────────────────────────
    # 編輯器以 content_json 為主、content_html 只在 content_json 空時才拿來轉換
    # （static/src/components/doc_editor/doc_editor.js 的 executeSetHTML fallback）。
    # 所以只改 content_html、不清 content_json，畫面永遠是舊的。

    OLD_JSON = '{"main": [{"value": "第一次開啟時轉出來的舊內容"}]}'

    def test_onchange_template_clears_content_json(self):
        """切換範本要一併清 content_json，否則編輯器照樣讀舊的 content_json。"""
        new_doc = self.Doc.new({'name': '新建中', 'content_json': self.OLD_JSON})
        new_doc.template_id = self.tpl
        new_doc._onchange_template_id()
        self.assertIn('範本標題', new_doc.content_html or '')
        self.assertFalse(new_doc.content_json)

    def test_reapply_template_snapshots_then_resets_content(self):
        """「重新套用範本」：先存版本快照（可還原），再換成範本目前的內容。"""
        doc = self.Doc.create({'name': '已轉過的文件', 'template_id': self.tpl.id})
        doc.write({
            'content_json': self.OLD_JSON,
            'content_html': '<p>轉換後跑版的內容</p>',
            'page_format': 'A5',
        })
        # 文件建好之後範本才被修改：舊文件不會自己跟著變
        self.tpl.write({'content_html': '<h1>修改後的範本</h1>', 'page_format': 'A4'})
        versions_before = len(doc.versions_data or [])

        doc.action_reapply_template()

        self.assertFalse(doc.content_json)
        self.assertIn('修改後的範本', doc.content_html or '')
        self.assertEqual(doc.page_format, 'A4')
        versions = doc.versions_data or []
        self.assertEqual(len(versions), versions_before + 1)
        # 快照存的是「套用前」的內容，才能還原
        self.assertEqual(versions[-1]['content_json'], self.OLD_JSON)
        self.assertIn('轉換後跑版的內容', versions[-1]['content_html'])

    def test_reapply_template_without_template_raises(self):
        """沒有範本的文件不能重新套用，且不可動到內容。"""
        doc = self.Doc.create({'name': '無範本', 'content_json': self.OLD_JSON})
        with self.assertRaises(UserError):
            doc.action_reapply_template()
        self.assertEqual(doc.content_json, self.OLD_JSON)
        self.assertFalse(doc.versions_data)

    # ─── 2026-11-06 抗辯（red-team）補的三條 ─────────────────────────

    def test_switch_template_on_saved_doc_keeps_content(self):
        """已存檔、有內容的文件在表單切換範本再儲存：原稿不可以被抹掉（要改用重新套用）。

        走真的表單（view 裡 content_json 是 invisible 宣告，onchange 改了就會被一起存回去）。
        """
        tpl_b = self.Template.create({'name': '範本B', 'content_html': '<h1>範本B</h1>'})
        doc = self.Doc.create({'name': '人工編輯過的文件', 'template_id': self.tpl.id})
        doc.write({'content_json': self.OLD_JSON, 'content_html': '<p>人工編輯的內容</p>'})

        with Form(doc) as form:
            form.template_id = tpl_b

        self.assertEqual(doc.template_id, tpl_b)
        self.assertEqual(doc.content_json, self.OLD_JSON)
        self.assertIn('人工編輯的內容', doc.content_html or '')

    def test_reapply_template_refuses_empty_template(self):
        """範本沒有內容時不准重新套用（否則文件被清成空白）。"""
        empty_tpl = self.Template.create({'name': '空範本', 'content_html': ''})
        doc = self.Doc.create({'name': '文件', 'template_id': empty_tpl.id})
        doc.write({'content_json': self.OLD_JSON})
        with self.assertRaises(UserError):
            doc.action_reapply_template()
        self.assertEqual(doc.content_json, self.OLD_JSON)

    def test_restore_after_reapply_brings_back_page_format(self):
        """重新套用改了紙張格式；從快照還原要連紙張格式一起回去。"""
        doc = self.Doc.create({'name': '文件', 'template_id': self.tpl.id})
        doc.write({'content_json': self.OLD_JSON, 'page_format': 'A5', 'page_orientation': 'portrait'})
        doc.action_reapply_template()
        self.assertEqual(doc.page_format, 'A4')
        snapshot = doc.versions_data[-1]
        # 套用之後使用者又改了方向；還原要回到快照當時的「大小＋方向」，不是拼出 A5 橫向
        doc.write({'page_orientation': 'landscape'})

        doc.restore_version(snapshot['version_no'])
        self.assertEqual(doc.page_format, 'A5')
        self.assertEqual(doc.page_orientation, 'portrait')
        self.assertEqual(doc.content_json, self.OLD_JSON)
