# -*- coding: utf-8 -*-
"""模組版號的共用工具。

⚠️ ir.module.module 兩個版本欄位的名字與意義相反（Odoo 原始碼 ir_module.py 自己註解寫明）：
   installed_version（標籤 Latest Version）＝磁碟上 manifest 寫的版號（非 stored compute，
                      經 lru_cache：改了 manifest 不重啟會讀到舊值）
   latest_version   （標籤 Installed Version）＝資料庫實際安裝的版號（升級完成時才寫入）
"""
import os
import re

import odoo
from odoo import release
from odoo.modules.module import get_modules
from odoo.tools import config

# 18.0.X.Y.Z：X 結構、Y 功能、Z 修正
VERSION_RE = re.compile(r'^%s\.(\d+)\.(\d+)\.(\d+)$' % re.escape(release.serie))
VERSION_EXAMPLE = '%s.1.0.0' % release.serie


def parse_version(version):
    """'18.0.1.7.2' → (1, 7, 2)；格式不符回 None。"""
    m = VERSION_RE.match((version or '').strip())
    return tuple(int(x) for x in m.groups()) if m else None


def custom_addons_paths():
    """addons_path 裡「我們自己放進去的」目錄（排除 Odoo 本體內建的 addons）。"""
    odoo_dir = os.path.realpath(os.path.dirname(odoo.__file__))
    paths = []
    for p in (config['addons_path'] or '').split(','):
        p = p.strip()
        if not p or not os.path.isdir(p):
            continue
        if os.path.realpath(p).startswith(odoo_dir + os.sep):
            continue
        paths.append(os.path.realpath(p))
    return paths


def custom_module_names():
    """自有與第三方目錄底下的所有模組名稱（含未安裝）。依所在目錄判斷，不看名稱前綴。"""
    roots = custom_addons_paths()
    names = set()
    for name in get_modules():
        for root in roots:
            if os.path.isfile(os.path.join(root, name, '__manifest__.py')):
                names.add(name)
                break
    return sorted(names)
