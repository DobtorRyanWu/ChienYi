# -*- coding: utf-8 -*-
"""自主檢查 dobtor 文件：把檢查類型的預設項目展開成靜態 HTML 表格列。

設計說明：
- dobtor 範本 template_self_inspection 的檢查清單寫死 3 列（{{ result_1/2/3 }}）。
- 不在 content_html 留 Jinja {% for %}（canvas-editor 會顯示原始字面而非渲染結果）。
- 改在建立 doc.document 後，server 端把清單表格 thead/tbody 換成該記錄
  inspection_type_id.default_item_ids 展開的實際列（self.inspection.type.item）。

**查驗段落欄（2026-08-07 新增）**：代操回報「檢查表格式有誤項目未見檢驗停留點、
施工前、中、後等」。資料一直都在——`self.inspection.type.item.stage_id` 指向查驗段落
（查驗停留點／施工前檢查／施工中檢查／施工完成檢查）——只是展開成 HTML 時沒帶出來。
thead 必須跟著改，否則欄數與資料列對不上、表格會歪掉。
"""
import re

from markupsafe import escape

# 範本清單表格的 thead / tbody（範本中各只有一個，屬於檢查清單那張表；
# 表頭資訊表與簽名表都是純 <tr> 沒有 thead/tbody，不會被誤傷）
_CHECKLIST_THEAD_RE = re.compile(r'<thead>.*?</thead>', re.DOTALL)
_CHECKLIST_TBODY_RE = re.compile(r'<tbody>.*?</tbody>', re.DOTALL)

_CELL = 'border:1px solid #000;padding:6px'

# 表頭：欄數必須與 _ROW_TMPL 的 <td> 數一致
_THEAD = (
    '<thead>'
    '<tr style="background:#f0f0f0">'
    '<th style="%(c)s;width:8%%">編號</th>'
    '<th style="%(c)s;width:18%%">查驗段落</th>'
    '<th style="%(c)s">檢查項目</th>'
    '<th style="%(c)s;width:15%%">合格/不合格</th>'
    '<th style="%(c)s">備註</th>'
    '</tr>'
    '</thead>'
) % {'c': _CELL}

# 單列 HTML；「　」為全形空白，供現場手填
_ROW_TMPL = (
    '<tr>'
    '<td style="%(c)s">%%(idx)d</td>'
    '<td style="%(c)s">%%(stage)s</td>'
    '<td style="%(c)s">%%(name)s</td>'
    '<td style="%(c)s;text-align:center">　</td>'
    '<td style="%(c)s">　</td>'
    '</tr>'
) % {'c': _CELL}


def sorted_by_stage(items):
    """依「查驗段落順序 → 項目順序」排序，讓項目依段落分群。

    ⚠ 不要改用模型的 `_order = 'stage_sequence, sequence, id'`：
    `stage_sequence` 是 `related='stage_id.sequence', store=True`，
    同一個交易內剛建立的項目尚未 flush，`_order` 會讀到還沒回填的 0，
    整批退回用 `sequence` 排 —— 段落分群就散了。實測（2026-08-07 E2E）：
    施工中(seq20) 的項目排在施工前(seq10) 之前。
    這裡直接讀 `stage_id.sequence`，不受 flush 時機影響。
    """
    return items.sorted(lambda i: (i.stage_id.sequence or 0, i.sequence or 0, i.id))


def inject_checklist(content_html, items):
    """把 content_html 的清單 thead/tbody 換成 items 展開的列。

    items 的順序直接沿用傳進來的順序——呼叫端應保留模型的
    `_order = 'stage_sequence, sequence, id'`，項目才會依段落分群。

    無 content_html、無 items 或找不到 tbody 時原樣回傳（安全降級）。
    """
    if not content_html or not items:
        return content_html
    rows = ''.join(
        _ROW_TMPL % {
            'idx': i,
            'stage': escape(item.stage_id.name or ''),
            'name': escape(item.name or ''),
        }
        for i, item in enumerate(items, 1)
    )
    new_html, n = _CHECKLIST_TBODY_RE.subn(
        '<tbody>' + rows + '</tbody>', content_html, count=1)
    if not n:
        return content_html
    # 資料列換成 5 欄了，表頭也要跟著換，否則欄數對不上
    new_html = _CHECKLIST_THEAD_RE.sub(_THEAD, new_html, count=1)
    return new_html
