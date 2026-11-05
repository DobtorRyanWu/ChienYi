# -*- coding: utf-8 -*-
"""自主檢查表（單張）「檢查時機」：複製出來的檢查類型也要打勾（2026-11-05）。

套印原本只認時機的 legacy_code，但 construction_quality 的設計是 legacy_code「只給資料
遷移用、匯入與日常操作一律以名稱為準」（self_inspection_type.py DEFAULT_TIMINGS 的說明），
而且它 copy=False——「複製到工程」走 copy()，複製出來的時機代碼全空 → 四格都印空白
（簡報示範庫 95 筆）。odoo18_dev 現在剛好 0 筆空代碼，所以真實資料看不出來。
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import self_inspection_form


@tagged('post_install', '-at_install', 'construction_template')
class TestSelfInspectionTiming(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '檢查時機測試', 'code': 'TPL-SITIME',
            'project_type': 'general', 'company_id': cls.env.company.id,
        })
        original = cls.env['self.inspection.type'].create({
            'name': '鋼筋組立檢查', 'project_id': cls.project.id})
        cls.itype = original.copy()

    def _timing(self, name):
        timing = self.itype.timing_ids.filtered(lambda t: t.name == name)
        self.assertEqual(len(timing), 1, '測資前提：複製的類型有「%s」' % name)
        return timing

    def test_copied_type_loses_legacy_code(self):
        """根因的前提：複製出來的時機沒有舊代碼（若哪天 copy 改了，這支要跟著重想）"""
        self.assertTrue(self.itype.timing_ids)
        self.assertFalse(any(self.itype.timing_ids.mapped('legacy_code')))

    def test_timing_marked_on_copied_type(self):
        before = self._timing('施工前檢查')
        insp = self.env['general.self.inspection'].create({
            'name': 'SI-TIME-1', 'sub_project_name': '北段鋼筋',
            'project_id': self.project.id, 'inspection_type_id': self.itype.id,
            'inspection_date': fields.Date.today(),
            'inspection_timing_ids': [(6, 0, before.ids)],
        })
        timing = self_inspection_form.build_context(insp)['inspection']
        self.assertEqual(vars(timing.inspectionTiming), {
            'arbitrary': '', 'beforeConstruction': 'V',
            'constructing': '', 'afterConstruction': ''})
        self.assertEqual(vars(timing.timingBox)['beforeConstruction'], '■')
        self.assertEqual(vars(timing.timingBox)['constructing'], '□')

    def test_paper_variant_name(self):
        """紙本寫「施工後檢查」（川易）也對到「施工完成檢查」那一格"""
        self.assertEqual(self_inspection_form.timing_code(
            self.env['self.inspection.type.timing'].new({'name': '施工後檢查'})), 'after')

    def test_preview_uses_same_rule(self):
        """「測試樣板」預覽與實際套印共用同一套判斷"""
        ctx = self.itype._test_context()
        marks = vars(ctx['inspection'].inspectionTiming)
        self.assertEqual(marks, {'arbitrary': 'V', 'beforeConstruction': 'V',
                                 'constructing': 'V', 'afterConstruction': 'V'},
                         '預覽應把類型上每個時機都勾起來（複製的類型也一樣）')
