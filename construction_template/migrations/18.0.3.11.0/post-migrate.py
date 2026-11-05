# -*- coding: utf-8 -*-
"""3.11.0：換系統預設的「矯正與預防處理紀錄」樣板（2026-11-06）。

照片紀錄表包進 `{%p for page in record.photoPages %}` 迴圈：同一階段不只一張照片時，
第 2 張起印在續頁（原本每階段只印一張，而且是最新那張）；表頭「第 1 頁 共 1 頁」改成
page.no／page.total。舊樣板（$record.images）照舊能用，只是不會出續頁。

系統裡的檔是「以前出貨過的版本」才換；被人換過的（checksum 不在 REPLACEABLE）一律不動，
seed 會記 WARNING。checksum 取自 git 歷史裡這個檔的每一個版本。做法同 18.0.3.8.2。
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

REPLACEABLE = {
    # defect_improvement.docx：2 個出貨版本
    'defect_improvement': {
        '39f2dde10b0a28ec0f7b46ddde8bfb40c045c70a',  # 341f994
        'dca3001eefd74ab8f9cb30f8b8857c44a8a7066d',  # a7a616f
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_default_templates(env, types=tuple(REPLACEABLE), replaceable=REPLACEABLE)
