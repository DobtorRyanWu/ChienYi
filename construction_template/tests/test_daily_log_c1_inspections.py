# -*- coding: utf-8 -*-
"""營造版施工日誌第一聯：當天已完成的自主檢查自動帶進「六、施工取樣試驗紀錄」。

淞源 2026-11-10 會議（記錄 C1）：工地手機填完的檢查紀錄要「跑回施工日誌，寫明今天做的抽查」。
老闆當場說「基本上都 OK」，但日誌對照表從來沒有引用自主檢查——這裡第一次接上。

用模組裡真正的空白樣板套印、斷言產出檔的儲存格：
* 手填的字原樣在前，後面接「本日自主檢查：」＋每筆一行；
* 那一格是合併儲存格、樣板沒開自動換行（多行字會印成一行被切掉），所以帶入時要換成自動換行並撐高列；
* 當天沒有已完成的檢查 → 產出檔與加這個功能之前相同（樣式檔一個位元組都不動、列高不動）。
"""

import io
import os
import re
import tempfile
import zipfile
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_quality.models.self_inspection_daily_summary import BLOCK_HEADING
from odoo.addons.construction_template.mappings import daily_log_c1
from odoo.addons.construction_template.utils.template_render import _render_placeholder

from .common import blank_template, leftovers_xlsx, xlsx_cells

SHEET = 'xl/worksheets/sheet1.xml'
STYLES = 'xl/styles.xml'
MANUAL = '混凝土坍度試驗 1 組'
LOCK_TEST_DAYS_AGO = 30        # 超過日誌的 14 天鎖定
ONE_LINE_MAX_HEIGHT = 20.0     # 樣板預設列高 16.5pt；撐高後一定比這個高


@tagged('post_install', '-at_install', 'construction_template')
class TestDailyLogC1Inspections(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '日誌帶入自主檢查測試', 'code': 'TPL-DLC1INSP',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        cls.employee = cls.env['hr.employee'].create(
            {'name': '日誌帶入測試員工', 'company_id': company.id})
        cls.today = fields.Date.today()
        cls.sheet = cls._sheet(cls.today)
        cls.itype = cls.env['self.inspection.type'].create({'name': '模板組立'})

    @classmethod
    def _sheet(cls, day):
        return cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': cls.env.company.id,
            'employee_id': cls.employee.id,
            'log_date': day,
            'sampling_test_record': MANUAL,
        })

    def _insp(self, result='pass', state='inspected', day=None, location='A 區'):
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'inspection_type_id': self.itype.id,
            'inspection_date': day or self.today, 'sub_project_name': '擋土牆',
            'inspection_location': location,
        })
        insp.checklist_ids.unlink()
        self.env['general.self.inspection.item'].create(
            {'inspection_id': insp.id, 'check_item': '題目', 'check_result': result})
        if state != 'draft':
            insp.write({'state': state})
        return insp

    def _render(self, sheet=None):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, 'out.xlsx')
            return _render_placeholder(
                blank_template('daily_log_c1.xlsx'), dst, daily_log_c1, sheet or self.sheet)

    @staticmethod
    def _zip_text(data, name):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read(name).decode('utf-8')

    def _sample_cell(self, data):
        """取樣試驗欄：(儲存格座標, 文字)。用手填的字找，不寫死座標（上面的表格列會讓它往下移）。"""
        found = [(ref, text) for ref, text in xlsx_cells(data)[SHEET].items() if MANUAL in (text or '')]
        self.assertEqual(len(found), 1, found)
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

    # ── 沒有檢查：與以前相同 ────────────────────────────────────────────
    def test_no_inspection_output_unchanged(self):
        self._insp(state='draft')                                 # 草稿不算
        self._insp(day=self.today - timedelta(days=1))            # 別天不算
        data = self._render()
        ref, text = self._sample_cell(data)
        self.assertEqual(text, MANUAL)
        self.assertNotIn('customHeight', self._row_attrs(data, ref))
        with zipfile.ZipFile(blank_template('daily_log_c1.xlsx')) as zf:
            self.assertEqual(self._zip_text(data, STYLES), zf.read(STYLES).decode('utf-8'),
                             '沒有帶入時不該動樣式檔')
        self.assertFalse(self._cell_wraps(data, ref))
        self.assertEqual(leftovers_xlsx(data), [])

    # ── 有檢查：接在手填後面、換行、撐高 ───────────────────────────────
    def test_done_inspections_appended_after_manual_text(self):
        self._insp(result='pass', location='A 區')
        self._insp(result='defect', state='confirmed', location='B 區')
        self._insp(state='draft')
        data = self._render()
        ref, text = self._sample_cell(data)
        self.assertEqual(text.split('\n'), [
            MANUAL,
            BLOCK_HEADING,
            '1. 模板組立（擋土牆 A 區）：合格',
            '2. 模板組立（擋土牆 B 區）：不合格',
        ])
        self.assertTrue(self._cell_wraps(data, ref), '合併儲存格沒開自動換行，多行字會印成一行被切掉')
        attrs = self._row_attrs(data, ref)
        self.assertIn('customHeight="1"', attrs)
        height = float(re.search(r'\sht="([\d.]+)"', attrs).group(1))
        self.assertGreater(height, ONE_LINE_MAX_HEIGHT * 3, '四行字的列高不能還是一行的高度')
        # 整張縮成一頁的設定還在（營造版第一聯照 EAGLE 維持一頁）
        self.assertIn('<pageSetUpPr fitToPage="1"/>', self._zip_text(data, SHEET))
        self.assertEqual(leftovers_xlsx(data), [])

    def test_empty_manual_text_prints_block_only(self):
        self.sheet.write({'sampling_test_record': False})
        self._insp()
        context = daily_log_c1.build_context(self.sheet)
        self.assertEqual(context['constructionSample'].split('\n'),
                         [BLOCK_HEADING, '1. 模板組立（擋土牆 A 區）：合格'])

    def test_export_lists_at_most_max_lines(self):
        total = daily_log_c1.MAX_INSPECTION_LINES + 2
        for _index in range(total):
            self._insp()
        lines = daily_log_c1.build_context(self.sheet)['constructionSample'].split('\n')
        # 手填 1 行＋標題 1 行＋上限筆數＋「共 N 筆」1 行
        self.assertEqual(len(lines), daily_log_c1.MAX_INSPECTION_LINES + 3)
        self.assertIn(str(total), lines[-1])
        # 畫面上的清單不設上限
        self.assertEqual(len(self.sheet.same_day_inspection_text.split('\n')), total + 1)

    # ── 已鎖定的日誌也帶得出來（不寫進日誌欄位）──────────────────────────
    def test_locked_sheet_still_gets_block(self):
        day = self.today - timedelta(days=LOCK_TEST_DAYS_AGO)
        old_sheet = self._sheet(day)
        self._insp(day=day)
        self.assertTrue(old_sheet._is_edit_locked())
        _ref, text = self._sample_cell(self._render(old_sheet))
        self.assertIn(BLOCK_HEADING, text)
        self.assertIn(BLOCK_HEADING, old_sheet.same_day_inspection_text)
        self.assertEqual(old_sheet.sampling_test_record, MANUAL, '手填欄位不能被改寫')

    def test_backend_field_empty_without_inspection(self):
        self.assertFalse(self.sheet.same_day_inspection_text)
