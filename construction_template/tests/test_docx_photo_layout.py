# -*- coding: utf-8 -*-
"""docx 套印的照片：不能被固定行高裁掉，也不能比所在的格子寬（2026-11-05）。

① 照片段落「固定行高」：樣板的照片格段落直接設了 `w:spacing w:lineRule="exact"`
   （矯正與預防處理紀錄 16pt、使用者上傳的 117 份自主檢查樣板 25pt）。docxtpl 把
   InlineImage 放進同一段，段落仍是 16pt 高 → LibreOffice 把照片裁成一條。
② 照片比格子寬：矯正與預防處理紀錄的照片格寬 7223 dxa（12.74 cm），對照表沒照樣板
   標記 `{height:6}` 縮圖、用了 14×10 cm 上限 → 照片 13.3 cm，Word 上右邊被切掉。
"""

import base64
import io
import zipfile

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import defect_improvement
from odoo.addons.construction_template.utils import docx_render

from .common import blank_template

EMU_PER_DXA = 635             # 1 dxa（1/20 pt）＝ 635 EMU
EMU_PER_CM = 360000
DEFAULT_CELL_MARGIN_DXA = 108  # Word 表格儲存格預設左右內距（各 0.19 cm）

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'


def _png(width, height):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (width, height), (200, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


def _body(data):
    """document.xml 解析成 lxml 樹。

    不用 regex 切段落：`<w:p …/>` 這種自我結束的空段落會讓 `<w:p .*?</w:p>` 一口吞掉
    下一段，兩張照片被算成同一段（2026-11-05 實際踩到，量尺本身說謊）。
    """
    from lxml import etree
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return etree.fromstring(zf.read('word/document.xml'))


def _is_exact(para):
    spacing = para.find(W + 'pPr/' + W + 'spacing')
    return spacing is not None and spacing.get(W + 'lineRule') == 'exact'


def _image_paragraphs(root):
    return [p for p in root.iter(W + 'p') if p.find('.//' + WP + 'inline') is not None]


def _exact_spacing_template(paragraph_texts):
    """一格一段、每段都是固定行高 16pt 的樣板（照片格的真實寫法）"""
    import docx
    from docx.enum.text import WD_LINE_SPACING
    from docx.shared import Pt

    doc = docx.Document()
    table = doc.add_table(rows=len(paragraph_texts), cols=1)
    for row, text in zip(table.rows, paragraph_texts):
        para = row.cells[0].paragraphs[0]
        para.add_run(text)
        para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        para.paragraph_format.line_spacing = Pt(16)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@tagged('post_install', '-at_install', 'construction_template')
class TestDocxPhotoParagraphNotExact(TransactionCase):

    def test_image_paragraphs_lose_exact_text_keeps_it(self):
        raw = _exact_spacing_template([
            # EAGLE 舊語法（矯正與預防處理紀錄、79 份自主檢查樣板）
            '+++IMAGE imageGenerator($record.images[0].src, $record.images[0].extension,'
            ' {height:6},$record.images[0].date)+++',
            # 原生 Jinja（系統預設的自主檢查表單張）
            '{{ page.image }}',
            # 對照組：一般文字段落的固定行高是版面設計，不能被動到
            '說明文字',
        ])
        png = _png(80, 60)
        out = docx_render.render(raw, {
            'record': {'images': [{'image': {'__image__': png}}]},
            'page': {'image': {'__image__': png}},
        })
        root = _body(out)
        images = _image_paragraphs(root)
        self.assertEqual(len(images), 2, '兩種寫法的照片都要套進去')
        for para in images:
            self.assertFalse(_is_exact(para), '照片所在段落還是固定行高 → 照片會被裁成一行高')
        text = [p for p in root.iter(W + 'p')
                if '說明文字' in ''.join(t.text or '' for t in p.iter(W + 't'))]
        self.assertEqual(len(text), 1)
        self.assertTrue(_is_exact(text[0]), '一般文字段落的固定行高被動到了')


@tagged('post_install', '-at_install', 'construction_template')
class TestDefectImprovementPhotoFits(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'general.defect.improvement' not in cls.env:
            cls.skipTest(cls, 'construction_general 沒有安裝')
        cls.project = cls.env['project.project'].create({
            'name': '缺失照片版面測試', 'code': 'TPL-DIPHOTO',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id,
        })
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'TPQA', 'contractor_prefix': 'TPQR',
        })
        cls.defect = cls.env['general.defect.improvement'].create({
            'project_id': cls.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '模板縫隙過大', 'source_type': 'daily_check',
            'state': 'notified',
        })
        # 一般橫式（4:3）＋超寬全景（3:1），後者用來證明寬度也有上限
        for stage, size in (('before', (800, 600)), ('during', (1200, 400))):
            att = cls.env['ir.attachment'].create({
                'name': '%s.png' % stage, 'mimetype': 'image/png',
                'datas': base64.b64encode(_png(*size)),
            })
            cls.env['supervision.photo'].create({
                'project_id': cls.project.id, 'attachment_id': att.id,
                'general_defect_id': cls.defect.id, 'photo_stage': stage,
            })

    def test_photos_fit_cell_and_are_not_clipped(self):
        with open(blank_template('defect_improvement.docx'), 'rb') as fp:
            raw = fp.read()
        out = docx_render.render(raw, defect_improvement.build_context(self.project))
        root = _body(out)
        images = _image_paragraphs(root)
        self.assertEqual(len(images), 2, '測資前提：前、中兩張照片都有印')
        for para in images:
            self.assertFalse(_is_exact(para), '照片段落是固定行高 → 會被裁成一條')
        # 每張照片要放得進它所在的格子（扣掉預設內距與段落左右縮排），高度照樣板 {height:6}
        for para in images:
            cell = next(para.iterancestors(W + 'tc'))
            width_dxa = int(cell.find(W + 'tcPr/' + W + 'tcW').get(W + 'w'))
            ind = para.find(W + 'pPr/' + W + 'ind')
            indent = sum(int(ind.get(W + side) or 0) for side in ('left', 'right')) if ind is not None else 0
            usable = (width_dxa - 2 * DEFAULT_CELL_MARGIN_DXA - indent) * EMU_PER_DXA
            extent = para.find('.//' + WP + 'extent')
            cx, cy = int(extent.get('cx')), int(extent.get('cy'))
            self.assertLessEqual(cx, usable, '照片比格子寬 → Word 上右邊被切掉')
            self.assertLessEqual(cy, 6 * EMU_PER_CM, '照片高度沒照樣板的 {height:6}')


@tagged('post_install', '-at_install', 'construction_template')
class TestDefectImprovementPhotoContinuation(TransactionCase):
    """同一階段不只一張照片：多的接在照片紀錄表的續頁，依拍攝先後（2026-11-06 使用者裁示）。

    樣板每個階段只有一格，原本只印第一張——而且「第一張」取的是 supervision.photo 的
    _order（shot_at desc），印出來的是最新那張。499 有 14 張照片只印出 13 張。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'general.defect.improvement' not in cls.env:
            cls.skipTest(cls, 'construction_general 沒有安裝')
        cls.project = cls.env['project.project'].create({
            'name': '缺失照片續頁測試', 'code': 'TPL-DICONT',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id, 'supervision_prefix': 'TCQA', 'contractor_prefix': 'TCQR'})
        cls.defect = cls.env['general.defect.improvement'].create({
            'project_id': cls.project.id, 'record_type': 'supervision',
            'check_type': 'construction', 'defect_category': 'workmanship',
            'defect_description': '護欄鬆脫', 'source_type': 'daily_check', 'state': 'notified'})
        # 改善前兩張：先拍的是橫的、後拍的是直的（用長寬分辨印在哪一頁）
        shots = [('before', (800, 600), '2026-10-01 08:00:00'),
                 ('before', (600, 800), '2026-10-02 08:00:00'),
                 ('during', (800, 600), '2026-10-03 08:00:00')]
        for stage, size, shot_at in shots:
            att = cls.env['ir.attachment'].create({
                'name': '%s.png' % stage, 'mimetype': 'image/png',
                'datas': base64.b64encode(_png(*size))})
            cls.env['supervision.photo'].create({
                'project_id': cls.project.id, 'attachment_id': att.id, 'shot_at': shot_at,
                'general_defect_id': cls.defect.id, 'photo_stage': stage})

    def test_extra_photo_goes_to_continuation_page(self):
        with open(blank_template('defect_improvement.docx'), 'rb') as fp:
            raw = fp.read()
        out = docx_render.render(raw, defect_improvement.build_context(self.project))
        root = _body(out)
        extents = [(int(e.get('cx')), int(e.get('cy'))) for e in root.iter(WP + 'extent')
                   if next(e.iterancestors(W + 'p')).find('.//' + WP + 'inline') is not None]
        self.assertEqual(len(extents), 3, '三張照片都要印出來（原本只印每階段第一張）')
        text = ''.join(root.itertext())
        self.assertIn('第 1 頁 共 2 頁', text.replace('  ', ' '))
        self.assertIn('第 2 頁 共 2 頁', text.replace('  ', ' '))
        # 第一頁：改善前（先拍的、橫的）＋改善中；續頁：改善前第二張（後拍的、直的）
        self.assertGreater(extents[0][0], extents[0][1], '第一頁要印先拍的那張（原本印最新的）')
        self.assertLess(extents[2][0], extents[2][1], '後拍的那張應在續頁')


@tagged('post_install', '-at_install', 'construction_template')
class TestSeed3110Migration(TransactionCase):
    """3.11.0 換系統預設的矯正與預防處理紀錄（照片續頁）：只換出貨過的版本"""

    def _load(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'migrations', '18.0.3.11.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mig_3_11_0', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_shipped_version_replaced_new_not_listed(self):
        import hashlib
        mod = self._load()
        with open(blank_template('defect_improvement.docx'), 'rb') as fp:
            new_sum = hashlib.sha1(fp.read()).hexdigest()
        self.assertNotIn(new_sum, mod.REPLACEABLE['defect_improvement'])
        tmpl = self.env['document.template'].search([
            ('template_type', '=', 'defect_improvement'), ('is_default', '=', True)], limit=1)
        self.assertTrue(tmpl, '測資前提：有系統預設')
        fake = b'fake shipped defect_improvement'
        tmpl.attachment_id.write({'datas': base64.b64encode(fake)})
        mod.REPLACEABLE['defect_improvement'].add(hashlib.sha1(fake).hexdigest())
        self.env.flush_all()
        mod.migrate(self.env.cr, '18.0.3.10.0')
        self.env.invalidate_all()
        self.assertEqual(tmpl.attachment_id.checksum, new_sum)
