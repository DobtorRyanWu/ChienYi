# -*- coding: utf-8 -*-
"""營造版施工日誌第一聯：其他多行文字欄（二十一、其他／分包通知／八、重要事項紀錄）也要自動換行並撐高列。

這幾格和「六、施工取樣試驗紀錄」一樣是合併儲存格、樣板沒開自動換行（或列高固定），
多行字會印成一行、超出的被切掉（2026-11-16 補上，取樣試驗欄 C1 已處理）。
條件：值有換行才動；單行（或空白）時產出檔與以前相同（營造版第一聯版面照 EAGLE，不再調）；
整張縮成一頁的設定（fitToPage）要還在。
"""
import io
import os
import re
import tempfile
import zipfile

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import daily_log_c1
from odoo.addons.construction_template.utils.template_render import _render_placeholder

from .common import blank_template, xlsx_cells

SHEET = 'xl/worksheets/sheet1.xml'
STYLES = 'xl/styles.xml'
# 欄位 → (對照表 token, 本測試用的多行字標記)
MULTILINE_FIELDS = {
    'safety_other_matters': 'other',
    'subcontractor_notification': 'subConstructorHandle',
    'important_matters': 'important',
}
LINES_PER_FIELD = 4
ONE_LINE_MAX_HEIGHT = 20.0     # 樣板預設列高 16.5pt；撐高成多行後一定比這個高


@tagged('post_install', '-at_install', 'construction_template')
class TestDailyLogC1WrapText(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '日誌多行欄測試', 'code': 'TPL-DLC1WRAP', 'project_type': 'general',
            'state': 'construction', 'company_id': company.id})
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.employee = cls.env['hr.employee'].create({'name': '日誌多行欄員工', 'company_id': company.id})

    def _sheet(self, **vals):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id, 'company_id': self.env.company.id,
            'employee_id': self.employee.id, 'log_date': fields.Date.today(), **vals})

    def _render(self, sheet):
        with tempfile.TemporaryDirectory() as tmp:
            return _render_placeholder(
                blank_template('daily_log_c1.xlsx'), os.path.join(tmp, 'out.xlsx'), daily_log_c1, sheet)

    @staticmethod
    def _zip_text(data, name):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read(name).decode('utf-8')

    def _find(self, data, marker):
        found = [ref for ref, text in xlsx_cells(data)[SHEET].items() if marker in (text or '')]
        self.assertEqual(len(found), 1, (marker, found))
        return found[0]

    def _row_attrs(self, data, ref):
        row = re.search(r'\d+', ref).group(0)
        return re.search(r'<row r="%s"([^>]*)>' % row, self._zip_text(data, SHEET)).group(1)

    def _cell_wraps(self, data, ref):
        sheet_xml = self._zip_text(data, SHEET)
        style = int(re.search(r'<c r="%s"[^>]*?\ss="(\d+)"' % ref, sheet_xml).group(1))
        cell_xfs = re.search(r'<cellXfs\b[^>]*>(.*?)</cellXfs>', self._zip_text(data, STYLES), re.S).group(1)
        xf = re.findall(r'<xf\b[^>]*?/>|<xf\b[^>]*?>.*?</xf>', cell_xfs, re.S)[style]
        return 'wrapText="1"' in xf

    def _row_height(self, data, ref):
        match = re.search(r'\sht="([\d.]+)"', self._row_attrs(data, ref))
        return float(match.group(1)) if match else 0.0

    def test_multiline_text_fields_wrap_and_grow(self):
        """修前：只有取樣試驗欄會換行；其他三格多行字印成一行被切掉。"""
        vals = {field: '\n'.join('%s第%d行' % (field, i) for i in range(1, LINES_PER_FIELD + 1))
                for field in MULTILINE_FIELDS}
        data = self._render(self._sheet(**vals))
        for field in MULTILINE_FIELDS:
            ref = self._find(data, '%s第1行' % field)
            self.assertTrue(self._cell_wraps(data, ref), '%s 沒開自動換行' % field)
            self.assertIn('customHeight="1"', self._row_attrs(data, ref), field)
            self.assertGreater(self._row_height(data, ref), ONE_LINE_MAX_HEIGHT * 2, field)
        # 營造版第一聯維持列印一頁：整張縮成一頁的設定還在
        self.assertIn('<pageSetUpPr fitToPage="1"/>', self._zip_text(data, SHEET))

    def test_single_line_text_output_unchanged(self):
        """單行：樣式檔不動、列高不動（與沒有這個功能時相同）。"""
        vals = {field: '單行%s' % field for field in MULTILINE_FIELDS}
        data = self._render(self._sheet(**vals))
        with zipfile.ZipFile(blank_template('daily_log_c1.xlsx')) as zf:
            self.assertEqual(self._zip_text(data, STYLES), zf.read(STYLES).decode('utf-8'))
        for field in MULTILINE_FIELDS:
            ref = self._find(data, '單行%s' % field)
            self.assertNotIn('customHeight', self._row_attrs(data, ref), field)
