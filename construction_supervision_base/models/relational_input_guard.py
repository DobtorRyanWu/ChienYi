# -*- coding: utf-8 -*-
"""呼叫端給的關聯 id 不能拿來以 sudo 讀資料（公司儀表板合約 §0b-23，線 H；對所有帳號）。

為什麼要有這一個程式點
----------------------
Odoo 的 related 欄位與儲存型 compute 預設 ``compute_sudo=True``（``odoo/fields.py`` ``_setup_attrs``）：
值是以超級使用者身分算的，不經 ir.rule。而 many2one／many2many／one2many 的值由呼叫端給——於是任何帳號把
「自己讀不到的紀錄 id」填進 ``onchange``、``create``、``write``，系統就以 sudo 把那筆紀錄的內容算出來回給他。
最嚴重的實例（11-06 抗辯 F1）：``supervision.photo.onchange([], {'attachment_id': X}, …)`` 回傳任意附件全文
（``image`` 是 related ``attachment_id.datas``）。在每個欄位逐一補一定會漏，所以這裡只有一條規則：

    **呼叫端給的 id 要被拿來以 sudo 計算東西時，呼叫端自己必須讀得到那筆紀錄。**

守衛欄位
--------
一個模型的「守衛欄位」＝會被某個 compute_sudo 欄位（related 或 compute，儲存或不儲存）當成依賴路徑第一段的
關聯欄位（many2one／one2many／many2many）。清單由 registry 的 ``field_depends`` 算出，每個模型在 registry
準備好之後只算一次（``_register_hook`` 重新設定欄位時清掉重算）；``guarded_fields_of()`` 可以在測試裡印出來比對。

「讀得到」的判定
----------------
用 ``comodel.search([('id', 'in', ids)])``，跟 ``read()``／``fetch()`` 決定能不能讀的是同一條路
（``odoo/models.py`` ``fetch``：有欄位要從資料庫取時走 ``_search``）。**不能只用 ``check_access('read')``**：
``ir.attachment`` 沒有覆寫 ``_check_access``，附件的讀取權（依附件掛的單據、res_id 空白只有建立者讀得到）
是在它覆寫的 ``_search`` 裡判定的（``odoo/addons/base/models/ir_attachment.py`` ``_search``）——只用
``check_access`` 時內部帳號對任何附件都會通過，F1 對監造方照樣打得穿（測試
``test_attachment_check_access_alone_is_not_enough`` 鎖住這一點）。

查哪些值
--------
- ``create``：呼叫端給的值，加上呼叫端控制得到的預設值（context 的 ``default_<欄位>``、``ir.default``）——
  核心在 ``super().create()`` 裡才補預設值，只查 vals 會被 ``default_attachment_id`` 繞過。
- ``write``：只查**改變了**的值。現值以 SQL 讀（不經 ORM 快取：以 sudo 讀現值會把值放進共用快取，之後以本人身分
  讀同一欄位就不再檢查權限）；寫回與現值相同的 id 不查——現值可能是別人設的、本人讀不到但本來就掛著。
- ``onchange``：表單上的值（新紀錄＝全部是新的；既有紀錄＝與資料庫現值比，只查改變了的）＋呼叫端控制得到的預設值。
- x2many 指令（``Command``）：LINK、SET、UPDATE 指到的既有 id 要讀得到（已經掛著的不查）；CREATE、UPDATE 的巢狀
  vals 遞迴到子模型查它自己的守衛欄位；many2one 給成 dict（onchange 的格式）時同理遞迴。
- ``copy``：呼叫端給的 ``default`` 要查；其餘值是從原紀錄複製來的（本人讀得到原紀錄才複製得了），不查——
  生產站有大量「附件 res_id 空白、建立者是系統」的舊照片，照片本身讀得到、附件本人讀不到，複製不能因此被擋。
  只認本模組的憑證物件（``is`` 比對），呼叫端自帶 context 偽造不了。

不查的
------
- ``env.su``：系統內部的 sudo 流程一律不查。
- 在**另一個模型**的 create／write／copy 裡、由伺服器端程式順手建／改的紀錄（例：工程 create 替新工程建分析帳戶，
  分析方案一般帳號沒有讀取 ACL）：值是伺服器挑的。呼叫端直接給的值一定在最外層那個模型的呼叫裡，x2many 的巢狀
  vals 也已在外層遞迴查過（``_nested_in_other_model_crud``；只在已經找到讀不到的 id 時才看呼叫堆疊）。
  已知殘餘：某個模型的 create／write 覆寫若把呼叫端的值原封轉交給另一個模型的 create（非 sudo），內層不再擋。
- 不存在的 id：交給核心照原本的方式報錯（外鍵、MissingError）。
- 路徑第二段以後（例：讀得到的 A 掛著讀不到的 B，related 經 A 讀 B）：那是既有資料，不是呼叫端給的，
  不在這條規則的範圍內（已知殘餘，回報給主迴圈）。
"""
import logging
import sys
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Command

_logger = logging.getLogger(__name__)

RELATIONAL_TYPES = frozenset({'many2one', 'one2many', 'many2many'})
# 「模型＋id」型欄位（Many2oneReference：res_id 配 res_model）。11-06 第二輪抗辯：mail.activity／rating.rating 的
# res_name 以 sudo 依 (res_model, res_id) 算，onchange 帶任意紀錄 id 就逐筆讀到別筆的顯示名稱（18.0 既有、所有帳號）
REFERENCE_TYPE = 'many2one_reference'
GUARDED_HEAD_TYPES = RELATIONAL_TYPES | {REFERENCE_TYPE}
# 目標模型名稱若是 related <many2one ir.model>.model（mail.activity、rating.rating 的 res_model），那個 many2one 也是入口
IR_MODEL = 'ir.model'
IR_MODEL_NAME_FIELD = 'model'
X2MANY_TYPES = frozenset({'one2many', 'many2many'})
DEFAULT_CTX_PREFIX = 'default_'
# registry 上的快取屬性名（每個 registry 一份：模組安裝／升級會建新的 registry）
CACHE_ATTR = '_relational_input_guard_cache'
# 錯誤訊息最多列幾個 id（全部列出沒有意義，也避免訊息過長）
MAX_IDS_IN_MESSAGE = 10
# 複製進行中的 context 旗標：只認 COPY_TOKEN 這個物件本身（同 construction_company_dashboard rule_scope 的寫法）
COPY_CTX = 'relational_input_guard_copy'
# 外層呼叫是這些方法時，視為「伺服器端程式在另一個模型的寫入裡順手建／改紀錄」（見 _nested_in_other_model_crud）
NESTING_METHODS = frozenset({'create', 'write', 'copy'})


class _CopyToken:
    """本模組內部的「複製進行中」憑證（不可序列化成 RPC 值，外部偽造不了）。"""
    __slots__ = ()

    def __repr__(self):
        return '<relational_input_guard copy token>'


COPY_TOKEN = _CopyToken()


# ── 守衛欄位清單 ─────────────────────────────────────────────────────────
def _compute_guarded_fields(model):
    """{關聯欄位名: (以它為路徑第一段、以 sudo 計算的欄位名, …)}。"""
    field_depends = model.pool.field_depends
    guarded = defaultdict(set)
    for field in model._fields.values():
        if not field.compute_sudo or not (field.compute or field.related):
            continue
        for path in field_depends.get(field, ()):
            head = path.split('.', 1)[0]
            dep = model._fields.get(head)
            if dep is not None and dep.type in GUARDED_HEAD_TYPES and head != field.name:
                guarded[head].add(field.name)
    # _inherits：子模型上看得到父模型的欄位（例 product.document 繼承 ir.attachment 的 folder_id、folder_path），
    # 呼叫端對子模型給父模型的關聯值，父模型那層的 sudo 欄位照樣算出來——父模型的守衛欄位也是子模型的
    # （第三輪抗辯 red-team：product.document.onchange 帶讀不到的資料夾讀到資料夾路徑）
    for parent_name in model._inherits:
        parent = model.env[parent_name]
        for head, users in _compute_guarded_fields(parent).items():
            if head in model._fields:
                guarded[head].update(name for name in users if name in model._fields)
    return {name: tuple(sorted(users)) for name, users in guarded.items()}


def guarded_fields_of(model):
    """模型的守衛欄位清單（快取在 registry；registry 還在載入時不快取，因為欄位還會再變）。"""
    registry = model.pool
    cache = vars(registry).setdefault(CACHE_ATTR, {})
    result = cache.get(model._name)
    if result is None:
        result = _compute_guarded_fields(model)
        if registry.ready:
            cache[model._name] = result
    return result


# ── 值的解析 ─────────────────────────────────────────────────────────────
def _as_id(value):
    """把呼叫端給的單一 id 正規化成正整數；不是真紀錄 id（False、NewId、'virtual_3'…）回 None。

    字串數字與整數值的浮點數也算：create 寫欄位時核心直接把值交給 SQL，'5'、5.0 都會被轉成 5。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _many2one_value(value, comodel_name):
    """many2one 的值 → (id 或 None, 巢狀 vals 或 None)。格式比照 ``Many2one.convert_to_cache``。"""
    if isinstance(value, models.BaseModel):
        if value._name != comodel_name:
            return None, None
        ids = [i for i in value._ids if _as_id(i)]
        return (ids[0] if ids else None), None
    if isinstance(value, dict):
        nested = {k: v for k, v in value.items() if k != 'id'}
        return _as_id(value.get('id')), nested
    if isinstance(value, (list, tuple)):
        return (_as_id(value[0]) if value else None), None
    return _as_id(value), None


def _x2many_commands(value):
    """x2many 的值 → [(指令, id, vals)]（比照 ``_RelationalMulti.convert_to_cache`` 接受的格式）。"""
    if not value:
        return []
    if isinstance(value, models.BaseModel):
        return [(Command.SET, None, list(value._ids))]
    if not isinstance(value, (list, tuple)):
        return []
    commands = []
    for command in value:
        if isinstance(command, dict):
            commands.append((Command.CREATE, None, command))
        elif isinstance(command, (list, tuple)) and command:
            op = command[0]
            arg1 = command[1] if len(command) > 1 else None
            arg2 = command[2] if len(command) > 2 else None
            commands.append((op, arg1, arg2))
        else:
            commands.append((Command.LINK, command, None))
    return commands


# ── 現值（SQL，不經 ORM 快取）──────────────────────────────────────────────
def _real_ids(records):
    return [i for i in records._ids if _as_id(i)]


def _current_values(records, field):
    """{紀錄 id: 現值 id 的集合}；欄位不是資料庫欄位（算不出現值）回 None＝每個值都當成新的。"""
    ids = _real_ids(records)
    if not ids:
        return {}
    env = records.env
    cr = env.cr
    result = {rid: set() for rid in ids}
    if field.type == 'many2one':
        if not field.store or not field.column_type:
            return None
        records.flush_recordset([field.name])
        cr.execute(f'SELECT id, "{field.name}" FROM "{records._table}" WHERE id = ANY(%s)', [ids])
    elif field.type == 'many2many':
        if not field.store:
            return None
        records.flush_recordset([field.name])
        cr.execute(f'SELECT "{field.column1}", "{field.column2}" FROM "{field.relation}" '
                   f'WHERE "{field.column1}" = ANY(%s)', [ids])
    else:  # one2many
        comodel = env[field.comodel_name]
        inverse = comodel._fields.get(field.inverse_name)
        if inverse is None or not inverse.store or not inverse.column_type:
            return None
        comodel.flush_model([inverse.name])
        query = f'SELECT "{inverse.name}", id FROM "{comodel._table}" WHERE "{inverse.name}" = ANY(%s)'
        params = [ids]
        if inverse.type == 'many2one_reference' and inverse.model_field:
            comodel.flush_model([inverse.model_field])
            query += f' AND "{inverse.model_field}" = %s'
            params.append(records._name)
        cr.execute(query, params)
    for rid, value in cr.fetchall():
        if value:
            result[rid].add(value)
    return result


def _already_linked(current, target_id):
    """target_id 是否在每一筆現有紀錄上都已經是現值（有任何一筆會因此改變，就要查）。"""
    if not current:
        return False
    return all(target_id in values for values in current.values())


# ── 收集與檢查 ───────────────────────────────────────────────────────────
def _caller_defaults(model, present):
    """呼叫端控制得到的預設值：context 的 default_<欄位>、ir.default（核心 default_get 的前兩個來源）。"""
    out = {}
    wanted = _default_fields_to_check(model)
    for key, value in model.env.context.items():
        if not key.startswith(DEFAULT_CTX_PREFIX):
            continue
        fname = key[len(DEFAULT_CTX_PREFIX):]
        if fname in wanted and fname not in present:
            out[fname] = value
    ir_defaults = model.env['ir.default']._get_model_defaults(model._name)
    for fname, value in ir_defaults.items():
        if fname in wanted and fname not in present and fname not in out:
            out[fname] = value
    return out


def _default_fields_to_check(model):
    """預設值要查哪些欄位：關聯欄位，加上守衛中的模型＋id 型欄位與它的目標模型來源（res_model、res_model_id）。"""
    names = {name for name, field in model._fields.items() if field.type in RELATIONAL_TYPES}
    for fname in guarded_fields_of(model):
        field = model._fields[fname]
        if field.type == REFERENCE_TYPE:
            names.add(fname)
            names.update(_reference_model_sources(model, field))
    return names


def _reference_model_sources(model, field):
    """模型＋id 型欄位的目標模型從哪些欄位給：model_field 本身（例 res_model），以及它若是
    related <many2one ir.model>.model，那個 many2one（例 res_model_id）。"""
    sources = []
    model_fname = field.model_field
    model_field = model._fields.get(model_fname) if model_fname else None
    if model_field is None:
        return sources
    sources.append(model_fname)
    # Odoo 18 的 Field.related 是字串（'res_model_id.model'），舊版是 tuple——兩種都接受
    related = model_field.related
    parts = related.split('.') if isinstance(related, str) else list(related or ())
    if len(parts) == 2 and parts[1] == IR_MODEL_NAME_FIELD:
        m2o = model._fields.get(parts[0])
        if m2o is not None and m2o.type == 'many2one' and m2o.comodel_name == IR_MODEL:
            sources.append(m2o.name)
    return sources


def _reference_model_from(env, model, field, source):
    """從一份 vals 讀目標模型名稱：(這份 vals 有沒有給, 模型名稱或 None)。"""
    for name in _reference_model_sources(model, field):
        if name not in source:
            continue
        value = source[name]
        if name == field.model_field:
            return True, (value if isinstance(value, str) and value else None)
        model_id, _nested = _many2one_value(value, IR_MODEL)
        found = env[IR_MODEL].sudo().browse(model_id).exists() if model_id else None
        return True, (found.model if found else None)
    return False, None


def _current_references(records, field):
    """{紀錄 id: (目標模型, 目標 id)}（SQL，不經 ORM 快取）；欄位不是資料庫欄位回 None＝每個值都當成新的。"""
    ids = _real_ids(records)
    if not ids:
        return {}
    model_field = records._fields.get(field.model_field) if field.model_field else None
    if not field.store or model_field is None or not model_field.store:
        return None
    records.flush_recordset([field.name, model_field.name])
    records.env.cr.execute(f'SELECT id, "{model_field.name}", "{field.name}" FROM "{records._table}" '
                           f'WHERE id = ANY(%s)', [ids])
    return {rid: (target_model, target_id) for rid, target_model, target_id in records.env.cr.fetchall()}


def _collect_references(model, vals, baseline, found, pair_source):
    """模型＋id 型守衛欄位：res_id 或它的目標模型來源有任一個在 vals 裡，就解出 (目標模型, 目標 id) 收進 found。

    值的來源依序：這份 vals → pair_source（另一份：查 vals 時是呼叫端的預設值，查預設值時是 vals）→ 現值。
    現有紀錄的目標沒變（同模型同 id）不查。"""
    env = model.env
    for fname in guarded_fields_of(model):
        field = model._fields[fname]
        if field.type != REFERENCE_TYPE:
            continue
        triggers = {fname, *_reference_model_sources(model, field)}
        if not triggers & set(vals):
            continue
        current = _current_references(baseline, field) if baseline else {}
        rows = list(current.values()) if current else [(None, None)]
        given, given_model = _reference_model_from(env, model, field, vals)
        if not given and pair_source:
            given, given_model = _reference_model_from(env, model, field, pair_source)
        id_source = vals if fname in vals else (pair_source if pair_source and fname in pair_source else None)
        for current_model, current_id in rows:
            target_model = given_model if given else current_model
            target_id = _as_id(id_source[fname]) if id_source is not None else current_id
            if not target_model or not target_id or target_model not in env:
                continue
            if current and (target_model, target_id) == (current_model, current_id):
                continue
            found[(model._name, fname, target_model)].add(target_id)


def _collect(model, vals, baseline, found, pair_source=None):
    """把 vals 裡要檢查的 (模型, 欄位, 目標模型) → {id} 收進 found；baseline＝現有紀錄（現值不查），新紀錄為空。
    pair_source：只給最外層，模型＋id 型欄位的另一半值可能在那裡（見 _collect_references）。"""
    if not isinstance(vals, dict):
        return
    guarded = guarded_fields_of(model)
    env = model.env
    _collect_references(model, vals, baseline, found, pair_source)
    for fname, value in vals.items():
        field = model._fields.get(fname)
        if field is None or field.type not in RELATIONAL_TYPES:
            continue
        comodel = env[field.comodel_name]
        is_guarded = fname in guarded
        current = None
        if is_guarded and baseline:
            current = _current_values(baseline, field)
        if field.type == 'many2one':
            target, nested = _many2one_value(value, field.comodel_name)
            if is_guarded and target and not _already_linked(current, target):
                found[(model._name, fname, field.comodel_name)].add(target)
            if nested:
                _collect(comodel, nested, comodel.browse(target) if target else comodel.browse(), found)
            continue
        for op, arg1, arg2 in _x2many_commands(value):
            if op == Command.CREATE:
                _collect(comodel, arg2, comodel.browse(), found)
            elif op == Command.UPDATE:
                target = _as_id(arg1)
                if is_guarded and target and not _already_linked(current, target):
                    found[(model._name, fname, field.comodel_name)].add(target)
                _collect(comodel, arg2, comodel.browse(target) if target else comodel.browse(), found)
            elif op == Command.LINK:
                target = _as_id(arg1)
                if is_guarded and target and not _already_linked(current, target):
                    found[(model._name, fname, field.comodel_name)].add(target)
            elif op == Command.SET and is_guarded:
                items = arg2._ids if isinstance(arg2, models.BaseModel) else (arg2 or ())
                for item in items:
                    target = _as_id(item)
                    if target and not _already_linked(current, target):
                        found[(model._name, fname, field.comodel_name)].add(target)
            # DELETE／UNLINK／CLEAR：拿掉關聯，不會帶出新的內容


def _first_forbidden(env, found):
    """回傳第一個「本人讀不到」的 (模型, 欄位, [id…])；全部讀得到回 None。"""
    for (model_name, fname, comodel_name), ids in found.items():
        if comodel_name not in env:
            continue
        comodel = env[comodel_name].with_context(active_test=False)
        existing = comodel.browse(sorted(ids)).exists()
        if not existing:
            continue
        try:
            readable = set(comodel.search([('id', 'in', existing.ids)]).ids)
        except AccessError:
            readable = set()
        forbidden = sorted(set(existing.ids) - readable)
        if forbidden:
            return model_name, fname, comodel_name, forbidden
    return None


def _nested_in_other_model_crud(model):
    """這次 create／write 是不是在**另一個模型**的 create／write／copy 裡面被伺服器端程式呼叫的。

    例：工程 create 在 super() 之前替新工程建分析帳戶，分析方案（account.analytic.plan）一般帳號沒有讀取 ACL
    ——值是伺服器挑的，不是呼叫端給的（全模組回歸實測：TestRpcCreateProject 經 XML-RPC 建工程被擋）。
    呼叫端直接給的值一定出現在最外層那個模型的呼叫裡（RPC／網頁的 create、write、onchange、web_save），
    而 x2many 的巢狀 vals 已在外層模型的檢查裡遞迴查過，所以內層另一個模型的呼叫不再擋。
    只在已經找到「讀不到的 id」時才往上看呼叫堆疊（正常路徑不付這個成本）。
    """
    # 從本函式往上爬：守衛自己的函式（名稱不在 NESTING_METHODS）與同一個模型的 create／write／copy 都會被跳過，
    # 所以起點不必寫死層數（拆函式也不會悄悄改變判定；第三輪抗辯 simplifier）
    frame = sys._getframe()
    while frame is not None:
        if frame.f_code.co_name in NESTING_METHODS:
            outer = frame.f_locals.get('self')
            if isinstance(outer, models.BaseModel) and outer._name != model._name:
                return outer._name
        frame = frame.f_back
    return None


def _raise_forbidden(model, forbidden):
    env = model.env
    model_name, fname, comodel_name, ids = forbidden
    owner = env[model_name]
    field = owner._fields[fname]
    computed = ', '.join(guarded_fields_of(owner).get(fname, ()))
    shown = ', '.join(str(i) for i in ids[:MAX_IDS_IN_MESSAGE])
    if len(ids) > MAX_IDS_IN_MESSAGE:
        shown += ' …'
    _logger.warning('relational_input_guard: uid %s 被擋：%s.%s → %s %s（以 sudo 計算的欄位：%s）',
                    env.uid, model_name, fname, comodel_name, ids, computed)
    raise AccessError(env._(
        '不能把您沒有讀取權限的紀錄填進「%(model)s」的「%(field)s」（%(fname)s）：'
        '這個欄位會以系統權限帶出關聯紀錄的內容（%(computed)s）。'
        '沒有讀取權限的紀錄：%(comodel)s id %(ids)s。',
        model=owner._description or model_name, field=field.string, fname=fname,
        computed=computed, comodel=comodel_name, ids=shown))


def check_relational_input(model, vals, baseline=None, with_defaults=False, allow_nested=False):
    """守衛本體：model＝呼叫端身分的 recordset（只用它的 env 與模型）；baseline＝現有紀錄（只查改變了的值）；
    allow_nested＝在另一個模型的 create／write／copy 裡被呼叫時放行（見 _nested_in_other_model_crud）。"""
    if model.env.su:
        return
    if with_defaults:
        defaults = _caller_defaults(model, vals if isinstance(vals, dict) else {})
        if defaults:
            # 呼叫端控制得到的預設值（context default_*、使用者自己的 ir.default）**不給巢狀放行**：
            # x2many 新增子紀錄時呼叫端的 context 會一路帶進子模型（核心行為），外層只查得到巢狀 vals、
            # 查不到子模型的預設值——在外層眼裡沒有這個值，只有子模型這一層看得到（11-06 第二輪抗辯實測：
            # 帶 default_attachment_id 對日誌／工程寫入新照片，照片以系統權限帶出讀不到的附件全文）
            _check_collected(model, defaults, model.browse(), allow_nested=False, pair_source=vals)
    else:
        defaults = None
    _check_collected(model, vals, baseline if baseline is not None else model.browse(), allow_nested,
                     pair_source=defaults)


def _check_collected(model, vals, baseline, allow_nested, pair_source=None):
    """收集 vals 裡的關聯 id、找出讀不到的；有就擋（allow_nested 時，巢狀在另一個模型的 create／write 裡放行）。"""
    found = defaultdict(set)
    _collect(model, vals, baseline, found, pair_source if isinstance(pair_source, dict) else None)
    if not found:
        return
    forbidden = _first_forbidden(model.env, found)
    if not forbidden:
        return
    if allow_nested:
        outer = _nested_in_other_model_crud(model)
        if outer:
            _logger.info('relational_input_guard: uid %s 在 %s 的 create／write 裡建立／修改 %s，'
                         '伺服器端給的值不擋：%s.%s → %s %s', model.env.uid, outer, model._name,
                         forbidden[0], forbidden[1], forbidden[2], forbidden[3])
            return
    _raise_forbidden(model, forbidden)


def _copy_in_progress(env):
    return env.context.get(COPY_CTX) is COPY_TOKEN


class Base(models.AbstractModel):
    _inherit = 'base'

    def _register_hook(self):
        # 欄位重新設定（registry 已準備好時 setup_models 會再呼叫 _register_hook）→ 清掉本模型的快取重算
        vars(self.pool).setdefault(CACHE_ATTR, {}).pop(self._name, None)
        return super()._register_hook()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            copying = _copy_in_progress(self.env)
            for vals in vals_list:
                if copying:
                    # 複製：值來自原紀錄，只查呼叫端控制得到的預設值（default 參數已在 copy() 查過）；
                    # 預設值不給巢狀放行（見 check_relational_input）
                    defaults = _caller_defaults(self, vals)
                    if defaults:
                        check_relational_input(self, defaults, allow_nested=False)
                else:
                    check_relational_input(self, vals, with_defaults=True, allow_nested=True)
        return super().create(vals_list)

    def write(self, vals):
        if self and not self.env.su:
            check_relational_input(self, vals, baseline=self, allow_nested=True)
        return super().write(vals)

    def copy(self, default=None):
        if self.env.su:
            return super().copy(default)
        if default:
            check_relational_input(self, default, allow_nested=True)
        records = super(Base, self.with_context(**{COPY_CTX: COPY_TOKEN})).copy(default)
        # 回傳的紀錄不可帶著憑證（呼叫端之後用它 write 時守衛要照常）
        return records.with_env(self.env)

    def onchange(self, values, field_names, fields_spec):
        if not self.env.su:
            form_values = {k: v for k, v in (values or {}).items() if k != 'id'}
            # 既有紀錄：與資料庫現值比，只查改變了的；新紀錄：全部是新的
            check_relational_input(self, form_values, baseline=self, with_defaults=True)
        return super().onchange(values, field_names, fields_spec)
