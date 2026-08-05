# -*- coding: utf-8 -*-
"""xlsx 佔位符套印：`${token}` 取值、`${table:collection.field}` 整列複製。

## 語法（來自舊 EAGLE 系統的樣板檔）

    ${project.name}                     純取值
    ${table:payItems.description}       表格列——整列會依集合筆數複製

一列裡只要出現任何 `${table:xxx.*}`，該列就是「樣板列」，會被展開成 N 列
（N = 集合筆數），其後所有列一併下移。

## 為什麼還是走原始 XML 而不是 openpyxl

新樣板雖然沒有 logo/VML（舊的那批有），但含 `xl/printerSettings/printerSettings1.bin`
——紙張大小、方向、邊界都在裡面。openpyxl 存檔會丟掉它，對要列印的公文表單
是實質損失。搭配 zip_patch 只改 worksheet XML，其餘 entry 位元組原封不動。

## 展開時要一起處理的東西

* 樣板列之後的所有 `<row r>` 與其中 `<c r>` 的列號要 +N-1
* `<mergeCells>`：樣板列內的合併範圍要跟著複製；位於樣板列之後的要下移；
  跨越樣板列的（例如 A5:A20）要把結尾拉長
* `<dimension ref>` 要更新
"""

import re

CELL_RE = re.compile(r'<c\s+r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.DOTALL)
ROW_RE = re.compile(r'<row\s+r="(\d+)"([^>]*?)(?:/>|>(.*?)</row>)', re.DOTALL)
SHARED_T_RE = re.compile(r'<si>(.*?)</si>', re.DOTALL)
T_TEXT_RE = re.compile(r'<t[^>]*>(.*?)</t>', re.DOTALL)
TOKEN_RE = re.compile(r'\$\{([^}]+)\}')
TABLE_TOKEN_RE = re.compile(r'\$\{table:([A-Za-z_][\w.]*?)\.([\w]+)\}')
MERGE_RE = re.compile(r'<mergeCell\s+ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"\s*/>')
DIMENSION_RE = re.compile(r'<dimension\s+ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"\s*/>')
STYLE_RE = re.compile(r'\ss="(\d+)"')


def parse_shared_strings(xml):
    """sharedStrings.xml → 字串陣列（同一 <si> 內多個 <t> 要接起來）"""
    return [''.join(T_TEXT_RE.findall(si)) for si in SHARED_T_RE.findall(xml)]


def cell_text(t_attr, body, shared):
    """取出儲存格的顯示文字（共用字串或 inline）"""
    if body is None:
        return ''
    if 't="s"' in t_attr:
        m = re.search(r'<v>(\d+)</v>', body)
        return shared[int(m.group(1))] if m and int(m.group(1)) < len(shared) else ''
    if 't="inlineStr"' in t_attr:
        return ''.join(T_TEXT_RE.findall(body))
    m = re.search(r'<v>(.*?)</v>', body, re.DOTALL)
    return m.group(1) if m else ''


def escape(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def render_cell(col, row, style_attr, text):
    """一律輸出 inlineStr，保留樣式索引（不動 sharedStrings 以免索引全亂）"""
    if text in (None, ''):
        return '<c r="%s%s"%s/>' % (col, row, style_attr)
    space = ' xml:space="preserve"' if re.search(r'^\s|\s$|\n', str(text)) else ''
    return '<c r="%s%s"%s t="inlineStr"><is><t%s>%s</t></is></c>' % (
        col, row, style_attr, space, escape(text))


def substitute(text, getter):
    """把文字裡的 ${...} 換成值；getter(token) 回傳字串"""
    return TOKEN_RE.sub(lambda m: str(getter(m.group(1))), text)


def _collections_of(row_body, shared):
    """該列用到的所有集合名稱（依出現順序去重）。

    一列可以同時掛多個集合——施工日誌第一聯 R21 同時有 manUsage 與 machineUsage
    （左半人員、右半機具），自主檢查總表也有 inspections.left / inspections.right。
    展開列數取各集合筆數的最大值，各自獨立索引，短的那邊留白。
    """
    found = []
    for col, rownum, attrs, body in CELL_RE.findall(row_body):
        for m in TABLE_TOKEN_RE.finditer(cell_text(attrs, body, shared)):
            if m.group(1) not in found:
                found.append(m.group(1))
    return found


def _rewrite_row(row_body, new_row_num, getter, shared):
    """重寫一列：換列號、填值"""
    out = []
    pos = 0
    for m in CELL_RE.finditer(row_body):
        out.append(row_body[pos:m.start()])
        col, _old_row, attrs, body = m.groups()
        style_m = STYLE_RE.search(attrs or '')
        style_attr = ' s="%s"' % style_m.group(1) if style_m else ''
        text = cell_text(attrs, body, shared)
        if '${' in text:
            out.append(render_cell(col, new_row_num, style_attr, substitute(text, getter)))
        else:
            # 沒有佔位符的儲存格：原樣保留，只換列號
            out.append(m.group(0).replace('r="%s%s"' % (col, _old_row),
                                          'r="%s%s"' % (col, new_row_num), 1))
        pos = m.end()
    out.append(row_body[pos:])
    return ''.join(out)


def expand_and_fill(sheet_xml, context):
    """展開表格列並填值。

    :param context: {'project.name': '磺港溪…', 'payItems': [ {..}, {..} ], ...}
                    純量用完整 token 當鍵；集合用集合名當鍵，值為 dict 陣列。
    :return: 新的 worksheet XML
    """
    shared = context.pop('__shared__', [])

    def scalar_getter(token):
        return context.get(token, '')

    # 單趟由上而下重建。不能「先插入複製列、再位移後續列」——那樣新插入的
    # 複製列本身也會被位移一次，跟原本要下移的列撞在一起（實測列 9/12/13）。
    out, pos, offset = [], 0, 0
    shifts = []                      # (樣板列的原列號, 增加的列數)
    for m in ROW_RE.finditer(sheet_xml):
        out.append(sheet_xml[pos:m.start()])
        orig_row, attrs, body = int(m.group(1)), m.group(2), m.group(3)
        colls = _collections_of(body, shared) if body else []

        if colls:
            data = {c: (context.get(c) or []) for c in colls}
            # 多集合同列時取最長的那個；沒資料也留一列空白，維持表格外觀
            count = max([len(v) for v in data.values()] + [1])
            for i in range(count):
                def getter(token, _i=i):
                    tm = TABLE_TOKEN_RE.fullmatch('${%s}' % token)
                    if tm:
                        rows_ = data.get(tm.group(1)) or []
                        return rows_[_i].get(tm.group(2), '') if _i < len(rows_) else ''
                    return context.get(token, '')
                new_row = orig_row + offset + i
                out.append('<row r="%s"%s>%s</row>' % (
                    new_row, attrs, _rewrite_row(body, new_row, getter, shared)))
            if count > 1:
                shifts.append((orig_row, count - 1))
            offset += count - 1
        else:
            new_row = orig_row + offset
            if body is None:
                out.append('<row r="%s"%s/>' % (new_row, attrs))
            else:
                out.append('<row r="%s"%s>%s</row>' % (
                    new_row, attrs, _renumber_cells(body, orig_row, new_row)))
        pos = m.end()
    out.append(sheet_xml[pos:])
    sheet_xml = ''.join(out)

    sheet_xml = _remap_merges(sheet_xml, shifts)
    sheet_xml = _shift_dimension(sheet_xml, offset)
    return _fill_scalars(sheet_xml, scalar_getter, shared)


def _renumber_cells(body, old_row, new_row):
    """只換列號、其餘原樣（沒有佔位符的一般列走這條）"""
    if old_row == new_row:
        return body
    return re.sub(r'<c\s+r="([A-Z]+)%s"' % old_row,
                  lambda c: '<c r="%s%s"' % (c.group(1), new_row), body)


def _row_start(row, shifts):
    """原列號 → 新列號（該列的起始位置）"""
    return row + sum(d for tr, d in shifts if tr < row)


def _row_end(row, shifts):
    """原列號 → 它在新表裡佔到的最後一列（樣板列會佔多列）"""
    return _row_start(row, shifts) + sum(d for tr, d in shifts if tr == row)


def _remap_merges(sheet_xml, shifts):
    """依展開結果重算所有合併範圍"""
    if not shifts:
        return sheet_xml

    def one(m):
        c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        delta = dict(shifts).get(r1)
        if delta and r1 == r2:
            # 樣板列內部的合併 → 每個複製列各一份
            base = _row_start(r1, shifts)
            return ''.join('<mergeCell ref="%s%s:%s%s"/>' % (c1, base + i, c2, base + i)
                           for i in range(delta + 1))
        return '<mergeCell ref="%s%s:%s%s"/>' % (
            c1, _row_start(r1, shifts), c2, _row_end(r2, shifts))

    sheet_xml = MERGE_RE.sub(one, sheet_xml)
    # count 必須等於實際數量，否則 Excel 判定檔案損毀
    total = len(MERGE_RE.findall(sheet_xml))
    return re.sub(r'<mergeCells count="\d+"', '<mergeCells count="%s"' % total, sheet_xml)




def _shift_dimension(sheet_xml, delta):
    return DIMENSION_RE.sub(
        lambda m: '<dimension ref="%s%s:%s%s"/>' % (
            m.group(1), m.group(2), m.group(3), int(m.group(4)) + delta),
        sheet_xml)


def _fill_scalars(sheet_xml, getter, shared):
    """填掉剩下的純量 ${...}"""
    def one(m):
        col, row, attrs, body = m.groups()
        text = cell_text(attrs, body, shared)
        if '${' not in text:
            return m.group(0)
        style_m = STYLE_RE.search(attrs or '')
        style_attr = ' s="%s"' % style_m.group(1) if style_m else ''
        return render_cell(col, row, style_attr, substitute(text, getter))
    return CELL_RE.sub(one, sheet_xml)


def has_placeholders(sheet_xml, shared):
    """這張表是不是佔位符樣板"""
    for col, row, attrs, body in CELL_RE.findall(sheet_xml):
        if '${' in cell_text(attrs, body, shared):
            return True
    return False
