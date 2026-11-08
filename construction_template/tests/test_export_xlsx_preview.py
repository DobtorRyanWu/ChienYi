# -*- coding: utf-8 -*-
"""產出的 xlsx 表單直接在瀏覽器唯讀預覽，不必每次下載（3.12.2，2026-11-08）。

使用者：「每次都還要下載，那我做樣板跟編輯器有何意義」。這裡驗：
- 真的走一次「匯出監造日報表第一聯」→ 回的是試算表預覽動作（不是下載），
  而且那個動作載得出內容、是唯讀、上方有下載原檔的網址；
- docx 照舊下載（沒有瀏覽器預覽）。
預覽本身（權限、格式、頁首圖）的測試在 dobtor_spreadsheet_editor/tests/。
"""

import unittest

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.models.template_export_mixin import (
    DOCX_MIMETYPE, XLSX_MIMETYPE,
)

PREVIEW_TAG = 'action_spreadsheet_oca'


@tagged('post_install', '-at_install', 'construction_template')
class TestExportXlsxPreview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not hasattr(cls.env['ir.attachment'], 'action_open_spreadsheet_preview'):
            # 沒裝 dobtor_spreadsheet_editor 的庫：本功能本來就不啟用（照舊下載）
            raise unittest.SkipTest('本庫沒有安裝 dobtor_spreadsheet_editor')
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '匯出預覽測試', 'code': 'TPL-XLSXPREVIEW',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        employee = cls.env['hr.employee'].create(
            {'name': '匯出預覽測試員工', 'company_id': company.id})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': company.id,
            'employee_id': employee.id,
            'log_date': fields.Date.today(),
        })

    def _unwrap(self, action):
        """資料有提醒時外層是 display_notification，真正的動作在 params.next"""
        if action.get('tag') == 'display_notification':
            return action['params']['next']
        return action

    def test_xlsx_export_opens_readonly_preview(self):
        action = self._unwrap(self.sheet.with_context(
            template_type='daily_log_1').action_export_daily_log_template())
        self.assertEqual(action['type'], 'ir.actions.client', action)
        self.assertEqual(action['tag'], PREVIEW_TAG)
        self.assertEqual(action['params']['model'], 'ir.attachment')

        att = self.env['ir.attachment'].browse(action['params']['spreadsheet_id'])
        # 預覽的就是剛產出、掛在這張日誌上的那個檔
        self.assertEqual((att.res_model, att.res_id), ('daily.log.sheet', self.sheet.id))
        self.assertEqual(att.mimetype, XLSX_MIMETYPE)

        data = att.get_spreadsheet_data()
        self.assertEqual(data['mode'], 'readonly')
        self.assertEqual(data['dobtor_preview']['download_url'],
                         '/web/content/%d?download=true' % att.id)
        # 日誌第一聯的標題真的有轉進來（不是空白試算表）
        contents = {c.get('content') for c in data['spreadsheet_raw']['sheets'][0]['cells'].values()}
        self.assertIn('公共工程監造日報表', contents)

    def test_docx_still_downloads(self):
        att = self.env['ir.attachment'].create({
            'name': 'x.docx', 'raw': b'PK', 'mimetype': DOCX_MIMETYPE,
            'res_model': 'daily.log.sheet', 'res_id': self.sheet.id,
        })
        action = self.sheet._export_result_action(att)
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('download=true', action['url'])
