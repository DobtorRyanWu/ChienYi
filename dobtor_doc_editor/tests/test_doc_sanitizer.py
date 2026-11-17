"""文件內容不能帶會在別人瀏覽器執行的東西（2026-11-17）。

背景（2026-11-06 抗辯發現、11-17 dev 重現）：
- doc.sanitizer 一直是 no-op：包 <div> 後 lxml 解析成 html>body>div，走訪時把不在白名單的 <body>
  拆掉，之後 root.find('.//body/div') 恆為 None → 原樣回傳輸入。<script>、onerror 全部存得進去。
- 前台協作者可寫 content_html＋清空 content_json → 內部人員開編輯器，canvas-editor 的 executeSetHTML
  把 HTML 用 innerHTML 塞進掛在 document 上的 shadow root → onerror 以內部人員的後台身分執行。
- content_json 完全不經過消毒：canvas-editor 遇到 block 元素會建 iframe，sandbox 沒給就是
  allow-scripts＋allow-same-origin，srcdoc 裡的 script 同源執行；超連結 url 沒擋 javascript:。

修法：sanitizer 真的生效（拆掉的標籤底下也要消毒、網址先正規化再比白名單、失敗不回原文）；
content_json 存檔時移除 block 元素、超連結只放行 http/https/mailto/tel／相對路徑。
白名單補上 dev 語料與 canvas-editor getHTML() 實際會產生的格式，第一次生效時不能吃掉欄寬與底色。
"""

import collections
import importlib.util
import json
import os
import re
from unittest.mock import patch

from lxml import html as lxml_html
from markupsafe import Markup

from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.dobtor_doc_editor.models import doc_sanitizer as sanitizer_module

from .scope_fixture import scope_portal_as_contractor

JINJA_RE = re.compile(r'\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}', re.S)
EVENT_ATTR_RE = re.compile(r'\son[a-z]+\s*=', re.I)
LARGE_DOC_BYTES = 600 * 1024   # 大於 doc_document.CONTENT_SIZE_THRESHOLD（500 KB），走附件路徑
MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'migrations', '18.0.2.4.9', 'post-migration.py')

IFRAME_BLOCK = {
    'type': 'block', 'value': '', 'height': 60,
    'block': {'type': 'iframe', 'iframeBlock': {'srcdoc': '<script>top.__xss=1</script>'}},
}


def _text(html):
    """去空白後的純文字（比對消毒前後有沒有掉字）。"""
    html = str(html or '')
    if not html.strip():
        return ''
    return re.sub(r'\s+', '', lxml_html.fragment_fromstring(html, create_parent='div').text_content())


def _inventory(html):
    """（標籤）、（標籤, 屬性）、（標籤, css 屬性）出現次數；比對消毒有沒有吃掉正常格式。"""
    inv = collections.Counter()
    html = str(html or '')
    if not html.strip():
        return inv
    root = lxml_html.fragment_fromstring(html, create_parent='div')
    for el in root.iter():
        if el is root or not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        inv[(tag,)] += 1
        for attr, val in el.attrib.items():
            inv[(tag, attr.lower())] += 1
            if attr.lower() == 'style':
                for decl in val.split(';'):
                    if ':' in decl:
                        inv[(tag, 'css:' + decl.split(':', 1)[0].strip().lower())] += 1
    return inv


def _walk(node):
    """canvas content_json 的所有 dict（遞迴）。"""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestDocSanitizerHtml(TransactionCase):

    def setUp(self):
        super().setUp()
        self.S = self.env['doc.sanitizer']

    def clean(self, html):
        return self.S.sanitize_html(html)

    def assertNoExecutable(self, out):
        low = str(out).lower()
        self.assertNotIn('<script', low)
        self.assertNotIn('<iframe', low)
        self.assertNotIn('<svg', low)
        self.assertIsNone(EVENT_ATTR_RE.search(str(out)), out)
        self.assertNotIn('javascript', low)

    # ── 會執行的東西要拿掉 ──────────────────────────────────────────

    def test_script_removed_text_kept(self):
        out = self.clean('<p>甲</p><script>alert(1)</script><p>乙</p>')
        self.assertNoExecutable(out)
        self.assertNotIn('alert', out)
        self.assertEqual(_text(out), '甲乙')

    def test_event_handlers_removed(self):
        out = self.clean('<p onclick="x()">字</p><img src="x" onerror="alert(1)">')
        self.assertNoExecutable(out)
        self.assertIn('<img src="x"', out)
        self.assertEqual(_text(out), '字')

    def test_children_of_unwrapped_tags_are_sanitized(self):
        """舊版拆掉非白名單標籤時，搬上來的子元素沒再消毒。"""
        for payload in (
            '<font><img src="x" onerror="alert(1)"></font>',
            '<custom><p onmouseover="alert(1)">字</p></custom>',
            '<center><font><a href="javascript:alert(1)">連</a></font></center>',
            '<svg><animate onbegin="alert(1)" attributeName="x"></animate></svg>',
            '<math><mtext><img src="x" onerror="alert(1)"></mtext></math>',
            '<noscript><img src="x" onerror="alert(1)"></noscript>',
            '<template><img src="x" onerror="alert(1)"></template>',
        ):
            with self.subTest(payload=payload):
                self.assertNoExecutable(self.clean(payload))

    def test_tail_text_kept(self):
        out = self.clean('<p>a<custom>b</custom>c<script>x</script>d<!-- 註解 -->e</p>')
        self.assertEqual(_text(out), 'abcde')

    def test_style_and_title_content_not_leaked_as_text(self):
        out = self.clean('<style>p{color:red}</style><title>標題</title><p>內文</p>')
        self.assertEqual(_text(out), '內文')

    def test_dangerous_href_schemes_removed(self):
        for href in (
            'javascript:alert(1)', 'JaVaScRiPt:alert(1)', '  javascript:alert(1)',
            'java\tscript:alert(1)', 'java&#x09;script:alert(1)', 'jav&#x0A;ascript:alert(1)',
            '&#106;avascript:alert(1)', '\x01javascript:alert(1)', 'vbscript:msgbox(1)',
            'data:text/html,<script>alert(1)</script>', 'data:image/svg+xml,<svg onload=alert(1)>',
        ):
            with self.subTest(href=href):
                out = self.clean(f'<a href="{href}">連結</a>')
                self.assertNotIn('href', out)
                self.assertEqual(_text(out), '連結')

    def test_safe_hrefs_kept(self):
        for href in ('https://example.com/a?b=1', 'http://x.y', 'mailto:a@b.c', 'tel:0223456789',
                     '/web#id=1', '#top', 'page.html', '?q=1'):
            with self.subTest(href=href):
                self.assertIn(f'href="{href}"', self.clean(f'<a href="{href}">連結</a>'))

    def test_img_src(self):
        self.assertIn('src="data:image/png;base64,AAAA"', self.clean('<img src="data:image/png;base64,AAAA">'))
        self.assertIn('src="https://a.b/c.png"', self.clean('<img src="https://a.b/c.png">'))
        for src in ('javascript:alert(1)', 'data:text/html,x', 'vbscript:x'):
            with self.subTest(src=src):
                self.assertNotIn('src=', self.clean(f'<img src="{src}">'))

    def test_dangerous_css_removed(self):
        out = self.clean('<p style="color: red; background: url(javascript:alert(1)); '
                         'width: expression(alert(1))">字</p>')
        self.assertIn('color: red', out)
        self.assertNotIn('url(', out)
        self.assertNotIn('expression', out)
        # CSS 跳脫可以拼出 url(／expression(，含反斜線的宣告一律丟
        out = self.clean('<p style="background: u\\72l(https://evil); color: blue">字</p>')
        self.assertNotIn('\\', out)
        self.assertIn('color: blue', out)

    def test_inputs(self):
        """canvas-editor getHTML() 會把核取方塊／單選輸出成 <input>；其他 input 一律不留。"""
        self.assertIn('checked', self.clean('<input type="checkbox" checked="true">'))
        self.assertIn('type="radio"', self.clean('<input type="radio">'))
        out = self.clean('<input type="checkbox" onclick="alert(1)" formaction="javascript:x" name="n">')
        self.assertIn('type="checkbox"', out)
        self.assertNoExecutable(out)
        self.assertNotIn('formaction', out)
        for payload in ('<input type="text" autofocus onfocus="alert(1)">', '<input>',
                        '<input type="image" src="x">', '<input type="hidden" value="x">'):
            with self.subTest(payload=payload):
                self.assertNotIn('<input', self.clean(payload))

    def test_fail_closed(self):
        """解析失敗時不能把原文原樣回傳（舊版 except: pass → return html_content）。"""
        with patch.object(sanitizer_module, '_parse_fragment', side_effect=ValueError('boom')):
            out = self.clean('<img src="x" onerror="alert(1)">')
        self.assertNotIn('<img', out)
        self.assertIn('&lt;img', out)

    def test_empty_inputs(self):
        self.assertEqual(self.clean(''), '')
        self.assertIsNone(self.clean(None))
        self.assertFalse(self.clean(False))
        self.assertEqual(self.clean('   ').strip(), '')

    def test_markup_input(self):
        out = self.clean(Markup('<p>x</p><script>1</script>'))
        self.assertNotIn('<script', str(out))
        self.assertIn('<p>x</p>', str(out))

    def test_report_flags_only_dangerous(self):
        """migration 用 report 判斷「要不要改這份文件」：良性但非白名單的格式不算危險。"""
        _clean, hits = self.S._sanitize_html_report('<p>ok</p><font color="red">字</font>')
        self.assertEqual(hits, [])
        for payload in ('<img src=x onerror=alert(1)>', '<script>1</script>',
                        '<a href="javascript:x">a</a>', '<p style="width:expression(1)">a</p>'):
            with self.subTest(payload=payload):
                _clean, hits = self.S._sanitize_html_report(payload)
                self.assertTrue(hits)

    # ── 正常格式不能被吃掉 ────────────────────────────────────────────

    def test_table_formatting_kept(self):
        """dev 語料與 canvas-editor getHTML() 實際用到、舊白名單沒有的格式。"""
        html = (
            '<table border="1" cellpadding="4" cellspacing="0" style="width:100%">'
            '<colgroup><col width="120"><col width="200"></colgroup>'
            '<tr style="background:#f0f0f0"><td width="30%" data-field="x" '
            'style="text-align-last: justify; justify-content: center; text-decoration-style: dashed">甲</td>'
            '<th width="70%" style="background-color: #eee">乙</th></tr></table>'
        )
        out = self.clean(html)
        self.assertEqual(_inventory(out), _inventory(html))
        self.assertEqual(_text(out), '甲乙')

    def test_jinja_tokens_kept(self):
        html = ('<p>{{ object.name }}</p><table><tr><td>{% if x %}是{% endif %}</td></tr></table>'
                '<p>{# 註 #}《工程名稱》</p>')
        out = self.clean(html)
        self.assertEqual(JINJA_RE.findall(out), JINJA_RE.findall(html))
        self.assertIn('《工程名稱》', out)

    def test_idempotent(self):
        for html in ('<p>a<font>b</font></p><img src=x onerror=1>',
                     '<table border="1"><tr><td style="background:#eee">x</td></tr></table>',
                     '<ul><li>一</li></ul><a href="java\tscript:1">a</a>'):
            with self.subTest(html=html):
                once = self.clean(html)
                self.assertEqual(self.clean(once), once)

    def test_all_templates_lossless(self):
        """庫裡所有範本消毒後：純文字、Jinja 標記、標籤／屬性／CSS 屬性清單完全不變，二次消毒不變。"""
        templates = self.env['doc.template'].sudo().with_context(active_test=False).search([])
        checked = 0
        for tpl in templates:
            html = str(tpl.content_html or '')
            if not html.strip():
                continue
            checked += 1
            with self.subTest(template=tpl.id, name=tpl.name):
                out = self.clean(html)
                self.assertEqual(_text(out), _text(html))
                self.assertEqual(JINJA_RE.findall(out), JINJA_RE.findall(html))
                self.assertEqual(_inventory(out), _inventory(html))
                self.assertEqual(self.clean(out), out)
        self.assertTrue(checked, '庫裡沒有任何有內容的範本，這個測試等於沒跑')


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestDocSanitizerCanvasJson(TransactionCase):

    def setUp(self):
        super().setUp()
        self.S = self.env['doc.sanitizer']

    def scrub(self, data):
        return json.loads(self.S.sanitize_canvas_json(json.dumps(data)))

    def assertNoBlock(self, data):
        for node in _walk(data):
            self.assertNotIn('block', node)
            self.assertNotEqual(node.get('type'), 'block')

    def test_top_level_block_removed(self):
        out = self.scrub([{'value': '甲'}, IFRAME_BLOCK, {'value': '乙'}])
        self.assertNoBlock(out)
        self.assertEqual([e['value'] for e in out], ['甲', '乙'])

    def test_nested_block_removed(self):
        table = {'type': 'table', 'value': '', 'trList': [{'tdList': [
            {'value': [{'value': '格'}, IFRAME_BLOCK]}]}]}
        out = self.scrub([table])
        self.assertNoBlock(out)
        self.assertEqual(out[0]['trList'][0]['tdList'][0]['value'], [{'value': '格'}])

    def test_header_main_footer_shape(self):
        out = self.scrub({'header': [IFRAME_BLOCK], 'main': [{'value': 'a'}, IFRAME_BLOCK], 'footer': []})
        self.assertNoBlock(out)
        self.assertEqual(out['main'], [{'value': 'a'}])

    def test_hyperlink_urls(self):
        def link(url):
            return {'type': 'hyperlink', 'value': '', 'url': url, 'valueList': [{'value': '點我'}]}
        for url in ('javascript:alert(1)', 'java\tscript:alert(1)', ' JAVASCRIPT:1', 'data:text/html,x',
                    'vbscript:1'):
            with self.subTest(url=url):
                out = self.scrub([link(url)])
                self.assertNotIn('url', out[0])
                self.assertEqual(out[0]['valueList'], [{'value': '點我'}])
        for url in ('https://example.com', 'mailto:a@b.c', '/web#id=1'):
            with self.subTest(url=url):
                self.assertEqual(self.scrub([link(url)])[0]['url'], url)

    def test_benign_json_returned_unchanged(self):
        """沒改到東西就回原字串：不重新序列化（不製造無關差異）。"""
        raw = '[{"value":"甲","bold":true},{"type":"table","trList":[]}]'
        self.assertIs(self.S.sanitize_canvas_json(raw), raw)

    def test_unparseable_left_as_is(self):
        """編輯器也解不開（JSON.parse 失敗→空白開始），原樣保留。"""
        for raw in ('not json', "{'a': 1}", ''):
            with self.subTest(raw=raw):
                self.assertEqual(self.S.sanitize_canvas_json(raw), raw)
        self.assertFalse(self.S.sanitize_canvas_json(False))
        self.assertIsNone(self.S.sanitize_canvas_json(None))

    def test_report(self):
        _clean, hits = self.S._sanitize_canvas_json_report(json.dumps([{'value': 'a'}]))
        self.assertEqual(hits, [])
        _clean, hits = self.S._sanitize_canvas_json_report(json.dumps([IFRAME_BLOCK]))
        self.assertTrue(hits)


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestDocumentWritePaths(TransactionCase):
    """原始攻擊鏈：前台協作者寫、內部人員讀。存進去的就要是乾淨的。"""

    def setUp(self):
        super().setUp()
        self.portal = new_test_user(
            self.env, login='doc_xss_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal')
        scope_portal_as_contractor(self.env, self.portal)
        self.internal = new_test_user(
            self.env, login='doc_xss_internal',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        self.doc = self.env['doc.document'].create({
            'name': 'XSS 測試文件', 'content_html': '<p>原文</p>',
            'collaborator_ids': [(6, 0, [self.portal.id, self.internal.id])]})

    def test_portal_write_html_sanitized(self):
        self.doc.with_user(self.portal).write({
            'content_html': '<p>嗨</p><img src="x" onerror="alert(1)">', 'content_json': False,
            'header_html': '<p onclick="alert(1)">頁首</p>'})
        self.assertNotIn('onerror', self.doc.get_content_html())
        self.assertIn('嗨', self.doc.get_content_html())
        self.assertNotIn('onclick', str(self.doc.header_html))

    def test_portal_write_json_scrubbed(self):
        self.doc.with_user(self.portal).write({
            'content_json': json.dumps([{'value': '甲'}, IFRAME_BLOCK])})
        self.assertNotIn('srcdoc', self.doc.content_json)
        self.assertEqual(json.loads(self.doc.content_json), [{'value': '甲'}])

    def test_create_scrubs_json(self):
        doc = self.env['doc.document'].create({
            'name': '建立', 'content_json': json.dumps([IFRAME_BLOCK, {'value': 'x'}])})
        self.assertNotIn('srcdoc', doc.content_json)

    def test_large_document_sanitized(self):
        filler = '<p>' + ('字' * 1000) + '</p>'
        html = filler * (LARGE_DOC_BYTES // len(filler.encode('utf-8')) + 1) + '<script>alert(1)</script>'
        # 前台帳號存大文件本來就會被 ir.attachment.check 擋（非內部帳號一律拒絕），這裡用內部帳號走附件路徑
        self.doc.with_user(self.internal).write({'content_html': html})
        self.assertTrue(self.doc.is_large_document)
        self.assertNotIn('<script', self.doc.get_content_html())

    def test_template_autofill_sanitized_format_kept(self):
        tpl = self.env['doc.template'].sudo().create({
            'name': 'XSS 範本',
            'content_html': ('<table border="1" cellpadding="4"><colgroup><col width="100"></colgroup>'
                             '<tr style="background:#f0f0f0"><td>表頭</td></tr></table>'
                             '<script>alert(1)</script>')})
        doc = self.env['doc.document'].create({'name': '從範本', 'template_id': tpl.id})
        html = doc.get_content_html()
        self.assertNotIn('<script', html)
        # style 會被正規化成「屬性: 值」
        for needle in ('border="1"', 'cellpadding="4"', 'width="100"', 'background: #f0f0f0'):
            self.assertIn(needle, html)

    def test_restore_tampered_version_sanitized(self):
        """versions_data 前台寫得到；還原（內部人員按的）也要經過消毒。"""
        self.doc.with_user(self.portal).write({'versions_data': [{
            'version_no': 99, 'label': '假快照',
            'content_html': '<img src="x" onerror="alert(1)">',
            'content_json': json.dumps([IFRAME_BLOCK]),
        }]})
        self.doc.with_user(self.internal).restore_version(99)
        self.assertNotIn('onerror', self.doc.get_content_html())
        self.assertNotIn('srcdoc', self.doc.content_json or '')


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestSaveRouteSanitized(HttpCase):
    """前台編輯器實際走的 /dobtor_doc/save。"""

    def setUp(self):
        super().setUp()
        self.portal = new_test_user(
            self.env, login='doc_xss_http_portal', password='doc_xss_http_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal')
        scope_portal_as_contractor(self.env, self.portal)
        self.doc = self.env['doc.document'].create({
            'name': 'HTTP 存檔', 'content_html': '<p>原文</p>',
            'collaborator_ids': [(6, 0, [self.portal.id])]})

    def test_portal_save_route(self):
        self.authenticate('doc_xss_http_portal', 'doc_xss_http_portal')
        result = self.make_jsonrpc_request('/dobtor_doc/save', {
            'doc_id': self.doc.id,
            'content_html': '<p>改</p><img src="x" onerror="alert(1)">',
            'content_json': json.dumps([{'value': '改'}, IFRAME_BLOCK]),
        })
        self.assertTrue(result.get('success'), result)
        self.doc.invalidate_recordset()
        self.assertNotIn('onerror', self.doc.get_content_html())
        self.assertIn('改', self.doc.get_content_html())
        self.assertNotIn('srcdoc', self.doc.content_json)


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestSanitizeMigration(TransactionCase):
    """換版時清掉「已經存進去」的危險內容；良性文件一律不動。"""

    def _migrate(self):
        spec = importlib.util.spec_from_file_location('doc_sanitize_migration_2_4_9', MIGRATION_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '18.0.2.4.8')
        self.env.invalidate_all()

    def test_only_dangerous_documents_rewritten(self):
        Doc = self.env['doc.document']
        bad = Doc.create({'name': '舊的惡意文件', 'content_html': '<p>x</p>'})
        good = Doc.create({'name': '舊的良性文件', 'content_html': '<p>x</p>'})
        # 繞過 ORM（模擬修補前存進去的資料）：良性文件故意用非白名單但無害的寫法
        benign_html = '<p><font color="red">紅字</font></p>'
        # 先把 create 的待寫入送出，否則之後 flush 會蓋掉下面用 SQL 設的 write_date
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE doc_document SET content_html = %s, content_json = %s WHERE id = %s",
            ['<p>舊</p><img src="x" onerror="alert(1)">', json.dumps([IFRAME_BLOCK]), bad.id])
        self.env.cr.execute(
            "UPDATE doc_document SET content_html = %s, content_json = %s, "
            "write_date = '2020-01-01 00:00:00' WHERE id = %s",
            [benign_html, '[{"value":"a"}]', good.id])
        self.env.invalidate_all()

        self._migrate()

        self.assertNotIn('onerror', bad.get_content_html())
        self.assertIn('舊', bad.get_content_html())
        self.assertNotIn('srcdoc', bad.content_json)
        self.assertEqual(str(good.content_html), benign_html)
        self.assertEqual(good.content_json, '[{"value":"a"}]')
        self.assertEqual(str(good.write_date), '2020-01-01 00:00:00')


# ── 抗辯 red-team 第 1 輪（2026-11-17）的可重現案例 ─────────────────────

JINJA_BUILT_TAG = ("<p>{{ ('%c'|format(60)) ~ 'img src=x onerror=alert(1)' ~ ('%c'|format(62)) }}</p>")
DEEP_JSON_DEPTH = 5000
HUGE_INT_DIGITS = 5000


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestRedTeamRound1(TransactionCase):

    def setUp(self):
        super().setUp()
        self.S = self.env['doc.sanitizer']
        self.doc = self.env['doc.document'].create({'name': '抗辯', 'content_html': '<p>x</p>'})

    def test_r1_jinja_cannot_build_tags_after_sanitize(self):
        """#1：存檔時看不到 Jinja 渲染後才組出的標籤 → 渲染出口要再消毒。"""
        stored = self.S.sanitize_html(JINJA_BUILT_TAG)
        for with_chip in (True, False):
            with self.subTest(with_chip=with_chip):
                out = self.doc._render_template(stored, self.doc, with_chip=with_chip)
                self.assertIsNone(EVENT_ATTR_RE.search(out), out)

    def test_r2_huge_integer_does_not_bypass_block_removal(self):
        """#2：超過 Python 整數位數上限時 json.loads 失敗，瀏覽器卻解得開。"""
        payload = '[' + json.dumps(IFRAME_BLOCK) + ',{"value":' + '9' * HUGE_INT_DIGITS + '}]'
        out, hits = self.S._sanitize_canvas_json_report(payload)
        self.assertTrue(hits)
        self.assertNotIn('srcdoc', out)

    def test_r3_non_string_url_removed(self):
        """#3：陣列會被瀏覽器轉成字串再當網址。"""
        raw = json.dumps([{'type': 'hyperlink', 'url': ['javascript:alert(1)'], 'valueList': [{'value': 'x'}]}])
        out, hits = self.S._sanitize_canvas_json_report(raw)
        self.assertTrue(hits)
        self.assertNotIn('url', json.loads(out)[0])
        # null 不算：瀏覽器端 `O.url && …` 直接略過
        raw = json.dumps([{'type': 'hyperlink', 'url': None, 'valueList': [{'value': 'x'}]}])
        self.assertIs(self.S.sanitize_canvas_json(raw), raw)

    def test_r4_css_external_resources_removed(self):
        """#4：任一處有 data:image 就整條放行；image-set() 不含 url( 也會外連。"""
        for style in ('background: url(http://evil.example/x) url(data:image/png,AAA)',
                      "background: image-set('http://evil.example/x.png' 1x)",
                      "background: -webkit-image-set('http://evil.example/x.png' 1x)"):
            with self.subTest(style=style):
                out = self.S.sanitize_html(f'<p style="{style}; color: red">a</p>')
                self.assertNotIn('evil', out)
                self.assertIn('color: red', out)
        # 正常寫法照留
        out = self.S.sanitize_html('<p style="color: rgb(73, 80, 87); background: url(data:image/png,AAA)">a</p>')
        self.assertIn('rgb(73, 80, 87)', out)
        self.assertIn('url(data:image/png,AAA)', out)

    def test_r5_deep_json_fails_closed_and_migration_survives(self):
        """#5：巢狀太深 RecursionError → 存檔失敗、migration 整個崩潰。"""
        deep = '[' * DEEP_JSON_DEPTH + json.dumps(IFRAME_BLOCK) + ']' * DEEP_JSON_DEPTH
        out, hits = self.S._sanitize_canvas_json_report(deep)
        self.assertEqual(out, '')
        self.assertTrue(hits)
        # 修補前就存進去的深巢狀文件：migration 不能崩，要清掉
        self.env.flush_all()
        self.env.cr.execute("UPDATE doc_document SET content_json = %s WHERE id = %s", [deep, self.doc.id])
        self.env.invalidate_all()
        TestSanitizeMigration._migrate(self)
        self.assertFalse(self.doc.content_json)


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestTemplatePreviewSanitized(HttpCase):
    """#1 的另一個出口：/dobtor_doc/template_preview 用自己的 Jinja 環境渲染。"""

    def test_template_preview(self):
        user = new_test_user(self.env, login='doc_xss_tpl_internal', password='doc_xss_tpl_internal',
                             groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        doc = self.env['doc.document'].create({'name': '範本預覽', 'content_html': JINJA_BUILT_TAG,
                                               'collaborator_ids': [(6, 0, [user.id])]})
        self.authenticate('doc_xss_tpl_internal', 'doc_xss_tpl_internal')
        result = self.make_jsonrpc_request('/dobtor_doc/template_preview', {
            'doc_id': doc.id, 'context': {'x': '1'}})
        self.assertTrue(result.get('success'), result)
        self.assertNotIn('onerror', result['html'])


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestRedTeamRound2(TransactionCase):
    """抗辯 red-team 第 2 輪（2026-11-17）的可重現案例。"""

    def setUp(self):
        super().setUp()
        self.S = self.env['doc.sanitizer']

    def test_data_url_with_semicolon_kept(self):
        """data:image/png;base64 的分號不能被當成宣告分隔（舊版切成殘缺的 url(data:image/png）。"""
        out = self.S.sanitize_html(
            '<p style="background: url(data:image/png;base64,iVBOR); color: red">a</p>')
        self.assertIn('url(data:image/png;base64,iVBOR)', out)
        self.assertIn('color: red', out)
        # 括號沒閉合時剩下的整段當一條宣告，照樣過函式白名單與 url 檢查
        out = self.S.sanitize_html(
            '<p style="background: url(data:image/png,a; color: url(http://evil.example/x)">a</p>')
        self.assertNotIn('evil', out)

    def test_lone_surrogate_survives_rewrite(self):
        """命中後重新序列化：孤立代理字元要保留跳脫，否則存檔／migration 寫回時編碼失敗。"""
        raw = '[{"type":"hyperlink","url":"javascript:1","valueList":[{"value":"\\ud800"}]}]'
        out, hits = self.S._sanitize_canvas_json_report(raw)
        self.assertTrue(hits)
        out.encode('utf-8')   # 不可丟 UnicodeEncodeError
        self.assertEqual(json.loads(out)[0]['valueList'][0]['value'], '\ud800')
