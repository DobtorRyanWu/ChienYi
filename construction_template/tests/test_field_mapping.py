# -*- coding: utf-8 -*-
"""樣板的「欄位對照」真的生效（utils/field_mapping.py、utils/template_render.py；淞源 2026-11-10 會議 C3）。

老闆說可以依機關微調欄位對應。樣板表單上的「欄位對照」JSON 以前只存不讀——套印完全不看它。
這裡用模組裡真正的空白樣板套印、斷言產出檔：
① 設了的位置改帶指定的欄位（座標式、佔位符 xlsx、docx 三種樣板都驗）；
② 沒設時產出檔與「不經過欄位對照」的路徑逐位元組相同；
③ 寫錯的（位置、欄位、格式器）存檔就擋下來並指出是哪一個位置；
④ __class__、底線開頭、限群組的欄位、一對多這類路徑一律不收；
⑤ 以前存進資料庫、現在不合格的對照（繞過存檔檢查）匯出時會停下來說明，不會默默照舊或少資料。
"""
import base64
import json
import os
import tempfile

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from ..mappings import daily_log_c1
from ..utils import field_mapping, template_render
from .common import blank_template, docx_texts, xlsx_cells

SHEET1 = 'xl/worksheets/sheet1.xml'
PROJECT_NAME = 'C3 欄位對照測試工程'
PROJECT_CODE = 'C3-FM-001'
CONTRACT_NO = 'C3 契約第 88 號'


@tagged('post_install', '-at_install', 'construction_template')
class TestFieldMapping(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': PROJECT_NAME, 'code': PROJECT_CODE, 'contract_no': CONTRACT_NO,
            'project_type': 'general', 'state': 'construction', 'company_id': company.id})
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': fields.Date.today()}).write({'state': 'active'})
        employee = cls.env['hr.employee'].create({'name': 'C3 測試員工', 'company_id': company.id})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id, 'company_id': company.id, 'employee_id': employee.id,
            'log_date': fields.Date.to_date('2026-11-12'), 'weather_am': 'sunny'})

    def _template(self, ttype, blank, mapping=None):
        """這個工程專屬的樣板（同一類型同一家公司只能有一份非預設樣板，所以每種類型只建一次，之後改它的欄位對照）。
        mapping=None＝欄位對照留空。"""
        template = self.env['document.template'].search([
            ('template_type', '=', ttype), ('project_id', '=', self.project.id)], limit=1)
        if not template:
            with open(blank_template(blank), 'rb') as handle:
                data = handle.read()
            attachment = self.env['ir.attachment'].create({
                'name': blank, 'datas': base64.b64encode(data), 'res_model': 'document.template'})
            template = self.env['document.template'].create({
                'name': 'C3 %s' % ttype, 'template_type': ttype, 'project_id': self.project.id,
                'attachment_id': attachment.id})
        template.write({'field_mapping': False if mapping is None else json.dumps(mapping, ensure_ascii=False)})
        return template

    def _cells(self, template, record=None):
        content, _name = template_render.render(template, record or self.sheet)
        return xlsx_cells(content)[SHEET1]

    # ── ① 座標式樣板（監造日報表第一聯） ────────────────────────────────
    def test_cells_override_changes_only_that_cell(self):
        plain = self._cells(self._template('daily_log_1', 'daily_log_1.xlsx'))
        self.assertEqual((plain['B6'], plain['K6']), (PROJECT_NAME, CONTRACT_NO), '前提：內建對照 B6＝工程名稱')
        mapped = self._cells(self._template('daily_log_1', 'daily_log_1.xlsx', {'B6': 'project_id.code'}))
        self.assertEqual(mapped['B6'], PROJECT_CODE)
        changed = {ref for ref in set(plain) | set(mapped) if plain.get(ref) != mapped.get(ref)}
        self.assertEqual(changed, {'B6'}, '其他儲存格一格都不能變')

    def test_formatter_date_and_selection(self):
        cells = self._cells(self._template('daily_log_1', 'daily_log_1.xlsx', {
            'I5': 'log_date|ad_date',           # 內建是民國 115.11.12
            'K6': 'log_date',                   # 沒指定格式器的日期印成西元
            'B5': 'weather_am',                 # 沒指定格式器的選項是代碼
            'D5': ' weather_am | selection_label ',     # 前後空白不影響
            'B6': 'project_id',                 # 多對一印名稱
        }))
        label = dict(self.sheet._fields['weather_am'].selection)['sunny']
        self.assertEqual((cells['I5'], cells['K6'], cells['B5'], cells['D5'], cells['B6']),
                         ('2026-11-12', '2026-11-12', 'sunny', label, self.project.display_name))

    # ── ① 佔位符樣板（營造版施工日誌第一聯）、docx（契約附表） ────────────
    def test_placeholder_override(self):
        plain = self._cells(self._template('daily_log_c1', 'daily_log_c1.xlsx'))
        name_cells = {ref for ref, text in plain.items() if text == PROJECT_NAME}
        self.assertTrue(name_cells, '前提：樣板上有印工程名稱的格子')
        mapped = self._cells(self._template('daily_log_c1', 'daily_log_c1.xlsx', {
            'project.name': 'project_id.code'}))
        self.assertEqual({ref for ref, text in mapped.items() if text == PROJECT_CODE}, name_cells)
        changed = {ref for ref in set(plain) | set(mapped) if plain.get(ref) != mapped.get(ref)}
        self.assertEqual(changed, name_cells)

    def test_docx_override(self):
        plain_bytes, _name = template_render.render(
            self._template('qc_staff_register', 'qc_staff_register.docx'), self.project)
        plain = ''.join(docx_texts(plain_bytes).values())
        self.assertIn(PROJECT_NAME, plain, '前提：內建對照會印工程名稱')
        self.assertNotIn(CONTRACT_NO, plain, '前提：這張表原本不印契約編號')
        mapped_bytes, _name = template_render.render(
            self._template('qc_staff_register', 'qc_staff_register.docx', {'projectName': 'contract_no'}),
            self.project)
        mapped = ''.join(docx_texts(mapped_bytes).values())
        self.assertIn(CONTRACT_NO, mapped)
        self.assertNotIn(PROJECT_NAME, mapped)

    # ── ② 沒設＝和原本一樣 ──────────────────────────────────────────────
    def test_no_mapping_output_is_byte_identical(self):
        for ttype, blank, record in (('daily_log_1', 'daily_log_1.xlsx', self.sheet),
                                     ('daily_log_c1', 'daily_log_c1.xlsx', self.sheet)):
            unset, _n = template_render.render(self._template(ttype, blank), record)
            empty, _n = template_render.render(self._template(ttype, blank, {}), record)
            self.assertEqual(unset, empty, ttype)
        # 佔位符樣板：經過 render()（會讀欄位對照）與直接走底層（完全不知道有欄位對照）產出相同
        template = self._template('daily_log_c1', 'daily_log_c1.xlsx')
        through_render, _n = template_render.render(template, self.sheet)
        with tempfile.TemporaryDirectory() as tmpdir:
            src, dst = os.path.join(tmpdir, 'src.xlsx'), os.path.join(tmpdir, 'out.xlsx')
            with open(src, 'wb') as handle:
                handle.write(template.attachment_id.raw)
            low_level = template_render._render_placeholder(src, dst, daily_log_c1, self.sheet)
        self.assertEqual(through_render, low_level)

    # ── ③④ 存檔時擋下來 ────────────────────────────────────────────────
    def test_bad_entries_are_rejected_on_save_with_the_key(self):
        template = self._template('daily_log_1', 'daily_log_1.xlsx')
        bad = [
            ({'B6': 'project_id.no_such_field'}, 'no_such_field'),
            ({'B6': '__class__'}, '__class__'),
            ({'B6': 'project_id.__class__.__name__'}, '__class__'),
            ({'B6': 'project_id._name'}, '_name'),
            ({'B6': 'project_id.name|no_such_formatter'}, 'no_such_formatter'),
            ({'B6': 'project_id.name|roc_date|money'}, '只能寫一個'),
            ({'projectName': 'project_id.name'}, '座標'),
            ({'b6': 'project_id.name'}, '座標'),
            ({'B6': 'man_machine_detail_ids.id'}, '多對一'),
            ({'B6': 'man_machine_detail_ids'}, '不能直接印'),
            ({'B6': 5}, '要寫成文字'),
            ({'B6': ''}, '要寫成文字'),
            ({'B6': '|roc_date'}, '沒有寫欄位路徑'),
            ({'B6': 'project_id..name'}, '不是可以用的欄位名稱'),
        ]
        if 'totp_secret' in self.env['res.users']._fields:
            bad.append(({'B6': 'create_uid.totp_secret'}, '限特定群組'))
        for mapping, expected in bad:
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValidationError) as caught, self.cr.savepoint():
                    template.write({'field_mapping': json.dumps(mapping)})
                message = str(caught.exception)
                self.assertIn('「%s」' % next(iter(mapping)), message, '要指出是哪一個位置')
                self.assertIn(expected, message)
        # 一次列出全部有問題的位置，好的那個不在裡面
        with self.assertRaises(ValidationError) as caught, self.cr.savepoint():
            template.write({'field_mapping': json.dumps({
                'B6': 'project_id.code', 'K6': 'nope', 'I5': 'log_date|nope'})})
        message = str(caught.exception)
        self.assertIn('「K6」', message)
        self.assertIn('「I5」', message)
        self.assertNotIn('「B6」', message)
        for not_an_object in ('[1, 2]', '"B6"', '{bad json'):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                template.write({'field_mapping': not_an_object})
        template.write({'field_mapping': json.dumps({'B6': 'project_id.code'})})
        self.assertEqual(template.get_field_mapping_dict(), {'B6': 'project_id.code'})

    def test_placeholder_keys_and_types_without_builtin_mapping(self):
        template = self._template('daily_log_c1', 'daily_log_c1.xlsx')
        for key in ('1abc', 'a-b', '_private', 'a..b', '${name}'):
            with self.subTest(key=key):
                with self.assertRaises(ValidationError), self.cr.savepoint():
                    template.write({'field_mapping': json.dumps({key: 'project_id.name'})})
        template.write({'field_mapping': json.dumps({'project.name': 'project_id.code', 'serialNo': 'name'})})
        # 這類樣板沒有內建對照表（不能套印）→ 欄位對照不會有作用，要明講
        parsed, errors = field_mapping.parse(self.env, None, {'B6': 'project_id.name'})
        self.assertEqual(parsed, {})
        self.assertEqual(len(errors), 1)
        self.assertIn('清空', errors[0])
        self.assertEqual(field_mapping.parse(self.env, None, {}), ({}, []))
        too_many = {'A%s' % (i + 1): 'project_id.name' for i in range(field_mapping.MAX_ENTRIES + 1)}
        _parsed, errors = field_mapping.parse(self.env, template_render.get_mapping('daily_log_1'), too_many)
        self.assertIn('最多', errors[0])

    # ── ⑤ 匯出時的把關 ──────────────────────────────────────────────────
    def _force_mapping(self, template, mapping):
        """繞過存檔檢查直接寫進資料庫（模擬以前「只存不讀」時代留下來的內容、或欄位後來被改名）。"""
        self.env.cr.execute('UPDATE document_template SET field_mapping = %s WHERE id = %s',
                            (json.dumps(mapping), template.id))
        template.invalidate_recordset(['field_mapping'])

    def test_stale_bad_mapping_stops_export_and_names_the_key(self):
        template = self._template('daily_log_1', 'daily_log_1.xlsx')
        self._force_mapping(template, {'A1': 'project_id.name', 'B2': 'date'})     # 舊版畫面上的範例
        with self.assertRaises(UserError) as caught:
            template_render.render(template, self.sheet)
        message = str(caught.exception)
        self.assertIn(template.display_name, message)
        self.assertIn('「B2」', message)
        self.assertIn('date', message)
        self.assertNotIn('「A1」', message, 'A1 那條路徑是合格的')

    def test_cell_missing_from_template_is_reported_as_field_mapping(self):
        template = self._template('daily_log_1', 'daily_log_1.xlsx', {'ZZ999': 'project_id.code'})
        with self.assertRaises(UserError) as caught:
            template_render.render(template, self.sheet)
        message = str(caught.exception)
        self.assertIn('ZZ999', message)
        self.assertIn('欄位對照', message)
        self.assertNotIn('mappings/', message, '這是樣板設定的問題，不要叫人去改程式')

    def test_table_token_cannot_become_a_single_field(self):
        context = daily_log_c1.build_context(self.sheet)
        table_token = next(key for key, value in context.items() if isinstance(value, list))
        template = self._template('daily_log_c1', 'daily_log_c1.xlsx', {table_token: 'project_id.code'})
        with self.assertRaises(UserError) as caught:
            template_render.render(template, self.sheet)
        self.assertIn(table_token, str(caught.exception))
        self.assertIn('明細表', str(caught.exception))
