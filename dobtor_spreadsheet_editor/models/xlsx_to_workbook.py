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


import re as _re

# 保守的 number format：只放 o-spreadsheet 確定支援的數值/百分比/貨幣/日期樣式；
# 含 era(e)/民國(ggg)/文字字面("...")/條件色([Red]) 等一律略過，避免顯示異常。
_NUMFMT_ALIAS = {
    '0': '0', '0.0': '0.0', '0.00': '0.00',
    '#,##0': '#,##0', '#,##0.0': '#,##0.0', '#,##0.00': '#,##0.00',
    '0%': '0%', '0.0%': '0.0%', '0.00%': '0.00%',
    '#,##0;-#,##0': '#,##0', '#,##0.00;-#,##0.00': '#,##0.00',
    '#,##0_ ': '#,##0', '#,##0.00_ ': '#,##0.00',
}
_NUM_ONLY = _re.compile(r'^[#0,.%]+$')
_DATE_ONLY = _re.compile(r'^[ymdhs/\-.: ]+$', _re.IGNORECASE)


def _safe_format(numfmt):
    if not numfmt or numfmt == 'General':
        return None
    nf = numfmt.strip()
    if nf in _NUMFMT_ALIAS:
        return _NUMFMT_ALIAS[nf]
    low = nf.lower()
    # 排除民國/era/文字字面/貨幣locale/條件色/補位符號
    if any(t in low for t in ('e', 'g', '"', '[$', '[red', '[blue', '*', '_', '@', '?')):
        return None
    if _NUM_ONLY.match(nf):
        return nf
    if _DATE_ONLY.match(nf):
        return low.replace('-', '/')  # o-spreadsheet 接受 yyyy/mm/dd 類
    return None


# 圖片錨點座標估算，與前端 image_extractor.ts 一致（COL_PX/ROW_PX）
_COL_PX = 64
_ROW_PX = 20


_XDR = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
_EMU_PER_PX = 9525
_MIME_BY_EXT = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                'gif': 'image/gif', 'bmp': 'image/bmp'}


def _norm_path(base_dir, target):
    """把 rels 的相對 target 解析成 zip 內絕對路徑。"""
    import posixpath
    if target.startswith('/'):
        return target.lstrip('/')
    return posixpath.normpath(posixpath.join(base_dir, target))


def _parse_rels(zf, rels_path):
    import xml.etree.ElementTree as ET
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    out = {}
    for rel in root.findall('{%s}Relationship' % _PR):
        out[rel.get('Id')] = (rel.get('Target'), rel.get('Type') or '')
    return out


def extract_images(file_bytes):
    """以 zip 解析 xlsx 內嵌圖片（openpyxl 無法讀既有檔的圖，故自解 drawings）。

    對齊前端 image_extractor.ts：座標 col*COL_PX/row*ROW_PX，sheet_index 對齊可見工作表順序。
    :return: [{sheet_index, base64, mimetype, x, y, width, height}]
    """
    import base64 as _b64
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    out = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except Exception:
        return out
    names = set(zf.namelist())
    if 'xl/workbook.xml' not in names:
        return out

    wb_rels = _parse_rels(zf, 'xl/_rels/workbook.xml.rels')
    wb_root = ET.fromstring(zf.read('xl/workbook.xml'))
    ss_main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheets_el = wb_root.find('{%s}sheets' % ss_main)
    if sheets_el is None:
        return out

    visible_parts = []  # 對齊 WorkbookData sheets（排除 hidden/veryHidden）
    for s in sheets_el.findall('{%s}sheet' % ss_main):
        state = s.get('state', 'visible')
        rid = s.get('{%s}id' % _R)
        if state in ('hidden', 'veryHidden') or not rid or rid not in wb_rels:
            if state in ('hidden', 'veryHidden'):
                continue
        tgt = wb_rels.get(rid, (None, None))[0]
        if not tgt:
            continue
        visible_parts.append(_norm_path('xl', tgt))

    for si, sheet_part in enumerate(visible_parts):
        import posixpath
        base = posixpath.dirname(sheet_part)
        sheet_rels = _norm_path(base, '_rels/%s.rels' % posixpath.basename(sheet_part))
        rels = _parse_rels(zf, sheet_rels)
        drawing_targets = [t for (t, typ) in rels.values() if typ.endswith('/drawing')]
        for dt in drawing_targets:
            draw_part = _norm_path(base, dt)
            if draw_part not in names:
                continue
            draw_base = posixpath.dirname(draw_part)
            draw_rels = _parse_rels(
                zf, _norm_path(draw_base, '_rels/%s.rels' % posixpath.basename(draw_part)))
            draw_root = ET.fromstring(zf.read(draw_part))
            for anchor in list(draw_root):
                tag = anchor.tag.split('}')[-1]
                if tag not in ('twoCellAnchor', 'oneCellAnchor'):
                    continue
                frm = anchor.find('{%s}from' % _XDR)
                if frm is None:
                    continue
                fc = int(frm.findtext('{%s}col' % _XDR, '0'))
                fr = int(frm.findtext('{%s}row' % _XDR, '0'))
                to = anchor.find('{%s}to' % _XDR)
                blip = anchor.find('.//{%s}blip' % _A)
                if blip is None:
                    continue
                embed = blip.get('{%s}embed' % _R)
                media_t = draw_rels.get(embed, (None, None))[0]
                if not media_t:
                    continue
                media_part = _norm_path(draw_base, media_t)
                if media_part not in names:
                    continue
                data = zf.read(media_part)
                if not data or len(data) > 4 * 1024 * 1024:
                    continue
                ext = media_part.rsplit('.', 1)[-1].lower()
                mimetype = _MIME_BY_EXT.get(ext)
                if not mimetype:
                    continue
                if to is not None:
                    tc = int(to.findtext('{%s}col' % _XDR, str(fc + 2)))
                    tr = int(to.findtext('{%s}row' % _XDR, str(fr + 5)))
                    width = max((tc - fc) * _COL_PX, 32)
                    height = max((tr - fr) * _ROW_PX, 32)
                else:
                    ext_el = anchor.find('{%s}ext' % _XDR)
                    if ext_el is not None:
                        width = max(int(int(ext_el.get('cx', '0')) / _EMU_PER_PX), 32)
                        height = max(int(int(ext_el.get('cy', '0')) / _EMU_PER_PX), 32)
                    else:
                        width, height = 120, 60
                out.append({
                    'sheet_index': si,
                    'base64': _b64.b64encode(data).decode(),
                    'mimetype': mimetype,
                    'x': fc * _COL_PX, 'y': fr * _ROW_PX,
                    'width': width, 'height': height,
                })
    return out


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
                fmt = _safe_format(getattr(cell, 'number_format', None))
                if fmt:
                    ocell['format'] = fmt
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
    visible = [ws for ws in wb.worksheets
               if getattr(ws, 'sheet_state', 'visible') == 'visible']
    sheets = []
    for idx, ws in enumerate(visible):
        sheets.append(_build_sheet(ws, 'sheet%d' % (idx + 1), style_pool, border_pool))
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

    images = extract_images(file_bytes)

    cell_count = sum(len(s['cells']) for s in sheets)
    log = 'xlsx 匯入：%d 工作表、%d 儲存格、%d 樣式、%d 邊框、%d 圖片' % (
        len(sheets), cell_count, len(style_pool.to_record()),
        len(border_pool.to_record()), len(images))
    _logger.info(log)
    return data, log, images
