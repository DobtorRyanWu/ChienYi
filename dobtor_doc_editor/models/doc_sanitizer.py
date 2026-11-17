"""文件內容消毒：HTML（content_html 等）與 canvas 結構資料（content_json）。

2026-11-17 修補（tests/test_doc_sanitizer.py）：
- 舊版把輸入包成 <div> 後用 HTMLParser 解析成 html>body>div，走訪時把 <body> 當非白名單拆掉，
  之後 find('.//body/div') 恆為 None → 原樣回傳，等於從來沒消毒過。
- 舊版拆掉非白名單標籤時，搬上來的子元素沒有再檢查；例外時回傳原文（fail-open）。
- content_json 完全沒檢查：canvas-editor 的 block 元素會建 iframe（sandbox 由資料決定，
  預設 allow-scripts＋allow-same-origin），超連結 url 直接進 href／window.open。
"""

import html as html_lib
import json
import logging
import re

from lxml import etree
from lxml import html as lxml_html
from odoo import models

_logger = logging.getLogger(__name__)

# 允許的 HTML 標籤白名單
ALLOWED_TAGS = {
    'p', 'div', 'span', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'blockquote', 'pre', 'code',
    'ul', 'ol', 'li',
    'table', 'colgroup', 'col', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
    'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'sub', 'sup', 'mark',
    'a', 'img',
    # canvas-editor getHTML() 把核取方塊／單選輸出成 <input>；只留這兩種（見 INPUT_TYPES）
    'input',
}

# 連內容整塊移除的標籤（不拆開保留內容：裡面的文字是程式碼／樣式，或是另一套解析規則）
DROP_WITH_CONTENT_TAGS = {
    'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet',
    'form', 'textarea', 'button', 'select', 'option', 'base', 'meta', 'link', 'title', 'head',
    'noscript', 'template', 'svg', 'math', 'video', 'audio', 'source', 'track', 'canvas',
}

# 這些標籤出現就代表內容可能會執行（migration 用來判斷要不要改寫舊文件）
DANGEROUS_TAGS = DROP_WITH_CONTENT_TAGS - {'style', 'title', 'head', 'meta'}

INPUT_TYPES = {'checkbox', 'radio'}
INPUT_ATTRIBUTES = {'type', 'checked', 'disabled'}

# 允許的屬性（按標籤）
ALLOWED_ATTRIBUTES = {
    '*': ['class', 'style', 'id', 'title', 'dir', 'lang'],
    'a': ['href', 'target', 'rel'],
    'img': ['src', 'alt', 'width', 'height'],
    # width：canvas-editor 只從 <col width> 讀欄寬（html_table_colwidth.js 也讀 td/th 的 width）
    'td': ['colspan', 'rowspan', 'width'],
    'th': ['colspan', 'rowspan', 'scope', 'width'],
    'col': ['span', 'width'],
    'colgroup': ['span'],
    # 表格框線：canvas-editor getHTML() 與 LibreOffice 匯入都會寫（dev 語料 155 處）
    'table': ['border', 'cellpadding', 'cellspacing'],
    # 清單 HTML 屬性（LibreOffice 及自訂清單類型）
    'ol': ['type', 'start'],
    'ul': ['type'],
    'li': ['value'],
    # 文件編輯器自訂屬性
    'span': ['data-expression', 'data-field', 'data-field-label', 'contenteditable'],
    'div': ['data-expression', 'data-field', 'data-field-label', 'contenteditable',
            'data-page-break', 'data-page', 'data-page-gap'],
}

# 允許的 CSS 屬性
ALLOWED_CSS = {
    'color', 'background-color', 'font-size', 'font-family', 'font-weight',
    'font-style', 'text-align', 'text-decoration', 'line-height',
    # 範本表頭底色寫成 background 簡寫（範本 3、5）；url() 仍只准 data:image
    'background',
    # canvas-editor getHTML() 會輸出
    'text-align-last', 'justify-content', 'text-decoration-style',
    # 縮排與間距（LibreOffice 大量使用）
    'text-indent', 'letter-spacing', 'word-spacing', 'text-transform',
    'margin', 'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
    'padding', 'padding-top', 'padding-bottom', 'padding-left', 'padding-right',
    'border', 'border-top', 'border-bottom', 'border-left', 'border-right',
    'border-collapse', 'border-spacing', 'border-color', 'border-style', 'border-width',
    'width', 'height', 'min-width', 'max-width', 'min-height',
    'display', 'vertical-align', 'white-space',
    # 分頁控制
    'page-break-before', 'page-break-after', 'page-break-inside',
    'break-before', 'break-after', 'break-inside',
    # 清單樣式
    'list-style-type', 'list-style', 'list-style-position', 'list-style-image',
    # 多欄排版
    'column-count', 'column-gap',
    # 圖文混排
    'float', 'clear',
    # 版面
    'box-sizing',
}

# 危險 CSS 模式：阻擋 expression/javascript/vbscript，以及非 data:image/ 的 url()
CSS_DANGEROUS = re.compile(r'(expression|javascript|vbscript)\s*\(', re.IGNORECASE)
_CSS_URL = re.compile(r'url\s*\(', re.IGNORECASE)
_CSS_SAFE_DATA_URL = re.compile(r'url\s*\(\s*["\']?\s*data:image/', re.IGNORECASE)
# CSS 值裡只准這些函式（dev 語料只用到 rgb）；image-set() 等會向外部主機發請求
SAFE_CSS_FUNCTIONS = {'rgb', 'rgba', 'hsl', 'hsla', 'url'}
_CSS_FUNCTION = re.compile(r'([a-z][a-z0-9-]*|-[a-z][a-z0-9-]*)\s*\(', re.IGNORECASE)
# CSS 跳脫（\72）與註解可以拼出被擋的字；正常文件不會用到，含這些字元的宣告整條丟
_CSS_SUSPICIOUS_CHARS = ('\\', '/*', '*/', '<', '>')

# 網址判斷前先拿掉的字元：瀏覽器解析網址時會忽略 ASCII 空白與控制字元（java<TAB>script:）
_URL_IGNORED_CHARS = re.compile(r'[\x00-\x20\x7f]+')
_URL_SCHEME = re.compile(r'^([a-z][a-z0-9+.\-]*):', re.IGNORECASE)
SAFE_LINK_SCHEMES = {'http', 'https', 'mailto', 'tel'}
SAFE_IMAGE_SCHEMES = {'http', 'https'}

# HTML 不允許的控制字元（保留 \t \n \r）；lxml 遇到會直接拒絕解析，先拿掉
_HTML_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Python 預設拒絕把超過 4300 位的數字字串轉成 int（json.loads 會丟 ValueError），
# 瀏覽器 JSON.parse 卻解得開——不能把這種內容當成「編輯器也解不開」而放行
_MAX_JSON_INT_DIGITS = 4000

# 失敗時寫進 log 的原文長度上限（避免整份文件灌進 log）
_LOG_PREVIEW_CHARS = 200


def _parse_fragment(html_text):
    """HTML 片段 → 包在一個 <div> 底下的元素（獨立成函式方便測試模擬解析失敗）。"""
    return lxml_html.fragment_fromstring(html_text, create_parent='div')


def _normalized_url(value):
    return _URL_IGNORED_CHARS.sub('', value or '').lower()


def _url_allowed(value, schemes, allow_data_image=False):
    """相對路徑一律放行；有 scheme 的只放行白名單（img 另外放行 data:image/）。"""
    url = _normalized_url(value)
    if allow_data_image and url.startswith('data:image/'):
        return True
    match = _URL_SCHEME.match(url)
    if not match:
        return True
    return match.group(1) in schemes


def _parse_json_int(text):
    """位數過多的整數改成 float（極大值成為 inf，重新序列化後瀏覽器反而解不開）。"""
    return int(text) if len(text) <= _MAX_JSON_INT_DIGITS else float(text)


def _split_css_declarations(style):
    """以分號切 CSS 宣告；括號與引號裡的分號不算（data:image/png;base64 不會被切斷）。"""
    parts, buf, depth, quote = [], [], 0, None
    for ch in style:
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(depth - 1, 0)
        elif ch == ';' and depth == 0:
            parts.append(''.join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append(''.join(buf))
    return parts


def link_url_allowed(value):
    """超連結網址可不可以留（HTML href 與 canvas 超連結共用）。"""
    return _url_allowed(value, SAFE_LINK_SCHEMES)


class DocSanitizer(models.AbstractModel):
    _name = 'doc.sanitizer'
    _description = '文件 HTML 清理器'

    # ─── HTML ─────────────────────────────────────────────────────

    def sanitize_html(self, html_content):
        """清理 HTML，保留白名單標籤與自訂 data-* 屬性，移除危險內容。"""
        return self._sanitize_html_report(html_content)[0]

    def _sanitize_html_report(self, html_content):
        """回傳 (清理後 HTML, 危險命中清單)。

        命中清單只列「會執行」的東西（危險標籤、on* 事件、不安全網址、危險 CSS）；
        良性但不在白名單的格式（例如 <font>）照樣被清掉，但不算命中——
        migration 只改寫有命中的舊文件，避免因序列化差異動到大量良性文件。
        """
        if not html_content:
            return html_content, []
        text = str(html_content)
        if not text.strip():
            return text, []
        hits = []
        text = _HTML_CONTROL_CHARS.sub('', text)
        try:
            root = _parse_fragment(text)
            self._sanitize_children(root, hits)
            result = etree.tostring(root, encoding='unicode', method='html')
            # 剝掉外層包裝 <div>（_parse_fragment 建的，沒有屬性）
            result = re.sub(r'^<div>', '', result)
            result = re.sub(r'</div>$', '', result)
            return result, hits
        except Exception:
            # 解析不了就當純文字顯示，絕不原樣放行
            _logger.warning('doc.sanitizer 解析失敗，內容改以純文字保存：%r',
                            text[:_LOG_PREVIEW_CHARS], exc_info=True)
            return html_lib.escape(text), ['parse_error']

    def _sanitize_children(self, parent, hits):
        # 由下而上：先處理子節點，再決定自己要留、要拆、還是整塊丟
        for child in list(parent):
            if not isinstance(child.tag, str):
                # 註解、處理指令：移除（drop_tree 會保留 tail 文字）
                child.drop_tree()
                continue
            tag = child.tag.lower()
            if tag in DROP_WITH_CONTENT_TAGS:
                if tag in DANGEROUS_TAGS:
                    hits.append(f'tag:{tag}')
                child.drop_tree()
                continue
            if tag == 'input':
                if (child.get('type') or '').strip().lower() not in INPUT_TYPES:
                    hits.append('tag:input')
                    child.drop_tree()
                    continue
            self._sanitize_children(child, hits)
            if tag not in ALLOWED_TAGS:
                # 非白名單：保留文字與（已清理過的）子元素，拆掉標籤本身
                child.drop_tag()
                continue
            self._sanitize_attributes(child, tag, hits)

    def _sanitize_attributes(self, element, tag, hits):
        if tag == 'input':
            allowed = INPUT_ATTRIBUTES
        else:
            allowed = set(ALLOWED_ATTRIBUTES.get('*', []))
            allowed.update(ALLOWED_ATTRIBUTES.get(tag, []))

        for attr in list(element.attrib):
            attr_lower = attr.lower()
            value = element.attrib[attr]
            if attr_lower.startswith('on'):
                hits.append(f'attr:{tag}@{attr_lower}')
                del element.attrib[attr]
                continue
            # 非白名單屬性移除（但保留 data-* 用於自訂元素；input 不留 data-*）
            if attr_lower not in allowed and not (tag != 'input' and attr_lower.startswith('data-')):
                del element.attrib[attr]
                continue
            if attr_lower == 'href' and not link_url_allowed(value):
                hits.append(f'url:{tag}@href')
                del element.attrib[attr]
                continue
            if attr_lower == 'src' and not _url_allowed(value, SAFE_IMAGE_SCHEMES, allow_data_image=True):
                hits.append(f'url:{tag}@src')
                del element.attrib[attr]
                continue
            if attr_lower == 'style':
                cleaned = self._sanitize_style(value, hits)
                if cleaned:
                    element.attrib[attr] = cleaned
                else:
                    del element.attrib[attr]

    def _sanitize_style(self, style_value, hits=None):
        hits = [] if hits is None else hits
        safe = []
        for decl in _split_css_declarations(style_value):
            decl = decl.strip()
            if ':' not in decl:
                continue
            prop, _, val = decl.partition(':')
            prop, val = prop.strip().lower(), val.strip()
            if prop not in ALLOWED_CSS:
                continue
            if CSS_DANGEROUS.search(val):
                hits.append(f'css:{prop}')
                continue
            if any(ch in val for ch in _CSS_SUSPICIOUS_CHARS):
                hits.append(f'css:{prop}')
                continue
            if {m.group(1).lower() for m in _CSS_FUNCTION.finditer(val)} - SAFE_CSS_FUNCTIONS:
                hits.append(f'css:{prop}')
                continue
            # 每一個 url() 都要是 data:image/（舊版只要任一處有 data:image 就整條放行）
            if len(_CSS_URL.findall(val)) != len(_CSS_SAFE_DATA_URL.findall(val)):
                hits.append(f'css:{prop}')
                continue
            safe.append(f'{prop}: {val}')
        return '; '.join(safe)

    # ─── canvas content_json ──────────────────────────────────────

    def sanitize_canvas_json(self, json_text):
        """移除 canvas 資料裡的 block 元素（iframe／video）、清掉不安全的超連結網址。"""
        return self._sanitize_canvas_json_report(json_text)[0]

    def _sanitize_canvas_json_report(self, json_text):
        """回傳 (清理後 JSON 字串, 命中清單)；沒改到東西就回原字串（不重新序列化）。"""
        if not json_text or not isinstance(json_text, str):
            return json_text, []
        hits = []
        try:
            data = json.loads(json_text, parse_int=_parse_json_int)
            cleaned = self._scrub_canvas_node(data, hits)
        except RecursionError:
            # 巢狀太深：Python 解不完、瀏覽器可能解得開 → 不保留（編輯器改從 content_html 轉）
            _logger.warning('doc.sanitizer：content_json 巢狀過深，已清空')
            return '', ['canvas:too_deep']
        except ValueError:
            # 瀏覽器 JSON.parse 也解不開（編輯器會空白開始、改從 content_html 轉），不會被渲染
            return json_text, []
        if not hits:
            return json_text, []
        # ensure_ascii：孤立代理字元（\ud800）保留跳脫形式，否則寫進資料庫時 UTF-8 編碼失敗
        return json.dumps(cleaned), hits

    def _scrub_canvas_node(self, node, hits):
        if isinstance(node, list):
            out = []
            for item in node:
                if isinstance(item, dict) and (item.get('type') == 'block' or 'block' in item):
                    hits.append('canvas:block')
                    continue
                out.append(self._scrub_canvas_node(item, hits))
            return out
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                # 非字串（例如陣列）會被瀏覽器轉成字串再當網址用，一律不留
                if key == 'url' and value is not None and not (
                        isinstance(value, str) and link_url_allowed(value)):
                    hits.append('canvas:url')
                    continue
                out[key] = self._scrub_canvas_node(value, hits)
            return out
        return node
