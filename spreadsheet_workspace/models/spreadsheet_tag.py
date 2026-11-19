# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class SpreadsheetSpreadsheetTag(models.Model):
    """OCA 標籤：只改繁中標籤。"""

    _inherit = 'spreadsheet.spreadsheet.tag'
    _description = '試算表標籤'

    name = fields.Char(string='名稱')
    color = fields.Integer(string='顏色')
