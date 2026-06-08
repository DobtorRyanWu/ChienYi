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
