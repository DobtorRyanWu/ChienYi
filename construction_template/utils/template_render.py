# -*- coding: utf-8 -*-
"""樣板套印：把記錄的資料填進 document.template 的空白樣板。

流程：
    document.template（附件 = 空白 xlsx）
      → 依 template_type 找對照表 mappings/<type>.py
      → 依對照表解出 {儲存格: 值}
      → xlsx_fill 改寫 worksheet XML
      → zip_patch 位元組層寫回（其餘 entry 原封不動）
      → 回傳 (bytes, 檔名)

對照表是**資料不是邏輯**，加一張新表只要加一個 mappings/<type>.py，不必改這裡。
"""

import importlib
import logging
import os
import tempfile
import zipfile

from odoo.exceptions import UserError

from . import docx_render
from . import xlsx_placeholder
from . import xlsx_sheets
from . import zip_patch
from .formatters import FORMATTERS
from .xlsx_fill import fill

_logger = logging.getLogger(__name__)

MAPPING_PACKAGE = 'odoo.addons.construction_template.mappings'


def get_mapping(template_type):
    """載入對照表模組；沒有就回 None（代表這型還沒做套印）。"""
    try:
        return importlib.import_module('%s.%s' % (MAPPING_PACKAGE, template_type))
    except ImportError:
        return None


def resolve(record, path):
    """沿 'a.b.c' 走訪記錄，回傳 (擁有最後一段欄位的記錄, 欄位名, 值)。

    回傳擁有者與欄位名是為了讓 selection_label 這類格式器能查到 Selection 定義。
    """
    parts = path.split('.')
    owner = record
    for name in parts[:-1]:
        owner = owner[name]
        if not owner:
            return owner, parts[-1], None
        owner = owner[:1] if hasattr(owner, 'ids') else owner
    field = parts[-1]
    return owner, field, (owner[field] if owner else None)


def apply_spec(record, spec):
    """對照表的一個值規格 → 實際字串／數字。

    spec 三種寫法：
        'a.b.c'                    直接取值
        ('a.b.c', '格式器名稱')     取值後套 formatters.py 的格式器
        callable(record)           需要組合多個欄位時用（例：數量+單位）
    """
    if callable(spec):
        return spec(record)
    path, formatter_name = (spec, None) if isinstance(spec, str) else spec
    owner, field, value = resolve(record, path)
    if formatter_name:
        formatter = FORMATTERS.get(formatter_name)
        if not formatter:
            raise UserError('對照表用了不存在的格式器：%s' % formatter_name)
        return formatter(value, owner, field)
    if value is None or value is False:
        return ''
    # Many2one 直接給名稱，避免印出 record repr
    if hasattr(value, 'display_name'):
        return value.display_name or ''
    return value


def build_values(record, mapping):
    """依對照表算出 {儲存格: 值}，含 ROWS 的明細迴圈。"""
    values = {}
    for ref, spec in getattr(mapping, 'CELLS', {}).items():
        values[ref] = apply_spec(record, spec)

    for block in getattr(mapping, 'ROWS', []):
        lines = record[block['source']]
        if block.get('filter'):
            lines = lines.filtered(block['filter'])
        max_rows = block.get('max_rows', len(lines))
        for offset, line in enumerate(lines[:max_rows]):
            row_num = block['start_row'] + offset
            for col, spec in block['columns'].items():
                values['%s%s' % (col, row_num)] = apply_spec(line, spec)
        if len(lines) > max_rows:
            _logger.warning(
                '樣板 %s 的 %s 只預留 %s 列，實際有 %s 筆，超出的沒有印出來',
                mapping.__name__, block['source'], max_rows, len(lines))
    return values


def _paginate(records, page_size, pad):
    """切頁並補足最後一頁——EAGLE 原系統的作法（每頁固定列數、不足補空白）"""
    if not records:
        return [list(pad and [dict(pad)] * page_size or [])]
    pages = [records[i:i + page_size] for i in range(0, len(records), page_size)]
    if pad:
        last = pages[-1]
        while len(last) < page_size:
            last.append(dict(pad))
    return pages


def _render_placeholder(src, dst, mapping, record):
    """佔位符樣板（${token} / ${table:coll.field}）——舊 EAGLE 系統帶來的格式。

    多工作表要全部處理：通報單的表頭在 sheet1、工項明細在 sheet2，
    只填第一張的話明細表會整張留著佔位符。

    對照表若宣告 PAGINATE，就照原系統的方式分頁：每頁固定列數、
    不足補空白列、用複製工作表產生「第N頁」。
    """
    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = xlsx_placeholder.parse_shared_strings(
                zf.read('xl/sharedStrings.xml').decode('utf-8'))
        sheets = {n: zf.read(n).decode('utf-8')
                  for n in sorted(names) if n.startswith('xl/worksheets/sheet')}
        base_parts = {n: zf.read(n).decode('utf-8') for n in
                      ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels',
                       '[Content_Types].xml') if n in names}
        for n in names:
            if n.startswith('xl/worksheets/_rels/'):
                base_parts[n] = zf.read(n).decode('utf-8')

    context = mapping.build_context(record)
    paginate = getattr(mapping, 'PAGINATE', None)
    updates, additions, leftover = {}, {}, set()

    if paginate:
        source = paginate['source']
        pages = _paginate(list(context.get(source) or []),
                          paginate['page_size'], paginate.get('pad'))
        total = len(pages)
        target = paginate.get('sheet') or sorted(sheets)[0]
        page_xmls = []
        for index, rows in enumerate(pages, start=1):
            ctx = dict(context, __shared__=shared)
            ctx[source] = rows
            # 原系統：頁碼是字串「第N頁」，且百分比只在最後一頁給值
            ctx['currentPageNo'] = '第%s頁' % index
            ctx['totalPageNo'] = '第%s頁' % total
            for key in paginate.get('last_page_only', ()):
                if index != total:
                    ctx[key] = ''
            new_xml = xlsx_placeholder.expand_and_fill(sheets[target], ctx)
            page_xmls.append(new_xml)
            leftover |= set(xlsx_placeholder.TOKEN_RE.findall(new_xml))
        updates, additions = xlsx_sheets.build_pages(base_parts, page_xmls)
        others = {n: x for n, x in sheets.items() if n != target}
    else:
        others = sheets

    for name, sheet_xml in others.items():
        if not xlsx_placeholder.has_placeholders(sheet_xml, shared):
            continue
        ctx = dict(context, __shared__=shared)
        new_xml = xlsx_placeholder.expand_and_fill(sheet_xml, ctx)
        updates[name] = new_xml.encode('utf-8')
        leftover |= set(xlsx_placeholder.TOKEN_RE.findall(new_xml))

    if leftover:
        # 沒填到的佔位符會原樣印在報表上，必須讓人知道
        _logger.warning('樣板 %s 有 %s 個佔位符沒有對應資料：%s',
                        mapping.__name__, len(leftover), '、'.join(sorted(leftover)[:12]))

    zip_patch.patch(src, dst, updates, additions)
    with open(dst, 'rb') as fp:
        return fp.read()


def _render_cells(src, dst, mapping, record, template):
    """座標對照樣板（舊監造版日報表這種沒有佔位符的檔）"""
    values = build_values(record, mapping)
    with zipfile.ZipFile(src) as zf:
        sheet_xml = zf.read(mapping.SHEET).decode('utf-8')

    new_xml, missing = fill(sheet_xml, values)
    if missing:
        # 填不進去代表對照表的座標寫錯了，必須讓人知道而不是默默少資料
        raise UserError(
            '樣板「%s」有 %s 個儲存格填不進去（樣板裡找不到該列）：%s\n'
            '請檢查 mappings/%s.py 的座標。'
            % (template.display_name, len(missing), '、'.join(missing[:10]),
               template.template_type))

    zip_patch.patch(src, dst, {mapping.SHEET: new_xml.encode('utf-8')})
    with open(dst, 'rb') as fp:
        return fp.read()


def render(template, record):
    """把 record 的資料填進 template 的空白樣板。

    :param template: document.template 記錄（要有 attachment_id）
    :param record: 資料來源記錄，模型須與對照表的 MODEL 相符
    :return: (檔案 bytes, 檔名)
    """
    template.ensure_one()
    record.ensure_one()

    if not template.attachment_id:
        raise UserError('樣板「%s」還沒有上傳檔案。' % template.display_name)

    mapping = get_mapping(template.template_type)
    if mapping is None:
        raise UserError(
            '「%s」這類樣板還沒有建立欄位對照表，無法自動帶入資料。\n'
            '目前可以先下載空白樣板自行填寫。'
            % dict(template._fields['template_type'].selection).get(
                template.template_type, template.template_type))

    # MODEL 可以是 tuple——同一份空白樣板由不同模型供資料（見 progress_report）
    allowed = mapping.MODEL if isinstance(mapping.MODEL, tuple) else (mapping.MODEL,)
    if record._name not in allowed:
        raise UserError('樣板「%s」對應的是 %s，不能用 %s 的資料套印。'
                        % (template.display_name, '、'.join(allowed), record._name))

    raw = template.attachment_id.raw
    mode = getattr(mapping, 'MODE', 'cells')

    # 樣板檔的種類要與對照表相符。掛錯檔（例如把 xlsx 上傳成 docx 類型的專案
    # 專屬樣板）時，底層套件會拋「is not a Word file, content type is …」這種
    # 看不懂的 ValueError，而且因為專案專屬樣板優先序最高，會直接蓋掉正確的
    # 系統預設樣板——訊息必須講清楚是哪一份樣板、該換成什麼。
    expected_ext = '.docx' if mode == 'docx' else '.xlsx'
    filename = template.attachment_id.name or ''
    if not filename.lower().endswith(expected_ext):
        raise UserError(
            '樣板「%s」的檔案是「%s」，但「%s」需要 %s 檔。\n'
            '請到「系統設定 > 樣板設定」開啟這份樣板，重新上傳正確格式的空白樣板；'
            '或把這份樣板停用，改用系統預設樣板。'
            % (template.display_name, filename,
               dict(template._fields['template_type'].selection).get(
                   template.template_type, template.template_type),
               expected_ext))

    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'src.xlsx')
        dst = os.path.join(tmpdir, 'out.xlsx')
        with open(src, 'wb') as fp:
            fp.write(raw)

        if mode == 'docx':
            filled = docx_render.render(raw, mapping.build_context(record))
        elif mode == 'placeholder':
            filled = _render_placeholder(src, dst, mapping, record)
        else:
            filled = _render_cells(src, dst, mapping, record, template)

    base = getattr(mapping, 'FILENAME', None)
    filename = base(record) if callable(base) else '%s_%s.xlsx' % (
        template.name or '樣板', record.display_name or record.id)
    return filled, filename
