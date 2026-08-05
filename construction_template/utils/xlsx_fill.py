# -*- coding: utf-8 -*-
"""在 xlsx 的 worksheet XML 裡就地填值，不重建 workbook。

## 為什麼不用 openpyxl

openpyxl 載入再儲存會**重寫整份 workbook**。本專案的空白樣板含
`xl/media/image1.jpg`（logo）與 `xl/drawings/vmlDrawing1.vml`，openpyxl 對 VML
的支援不完整，而 2026-08-04 的 7 個 commit（7c26cbf→b641e36）才剛把這些檔的
容器層結構、OOXML 宣告與中文字型修好。重寫等於把那些努力丟掉。

本模組只改 `xl/worksheets/sheetN.xml` 裡目標儲存格那一小段 XML，
其餘 entry 交給 `zip_patch.patch()` 位元組原封複製。

## 儲存格寫法

一律改成 `t="inlineStr"`，**不動 `sharedStrings.xml`**——否則要重算所有索引。

    原始  <c r="B6" s="141" t="s"><v>8</v></c>
    填後  <c r="B6" s="141" t="inlineStr"><is><t>磺港溪整治工程</t></is></c>
    空格  <c r="C6" s="142"/>  →  <c r="C6" s="142" t="inlineStr"><is><t>值</t></is></c>

`s=`（樣式索引）必須沿用，否則格線、字型、對齊全部掉光。
數字不加 `t`，直接寫 `<v>`。
"""

import re

CELL_RE_TMPL = r'<c r="{ref}"(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)'
ROW_RE_TMPL = r'<row r="{row}"(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</row>)'
STYLE_RE = re.compile(r'\ss="(\d+)"')
COL_RE = re.compile(r'^([A-Z]+)(\d+)$')
# 值前後有空白或換行時，少了 xml:space 會被 Excel 吃掉
NEEDS_PRESERVE = re.compile(r'^\s|\s$|\n')


def col_to_index(col_letters):
    """'A' → 1, 'B' → 2, 'AA' → 27"""
    idx = 0
    for ch in col_letters:
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx


def split_ref(ref):
    """'B6' → ('B', 6)"""
    m = COL_RE.match(ref)
    if not m:
        raise ValueError('儲存格座標格式錯誤：%s' % ref)
    return m.group(1), int(m.group(2))


def escape(text):
    return (str(text).replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def build_cell(ref, style_attr, value):
    """組出一顆完整的 <c> 元素。value 為 None/'' 時只留樣式（清空內容）。"""
    if value is None or value == '':
        return '<c r="%s"%s/>' % (ref, style_attr)
    if isinstance(value, bool):
        value = '是' if value else '否'
    if isinstance(value, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, style_attr, value)
    text = escape(value)
    space = ' xml:space="preserve"' if NEEDS_PRESERVE.search(str(value)) else ''
    return '<c r="%s"%s t="inlineStr"><is><t%s>%s</t></is></c>' % (
        ref, style_attr, space, text)


def fill(sheet_xml, values):
    """把 {儲存格座標: 值} 填進 worksheet XML。

    :param sheet_xml: worksheet XML 的 str
    :param values: {'B6': '工程名稱', 'C7': 123, ...}
    :return: (新的 XML str, 未能填入的座標清單)

    儲存格不存在時會嘗試依欄序插進該列；連列都不存在才回報失敗
    （回報而不是靜默略過——填不進去代表對照表寫錯了，必須讓人知道）。
    """
    missing = []
    for ref, value in values.items():
        col_letters, row_num = split_ref(ref)
        cell_re = re.compile(CELL_RE_TMPL.format(ref=re.escape(ref)), re.DOTALL)
        match = cell_re.search(sheet_xml)

        if match:
            style_match = STYLE_RE.search(match.group('attrs') or '')
            style_attr = ' s="%s"' % style_match.group(1) if style_match else ''
            sheet_xml = (sheet_xml[:match.start()]
                         + build_cell(ref, style_attr, value)
                         + sheet_xml[match.end():])
            continue

        # 儲存格不存在 → 插進所屬的 <row>
        inserted = _insert_cell(sheet_xml, ref, col_letters, row_num, value)
        if inserted is None:
            missing.append(ref)
        else:
            sheet_xml = inserted

    return sheet_xml, missing


def _insert_cell(sheet_xml, ref, col_letters, row_num, value):
    """把新儲存格依欄序插進既有的 <row>；找不到該列回傳 None。"""
    row_re = re.compile(ROW_RE_TMPL.format(row=row_num), re.DOTALL)
    row_match = row_re.search(sheet_xml)
    if not row_match:
        return None

    new_cell = build_cell(ref, '', value)
    body = row_match.group('body')

    if body is None:                      # <row r="9"/> 自閉合空列
        attrs = row_match.group('attrs') or ''
        new_row = '<row r="%s"%s>%s</row>' % (row_num, attrs, new_cell)
        return sheet_xml[:row_match.start()] + new_row + sheet_xml[row_match.end():]

    target_idx = col_to_index(col_letters)
    insert_at = len(body)                 # 預設插在最後
    for m in re.finditer(r'<c r="([A-Z]+)\d+"', body):
        if col_to_index(m.group(1)) > target_idx:
            insert_at = m.start()
            break
    new_body = body[:insert_at] + new_cell + body[insert_at:]
    return (sheet_xml[:row_match.start('body')] + new_body
            + sheet_xml[row_match.end('body'):])
