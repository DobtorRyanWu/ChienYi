# -*- coding: utf-8 -*-
"""spreadsheet.spreadsheet 擴充。

§5.3：待注入圖片（dobtor_pending_images），post-load CREATE_IMAGE 用。
§4.5.1：通用關聯（res_model/res_id）+ 匯入來源 metadata，供 xlsx.linked.mixin
        讓任何 ChienYi 業務模型回掛試算表（取代硬編碼 FK）。
"""
from odoo import fields, models


class SpreadsheetSpreadsheet(models.Model):
    _inherit = "spreadsheet.spreadsheet"

    # ── §5.3 可編輯圖片 ──
    dobtor_pending_images = fields.Text(
        string="待注入圖片",
        help="xlsx 內嵌圖片定義（JSON list）；o-spreadsheet 載入後派發 CREATE_IMAGE 注入後清空。",
    )

    # ── §4.5.1 通用關聯（res_model/res_id）──
    # 通用回掛：任何業務記錄（估驗/契約變更/月報…）以 res_model+res_id 關聯，
    # 不需各自在 spreadsheet 上開 FK 欄位（取代硬編碼 payment_estimate_id 模式）。
    res_model = fields.Char(
        string="來源模型",
        index=True,
        help="關聯的業務記錄模型名（如 payment.estimate）。",
    )
    res_id = fields.Many2oneReference(
        string="來源記錄",
        model_field="res_model",
        index=True,
        help="關聯的業務記錄 id（搭配 res_model）。",
    )

    # ── §4.5.1 匯入來源 metadata ──
    source_filename = fields.Char(
        string="來源檔名",
        help="匯入的原始 xlsx/csv 檔名。",
    )
    fidelity_grade = fields.Char(
        string="保真等級",
        help="匯入保真評級（如 A-/B）；由匯入流程或人工標記。",
    )
    parse_log = fields.Text(
        string="解析記錄",
        help="匯入解析摘要/警告（工作表數、未支援項目等）。",
    )
