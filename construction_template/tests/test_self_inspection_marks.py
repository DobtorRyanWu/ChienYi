# -*- coding: utf-8 -*-
"""自主檢查表（單張）套印：分欄勾記與新北檢查表要的表頭欄位。

新北契約的固定清單檢查表把結果印成**分開的欄**——施工前安衛檢查「合格／不合格」、
工地環境清潔「不適用／是／否」——而系統原本只有一個 result 符號（○╳／）。
樣板裡用 `{% if item.result == '○' %}V{% endif %}` 也做得到，但 block if 完全不受
欄位守門（template_tokens）保護：拼錯 item.reslt 不會報錯、只會整欄空白。
所以把勾記放進 context，讓守門驗得到：

    item.passMark / defectMark / naMark   'V' 或空白（與量測列既有的 passMark 同義）
    inspection.timingBox.<時機>            '■' 或 '□'（生態檢核表的「□施工前 □施工中 □完工後」）
    inspection.inspector                  填表人
    inspection.defectCount                「共 項不合格」
    inspection.note                       備註說明
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import self_inspection_form
from odoo.addons.construction_template.utils import template_tokens


@tagged('post_install', '-at_install', 'construction_template')
class TestSelfInspectionMarks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '分欄勾記測試', 'code': 'TPL-SIMARK',
            'project_type': 'general', 'company_id': cls.env.company.id,
        })
        cls.itype = cls.env['self.inspection.type'].create({
            'name': '工地職業安全衛生施工前檢查紀錄表', 'project_id': cls.project.id})
        cls.stage = cls.env['self.inspection.type.stage'].create(
            {'type_id': cls.itype.id, 'name': '每日必檢項目', 'sequence': 10})
        cls.insp = cls.env['general.self.inspection'].create({
            'name': 'SI-MARK-1',
            'sub_project_name': '每日施工前檢查',
            'project_id': cls.project.id,
            'inspection_type_id': cls.itype.id,
            'inspection_date': fields.Date.today(),
            'note': '下雨暫停高處作業',
        })
        cls.insp.checklist_ids.unlink()
        Item = cls.env['general.self.inspection.item']
        for seq, (name, result) in enumerate(
                [('勤前教育', 'pass'), ('防護具', 'defect'), ('高處作業', 'na')], start=1):
            Item.create({'inspection_id': cls.insp.id, 'sequence': seq,
                         'stage_id': cls.stage.id, 'check_item': name,
                         'check_result': result})

    def _items(self, ctx):
        return [item for stage in ctx['inspection'].stages for item in stage.items]

    def test_item_marks(self):
        ctx = self_inspection_form.build_context(self.insp)
        marks = [(i.name, i.passMark, i.defectMark, i.naMark) for i in self._items(ctx)]
        self.assertEqual(marks, [
            ('勤前教育', 'V', '', ''),
            ('防護具', '', 'V', ''),
            ('高處作業', '', '', 'V'),
        ])
        # 舊的單一符號照舊
        self.assertEqual([i.result for i in self._items(ctx)], ['○', '╳', '／'])

    def test_header_fields(self):
        ctx = self_inspection_form.build_context(self.insp)
        insp = ctx['inspection']
        self.assertEqual(insp.defectCount, 1)
        self.assertEqual(insp.note, '下雨暫停高處作業')
        self.assertEqual(insp.inspector, self.insp.inspector_id.name)
        self.assertEqual(set(vars(insp.timingBox)), set(self_inspection_form.TIMING_SLOTS))
        self.assertTrue(all(v in ('■', '□') for v in vars(insp.timingBox).values()))

    def test_schema_knows_new_tokens(self):
        # 守門要認得新欄位，拼錯的仍要被抓到
        good = ('{%tr for stage in inspection.stages %}{%tr for item in stage.items %}'
                '{{ item.passMark }}{{ item.defectMark }}{{ item.naMark }}'
                '{%tr endfor %}{%tr endfor %}'
                '{{ inspection.inspector }}{{ inspection.defectCount }}{{ inspection.note }}'
                '{{ inspection.timingBox.beforeConstruction }}')
        bad = good.replace('item.naMark', 'item.naMarc')
        schema = self_inspection_form.TOKEN_SCHEMA
        self.assertFalse(template_tokens.unknown_tokens(good, schema))
        self.assertTrue(template_tokens.unknown_tokens(bad, schema))

    def test_test_context_rotates_results(self):
        # 「測試樣板」的假資料若每項都是合格，三欄勾記永遠是 V／空／空，錯位看不出來
        for name in ('甲', '乙', '丙'):
            self.env['self.inspection.type.item'].create(
                {'type_id': self.itype.id, 'stage_id': self.stage.id, 'name': name})
        ctx = self.itype._test_context()
        items = self._items(ctx)
        self.assertEqual({(i.passMark, i.defectMark, i.naMark) for i in items},
                         {('V', '', ''), ('', 'V', ''), ('', '', 'V')})

    # ---------- 結果欄位（construction_quality self_inspection_mark.py，2026-10-28）----------
    def _layout_insp(self, layout, marks):
        itype = self.env['self.inspection.type'].create({
            'name': '結果欄位 %s' % layout, 'project_id': self.project.id, 'result_layout': layout})
        insp = self.env['general.self.inspection'].create({
            'name': 'SI-LAYOUT', 'project_id': self.project.id, 'inspection_type_id': itype.id,
            'sub_project_name': itype.name, 'inspection_date': fields.Date.today()})
        insp.checklist_ids.unlink()
        for seq, mark in enumerate(marks, start=1):
            self.env['general.self.inspection.item'].create({
                'inspection_id': insp.id, 'sequence': seq, 'check_item': '第%d題' % seq, 'mark': mark})
        return itype, insp

    def _slots(self, ctx):
        return [(i.passMark, i.partialMark, i.defectMark, i.naMark) for i in self._items(ctx)]

    def test_record_layout_prints_the_actual_mark(self):
        # 環境清潔表：「否」換算成合格（不算缺失），但要印在「否」欄——反著問的題目照實勾
        _t, insp = self._layout_insp('yes_no', ['yes', 'no', 'na', False])
        ctx = self_inspection_form.build_context(insp)
        self.assertEqual(self._slots(ctx), [('V', '', '', ''), ('', '', 'V', ''), ('', '', '', 'V'), ('', '', '', '')])
        self.assertEqual(ctx['inspection'].defectCount, 0)

    def test_partial_layout_prints_partial_column(self):
        _t, insp = self._layout_insp('yes_partial_no', ['yes', 'partial', 'no'])
        ctx = self_inspection_form.build_context(insp)
        self.assertEqual(self._slots(ctx), [('V', '', '', ''), ('', 'V', '', ''), ('', '', 'V', '')])
        self.assertEqual(ctx['inspection'].defectCount, 2)

    def test_standard_layout_never_prints_partial(self):
        ctx = self_inspection_form.build_context(self.insp)
        self.assertEqual([i.partialMark for i in self._items(ctx)], ['', '', ''])
        self.assertIn('partialMark', self_inspection_form.TOKEN_SCHEMA['inspection.stages[].items[]'])

    def test_test_context_rotates_layout_marks(self):
        itype, _insp = self._layout_insp('yes_partial_no', [])
        for name in ('甲', '乙', '丙'):
            self.env['self.inspection.type.item'].create({'type_id': itype.id, 'name': name})
        slots = set(self._slots(itype._test_context()))
        self.assertEqual(slots, {('V', '', '', ''), ('', 'V', '', ''), ('', '', 'V', '')})
