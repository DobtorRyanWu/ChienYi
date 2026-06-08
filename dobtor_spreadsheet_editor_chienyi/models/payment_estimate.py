# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PaymentEstimate(models.Model):
    """估驗計價：關聯由本估驗匯入建立的試算表。"""

    _inherit = "payment.estimate"

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
            cells["%s2" % self._sse_col_letter(c)] = {"content": header, "style": 1}
        lines = self.line_ids.sorted(key=lambda r: (r.sequence or 0, r.id))
        # 金額欄改即時公式：H 本次估驗金額 = 單價(F) × 本次估驗數量(G)；J 累計估驗金額 = 單價(F) × 累計數量(I)
        formula_cols = {"estimate_amount": "=F%d*G%d", "cumulative_estimate_amount": "=F%d*I%d"}
        for r, line in enumerate(lines, start=3):
            for c, (_h, field) in enumerate(self._SSE_COLUMNS, start=1):
                col = self._sse_col_letter(c)
                if field in formula_cols:
                    cells["%s%d" % (col, r)] = {"content": formula_cols[field] % (r, r)}
                    continue
                value = line[field]
                if value in (False, None, ""):
                    continue
                content = value if isinstance(value, str) else repr(value)
                cells["%s%d" % (col, r)] = {"content": content}
        n_rows = max(len(lines) + 2, 1)
        n_cols = max(len(headers), 1)
        # 小計列（SUM 公式、粗體）
        if lines:
            last = len(lines) + 2
            sub = last + 1
            cells["B%d" % sub] = {"content": "小計", "style": 1}
            cells["H%d" % sub] = {"content": "=SUM(H3:H%d)" % last, "style": 1}
            cells["J%d" % sub] = {"content": "=SUM(J3:J%d)" % last, "style": 1}
            n_rows = sub
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
                    "cols": {},
                    "rows": {},
                    "conditionalFormats": [],
                    "figures": [],
                }
            ],
            "styles": {1: {"bold": True}},
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
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "action_spreadsheet_oca",
            "params": {"spreadsheet_id": spreadsheet.id, "model": "spreadsheet.spreadsheet"},
        }
