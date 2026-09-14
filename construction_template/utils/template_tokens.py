# -*- coding: utf-8 -*-
"""檢查使用者上傳的樣板，欄位名稱寫對了沒有。

## 為什麼需要這一關

docxtpl 對「樣板寫了系統沒有的欄位」是**完全無聲**的：Jinja2 的 Undefined
直接印成空字串。2026-09-13 用兩份刻意寫錯的樣板實測：

    完全沒有佔位符的空白紙本  → 產出一份檔案，每一格都空白，不報錯
    {{ projectTitle }}（正確是 projectName）
    {{ item.detail }}（正確是 item.situation）
                              → 產出一份檔案，每一格都空白，不報錯

使用者拿到的是一份「看起來很正常、只是全部沒填」的檢查表，只會以為是自己
忘了填資料。這與「讀不到被靜靜當成合格」是同一類問題，必須在套印前擋下來。

## 怎麼判斷

樣板裡的欄位有兩種寫法（兩種都要認，因為使用者可能拿舊樣板改）：

    {{ a.b }}                     動態表格樣板
    {% for X in a.b %}            動態表格樣板的迴圈
    +++INS a.b+++                 舊 EAGLE 樣板
    +++FOR X IN a.b+++            舊 EAGLE 樣板的迴圈
    +++INS a.stages[0].items[1].standard+++   舊樣板的硬編索引

迴圈變數名是使用者自己取的（`{% for 隨便 in inspection.stages %}`），所以
不能只比對固定名稱——要先建立「迴圈變數 → 它綁到哪個集合」的對應，再把
`隨便.name` 解析成 `inspection.stages[].name` 去查表。
"""

import re

from odoo import _
from odoo.exceptions import UserError

# {{ ... }}：內容可能含點號、索引、加號（images[evenIndex + 1]）
CURLY_RE = re.compile(r'\{\{\s*([^}]+?)\s*\}\}')
# {% for X in a.b %} / {%tr for X in a.b %}
JINJA_FOR_RE = re.compile(
    r'\{%-?\s*(?:tr\s+|p\s+)?for\s+(\w+)\s+in\s+([\w.\[\]]+)\s*-?%\}')
# +++INS a.b+++（允許點號前後空白、允許索引）
INS_RE = re.compile(r'\+{3}INS\s+\$?\s*([\w.\[\]\s$+\-]+?)\s*\+{3,4}')
# +++FOR X IN a.b+++
FOR_RE = re.compile(r'\+{3}FOR\s+(\w+)\s+IN\s+\$?([\w.]+)\s*\+{3,4}')
# +++IMAGE imageGenerator(a.images[...].src …)+++
IMAGE_RE = re.compile(r'\+{3}IMAGE\s+imageGenerator\(\s*\$?([\w.]+)\.images\[')

# 索引一律正規化成 []：stages[0] 與 stages[$evenIndex] 是同一個東西
INDEX_RE = re.compile(r'\[[^\]]*\]')

# 這些是 Jinja2 自己的東西或樣板裡的運算式片段，不是資料欄位
IGNORE_ROOTS = {'loop', 'true', 'false', 'none', 'True', 'False', 'None'}


def _normalize(path):
    """`stages[0].items[1].standard` → `stages[].items[].standard`"""
    return INDEX_RE.sub('[]', re.sub(r'\s', '', path))


def _strip_tags(xml):
    return re.sub(r'<[^>]+>', '', xml)


def collect(xml):
    """從 document.xml 收集 (欄位路徑清單, 迴圈變數→集合路徑)。"""
    flat = _strip_tags(xml)

    loops = {}
    for var, coll in JINJA_FOR_RE.findall(flat):
        loops[var] = _normalize(coll)
    for var, coll in FOR_RE.findall(flat):
        loops[var] = _normalize(coll)

    paths = []
    for raw in CURLY_RE.findall(flat):
        # `page.second.image }}…{% if` 這種殘片不會出現（CURLY_RE 已限制 }），
        # 但運算式（a if b else c）要先切掉修飾與過濾器
        expr = raw.split('|')[0].strip()
        if not expr or expr.startswith('%'):
            continue
        for token in re.findall(r'[A-Za-z_][\w.\[\]$+\- ]*', expr):
            token = token.strip()
            if token:
                paths.append(_normalize(token))
    for raw in INS_RE.findall(flat):
        paths.append(_normalize(raw))
    for root in IMAGE_RE.findall(flat):
        paths.append(_normalize('%s.images[]' % root))
    for coll in loops.values():
        paths.append(coll)
    return paths, loops


def _resolve(path, loops):
    """把迴圈變數換成它綁的集合路徑。

    `item.standard`（item ← stage.items，stage ← inspection.stages）
      → `inspection.stages[].items[].standard`
    """
    seen = 0
    while seen < 10:                       # 巢狀迴圈不會深到哪去，順便防環
        head, _dot, rest = path.partition('.')
        base = head.replace('[]', '')
        if base not in loops:
            return path
        path = '%s[]%s%s' % (loops[base], '.' if rest else '', rest)
        seen += 1
    return path


def unknown_tokens(xml, schema):
    """回傳樣板裡「系統提供不了」的欄位路徑（排序後、去重）。

    :param schema: mappings 的 TOKEN_SCHEMA
    """
    paths, loops = collect(xml)
    bad = set()
    for path in paths:
        resolved = _resolve(path, loops)
        parts = resolved.split('.')
        if parts[0].replace('[]', '') in IGNORE_ROOTS:
            continue
        prefix = ''
        for part in parts:
            name = part.replace('[]', '')
            allowed = schema.get(prefix)
            if allowed is None:
                # 這一層沒有定義（例如 item.foo.bar），前一層已經報過就別重複
                break
            if name not in allowed:
                bad.add(resolved)
                break
            prefix = ('%s.%s' % (prefix, part)) if prefix else part
    return sorted(bad)


def has_any_token(xml):
    """這份樣板到底有沒有任何可填的欄位。

    完全沒有的話，套印出來就是原封不動的空白表——使用者不會發現。
    """
    paths, _loops = collect(xml)
    return bool(paths)


def check_or_raise(xml, schema, source_label):
    """守門入口：樣板的欄位名稱有問題就擋下，訊息直接給人看。

    檢查紀錄的匯出與檢查類型的「測試樣板」共用這一支——訊息只寫一次，
    兩條路才不會漂移。
    """
    if not has_any_token(xml):
        raise UserError(_(
            '%s 裡面沒有任何可以填資料的欄位。\n\n'
            '套印出來會是一份完全空白的表——這通常是把「空白紙本」當成樣板'
            '上傳了。樣板必須在要填資料的格子裡寫上欄位標記，例如\n'
            '　　{{ projectName }}　{{ inspection.no }}\n\n'
            '可以到「系統設定 ▸ 樣板設定」下載「自主檢查表（單張）」的'
            '空白範本當作起點。'
        ) % source_label)

    unknown = unknown_tokens(xml, schema)
    if unknown:
        listed = '\n'.join('• {{ %s }}' % u for u in unknown[:12])
        if len(unknown) > 12:
            listed += '\n…等 %d 個' % len(unknown)
        raise UserError(_(
            '%s 裡有 %d 個系統填不出來的欄位，套印後那幾格會是空白：\n\n%s\n\n'
            '請檢查是不是拼錯或自己發明了欄位名稱。'
            '可用的欄位請參考「自主檢查表（單張）」的空白範本。'
        ) % (source_label, len(unknown), listed))
