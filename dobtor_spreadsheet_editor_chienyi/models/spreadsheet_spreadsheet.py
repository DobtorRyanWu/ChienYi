# -*- coding: utf-8 -*-
from odoo import fields, models


class SpreadsheetSpreadsheet(models.Model):
    """擴 OCA spreadsheet.spreadsheet，加上回掛估驗計價的關聯。"""

    _inherit = "spreadsheet.spreadsheet"

    payment_estimate_id = fields.Many2one(
        comodel_name="payment.estimate",
        string="關聯估驗計價",
        ondelete="set null",
        index=True,
        help="由估驗計價「匯入估驗試算表」建立的試算表，回掛到該估驗記錄。",
    )
