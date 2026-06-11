# -*- coding: utf-8 -*-
"""spreadsheet.spreadsheet 擴充：待注入圖片（§5.3 可編輯圖片 post-load 方案）。

xlsx 匯入的內嵌圖片不放進初始 spreadsheet_raw（避免 o-spreadsheet v1→v22 遷移
對 image figure 的 dataSets 假設崩潰），改存此欄位（JSON），由前端 renderer
載入完成後 dispatch CREATE_IMAGE 注入、再清空。
"""
from odoo import fields, models


class SpreadsheetSpreadsheet(models.Model):
    _inherit = "spreadsheet.spreadsheet"

    dobtor_pending_images = fields.Text(
        string="待注入圖片",
        help="xlsx 內嵌圖片定義（JSON list）；o-spreadsheet 載入後派發 CREATE_IMAGE 注入後清空。",
    )
