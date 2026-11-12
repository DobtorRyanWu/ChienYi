# -*- coding: utf-8 -*-
"""樣板上的「欄位對照」（document.template.field_mapping）：檢查寫法、解析成 {位置: (欄位路徑, 格式器)}。

淞源 2026-11-10 會議 C3：老闆說可以依機關微調欄位對應。樣板表單上一直有「欄位對照」這個 JSON 欄位，
但套印從來沒有讀它（只存不讀）。這裡讓它生效：它是「蓋在內建對照表（mappings/<類型>.py）上面的微調」，
沒填的位置照內建對照表，填了的位置改用這裡指定的欄位。

寫法：{"位置": "欄位路徑"} 或 {"位置": "欄位路徑|格式器"}
* 位置：座標式樣板（對照表 MODE＝cells）寫儲存格座標，例 "B6"；
        佔位符樣板（xlsx 的 ${代號}、docx 的 {{ 代號 }}）寫代號，例 "projectName"、"project.name"（代號本身可以帶點）。
        明細表（一列一筆）不能在這裡改：整張明細表的代號會被擋下來，明細欄位的代號寫了也不會有作用。
* 欄位路徑：從這張表的資料來源（對照表的 MODEL）出發，用 . 一層一層走，例 "project_id.partner_id.name"。
* 格式器：utils/formatters.py 的 FORMATTERS（民國日期、選項文字、金額…）。

路徑只准走欄位，而且收得很緊（這是一段會被存進資料庫、之後由別人匯出時執行的設定）：
* 每一段都要是模型上真的有的欄位；底線開頭的一律不收（擋 __class__ 這類屬性）；
* 中間只能經過「多對一」欄位（一對多／多對多要取哪一筆說不清楚）；
* 最後一段要是印得出來的型別（文字、數字、日期、布林、選項、多對一）；
* 限特定群組才能讀的欄位不收（匯出的人不一定有那個群組；也避免把機敏欄位印進表單）。
"""
import re

from .formatters import FORMATTERS

MODE_CELLS = 'cells'
CELL_KEY = re.compile(r'^[A-Z]{1,3}[1-9][0-9]*$')
TOKEN_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$')
FORMATTER_SEPARATOR = '|'
PRINTABLE_TYPES = frozenset({
    'char', 'text', 'integer', 'float', 'monetary', 'date', 'datetime', 'boolean', 'selection', 'many2one'})
MAX_ENTRIES = 200           # 一份樣板最多微調幾個位置（再多就該改內建對照表）


def parse_spec(spec):
    """'路徑' 或 '路徑|格式器' → (路徑, 格式器名稱或 None)。寫法不對丟 ValueError（訊息給使用者看）。"""
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError('要寫成文字，例："project_id.name"')
    path, _sep, formatter = (part.strip() for part in spec.partition(FORMATTER_SEPARATOR))
    if not path:
        raise ValueError('沒有寫欄位路徑')
    if FORMATTER_SEPARATOR in formatter:
        raise ValueError('格式器只能寫一個')
    if formatter and formatter not in FORMATTERS:
        raise ValueError('沒有「%s」這個格式器（可用：%s）' % (formatter, '、'.join(sorted(FORMATTERS))))
    return path, formatter or None


def check_path(env, model_name, path):
    """path 能不能從 model_name 走得通、印得出來；不行丟 ValueError（訊息給使用者看）。"""
    model = env[model_name]
    parts = path.split('.')
    for index, name in enumerate(parts):
        if not name or name.startswith('_'):
            raise ValueError('「%s」不是可以用的欄位名稱' % name)
        field = model._fields.get(name)
        if field is None:
            raise ValueError('「%s」（%s）沒有「%s」這個欄位' % (model._description, model._name, name))
        if field.groups:
            raise ValueError('欄位「%s」限特定群組才能讀，不能放進欄位對照' % name)
        if index == len(parts) - 1:
            if field.type not in PRINTABLE_TYPES:
                raise ValueError('欄位「%s」的型別（%s）不能直接印在表單上' % (name, field.type))
        else:
            if field.type != 'many2one':
                raise ValueError('路徑中間只能經過「多對一」欄位，「%s」是 %s' % (name, field.type))
            model = env[field.comodel_name]


def parse(env, mapping_module, mapping_dict):
    """整份欄位對照 → ({位置: (路徑, 格式器)}, [錯誤訊息])。

    mapping_module：這類樣板的內建對照表（mappings/<類型>.py）；None＝這類樣板還沒有對照表（不能套印，也就不能微調）。
    """
    if not isinstance(mapping_dict, dict):
        return {}, ['欄位對照要是一個 JSON 物件：{"位置": "欄位路徑"}']
    if not mapping_dict:
        return {}, []
    if mapping_module is None:
        return {}, ['這類樣板還沒有內建的對照表、不能自動套印，所以欄位對照不會有作用；請把它清空']
    if len(mapping_dict) > MAX_ENTRIES:
        return {}, ['欄位對照最多 %s 個位置（現在 %s 個）' % (MAX_ENTRIES, len(mapping_dict))]
    cells = getattr(mapping_module, 'MODE', MODE_CELLS) == MODE_CELLS
    models = mapping_module.MODEL if isinstance(mapping_module.MODEL, tuple) else (mapping_module.MODEL,)
    parsed, errors = {}, []
    for key, spec in mapping_dict.items():
        if cells and not CELL_KEY.match(key):
            errors.append('「%s」：這類樣板是照儲存格座標填的，位置要寫座標（例：B6）' % key)
            continue
        if not cells and not TOKEN_KEY.match(key):
            errors.append('「%s」：這類樣板是照佔位符填的，位置要寫樣板裡的代號（英文字母開頭，只能有英數字、底線與點）' % key)
            continue
        try:
            path, formatter = parse_spec(spec)
            for model_name in models:
                check_path(env, model_name, path)
        except ValueError as exc:
            errors.append('「%s」：%s' % (key, exc))
            continue
        parsed[key] = (path, formatter)
    return parsed, errors
