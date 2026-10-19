# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_round


class PaymentEstimate(models.Model):
    """估驗計價：關聯由本估驗匯入建立的試算表。

    §4.5.2：改繼承通用 xlsx.linked.mixin（res_model/res_id 通用回掛），
    保留既有 payment_estimate_id FK 與方法以維持向後相容。
    """

    _name = "payment.estimate"
    _inherit = ["payment.estimate", "xlsx.linked.mixin"]

    # ── §4.5.2 mixin hook 覆寫 ──
    def _xlsx_default_name(self):
        self.ensure_one()
        return _("%s 工項試算表") % (self.name or _("估驗計價"))

    def _xlsx_build_data(self):
        return self._build_estimate_workbook_data()

    spreadsheet_ids = fields.One2many(
        comodel_name="spreadsheet.spreadsheet",
        inverse_name="payment_estimate_id",
        string="關聯試算表",
    )
    spreadsheet_count = fields.Integer(
        string="試算表數",
        compute="_compute_spreadsheet_count",
    )

    @api.depends("spreadsheet_ids")
    def _compute_spreadsheet_count(self):
        for rec in self:
            rec.spreadsheet_count = len(rec.spreadsheet_ids)

    def action_open_spreadsheets(self):
        """開啟本估驗關聯的試算表清單。"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("關聯試算表"),
            "res_model": "spreadsheet.spreadsheet",
            "domain": [("payment_estimate_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"default_payment_estimate_id": self.id},
        }

    # 估驗工項 → 試算表欄位（表頭, 欄位名）
    _SSE_COLUMNS = [
        ("項目編號", "item_no"),
        ("項目及說明", "description"),
        ("單位", "unit"),
        ("契約數量", "contract_qty"),
        ("核定數量", "approved_qty"),
        ("單價", "unit_price"),
        ("本次估驗數量", "estimate_qty"),
        ("本次估驗金額", "estimate_amount"),
        ("累計估驗數量", "cumulative_estimate_qty"),
        ("累計估驗金額", "cumulative_estimate_amount"),
    ]

    @staticmethod
    def _sse_col_letter(idx):
        """1-based 欄索引 → 欄字母（1→A、27→AA）。"""
        s = ""
        n = idx
        while n > 0:
            n, rem = divmod(n - 1, 26)
            s = chr(65 + rem) + s
        return s

    def _build_estimate_workbook_data(self):
        """估驗工項 → o-spreadsheet WorkbookData（標題 + 粗體表頭 + 資料列）。"""
        self.ensure_one()
        headers = [h for h, _f in self._SSE_COLUMNS]
        cells = {"A1": {"content": self.name or "估驗計價", "style": 1}}
        for c, header in enumerate(headers, start=1):
            cells["%s2" % self._sse_col_letter(c)] = {"content": header, "style": 2}
        lines = self.line_ids.sorted(key=lambda r: (r.sequence or 0, r.id))
        # 金額欄改即時公式：H 本次估驗金額 = 單價(F) × 本次估驗數量(G)。
        # J 累計估驗金額（葉節點）= 前期已核定累計金額（寫成常數）+ 本次估驗金額(H)，
        # 與後台 construction_payment 18.0.1.8.1 的算法相同（見下方迴圈）。
        # 彙總列沿用 =F×I：彙總列單價是空的、算出 0，下方小計 SUM 才不會重複加總。
        formula_cols = {"estimate_amount": "=F%d*G%d", "cumulative_estimate_amount": "=F%d*I%d"}
        # D-J 數值欄套千分位格式（format id 1）
        numeric_fields = {
            "contract_qty", "approved_qty", "unit_price", "estimate_qty",
            "estimate_amount", "cumulative_estimate_qty", "cumulative_estimate_amount",
        }
        for r, line in enumerate(lines, start=3):
            for c, (_h, field) in enumerate(self._SSE_COLUMNS, start=1):
                col = self._sse_col_letter(c)
                cell = None
                if field == "cumulative_estimate_amount" and not line.is_summary_item:
                    # 🔴 不可用 =F×I（單價 × 累計數量）：前期是手動金額、單價 0 的整包項
                    #    （稅什費等）、單價中途改過時都會跟後台對不上。前期的錢只能由
                    #    後台算好（前期各期本次金額相加），試算表裡看不到前期的列，
                    #    所以寫成常數；加上 H 欄，在試算表裡改本期數量累計仍會跟著重算。
                    #    6 位小數：前期金額＝單價(2位)×數量(4位)之和，6 位是精確值，
                    #    只去掉浮點尾數（避免公式裡出現 16530.434999999998）。
                    prev = float_round(line.previous_approved_amount or 0.0, precision_digits=6)
                    cell = {"content": ("=%r+H%d" % (prev, r)) if prev else ("=H%d" % r)}
                elif field in formula_cols:
                    # 金額經人工覆寫者不可再套 單價×數量 的公式，否則試算表會顯示成
                    # 與後台不同的數字；改直接寫入模型算好的值。
                    if line.is_amount_manual:
                        cell = {"content": repr(line[field] or 0.0)}
                    else:
                        cell = {"content": formula_cols[field] % (r, r)}
                elif field == "description":
                    # 依 item_no 點數縮排（全形空白）
                    depth = (line.item_no or "").count(".")
                    text = line.description or ""
                    if text:
                        cell = {"content": ("　" * depth) + text}
                else:
                    value = line[field]
                    if value not in (False, None, ""):
                        cell = {"content": value if isinstance(value, str) else repr(value)}
                if cell is None:
                    continue
                if field in numeric_fields:
                    cell["format"] = "#,##0.00"
                    cell["style"] = 3  # 數字右對齊
                cells["%s%d" % (col, r)] = cell
        n_rows = max(len(lines) + 2, 1)
        n_cols = max(len(headers), 1)
        # 小計列（SUM 公式、粗體）
        if lines:
            last = len(lines) + 2
            sub = last + 1
            cells["B%d" % sub] = {"content": "小計", "style": 4}
            cells["H%d" % sub] = {"content": "=SUM(H3:H%d)" % last, "style": 5, "format": "#,##0.00"}
            cells["J%d" % sub] = {"content": "=SUM(J3:J%d)" % last, "style": 5, "format": "#,##0.00"}
            n_rows = sub
        # 欄寬（px，0-based 欄索引）：項目編號/說明/單位/數值欄
        col_px = [72, 300, 48, 84, 84, 84, 96, 110, 96, 110]
        cols = {i: {"size": col_px[i]} for i in range(min(n_cols, len(col_px)))}
        return {
            "version": 1,
            "sheets": [
                {
                    "id": "sheet1",
                    "name": (self.name or "估驗計價")[:31],
                    "colNumber": n_cols,
                    "rowNumber": n_rows,
                    "cells": cells,
                    "merges": [],
                    "cols": cols,
                    "rows": {},
                    "conditionalFormats": [],
                    "figures": [],
                    # 凍結標題 + 表頭兩列（卷動時固定）
                    "panes": {"xSplit": 0, "ySplit": 2},
                }
            ],
            "styles": {
                1: {"bold": True},
                2: {"bold": True, "align": "center", "fillColor": "#D9E1F2"},  # 表頭
                3: {"align": "right"},  # 數字右對齊
                4: {"bold": True, "fillColor": "#FCE4D6"},  # 小計標籤
                5: {"bold": True, "align": "right", "fillColor": "#FCE4D6"},  # 小計數字
            },
            "formats": {},
            "borders": {},
        }

    def action_generate_spreadsheet(self):
        """從估驗工項產生可編輯試算表（回掛本估驗）並開啟。"""
        self.ensure_one()
        spreadsheet = self.env["spreadsheet.spreadsheet"].create(
            {
                "name": _("%s 工項試算表") % (self.name or _("估驗計價")),
                "spreadsheet_raw": self._build_estimate_workbook_data(),
                "payment_estimate_id": self.id,
                # §4.5.2 通用回掛（與 mixin 一致）
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "action_spreadsheet_oca",
            "params": {"spreadsheet_id": spreadsheet.id, "model": "spreadsheet.spreadsheet"},
        }
