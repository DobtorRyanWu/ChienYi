# -*- coding: utf-8 -*-
"""把業務資料填進 dobtor 範本 HTML 的共用工具（估驗計價、自主檢查都用）。

兩件事，各自是一個已實跑重現過的洞（2026-11-08 抗辯）：

1. 資料值會變成 Jinja 原始碼：填好的 content_html 之後會被匯出 PDF／DOCX 與快速預覽
   整份交給 Jinja 渲染（dobtor_doc_editor doc.render.mixin._render_template）。
   escape() 只處理 & < > ' "，所以名稱裡的 {{ 7*7 }} 會印出 49、{# … #} 會讓中間的列在 PDF 消失。
   → safe_text()：跳脫 HTML，並把會組成 Jinja 開頭的「{」換成全形「｛」：
     後面接 { % #（{{ {% {#）、後面接《（別名巨集《token》會展開成 {{ … }}，拼成 {{{ 語法錯誤）、
     以及在值的結尾（兩個值緊貼時，前一個結尾的 { 會和後一個開頭的 { 拼起來）。
     不用 &#123;：編輯器存檔會把實體還原成 {；不用零寬字元：canvas-editor 自己拿 ​ 當內部記號。

2. 不能用「第一個 <tbody>」認資料表：範本在後台 HTML 編輯器存過一次，瀏覽器會替沒寫 tbody 的
   表頭表補上 <tbody>，表頭就整張被換掉。
   → replace_item_table()：只動「唯一一張有 <thead> 的表」；找不到、不只一張、或有巢狀表格
     （非貪婪比對會切錯表）一律原樣回傳並記 warning——使用者看到的是範本的空白列，
     log 裡要分得出「沒填」和「本來就沒有資料」。
"""
import logging
import re

from markupsafe import escape

_logger = logging.getLogger(__name__)

_JINJA_OPEN_RE = re.compile(r'\{(?=[{%#《]|$)')
_TABLE_OPEN_RE = re.compile(r'<table\b', re.IGNORECASE)
_TABLE_RE = re.compile(r'<table\b[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)
_THEAD_RE = re.compile(r'<thead\b[^>]*>.*?</thead>', re.DOTALL | re.IGNORECASE)
_TBODY_RE = re.compile(r'<tbody\b[^>]*>.*?</tbody>', re.DOTALL | re.IGNORECASE)


def safe_text(value):
    """要寫進範本 HTML 的資料值：跳脫 HTML，並拆掉會組成 Jinja 開頭的「{」（見檔頭）。"""
    return _JINJA_OPEN_RE.sub('｛', str(escape(value)))


def replace_item_table(content_html, tbody_html, thead_html=None, label=''):
    """把「唯一一張有 <thead> 的表」的 tbody（以及 thead，有給的話）換掉。

    tbody_html／thead_html 是完整的 <tbody>…</tbody>／<thead>…</thead>，裡面的資料值
    呼叫端要先過 safe_text()。無法安全定位時原樣回傳並記 warning（label 標明是哪一份文件）。
    """
    content_html = str(content_html)

    def keep(reason):
        _logger.warning('範本資料表沒有填入（%s）：%s，保留範本原樣', label or '未標明', reason)
        return content_html

    tables = list(_TABLE_RE.finditer(content_html))
    if len(_TABLE_OPEN_RE.findall(content_html)) != len(tables):
        return keep('範本有巢狀表格')
    found = [(m, _THEAD_RE.search(m.group(0))) for m in tables]
    found = [(m, thead) for m, thead in found if thead]
    if len(found) != 1:
        return keep('帶 <thead> 的表有 %d 張（要恰好 1 張）' % len(found))
    table, thead = found[0]
    text = table.group(0)
    tbody = _TBODY_RE.search(text, thead.end())
    if tbody is None:
        return keep('資料表在 <thead> 之後沒有 <tbody>')
    new_text = (text[:thead.start()] + (thead_html or thead.group(0))
                + text[thead.end():tbody.start()] + tbody_html + text[tbody.end():])
    return content_html[:table.start()] + new_text + content_html[table.end():]
