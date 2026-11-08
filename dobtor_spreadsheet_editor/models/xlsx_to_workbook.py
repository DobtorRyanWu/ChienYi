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
    # 民國紀年／文字字面／地區碼／顏色／留白等交給 _convert_format 逐字元判斷
    if _NUM_ONLY.match(nf):
        return nf
    if _DATE_ONLY.match(nf):
        return low.replace('-', '/')  # o-spreadsheet 接受 yyyy/mm/dd 類
    return _convert_format(nf)


# ── 帶文字字面／留白／顏色的格式（2026-11-08 補）─────────────────────────────
# 監造日報表的 `0_ "天"`、`0_ "次"`、`#,##0_);[Red]\(#,##0\)` 原本整個被丟掉，
# 預覽上「740 天」變成「740」。o-spreadsheet 其實認得 "字面"、\跳脫字元與
# 下列單字元（o_spreadsheet.js 的 tokenizeFormat／alwaysEscapedCharsInFormat），
# 所以逐字元轉寫；遇到它不認得或語意會變的（民國紀年 e/g、科學記號、AM/PM、
# 條件段 [>=100]、經過時間 [h]）整個格式放棄＝照舊不帶格式，不硬轉。
_OSS_LITERAL_CHARS = set('$+-/():!^&~{}<>= ')
_FMT_COLOR = _re.compile(r'(?i)(black|blue|cyan|green|magenta|red|white|yellow|color\s*\d+)')
_FMT_MAX_SECTIONS = 4   # 正數;負數;零;文字


def _split_format_sections(nf):
    """以 ; 切段，略過 "..." 與 \\x 裡的分號。"""
    parts, buf, i = [], [], 0
    while i < len(nf):
        ch = nf[i]
        if ch == '"':
            j = nf.find('"', i + 1)
            j = len(nf) - 1 if j < 0 else j
            buf.append(nf[i:j + 1])
            i = j + 1
            continue
        if ch == '\\':
            buf.append(nf[i:i + 2])
            i += 2
            continue
        if ch == ';':
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append(''.join(buf))
    return parts


def _convert_format_section(sec):
    """單一段 Excel 格式 → (o-spreadsheet 寫法, 種類)；做不到回 None。

    種類：num／date／text／literal（只有字面，沒有數字或日期位置）。
    """
    out, kinds, i = [], set(), 0
    while i < len(sec):
        ch = sec[i]
        if ch == '"':
            j = sec.find('"', i + 1)
            if j < 0:
                return None
            out.append(sec[i:j + 1])
            i = j + 1
        elif ch == '\\':
            if i + 1 >= len(sec):
                return None
            out.append(sec[i:i + 2])
            i += 2
        elif ch == '[':
            j = sec.find(']', i)
            if j < 0:
                return None
            inner = sec[i + 1:j]
            if inner.startswith('$'):
                # [$NT$-404] → "NT$"；[$-404] 只是地區碼 → 拿掉
                sym = inner[1:].split('-', 1)[0].replace('"', '')
                if sym:
                    out.append('"%s"' % sym)
            elif not _FMT_COLOR.fullmatch(inner):
                return None          # 條件段、經過時間等：語意不同，不轉
            i = j + 1                # 顏色：預覽不上色，數字照樣顯示
        elif ch == '_':
            out.append(' ')          # 對齊留白（寬度＝下一個字元）→ 一個空白
            i += 2
        elif ch == '*':
            i += 2                   # 重複填滿字元：預覽用不到
        elif ch in '0#?':
            out.append('0' if ch == '0' else '#')
            kinds.add('num')
            i += 1
        elif ch in ',.':
            out.append(ch)
            i += 1
        elif ch == '%':
            out.append(ch)
            kinds.add('num')
            i += 1
        elif ch == '@':
            out.append(ch)
            kinds.add('text')
            i += 1
        elif ch.lower() in 'dmyhs':
            out.append(ch.lower())
            kinds.add('date')
            i += 1
        elif ch in _OSS_LITERAL_CHARS:
            out.append(ch)
            i += 1
        else:
            return None              # e／g（民國紀年）、E+、AM/PM、General…
    if len(kinds) > 1:
        return None
    return ''.join(out), (kinds.pop() if kinds else 'literal')


def _convert_format(nf):
    """整個 Excel number format → o-spreadsheet 可解析的格式；做不到回 None。

    段落規則照 o-spreadsheet 的 convertFormatToInternalFormat：第一段要是數字或
    日期（只有一段時可以是文字）、第二／三段數字或日期、第四段文字。
    """
    sections = _split_format_sections(nf)
    if len(sections) > _FMT_MAX_SECTIONS or not sections[0].strip():
        return None
    converted = []
    for idx, sec in enumerate(sections):
        if not sec:
            converted.append('')
            continue
        res = _convert_format_section(sec)
        if res is None:
            return None
        text, kind = res
        if idx == 0 and kind == 'text' and len(sections) > 1:
            return None
        if idx in (1, 2) and kind == 'text':
            return None
        if idx == 3 and kind not in ('text', 'literal'):
            return None
        converted.append(text)
    result = ';'.join(converted).rstrip(';')
    return result or None


# 文字格的內容若長得像數字／日期（'45.60'、'258,923,496'、'2024/12/31'），o-spreadsheet
# 會把它解析成數值再套格式——jt 監造日報表「實際進度」是文字 '45.60' 配 0.00%，預覽變成
# 4560.00%。Excel 對文字格不套數字格式，所以這種格改用文字格式 @ 照字面顯示。
_TEXT_PARSED_AS_VALUE = _re.compile(
    r'\s*(?:'
    r'[-+]?\$?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?\s*%?'     # 數字／千分位／百分比
    r'|\d{1,4}([/\-.])\d{1,2}(?:\1\d{1,4})?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?'  # 日期
    r'|\d{1,2}:\d{2}(?::\d{2})?'                                    # 時間
    r'|true|false'
    r')\s*', _re.IGNORECASE)
TEXT_FORMAT = '@'


def _text_cell_needs_text_format(cell):
    value = cell.value
    return (getattr(cell, 'data_type', None) == 's' and isinstance(value, str)
            and not value.startswith('=')
            and bool(_TEXT_PARSED_AS_VALUE.fullmatch(value)))


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


_VML_V = 'urn:schemas-microsoft-com:vml'
_VML_O = 'urn:schemas-microsoft-com:office:office'


def _pt_to_px(val):
    """VML style 尺寸字串 → px（預設單位 pt，96/72）。"""
    if val is None:
        return 0
    s = str(val).strip().lower()
    try:
        if s.endswith('px'):
            return int(round(float(s[:-2])))
        if s.endswith('pt'):
            return int(round(float(s[:-2]) * 96.0 / 72.0))
        return int(round(float(s) * 96.0 / 72.0))
    except ValueError:
        return 0


def _parse_vml_style(style):
    out = {}
    for part in (style or '').replace('\n', '').split(';'):
        if ':' in part:
            k, v = part.split(':', 1)
            out[k.strip().lower()] = v.strip()
    return out


def _parse_vml_images(zf, vml_part, names, sheet_index):
    """解析 VML（舊版）內嵌圖：<v:shape style=...><v:imagedata o:relid=.../>。"""
    import base64 as _b64
    import posixpath
    import xml.etree.ElementTree as ET
    if vml_part not in names:
        return []
    vml_base = posixpath.dirname(vml_part)
    vml_rels = _parse_rels(
        zf, _norm_path(vml_base, '_rels/%s.rels' % posixpath.basename(vml_part)))
    try:
        root = ET.fromstring(zf.read(vml_part))
    except Exception:
        return []
    out = []
    for shape in root.iter('{%s}shape' % _VML_V):
        imed = shape.find('{%s}imagedata' % _VML_V)
        if imed is None:
            continue
        relid = imed.get('{%s}relid' % _VML_O) or imed.get('relid')
        media_t = vml_rels.get(relid, (None, None))[0]
        if not media_t:
            continue
        media_part = _norm_path(vml_base, media_t)
        if media_part not in names:
            continue
        data = zf.read(media_part)
        if not data or len(data) > 4 * 1024 * 1024:
            continue
        ext = media_part.rsplit('.', 1)[-1].lower()
        mimetype = _MIME_BY_EXT.get(ext)
        if not mimetype:
            continue
        st = _parse_vml_style(shape.get('style'))
        x = _pt_to_px(st.get('margin-left', '0'))
        y = _pt_to_px(st.get('margin-top', '0'))
        width = max(_pt_to_px(st.get('width', '120')) or 120, 32)
        height = max(_pt_to_px(st.get('height', '60')) or 60, 32)
        out.append({
            'sheet_index': sheet_index,
            'base64': _b64.b64encode(data).decode(),
            'mimetype': mimetype,
            'x': max(x, 0), 'y': max(y, 0), 'width': width, 'height': height,
        })
    return out


def _parse_rels(zf, rels_path):
    import xml.etree.ElementTree as ET
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    out = {}
    for rel in root.findall('{%s}Relationship' % _PR):
        out[rel.get('Id')] = (rel.get('Target'), rel.get('Type') or '')
    return out


def _header_footer_rids(zf, sheet_part, names):
    """工作表 XML 裡 <legacyDrawingHF r:id> 指到的 rel id（頁首／頁尾圖用的 VML）。"""
    import xml.etree.ElementTree as ET
    if sheet_part not in names:
        return set()
    try:
        root = ET.fromstring(zf.read(sheet_part))
    except ET.ParseError:
        return set()
    ss_main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    return {el.get('{%s}id' % _R) for el in root.iter('{%s}legacyDrawingHF' % ss_main)}


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
        # 舊版 VML 內嵌圖。排除頁首／頁尾圖（<legacyDrawingHF>，例如 &C&G 置中頁首浮水印）：
        # 它只在列印／整頁模式出現、不是貼在儲存格上的圖；當成浮動圖片放左上角會整片
        # 蓋住表頭（2026-11-08 jt 監造日報表實例；樣板庫 4 個有圖的 xlsx 全是這種）。
        hf_rids = _header_footer_rids(zf, sheet_part, names)
        for rid, (vt, typ) in rels.items():
            if typ.endswith('/vmlDrawing') and rid not in hf_rids:
                out.extend(_parse_vml_images(zf, _norm_path(base, vt), names, si))
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
            if content != '' and _text_cell_needs_text_format(cell):
                ocell['format'] = TEXT_FORMAT   # 見 _TEXT_PARSED_AS_VALUE
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


# 防 zip 炸彈（2026-11-08）：openpyxl 把整份 XML 讀進記憶體（每格是一個 Python 物件），
# 1 MB 的 xlsx 可以宣稱解開有幾 GB。Python zipfile 只會解到 zip 裡宣告的大小
# （ZipExtFile 以 file_size 截斷），所以加總宣告的 XML 大小就是實際讀取量的上限。
# 只算 XML 類：圖片 openpyxl 不解析。jt 11-08 實測最大的 xlsx 解開共 11.5 MB（多半是圖）。
MAX_UNZIPPED_XML_BYTES = 40 * 1024 * 1024
_XML_PART_SUFFIXES = ('.xml', '.rels', '.vml')


class XlsxTooLarge(ValueError):
    """xlsx 解壓後的 XML 超過 MAX_UNZIPPED_XML_BYTES。"""


def _guard_unzipped_size(file_bytes):
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            total = sum(i.file_size for i in zf.infolist()
                        if i.filename.lower().endswith(_XML_PART_SUFFIXES))
    except zipfile.BadZipFile:
        return              # 不是 zip：交給 openpyxl 照原本的方式報錯
    if total > MAX_UNZIPPED_XML_BYTES:
        raise XlsxTooLarge('xlsx 解壓後 XML 共 %d bytes，超過上限 %d'
                           % (total, MAX_UNZIPPED_XML_BYTES))


def xlsx_bytes_to_workbook_data(file_bytes, base):
    """把 xlsx bytes 轉成 o-spreadsheet WorkbookData dict。

    :param base: 由 spreadsheet.spreadsheet._empty_spreadsheet_data() 提供的底稿
                 （含正確 version / settings.locale / revisionId），只覆寫 sheets/池。
    :return: (workbook_data:dict, parse_log:str)
    :raises XlsxTooLarge: 解壓後太大（不解析，避免拖垮 worker）
    """
    import io
    from openpyxl import load_workbook

    _guard_unzipped_size(file_bytes)

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
