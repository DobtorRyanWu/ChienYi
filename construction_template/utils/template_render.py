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


def _sheet_and_shared(zf):
    """回傳 (worksheet entry 名稱, 共用字串陣列)"""
    names = zf.namelist()
    sheet = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))[0]
    shared = []
    if 'xl/sharedStrings.xml' in names:
        shared = xlsx_placeholder.parse_shared_strings(
            zf.read('xl/sharedStrings.xml').decode('utf-8'))
    return sheet, shared


def _render_placeholder(src, dst, mapping, record):
    """佔位符樣板（${token} / ${table:coll.field}）——舊 EAGLE 系統帶來的格式"""
    with zipfile.ZipFile(src) as zf:
        sheet_name, shared = _sheet_and_shared(zf)
        sheet_xml = zf.read(sheet_name).decode('utf-8')

    context = mapping.build_context(record)
    context['__shared__'] = shared
    new_xml = xlsx_placeholder.expand_and_fill(sheet_xml, context)

    leftover = sorted(set(xlsx_placeholder.TOKEN_RE.findall(new_xml)))
    if leftover:
        # 沒填到的佔位符會原樣印在報表上，必須讓人知道
        _logger.warning('樣板 %s 有 %s 個佔位符沒有對應資料：%s',
                        mapping.__name__, len(leftover), '、'.join(leftover[:12]))

    zip_patch.patch(src, dst, {sheet_name: new_xml.encode('utf-8')})
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

    if record._name != mapping.MODEL:
        raise UserError('樣板「%s」對應的是 %s，不能用 %s 的資料套印。'
                        % (template.display_name, mapping.MODEL, record._name))

    raw = template.attachment_id.raw
    mode = getattr(mapping, 'MODE', 'cells')

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
