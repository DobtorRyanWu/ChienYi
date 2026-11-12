# -*- coding: utf-8 -*-
"""佔位符樣板：被點名的 `${token}` 那一格改成自動換行，並把那一列撐高。

## 為什麼需要

合併儲存格的列，Excel 與 LibreOffice 都不會自動調列高；樣板上的文字格也多半沒開自動換行。
多行文字塞進去只會印成一行，超出格子的部分被切掉（營造版施工日誌第一聯的
「六、施工取樣試驗紀錄」H32:V32 就是這樣）。

## 怎麼用

對照表宣告 `WRAP_TOKENS(context)`，回傳「這一次套印要處理的 token」（見 mappings/daily_log_c1.py）。
template_render._render_placeholder 在**填值之前**呼叫 wrap_tokens()：

1. 那一格的樣式換成「原樣式＋自動換行」：在 styles.xml 的 cellXfs 尾端加一筆，既有樣式一筆都不改。
2. 那一列的列高設成「估計行數 × 一行的高度」，只會加高、不會縮。

沒被點名的 token、樣板裡找不到的 token 都不動（原樣回傳）。
行數是估的（字寬以全形 2、半形 1 計，再留餘裕）：估多只是多一點空白，估少會切字，所以往多的方向估。
"""
import math
import re
import unicodedata

from .xlsx_placeholder import CELL_RE, MERGE_RE, ROW_RE, STYLE_RE, TABLE_TOKEN_RE, cell_text

STYLES_ENTRY = 'xl/styles.xml'

CELL_XFS_RE = re.compile(r'(<cellXfs\b[^>]*>)(.*?)(</cellXfs>)', re.DOTALL)
XF_RE = re.compile(r'<xf\b[^>]*?/>|<xf\b[^>]*?>.*?</xf>', re.DOTALL)
XF_OPEN_RE = re.compile(r'<xf\b([^>]*?)(/?)>')
ALIGNMENT_RE = re.compile(r'<alignment\b([^>]*?)/>')
FONTS_RE = re.compile(r'<fonts\b[^>]*>(.*?)</fonts>', re.DOTALL)
FONT_RE = re.compile(r'<font\b[^>]*?/>|<font\b[^>]*?>.*?</font>', re.DOTALL)
FONT_SIZE_RE = re.compile(r'<sz\s+val="([\d.]+)"')
FONT_ID_RE = re.compile(r'\sfontId="(\d+)"')
COUNT_RE = re.compile(r'\scount="\d+"')
COL_RE = re.compile(r'<col\b([^>]*?)/>')
COL_ATTR_RE = re.compile(r'\b(min|max|width)="([\d.]+)"')
DEFAULT_COL_WIDTH_RE = re.compile(r'<sheetFormatPr\b[^>]*?\sdefaultColWidth="([\d.]+)"')
ROW_HEIGHT_RE = re.compile(r'\sht="([\d.]+)"')
ROW_CUSTOM_HEIGHT_RE = re.compile(r'\scustomHeight="[^"]*"')

WRAP_ATTR = 'wrapText="1"'
DEFAULT_FONT_SIZE = 12.0            # 樣板讀不到字級時的假設（公文表單慣用 12pt）
DEFAULT_COL_WIDTH = 8.43            # Excel 的預設欄寬（樣板沒寫 defaultColWidth 時）
WIDE_CHAR_UNITS = 2.0               # 全形字佔幾個欄寬單位（欄寬單位＝預設字型一個數字的寬度）
NARROW_CHAR_UNITS = 1.0
WIDTH_SAFETY = 1.08                 # 字寬估計的餘裕：寧可多估一行
CELL_PADDING_UNITS = 1.0            # 儲存格左右內距
LINE_HEIGHT_RATIO = 1.4             # 一行的高度＝字級 × 這個比例（12pt → 16.8pt，樣板預設列高是 16.5）
ROW_PADDING_PT = 3.0                # 上下留白


def _col_index(letters):
    index = 0
    for char in letters:
        index = index * 26 + ord(char) - ord('A') + 1
    return index


def _col_widths(sheet_xml):
    """欄號（1 起算）→ 欄寬。沒列在 <cols> 的欄用預設欄寬。"""
    widths = {}
    for attrs in COL_RE.findall(sheet_xml):
        values = dict(COL_ATTR_RE.findall(attrs))
        if not {'min', 'max', 'width'} <= set(values):
            continue
        for index in range(int(float(values['min'])), int(float(values['max'])) + 1):
            widths[index] = float(values['width'])
    default = DEFAULT_COL_WIDTH_RE.search(sheet_xml)
    return widths, float(default.group(1)) if default else DEFAULT_COL_WIDTH


def _cell_span(sheet_xml, col, row):
    """這一格所在合併範圍的 (起欄, 迄欄)；沒合併就是自己那一欄。"""
    index = _col_index(col)
    for c1, r1, c2, r2 in MERGE_RE.findall(sheet_xml):
        if int(r1) <= row <= int(r2) and _col_index(c1) <= index <= _col_index(c2):
            return _col_index(c1), _col_index(c2)
    return index, index


# 全形（W、F）之外，「寬度不定」（A：…、°、± 這類）在中文字型裡也印成全形，一併當全形算
WIDE_EAST_ASIAN_WIDTHS = ('W', 'F', 'A')


def _text_units(text):
    return sum(WIDE_CHAR_UNITS if unicodedata.east_asian_width(char) in WIDE_EAST_ASIAN_WIDTHS
               else NARROW_CHAR_UNITS for char in text)


def estimate_lines(text, capacity_units):
    """text 在可容納 capacity_units 個欄寬單位的格子裡，自動換行後大約幾行（至少 1）。"""
    capacity = max(capacity_units, WIDE_CHAR_UNITS)
    return sum(max(1, math.ceil(_text_units(line) * WIDTH_SAFETY / capacity))
               for line in (text or '').split('\n')) or 1


def _font_sizes(styles_xml):
    block = FONTS_RE.search(styles_xml)
    sizes = []
    for font in FONT_RE.findall(block.group(1) if block else ''):
        size = FONT_SIZE_RE.search(font)
        sizes.append(float(size.group(1)) if size else DEFAULT_FONT_SIZE)
    return sizes or [DEFAULT_FONT_SIZE]


def _wrapped_xf(xf):
    """同一筆樣式加上自動換行；本來就有自動換行回 None。"""
    alignment = ALIGNMENT_RE.search(xf)
    if alignment:
        if WRAP_ATTR in alignment.group(0):
            return None
        return xf[:alignment.start()] + '<alignment%s %s/>' % (alignment.group(1).rstrip(), WRAP_ATTR) \
            + xf[alignment.end():]
    opening = XF_OPEN_RE.match(xf)
    attrs = opening.group(1).rstrip()
    if 'applyAlignment=' not in attrs:
        attrs += ' applyAlignment="1"'
    body = '' if opening.group(2) else xf[opening.end():-len('</xf>')]
    return '<xf%s><alignment %s/>%s</xf>' % (attrs, WRAP_ATTR, body)


def _add_wrapped_style(styles_xml, style_index):
    """回傳 (新的 styles_xml, 要用的樣式索引, 這一格的字級)。"""
    block = CELL_XFS_RE.search(styles_xml)
    sizes = _font_sizes(styles_xml)
    if not block:
        return styles_xml, style_index, sizes[0]
    xfs = XF_RE.findall(block.group(2))
    if style_index is None or style_index >= len(xfs):
        return styles_xml, style_index, sizes[0]
    xf = xfs[style_index]
    font_id = FONT_ID_RE.search(xf)
    size = sizes[int(font_id.group(1))] if font_id and int(font_id.group(1)) < len(sizes) else sizes[0]
    wrapped = _wrapped_xf(xf)
    if wrapped is None:
        return styles_xml, style_index, size
    if wrapped in xfs:
        # 同一張表有兩格要換行、原樣式又相同：共用同一筆
        return styles_xml, xfs.index(wrapped), size
    opening = COUNT_RE.sub(' count="%s"' % (len(xfs) + 1), block.group(1), count=1)
    styles_xml = (styles_xml[:block.start()] + opening + block.group(2) + wrapped + block.group(3)
                  + styles_xml[block.end():])
    return styles_xml, len(xfs), size


def wrap_tokens(sheet_xml, styles_xml, shared, texts):
    """texts: {token: 這次要填進去的文字}。回傳 (sheet_xml, styles_xml)。

    只處理「整格就是 ${token}」的儲存格；表格列（${table:…}）不處理（它會被複製成多列）。
    """
    if not texts:
        return sheet_xml, styles_xml
    wanted = {'${%s}' % token: text for token, text in texts.items()}
    widths, default_width = _col_widths(sheet_xml)
    default_size = _font_sizes(styles_xml)[0]
    out, pos = [], 0
    for row_match in ROW_RE.finditer(sheet_xml):
        row_num, row_attrs, body = int(row_match.group(1)), row_match.group(2), row_match.group(3)
        if not body:
            continue
        cells = [(cell, cell_text(cell.group(3), cell.group(4), shared).strip())
                 for cell in CELL_RE.finditer(body)]
        if (not any(text in wanted for _cell, text in cells)
                or any(TABLE_TOKEN_RE.search(text) for _cell, text in cells)):
            continue
        needed_height = 0.0
        new_body, body_pos = [], 0
        for cell, template_text in cells:
            if template_text not in wanted:
                continue
            col, _row, attrs, _cell_body = cell.groups()
            style_match = STYLE_RE.search(attrs or '')
            style_index = int(style_match.group(1)) if style_match else None
            styles_xml, new_index, font_size = _add_wrapped_style(styles_xml, style_index)
            first, last = _cell_span(sheet_xml, col, row_num)
            total_width = sum(widths.get(index, default_width) for index in range(first, last + 1))
            # 欄寬單位以預設字型計；這一格字比較大，能放的字就比較少
            capacity = (total_width - CELL_PADDING_UNITS) / (font_size / default_size)
            lines = estimate_lines(wanted[template_text], capacity)
            needed_height = max(needed_height, lines * font_size * LINE_HEIGHT_RATIO + ROW_PADDING_PT)
            if new_index != style_index and style_match:
                new_attrs = attrs[:style_match.start()] + ' s="%s"' % new_index + attrs[style_match.end():]
                new_cell = cell.group(0).replace(attrs, new_attrs, 1)
                new_body.append(body[body_pos:cell.start()])
                new_body.append(new_cell)
                body_pos = cell.end()
        new_body.append(body[body_pos:])
        current = ROW_HEIGHT_RE.search(row_attrs)
        if current and float(current.group(1)) >= needed_height:
            new_attrs = row_attrs
        else:
            new_attrs = ROW_CUSTOM_HEIGHT_RE.sub('', ROW_HEIGHT_RE.sub('', row_attrs))
            new_attrs += ' ht="%s" customHeight="1"' % round(needed_height, 2)
        out.append(sheet_xml[pos:row_match.start()])
        out.append('<row r="%s"%s>%s</row>' % (row_num, new_attrs, ''.join(new_body)))
        pos = row_match.end()
    out.append(sheet_xml[pos:])
    return ''.join(out), styles_xml
