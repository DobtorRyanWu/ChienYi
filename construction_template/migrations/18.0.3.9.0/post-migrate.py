# -*- coding: utf-8 -*-
"""3.9.0：換系統預設的估驗計價表樣板（2026-11-05）。

estimate_report（工程估驗計價單）：拿掉 xl/calcChain.xml（與 workbook.xml.rels、
[Content_Types].xml 裡指向它的兩行）。e9ae543 刪掉兩個公式時沒清 calcChain，
它還記著 E24、I23 → Excel 正常模式打不開。

系統裡的檔是「以前出貨過的版本」才換；被人換過的（checksum 不在 REPLACEABLE）一律不動，
seed 會記 WARNING。checksum 取自 git 歷史裡這個檔的每一個版本（sha1，與
ir.attachment.checksum 同一種算法）。做法同 18.0.3.8.2。

（監造日報表（一）第 13–16 列 1.5pt 原本也要在這裡換，使用者 2026-11-05 裁示維持原始版面，撤回。）
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

REPLACEABLE = {
    # estimate_report.xlsx：8 個出貨版本
    'estimate_report': {
        '2b029fd9f2d540ced7c2942c7f850e0adccf8f17',  # e9ae543
        'f60f2edc4ef64629b461718a15d49a61bd2b0c5d',  # 8ef9ab8
        'd0dd2c60a723489544eaeeb4aeb0d786aee2a726',  # c20c5aa
        '779bf6e62b013ea5072a1931cd8fe9f8ccdc0109',  # 8091622
        '29895731faf37aa1606dab6a1b9857fadfa19b78',  # 52dd7ab
        'bbfe68a66629699f81dc10e87742adb4bed785e8',  # 7c26cbf
        '2c6514a0a3c19649b573fe0544980ebaef236667',  # 17932ad
        '9a29a32fd7920aaa816be66d6cf146d0de9f7671',  # 84ab5bf
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env, types=tuple(REPLACEABLE), replaceable=REPLACEABLE)
