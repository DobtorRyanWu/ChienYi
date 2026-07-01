# -*- coding: utf-8 -*-
"""spreadsheet.spreadsheet 擴充。

§5.3：待注入圖片（dobtor_pending_images），post-load CREATE_IMAGE 用。
§4.5.1：通用關聯（res_model/res_id）+ 匯入來源 metadata，供 xlsx.linked.mixin
        讓任何 ChienYi 業務模型回掛試算表（取代硬編碼 FK）。
"""
from odoo import api, fields, models


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

    @api.model
    def create_from_xlsx(self, name, file_bytes, res_model=None, res_id=None,
                         source_filename=None):
        """由 xlsx 二進位建立一筆試算表（後端 openpyxl → o-spreadsheet WorkbookData）。

        回傳建立的 recordset；呼叫端可接 `.open_spreadsheet()` 開啟編輯器。
        """
        from .xlsx_to_workbook import xlsx_bytes_to_workbook_data

        base = self._empty_spreadsheet_data()  # 沿用 OCA 底稿（正確 version/locale/revisionId）
        data, log, images = xlsx_bytes_to_workbook_data(file_bytes, base)
        vals = {
            'name': name,
            'spreadsheet_raw': data,
            'fidelity_grade': 'B',
            'parse_log': log,
        }
        if res_model:
            vals['res_model'] = res_model
        if res_id:
            vals['res_id'] = res_id
        if source_filename:
            vals['source_filename'] = source_filename
        ss = self.create(vals)
        if images:
            ss._dobtor_store_pending_images(images, source_filename)
        return ss

    def _dobtor_store_pending_images(self, images, source_filename=None):
        """把匯入的內嵌圖片建成 ir.attachment，並寫入 dobtor_pending_images（供
        image_inject_patch 於編輯器載入後 dispatch CREATE_IMAGE 注入）。"""
        self.ensure_one()
        import json

        Att = self.env['ir.attachment'].sudo()
        pending = []
        for k, img in enumerate(images):
            ext = (img.get('mimetype') or 'image/png').split('/')[-1]
            att = Att.create({
                'name': '%s_img_%d.%s' % (source_filename or 'xlsx', k, ext),
                'datas': img['base64'],
                'mimetype': img.get('mimetype') or 'image/png',
                'res_model': 'spreadsheet.spreadsheet',
                'res_id': self.id,
            })
            token = att.generate_access_token()[0]
            size = {'width': img['width'], 'height': img['height']}
            pending.append({
                'sheetId': 'sheet%d' % (img['sheet_index'] + 1),
                'figureId': 'sse_img_%d_%d' % (self.id, k),
                'position': {'x': img['x'], 'y': img['y']},
                'size': size,
                'definition': {
                    'path': '/web/image/%d?access_token=%s' % (att.id, token),
                    'mimetype': img.get('mimetype') or 'image/png',
                    'size': size,
                },
            })
        if pending:
            self.dobtor_pending_images = json.dumps(pending)
