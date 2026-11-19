# -*- coding: utf-8 -*-
"""樣板庫載入（hooks.load_inspection_library）：建得出來、重跑不重複、略過同名既有類型。"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_quality.hooks import load_inspection_library, _read_library


def _fixture(name):
    return [{
        'name': name, 'sequence': 10, 'category': 'civil', 'description': None, 'result_layout': 'standard',
        'allow_close_with_defect': False, 'template_filename': None, 'docx': None,
        'stages': [{'name': '施工前', 'sequence': 10, 'legacy_code': 'stage1'},
                   {'name': '施工後', 'sequence': 30, 'legacy_code': 'stage3'}],
        'timings': [{'name': '施工後檢查', 'sequence': 10, 'legacy_code': 'after'}],
        'items': [{'name': '題一', 'sequence': 10, 'check_standard': None, 'note': None,
                   'reverse_question': False, 'stage': '施工前', 'stage_sequence': 10},
                  {'name': '題二', 'sequence': 20, 'check_standard': '規範', 'note': None,
                   'reverse_question': True, 'stage': '施工後', 'stage_sequence': 30}],
    }]


@tagged('post_install', '-at_install', 'inspection_library')
class TestInspectionLibraryHook(TransactionCase):

    def test_load_builds_stages_items_and_is_idempotent(self):
        lib = _fixture('測試樣板庫-唯一名稱-A')
        self.assertEqual(load_inspection_library(self.env, library=lib), 1)
        rec = self.env['self.inspection.type'].search([('name', '=', '測試樣板庫-唯一名稱-A'),
                                                       ('project_id', '=', False)])
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.stage_ids.mapped('name'), ['施工前', '施工後'])
        self.assertEqual(len(rec.timing_ids), 1)
        by_name = {i.name: i for i in rec.default_item_ids}
        self.assertEqual(by_name['題一'].stage_id.name, '施工前')
        self.assertEqual(by_name['題二'].stage_id.name, '施工後')
        self.assertTrue(by_name['題二'].reverse_question)
        self.assertEqual(load_inspection_library(self.env, library=lib), 0)      # 重跑不重複
        self.assertEqual(self.env['self.inspection.type'].search_count(
            [('name', '=', '測試樣板庫-唯一名稱-A'), ('project_id', '=', False)]), 1)

    def test_shipped_library_has_77_types_and_loads_nothing_on_populated_db(self):
        lib = _read_library()
        self.assertEqual(len(lib), 77)                       # 上游說 77 份，少了不可靜默
        self.assertEqual(sum(len(t['items']) for t in lib), 747)
        names = set(self.env['self.inspection.type'].with_context(active_test=False).search(
            [('project_id', '=', False)]).mapped('name'))
        if all(t['name'] in names for t in lib):             # dev 庫已有全部：一筆都不該新建
            self.assertEqual(load_inspection_library(self.env), 0)
