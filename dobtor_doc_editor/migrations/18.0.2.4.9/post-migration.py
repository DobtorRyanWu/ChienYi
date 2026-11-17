# -*- coding: utf-8 -*-
"""清掉「修補前就已經存進去」的危險文件內容（doc.sanitizer 失效修補，2026-11-17）。

doc.sanitizer 以前是 no-op、content_json 也從沒檢查過，所以既有文件裡可能已經有
會在內部人員瀏覽器執行的內容。修補後只有「之後的寫入」會被消毒，這裡補清舊資料。

只改寫「判定含危險內容」的文件（危險標籤、on* 事件、不安全網址、危險 CSS、canvas block／不安全超連結）；
良性文件一律不動——消毒會重新序列化 HTML，全部寫回會無故改到每一份文件。
寫回走 ORM write()（會再消毒一次、處理大文件附件）。改了哪些文件以 WARNING 列出。
idempotent：清過一次就不再有命中，重跑不動。
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_HTML_FIELDS = ('content_html', 'header_html', 'footer_html',
                'first_header_html', 'first_footer_html')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sanitizer = env['doc.sanitizer']
    docs = env['doc.document'].search([])
    changed = []
    for doc in docs:
        vals = {}
        hits = []
        for field in _HTML_FIELDS:
            raw = doc.get_content_html() if field == 'content_html' else doc[field]
            if not raw:
                continue
            clean, field_hits = sanitizer._sanitize_html_report(raw)
            if field_hits:
                vals[field] = clean
                hits.extend(f'{field}:{h}' for h in field_hits)
        if doc.content_json:
            clean, json_hits = sanitizer._sanitize_canvas_json_report(doc.content_json)
            if json_hits:
                vals['content_json'] = clean
                hits.extend(f'content_json:{h}' for h in json_hits)
        if vals:
            doc.write(vals)
            changed.append(doc.id)
            _logger.warning('doc.document %s 含可執行內容，已清除：%s', doc.id, sorted(set(hits)))
    _logger.info('文件內容消毒掃描：共 %s 份，清除 %s 份 %s', len(docs), len(changed), changed)
