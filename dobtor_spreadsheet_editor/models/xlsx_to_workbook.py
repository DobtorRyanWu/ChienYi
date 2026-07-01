# -*- coding: utf-8 -*-
"""xlsx 二進位 → o-spreadsheet WorkbookData（後端 openpyxl 匯入器）。

MVP 保真範圍（對應前端 to_ospreadsheet.ts 的輸出 schema）：
- 儲存格值/公式（content 字串）
- 樣式池 styles（bold/italic/underline/strike/fontSize/textColor/fillColor/align/verticalAlign/wrapping）
- 邊框池 borders（thin/medium/thick/dashed/dotted，含顏色）— 表單版型關鍵
- 合併儲存格 merges、欄寬 cols、列高 rows

暫不處理：number format（避免不相容格式造成顯示異常）、圖表、圖片、條件式格式、資料驗證、公式轉譯。
cell.style / cell.border 用池 id（number），與 to_ospreadsheet.ts 一致；頂層 formats 留空 {}。
"""
import datetime
import json
import logging

_logger = logging.getLogger(__name__)

# Excel 邊框 style → o-spreadsheet（僅 thin/medium/thick/dashed/dotted），對齊 to_ospreadsheet.ts
_BORDER_STYLE_MAP = {
    'thin': 'thin', 'hair': 'thin',
    'medium': 'medium', 'mediumDashed': 'medium', 'mediumDashDot': 'medium',
    'mediumDashDotDot': 'medium', 'double': 'medium', 'thick': 'thick',
    'dashed': 'dashed', 'dashDot': 'dashed', 'dashDotDot': 'dashed', 'slantDashDot': 'dashed',
    'dotted': 'dotted',
}
_VALIGN_MAP = {'top': 'top', 'center': 'middle', 'bottom': 'middle', 'justify': 'middle'}
_DEFAULT_FONT_SIZES = (10.0, 11.0)


class _Pool:
    """去重池：相同內容回傳同一個 1-based id。"""

    def __init__(self):
        self._index = {}
        self._items = {}
        self._n = 0

    def intern(self, obj):
        key = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        if key in self._index:
            return self._index[key]
        self._n += 1
        self._index[key] = self._n
        self._items[str(self._n)] = obj
        return self._n

    def to_record(self):
        return self._items


def _hex(color):
    """openpyxl Color → '#RRGGBB'；僅處理明確 ARGB rgb 字串，theme/indexed 略過。"""
    if color is None:
        return None
    rgb = getattr(color, 'rgb', None)
    if isinstance(rgb, str) and len(rgb) == 8:
        return '#' + rgb[2:].upper()
    return None


def _cell_content(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, str):
        return value  # 含 "=公式"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return ('%d' % value) if value.is_integer() else repr(value)
    if isinstance(value, datetime.datetime):
        if (value.hour, value.minute, value.second) == (0, 0, 0):
            return value.strftime('%Y/%m/%d')
        return value.strftime('%Y/%m/%d %H:%M')
    if isinstance(value, datetime.date):
        return value.strftime('%Y/%m/%d')
    if isinstance(value, datetime.time):
        return value.strftime('%H:%M')
    return str(value)


def _ostyle(cell):
    s = {}
    f = cell.font
    if f is not None:
        if f.bold:
            s['bold'] = True
        if f.italic:
            s['italic'] = True
        if f.strike:
            s['strikethrough'] = True
        if f.underline and f.underline != 'none':
            s['underline'] = True
        try:
            if f.size and float(f.size) not in _DEFAULT_FONT_SIZES:
                s['fontSize'] = int(float(f.size))
        except (TypeError, ValueError):
            pass
        c = _hex(f.color)
        if c and c != '#000000':
            s['textColor'] = c
    fill = cell.fill
    if fill is not None and getattr(fill, 'patternType', None) == 'solid':
        c = _hex(fill.fgColor)
        if c and c != '#000000':
            s['fillColor'] = c
    al = cell.alignment
    if al is not None:
        h = al.horizontal
        if h in ('left', 'right', 'center'):
            s['align'] = h
        elif h == 'centerContinuous':
            s['align'] = 'center'
        if al.vertical in _VALIGN_MAP:
            s['verticalAlign'] = _VALIGN_MAP[al.vertical]
        if al.wrap_text:
            s['wrapping'] = 'wrap'
    return s


def _edge(side):
    if not side or not side.style or side.style == 'none':
        return None
    return {
        'style': _BORDER_STYLE_MAP.get(side.style, 'thin'),
        'color': _hex(getattr(side, 'color', None)) or '#000000',
    }


def _oborder(cell):
    bd = cell.border
    if bd is None:
        return None
    b = {}
    for k in ('top', 'bottom', 'left', 'right'):
        e = _edge(getattr(bd, k, None))
        if e:
            b[k] = e
    return b or None


def _build_sheet(ws, sheet_id, style_pool, border_pool):
    from openpyxl.utils import column_index_from_string

    max_col = max(ws.max_column or 1, 26)
    max_row = max(ws.max_row or 1, 100)

    cells = {}
    for row in ws.iter_rows():
        for cell in row:
            content = _cell_content(cell.value)
            ocell = {}
            if content != '':
                ocell['content'] = content
            if getattr(cell, 'has_style', False):
                st = _ostyle(cell)
                if st:
                    ocell['style'] = style_pool.intern(st)
                bd = _oborder(cell)
                if bd:
                    ocell['border'] = border_pool.intern(bd)
            # 只在有內容/樣式/邊框時輸出（對齊 to_ospreadsheet.ts L319）
            if ocell:
                ocell.setdefault('content', '')
                cells[cell.coordinate] = ocell

    merges = [str(rng) for rng in ws.merged_cells.ranges]

    cols = {}
    for dim in ws.column_dimensions.values():
        if dim.width and dim.min and dim.max:
            px = int(round(dim.width * 7)) + 5
            for ci in range(dim.min, dim.max + 1):
                cols[str(ci - 1)] = {'size': px}
    rows = {}
    for r, dim in ws.row_dimensions.items():
        if dim.height:
            rows[str(r - 1)] = {'size': int(round(dim.height * 96 / 72))}

    return {
        'id': sheet_id,
        'name': ws.title,
        'colNumber': max_col,
        'rowNumber': max_row,
        'cells': cells,
        'merges': merges,
        'cols': cols,
        'rows': rows,
        'conditionalFormats': [],
        'dataValidationRules': [],
        'tables': [],
        'figures': [],
        'areGridLinesVisible': True,
    }


def xlsx_bytes_to_workbook_data(file_bytes, base):
    """把 xlsx bytes 轉成 o-spreadsheet WorkbookData dict。

    :param base: 由 spreadsheet.spreadsheet._empty_spreadsheet_data() 提供的底稿
                 （含正確 version / settings.locale / revisionId），只覆寫 sheets/池。
    :return: (workbook_data:dict, parse_log:str)
    """
    import io
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=False)
    style_pool = _Pool()
    border_pool = _Pool()
    sheets = []
    for i, ws in enumerate(wb.worksheets):
        if getattr(ws, 'sheet_state', 'visible') != 'visible':
            continue
        sheets.append(_build_sheet(ws, 'sheet%d' % (i + 1), style_pool, border_pool))
    if not sheets:
        sheets.append({
            'id': 'sheet1', 'name': 'Sheet1', 'colNumber': 26, 'rowNumber': 100,
            'cells': {}, 'merges': [], 'cols': {}, 'rows': {},
            'conditionalFormats': [], 'dataValidationRules': [], 'tables': [],
            'figures': [], 'areGridLinesVisible': True,
        })

    data = dict(base or {})
    data.setdefault('version', 1)
    data.setdefault('revisionId', 'START_REVISION')
    data['sheets'] = sheets
    data['styles'] = style_pool.to_record()
    data['formats'] = {}
    data['borders'] = border_pool.to_record()

    cell_count = sum(len(s['cells']) for s in sheets)
    log = 'xlsx 匯入：%d 工作表、%d 儲存格、%d 樣式、%d 邊框' % (
        len(sheets), cell_count, len(style_pool.to_record()), len(border_pool.to_record()))
    _logger.info(log)
    return data, log
