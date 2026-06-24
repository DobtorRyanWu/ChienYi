# -*- coding: utf-8 -*-
"""自主檢查 dobtor 文件：把檢查類型的預設項目展開成靜態 HTML 表格列。

設計說明：
- dobtor 範本 template_self_inspection 的檢查清單寫死 3 列（{{ result_1/2/3 }}）。
- 不在 content_html 留 Jinja {% for %}（canvas-editor 會顯示原始字面而非渲染結果）。
- 改在建立 doc.document 後，server 端把清單表格 tbody 換成該記錄
  inspection_type_id.default_item_ids 展開的實際列（self.inspection.type.item）。
"""
import re

from markupsafe import escape

# 範本清單表格的 tbody（範本中唯一的 <tbody>，含寫死 3 列 {{ result_x }}）
_CHECKLIST_TBODY_RE = re.compile(r'<tbody>.*?</tbody>', re.DOTALL)

# 單列 HTML，沿用範本既有的儲存格樣式；「　」為全形空白，供現場手填
_ROW_TMPL = (
    '<tr>'
    '<td style="border:1px solid #000;padding:6px">%(idx)d</td>'
    '<td style="border:1px solid #000;padding:6px">%(name)s</td>'
    '<td style="border:1px solid #000;padding:6px;text-align:center">　</td>'
    '<td style="border:1px solid #000;padding:6px">　</td>'
    '</tr>'
)


def inject_checklist(content_html, items):
    """把 content_html 的清單 tbody 換成 items 展開的列。

    無 content_html、無 items 或找不到 tbody 時原樣回傳（安全降級）。
    """
    if not content_html or not items:
        return content_html
    rows = ''.join(
        _ROW_TMPL % {'idx': i, 'name': escape(item.name or '')}
        for i, item in enumerate(items, 1)
    )
    new_html, n = _CHECKLIST_TBODY_RE.subn(
        '<tbody>' + rows + '</tbody>', content_html, count=1)
    return new_html if n else content_html
