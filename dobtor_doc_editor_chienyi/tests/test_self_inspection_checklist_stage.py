# -*- coding: utf-8 -*-
"""A14 — 自主檢查表的檢查項目要顯示查驗段落（檢驗停留點／施工前中後）。

代操 2026-08-06 回報：「檢查表格式有誤項目未見檢驗停留點、施工前、中、後等」。

模型端早就有資料——`self.inspection.type.item.stage_id` 指向查驗段落，
`_order = 'stage_sequence, sequence, id'` 也已讓項目依段落自然分群——
但 `inject_checklist()` 展開成 HTML 時只給了「編號／檢查項目」，段落整個掉了。
"""

from odoo.tests import TransactionCase, tagged

from ..models.self_inspection_doc_helper import inject_checklist

# 範本裡檢查清單表格的原始骨架（寫死 3 列、無查驗段落欄）
_SKELETON = (
    '<h3>檢查項目清單</h3>'
    '<table><thead><tr>'
    '<th style="border:1px solid #000;padding:6px;width:8%">編號</th>'
    '<th style="border:1px solid #000;padding:6px">檢查項目</th>'
    '<th style="border:1px solid #000;padding:6px;width:15%">合格/不合格</th>'
    '<th style="border:1px solid #000;padding:6px">備註</th>'
    '</tr></thead><tbody>'
    '<tr><td>1</td><td>　</td><td>{{ result_1 }}</td><td>　</td></tr>'
    '<tr><td>2</td><td>　</td><td>{{ result_2 }}</td><td>　</td></tr>'
    '<tr><td>3</td><td>　</td><td>{{ result_3 }}</td><td>　</td></tr>'
    '</tbody></table>'
)


@tagged('post_install', '-at_install', 'dobtor_doc_editor_chienyi')
class TestSelfInspectionChecklistStage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'A14 測試工程',
            'code': 'A14-TEST',
            'project_type': 'general',
        })
        cls.itype = cls.env['self.inspection.type'].create({
            'name': 'A14 開挖作業檢查',
            'project_id': cls.project.id,
        })
        Stage = cls.env['self.inspection.type.stage']
        # 刻意讓「施工前」的 sequence 大於「施工中」，用來驗排序是走
        # stage_sequence 而不是項目自己的 sequence
        cls.stage_during = Stage.create({
            'type_id': cls.itype.id, 'name': '施工中檢查', 'sequence': 20})
        cls.stage_before = Stage.create({
            'type_id': cls.itype.id, 'name': '施工前檢查', 'sequence': 10})
        cls.stage_hold = Stage.create({
            'type_id': cls.itype.id, 'name': '查驗停留點', 'sequence': 30})

        Item = cls.env['self.inspection.type.item']
        # sequence 故意錯開：若程式用 .sorted('sequence') 就會打散段落分群
        cls.item_during = Item.create({
            'type_id': cls.itype.id, 'stage_id': cls.stage_during.id,
            'name': '開挖支撐', 'sequence': 1})
        cls.item_before = Item.create({
            'type_id': cls.itype.id, 'stage_id': cls.stage_before.id,
            'name': '開挖高程與設計核對', 'sequence': 5})
        cls.item_hold = Item.create({
            'type_id': cls.itype.id, 'stage_id': cls.stage_hold.id,
            'name': '安全衛生查驗點', 'sequence': 9})
        cls.item_nostage = Item.create({
            'type_id': cls.itype.id, 'name': '無段落項目', 'sequence': 99})

    def _render(self):
        return inject_checklist(_SKELETON, self.itype.default_item_ids)

    def test_stage_name_appears_for_each_item(self):
        """每個項目的查驗段落名稱都要出現在展開後的 HTML。"""
        html = self._render()
        for stage in ('施工前檢查', '施工中檢查', '查驗停留點'):
            self.assertIn(stage, html, '查驗段落「%s」沒有出現在檢查項目清單' % stage)

    def test_header_has_stage_column(self):
        """表頭要有「查驗段落」欄，否則欄數與資料列對不上。"""
        html = self._render()
        self.assertIn('查驗段落', html, '表頭缺少「查驗段落」欄')

    def test_row_cell_count_matches_header(self):
        """每一資料列的 <td> 數必須等於表頭 <th> 數。"""
        import re
        thead = re.search(r'<thead>.*?</thead>', html := self._render(), re.S).group(0)
        tbody = re.search(r'<tbody>.*?</tbody>', html, re.S).group(0)
        n_th = len(re.findall(r'<th[ >]', thead))
        for row in re.findall(r'<tr>.*?</tr>', tbody, re.S):
            self.assertEqual(len(re.findall(r'<td[ >]', row)), n_th,
                             '資料列欄數與表頭不符：%s' % row)

    def test_items_grouped_by_stage_order(self):
        """項目依 stage_sequence 分群排序，不是依項目自己的 sequence。"""
        html = self._render()
        pos = [html.index(n) for n in ('開挖高程與設計核對', '開挖支撐', '安全衛生查驗點')]
        self.assertEqual(pos, sorted(pos),
                         '項目未依查驗段落順序排列（施工前→施工中→停留點）')

    def test_item_without_stage_still_rendered(self):
        """沒有段落的項目照樣要印出來，段落欄留空即可。"""
        self.assertIn('無段落項目', self._render())

    def test_no_items_returns_original(self):
        """無項目時原樣回傳，不得破壞範本（既有的安全降級行為）。"""
        empty = self.env['self.inspection.type.item'].browse()
        self.assertEqual(inject_checklist(_SKELETON, empty), _SKELETON)

    def test_real_path_through_create_linked_doc(self):
        """走真實路徑（_create_linked_doc）驗段落順序。

        單元測試直接餵 default_item_ids 會矇到——`stage_sequence` 是
        `store=True` 的 related，同一交易內尚未 flush 時 `_order` 讀到 0，
        整批退回用 `sequence` 排。2026-08-07 E2E 實測就是這樣讓
        施工中(seq20) 排到施工前(seq10) 前面，而單元測試卻是綠的。
        """
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id,
            'inspection_type_id': self.itype.id,
            'sub_project_name': 'A14 分項',
        })
        doc = insp._create_linked_doc()
        self.assertTrue(doc, '未建立 doc.document')
        html = doc.content_html or ''
        self.assertIn('查驗段落', html, '真實路徑產出的文件缺少查驗段落欄')
        for a, b in (('施工前檢查', '施工中檢查'), ('施工中檢查', '查驗停留點')):
            self.assertLess(html.index(a), html.index(b),
                            '段落順序錯誤：「%s」應排在「%s」之前' % (a, b))
