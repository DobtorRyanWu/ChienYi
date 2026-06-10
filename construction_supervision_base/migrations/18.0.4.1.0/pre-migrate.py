# -*- coding: utf-8 -*-
"""pre-migration:回填 project_task 三個必填欄位的既有 NULL/空值

背景:18.0.4.x 起 project_task 的 planned_qty / unit / unit_price 改為 required=True
(契約工項標準化)。既有資料庫若有 NULL/空值,Odoo 在套用 DB NOT NULL 約束時會
噴 "unable to set NOT NULL on column" 並讓欄位維持 nullable(約束未生效)。

此 pre-migrate 在模型 schema 同步「之前」先把舊資料補成預設值,讓 NOT NULL 能順利套上。
- planned_qty(契約數量, Float)→ 0
- unit_price(契約單價, Float)→ 0
- unit(計量單位, Char)→ '式'(營造常用的整批/總價單位)

全新安裝不會跑 migration(無既有資料、表建立即帶 NOT NULL),故僅影響既有 DB 升級。
"""

# 必填欄位的回填預設值(具名常數,避免魔術值)
DEFAULT_PLANNED_QTY = 0
DEFAULT_UNIT_PRICE = 0
DEFAULT_UNIT = '式'


def migrate(cr, version):
    # version 為 None 代表全新安裝,不需回填
    if not version:
        return

    cr.execute(
        "UPDATE project_task SET planned_qty = %s WHERE planned_qty IS NULL",
        (DEFAULT_PLANNED_QTY,),
    )
    cr.execute(
        "UPDATE project_task SET unit_price = %s WHERE unit_price IS NULL",
        (DEFAULT_UNIT_PRICE,),
    )
    cr.execute(
        "UPDATE project_task SET unit = %s WHERE unit IS NULL OR unit = ''",
        (DEFAULT_UNIT,),
    )
