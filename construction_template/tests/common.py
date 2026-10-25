# -*- coding: utf-8 -*-
"""套印測試共用：讀產出檔的儲存格／段落文字、掃描沒被換掉的標記。

掃描只看「實際被引用的文字」：xlsx 的佔位符格套印後會改寫成 inlineStr，原本的
共用字串還留在 sharedStrings.xml 裡（沒有儲存格引用它）——直接掃整份
sharedStrings 會把這些孤兒字串誤判成殘留。
"""

import html
import io
import re
import zipfile

from odoo.tools.misc import file_path

from ..utils import xlsx_placeholder

# 套印後不該再出現的標記：xlsx 佔位符、docxtpl、EAGLE 舊語法
LEFTOVER_RE = re.compile(r'\$\{|\{\{|\{%|\+\+\+')

CELL_RE = re.compile(r'<c r="([A-Z]+\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.DOTALL)
W_T_RE = re.compile(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>')


def blank_template(name):
    """模組內的空白樣板路徑（data/templates_blank/<name>）"""
    return file_path('construction_template/data/templates_blank/%s' % name)


def xlsx_cells(data):
    """xlsx bytes → {工作表檔名: {儲存格: 顯示文字}}"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = xlsx_placeholder.parse_shared_strings(
                zf.read('xl/sharedStrings.xml').decode('utf-8'))
        result = {}
        for name in sorted(names):
            if not (name.startswith('xl/worksheets/sheet') and name.endswith('.xml')):
                continue
            xml = zf.read(name).decode('utf-8')
            result[name] = {ref: xlsx_placeholder.cell_text(attrs, body, shared)
                            for ref, attrs, body in CELL_RE.findall(xml)}
    return result


def docx_texts(data):
    """docx bytes → 每個 part（本文、頁首頁尾）的段落文字串接"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: html.unescape(''.join(W_T_RE.findall(zf.read(name).decode('utf-8'))))
                for name in zf.namelist()
                if name.startswith('word/') and name.endswith('.xml')
                and ('document' in name or 'header' in name or 'footer' in name)}


def leftovers_xlsx(data):
    """所有儲存格裡還留著的標記：[(工作表, 儲存格, 文字)]"""
    return [(sheet, ref, text)
            for sheet, cells in xlsx_cells(data).items()
            for ref, text in cells.items() if LEFTOVER_RE.search(text or '')]


def leftovers_docx(data):
    return [(part, LEFTOVER_RE.search(text).group(0))
            for part, text in docx_texts(data).items() if LEFTOVER_RE.search(text)]
