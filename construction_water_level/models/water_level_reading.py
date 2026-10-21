# -*- coding: utf-8 -*-

from odoo import fields, models


class WaterLevelReading(models.Model):
    _inherit = 'water.level.reading'

    # 由監測站帶入。ingest 走原生 SQL，值由 water.level.device._ingest_extra_columns() 明寫；
    # reading 的 append-only trigger 只保護量測欄位，所以 related 重算的 UPDATE 放行。
    project_id = fields.Many2one(
        'project.project', string='工程案件',
        related='device_id.project_id', store=True, index=True)
