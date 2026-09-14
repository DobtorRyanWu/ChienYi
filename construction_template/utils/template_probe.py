# -*- coding: utf-8 -*-
"""自主檢查表 Word 樣板的結構偵測。

一支模組兩個用途：

  1. **守門**——套印前確認「這份樣板裝不裝得下這張檢查紀錄」。
  2. **反推**——從使用者上傳的樣板，反推出檢查類型的查驗段落、預設檢查項目、
     量測區塊，省掉逐項手打。

## 為什麼要偵測樣板是哪一種

使用者上傳的樣板有兩種寫法：

    硬編索引  +++INS inspection.stages[0].items[1].standard+++
    動態表格  {%tr for stage in inspection.stages %}…{{ item.standard }}

硬編樣板的表格**列數是固定的**，每一格寫死「第幾段第幾項」。後果實測
（2026-09-11，鋼筋樣板 2/9/8）：

    資料剛好  → 正確
    資料比樣板少 → UndefinedError: list object has no element 3（當場崩潰）
    資料比樣板多 → 成功產出，但多的項目**完全消失且不報錯**

第三種最危險——檔案看起來完全正常。所以硬編樣板一定要守門，而動態樣板
不限項目數、不需要守門。這個判斷必須自動做，不能問使用者。

## 🔴 守門不能只比數量

12 項對 12 列、順序錯了照樣通過，而產出的檔案每一格都有字、只是全部錯位，
沒有人看得出來。硬編樣板的**項目名稱是印刷在樣板裡的**（實測 79 份共 763 格，
抽得到 758 格 ＝ 99.3%），所以要逐列比對名稱。
"""

import collections
import io
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

# +++INS inspection.stages[0].items[1].standard+++ 以及轉成 Jinja 之後的形式
INDEX_RE = re.compile(r'stages\s*\[\s*(\d+)\s*\]\s*\.\s*items\s*\[\s*(\d+)\s*\]\s*\.\s*(\w+)')
# 動態樣板的迴圈（{%tr for ... %} 與 {% for ... %} 都算）
DYNAMIC_RE = re.compile(r'\{%\s*(?:tr\s+)?for\s+\w+\s+in\s+', re.S)
# 任何一種佔位符：用來判斷「這一格是不是純佔位符」
TOKEN_RE = re.compile(r'\+{3}[^+]{0,160}\+{3,4}|\{\{.*?\}\}|\{%.*?%\}', re.S)

KIND_INDEXED = 'indexed'
KIND_DYNAMIC = 'dynamic'
KIND_UNKNOWN = 'unknown'

# 正常的一列有這四個欄位；只有 standard 的是量測型（紙本「鋼筋組立抽查情形」
# 那種：一個標題底下若干行單行文字，沒有標準/情形/結果/備註四欄之分）
FULL_FIELDS = frozenset(('standard', 'situation', 'result', 'remark'))


def _cell_text(tc):
    parts = []
    for p in tc.iter(W + 'p'):
        parts.append(''.join(t.text or '' for t in p.iter(W + 't')))
    return '\n'.join(x for x in parts if x).strip()


def _vmerge(tc):
    pr = tc.find(W + 'tcPr')
    if pr is None:
        return None
    vm = pr.find(W + 'vMerge')
    return None if vm is None else (vm.get(W + 'val') or 'continue')


def _is_token_only(text):
    """整格只有佔位符 → 不是印刷文字，抽不到人看的內容"""
    return not TOKEN_RE.sub('', text or '').strip()


class Row(object):
    """樣板表格裡的一列（只收有佔位符的那些）"""

    __slots__ = ('stage_index', 'item_index', 'fields', 'stage_name', 'item_name')

    def __init__(self, stage_index, item_index, fields, stage_name, item_name):
        self.stage_index = stage_index
        self.item_index = item_index
        self.fields = fields
        self.stage_name = stage_name
        self.item_name = item_name

    @property
    def is_measure_like(self):
        """只有 standard 一欄 —— 量測型（見模組說明）"""
        return self.fields == frozenset(('standard',))


class Probe(object):
    """偵測結果"""

    def __init__(self, kind, rows=None, timings=None, error=None, xml=''):
        self.kind = kind
        self.rows = rows or []
        self.timings = timings or []
        self.error = error
        # 原始 document.xml——欄位名稱的檢查（utils/template_tokens）要用，
        # 存在這裡才不必為了那一關再解一次 zip。
        self.xml = xml

    @property
    def is_indexed(self):
        return self.kind == KIND_INDEXED

    def capacity(self):
        """硬編樣板每一段能放幾項：{段索引: 列數}"""
        counter = collections.Counter()
        for row in self.rows:
            counter[row.stage_index] = max(counter[row.stage_index],
                                           row.item_index + 1)
        return dict(counter)

    def stage_names(self):
        """{段索引: 段落名稱}（取該段第一個抽得到的）"""
        names = {}
        for row in self.rows:
            if row.stage_name and row.stage_index not in names:
                names[row.stage_index] = row.stage_name
        return names

    def checklist_rows(self):
        return [r for r in self.rows if not r.is_measure_like]

    def measure_blocks(self):
        """連續、單一欄位、共用同一個標題的列 → 一個量測區塊。

        回傳 [(標題, 列數, 段索引)]。實測 79 份樣板只有「鋼筋組立」一處
        （8 列），規則刻意寫窄：形狀不符的一律留在檢查項目裡，不要猜。
        """
        blocks = []
        current = None
        for row in self.rows:
            if not row.is_measure_like:
                current = None
                continue
            title = row.item_name or ''
            # 🔴 延續列的標題「空白」與「垂直合併」要等價。
            # 那 79 份樣板的量測區塊是用 vMerge 做的（第 2 列起沒有自己的格子），
            # 但使用者自己用 Word 做樣板時，常常是把第 2 列起的標題格**留白**——
            # 兩者在紙上長得一模一樣。原本只認 vMerge，留白會被判成「另一個
            # 沒有標題的區塊」，於是一個 8 列的區塊裂成 1 列 + 7 列，
            # 套印時後半段還會把前半段已經填好的量測資料整個蓋成空白
            # （2026-09-13 實測：完全吻合的樣板反而被擋下，說「只有 7 項」）。
            same_block = (current is not None
                          and current[2] == row.stage_index
                          and (title == current[0] or not title))
            if same_block:
                blocks[-1] = (current[0], blocks[-1][1] + 1, row.stage_index)
                current = (current[0], blocks[-1][1], row.stage_index)
            else:
                blocks.append((title, 1, row.stage_index))
                current = (title, 1, row.stage_index)
        return blocks

    def has_measure_slot(self):
        """這份樣板有沒有「印得出量測列」的地方。

        硬編樣板看有沒有單欄位的連續列；動態樣板看有沒有跑 inspection.measures
        的迴圈。兩者都沒有的話，已經填好的量測記錄會**靜靜消失**。
        """
        if self.is_indexed:
            return bool(self.measure_blocks())
        return 'inspection.measures' in re.sub(r'<[^>]+>', '', self.xml)


def probe(raw_bytes):
    """讀一份 docx，回傳 Probe。不是合法 docx 時回 KIND_UNKNOWN 並帶 error。"""
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            xml = zf.read('word/document.xml').decode('utf-8')
    except Exception as exc:                       # noqa: BLE001 —— 什麼壞法都要接住
        return Probe(KIND_UNKNOWN, error='讀不到 Word 檔的內容（%s）' % exc)

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return Probe(KIND_UNKNOWN, error='Word 檔的內容無法解析（%s）' % exc)

    body = root.find(W + 'body')
    if body is None:
        return Probe(KIND_UNKNOWN, error='Word 檔沒有內容')

    # 🔴 不能拿原始 XML 判斷有沒有佔位符：Word 會把 +++INS …+++ 這種標記切碎成
    # 好幾個 <w:t>（每次編輯都可能重切），所以 `stages[0].items[1]` 在原始 XML 裡
    # 往往被標籤攔腰切斷，INDEX_RE 直接找不到。2026-09-11 實測就是這樣失敗的：
    # rows 抓得到（那是拼接過段落文字才比對的），kind 卻判成 unknown ——
    # 於是 is_indexed 為 False、check_fit() 直接回空清單，**守門形同不存在**，
    # 一路走到套印才爆 docxtpl 的原始錯誤（list object has no element 1）。
    # 所以：indexed 以 rows 為準（它本來就是逐格拼接後比對出來的），
    # dynamic 才用去標籤後的全文判斷。
    flat = re.sub(r'<[^>]+>', '', xml)
    has_dynamic = bool(DYNAMIC_RE.search(flat))

    rows = []
    timings = []
    for tbl in body.iter(W + 'tbl'):
        cur_stage = cur_item = None
        for tr in tbl.findall(W + 'tr'):
            cells = tr.findall(W + 'tc')
            texts = [_cell_text(c) for c in cells]
            joined = '\n'.join(texts)

            if not timings and texts and texts[0] == '檢查時機' and len(texts) > 1:
                timings = [p.strip() for p in TOKEN_RE.split(texts[1]) if p.strip()]

            found = INDEX_RE.findall(joined)
            if not found:
                continue
            stage_index = int(found[0][0])
            item_index = int(found[0][1])
            fields = frozenset(f for _s, _i, f in found)

            # 第一欄＝段落名，第二欄＝項目名；垂直合併的延續列沿用上一個
            stage_name = None
            if cells:
                text0 = texts[0]
                if text0 and not _is_token_only(text0):
                    cur_stage = text0
                elif _vmerge(cells[0]) != 'continue':
                    cur_stage = None
                stage_name = cur_stage

            item_name = None
            if len(cells) > 1:
                text1 = texts[1]
                if text1 and not _is_token_only(text1):
                    cur_item = text1
                    item_name = text1
                elif _vmerge(cells[1]) == 'continue':
                    item_name = cur_item
                else:
                    cur_item = None
            rows.append(Row(stage_index, item_index, fields, stage_name, item_name))

    if rows:
        kind = KIND_INDEXED
    elif has_dynamic:
        kind = KIND_DYNAMIC
    else:
        kind = KIND_UNKNOWN
    return Probe(kind, rows=rows, timings=timings, xml=xml)


# --------------------------------------------------------------------- 守門
def _norm(text):
    """比對名稱前的正規化：全形空白、換行、前後空白都不算差異。

    樣板是人在 Word 裡排版出來的，同一個項目名稱常常夾雜換行與全形空白，
    拿原字串硬比會整批誤報。
    """
    return re.sub(r'\s+', '', (text or '').replace('　', ''))


def check_fit(probe_result, groups, strict_names=True):
    """樣板裝不裝得下這些資料。回傳人看得懂的問題清單（空 list ＝ 沒問題）。

    :param groups: [(段落名稱, [項目名稱, ...]), ...] —— 依畫面順序
    :param strict_names: 是否逐列比對名稱（只對硬編樣板有意義）
    """
    if not probe_result.is_indexed:
        return []                      # 動態樣板不限項目數

    problems = []
    capacity = probe_result.capacity()
    rows = probe_result.checklist_rows()
    by_stage = collections.defaultdict(dict)
    for row in rows:
        by_stage[row.stage_index][row.item_index] = row

    if len(groups) > len(capacity):
        problems.append(
            '這份樣板只有 %d 個查驗段落，目前的資料有 %d 個段落，'
            '第 %d 段之後的項目不會印出來。'
            % (len(capacity), len(groups), len(groups)))
    # 反過來也要擋：樣板要第 3 段而資料只有 2 段，套印會直接崩潰
    # （UndefinedError: list object has no element 2）。2026-09-11 實測——
    # 反推出來的檢查類型第 3 段只有量測區塊、沒有檢查項目時就會撞上。
    for missing in range(len(groups), len(capacity)):
        problems.append(
            '樣板的第 %d 段有 %d 列，但目前的資料只有 %d 個查驗段落，'
            '套印會因為找不到第 %d 段而失敗。'
            % (missing + 1, capacity.get(missing, 0), len(groups), missing + 1))

    for index, (stage_name, item_names) in enumerate(groups):
        room = capacity.get(index)
        if room is None:
            continue               # 上面那條已經整段報過了
        label = stage_name or '第 %d 段' % (index + 1)
        if len(item_names) > room:
            problems.append(
                '「%s」在樣板上只有 %d 列，目前有 %d 項，'
                '多出來的 %d 項不會印出來。'
                % (label, room, len(item_names), len(item_names) - room))
        elif len(item_names) < room:
            problems.append(
                '「%s」在樣板上有 %d 列，目前只有 %d 項，'
                '套印會因為找不到第 %d 項而失敗。'
                % (label, room, len(item_names), len(item_names) + 1))

        if not strict_names:
            continue
        for position, name in enumerate(item_names[:room]):
            row = by_stage.get(index, {}).get(position)
            if row is None or not row.item_name:
                continue           # 樣板那一格沒有印刷文字，無從比對
            if _norm(row.item_name) != _norm(name):
                problems.append(
                    '「%s」第 %d 項對不上：樣板上印的是「%s」，'
                    '目前的資料是「%s」。順序不同會讓整欄資料錯位。'
                    % (label, position + 1, row.item_name, name))
    return problems


def groups_from_record(record):
    """把一張檢查紀錄整理成 check_fit() 要的 [(段落名, [項目名])]。

    分群基準與 mappings/self_inspection_form._stages() 必須一致，
    否則守門過了、套印仍然錯位。
    """
    groups = []
    index = {}
    for line in record.checklist_ids:
        key = line.stage_id.id or 0
        if key not in index:
            index[key] = (line.stage_id.name or '', [])
            groups.append(index[key])
        index[key][1].append(line.check_item or '')
    return groups


def groups_from_type(inspection_type, probe_result=None):
    """檢查類型的「預設檢查項目」→ 同上格式（測試樣板用）。

    排序必須與 default_item_ids 的 _order 一致——那就是使用者在畫面上看到的
    順序，也是套印時逐列對應的順序。

    硬編樣板還要把量測區塊併進來：它在紙本上就印在檢查項目表格裡，佔掉某一
    段的位置（見 mappings/self_inspection_form._merge_measures_into_stages）。
    這裡用區塊的「預印列數」當長度——測試樣板本來就是在測版面容量。
    """
    groups = []
    index = {}
    for item in inspection_type.default_item_ids:
        key = item.stage_id.id or 0
        if key not in index:
            index[key] = (item.stage_id.name or '', [])
            groups.append(index[key])
        index[key][1].append(item.name or '')

    if probe_result is not None and probe_result.is_indexed:
        blocks = probe_result.measure_blocks()
        names = probe_result.stage_names()
        measures = list(inspection_type.measure_ids)
        for offset, (title, row_count, stage_index) in enumerate(blocks):
            block = measures[offset] if offset < len(measures) else None
            # 長度一律用**樣板的**列數，不是區塊定義的「預印列數」——套印時
            # 不足的量測列會補空白補到樣板列數（見 mappings 的
            # _merge_measures_into_stages），兩邊的判斷基準必須一致，否則
            # 使用者把預印列數設成 4、樣板有 8 列時會誤報「資料比樣板少」。
            count = row_count
            label = names.get(stage_index) or (block.name if block else title)
            while len(groups) <= stage_index:
                groups.append(('', []))
            groups[stage_index] = (label, [(block.name if block else title)] * count)
    return groups
