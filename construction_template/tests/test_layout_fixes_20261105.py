# -*- coding: utf-8 -*-
"""跑版檢查（2026-11-05，.claude/scratch/20261105-template-layout/report.md）修正的測試。

① docx 套印後結尾多一頁白紙。三種樣子，Word 實印都多一頁：
   A. 每頁結尾放分頁符號的迴圈（管制表、矯正與預防處理紀錄）：最後一頁後面還有「分頁＋空段落」
   B. 照片頁迴圈的每頁結尾是「分節（下一頁）」（使用者上傳的自主檢查樣板 89 種、自主檢查表單張）：
      最後一個分節後面只剩空段落，Word 為它們開一整頁
   C. 第一頁剛好排滿，後面的空段落被推到第二頁（估驗照片沒有照片時）
   修法：docx_render.render() 存檔前拿掉文件結尾沒有內容的段落、分頁符號與空的最後一節。
"""

import io

from odoo.tests.common import TransactionCase, tagged

from ..utils import docx_render

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _q(tag):
    return '{%s}%s' % (W_NS, tag)


def _docx(build):
    """用 python-docx 造一份樣板，build(doc) 負責放內容"""
    import docx
    doc = docx.Document()
    build(doc)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _body(data):
    import docx
    return docx.Document(io.BytesIO(data)).element.body


def _blocks(body):
    """body 底下的段落與表格（不含 body 層的 sectPr、書籤）"""
    return [el for el in body if el.tag in (_q('p'), _q('tbl'))]


def _text(el):
    return ''.join(t.text or '' for t in el.iter(_q('t')))


def _has_page_break(el):
    return any(br.get(_q('type')) == 'page' for br in el.iter(_q('br')))


def _section_break(el):
    return el.tag == _q('p') and el.find('%s/%s' % (_q('pPr'), _q('sectPr'))) is not None


def _final_section_blocks(body):
    """最後一節的內容：最後一個「帶分節的段落」之後的區塊"""
    blocks = _blocks(body)
    last_break = max((i for i, el in enumerate(blocks) if _section_break(el)), default=-1)
    return blocks[last_break + 1:]


def _is_blank(el):
    return (el.tag == _q('p') and not _text(el).strip()
            and el.find('.//' + _q('drawing')) is None)


@tagged('post_install', '-at_install', 'construction_template')
class TestTrailingBlankPage(TransactionCase):

    def _render(self, build):
        return _body(docx_render.render(_docx(build), {}))

    def test_section_loop_tail_has_no_empty_last_section(self):
        """B：分節後只剩空段落 → 最後一節不能是空的（否則 Word 多一頁白紙）"""
        from docx.enum.section import WD_SECTION

        def build(doc):
            doc.add_paragraph('檢查表本體')
            doc.add_section(WD_SECTION.NEW_PAGE)
            doc.add_table(rows=1, cols=1).cell(0, 0).text = '照片頁'
            doc.add_section(WD_SECTION.NEW_PAGE)
            for _ in range(3):
                doc.add_paragraph('')
        before = _body(_docx(build))
        self.assertTrue(_final_section_blocks(before), '測試樣板本身要有「空的最後一節」')
        self.assertTrue(all(_is_blank(el) for el in _final_section_blocks(before)))

        body = self._render(build)
        tail = _final_section_blocks(body)
        self.assertTrue(tail and not all(_is_blank(el) for el in tail),
                        '最後一節只剩空段落 → Word 會多印一頁白紙')
        texts = [_text(el) for el in _blocks(body)]
        self.assertIn('檢查表本體', texts)
        self.assertTrue(any('照片頁' in t for t in texts), '照片頁的內容不能被刪掉')

    def test_page_break_loop_tail_has_no_trailing_break(self):
        """A：表格後面接「分頁＋空段落」→ 結尾不能留分頁符號"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_table(rows=1, cols=1).cell(0, 0).text = '紀錄'
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('')
        body = self._render(build)
        blocks = _blocks(body)
        last_table = max(i for i, el in enumerate(blocks) if el.tag == _q('tbl'))
        after = blocks[last_table + 1:]
        self.assertFalse(any(_has_page_break(el) for el in after), '結尾還有分頁符號')
        # Word 規定文件最後一塊要是段落：表格後面要留剛好一段（而且要小到不會被推到下一頁）
        self.assertEqual(len(after), 1)
        size = after[0].find('.//' + _q('sz'))
        self.assertIsNotNone(size, '表格後面那段要縮成極小字，避免被擠到下一頁')
        self.assertLessEqual(int(size.get(_q('val'))), 2)

    def test_trailing_empty_paragraphs_after_text_removed(self):
        """C：文字後面的空段落（會被推到第二頁）要拿掉"""
        def build(doc):
            doc.add_paragraph('1/1')
            doc.add_paragraph('')
            doc.add_paragraph('')
        blocks = _blocks(self._render(build))
        self.assertEqual([_text(el) for el in blocks], ['1/1'])

    def test_page_break_inside_last_paragraph_is_kept(self):
        """抗辯審查（skeptic F4）：最後一段「中間」的分頁（附件另起一頁）不能拿掉，只拿結尾的"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('本文')
            para = doc.add_paragraph('附件：')
            para.add_run().add_break(WD_BREAK.PAGE)
            para.add_run('照片清單')
            para.add_run().add_break(WD_BREAK.PAGE)
        last = _blocks(self._render(build))[-1]
        breaks = [br for br in last.iter(_q('br')) if br.get(_q('type')) == 'page']
        self.assertEqual(len(breaks), 1, '中間那個分頁要留、結尾那個要拿掉')

    def test_page_break_before_on_last_paragraph_is_kept(self):
        """抗辯審查（skeptic F4）：最後一段設了「段落前分頁」＝它本來就要另起一頁，不能拿掉"""
        def build(doc):
            doc.add_paragraph('本文')
            doc.add_paragraph('簽核頁').paragraph_format.page_break_before = True
        last = _blocks(self._render(build))[-1]
        self.assertIsNotNone(last.find('%s/%s' % (_q('pPr'), _q('pageBreakBefore'))))

    def test_signature_line_at_end_is_kept(self):
        """抗辯審查（red-team F5）：結尾只有「加底線的全形空白」＝簽名線，看得見，不能當空段落刪"""
        def build(doc):
            doc.add_paragraph('本文')
            doc.add_paragraph().add_run('　　　　　　').underline = True
        blocks = _blocks(self._render(build))
        self.assertEqual(len(blocks), 2, '簽名線被刪了')

    def test_blank_paragraphs_in_the_middle_are_kept(self):
        """對照組：中間的空段落（排版用的空行）不能動"""
        def build(doc):
            doc.add_paragraph('A')
            doc.add_paragraph('')
            doc.add_paragraph('B')
        blocks = _blocks(self._render(build))
        self.assertEqual([_text(el) for el in blocks], ['A', '', 'B'])

    def test_section_break_with_content_after_is_kept(self):
        """對照組：最後一節有內容時，分節符號要保留（版面方向、頁首頁尾可能不同）"""
        from docx.enum.section import WD_SECTION

        def build(doc):
            doc.add_paragraph('第一節')
            doc.add_section(WD_SECTION.NEW_PAGE)
            doc.add_paragraph('第二節')
        body = self._render(build)
        self.assertEqual(sum(1 for el in _blocks(body) if _section_break(el)), 1)
        self.assertEqual([_text(el) for el in _blocks(body) if not _section_break(el)],
                         ['第一節', '第二節'])


@tagged('post_install', '-at_install', 'construction_template')
class TestXlsxNumberCells(TransactionCase):
    """② 營造版施工日誌（二）完成百分率印成「0.20989999999999998」、累計印成「1.5262」。

    對照表照 EAGLE 給 0~1 的小數（儲存格是 0.00% 格式），但寫入引擎一律寫成文字（inlineStr），
    文字不吃數字格式 → 印出一長串小數。進度報告的百分比是同一個寫法。
    修法：整格只有一個 ${...}、值是數字時寫成數值儲存格，讓樣板自己的格式生效。
    """

    SHEET = ('<worksheet><sheetData>'
             '<row r="1"><c r="A1" s="7" t="inlineStr"><is><t>${pct}</t></is></c>'
             '<c r="B1" s="3" t="inlineStr"><is><t>${name}</t></is></c>'
             '<c r="C1" s="3" t="inlineStr"><is><t>第${page}頁</t></is></c>'
             '<c r="D1" s="3" t="inlineStr"><is><t>${flag}</t></is></c>'
             '<c r="E1" s="7" t="inlineStr"><is><t>${missing}</t></is></c></row>'
             '<row r="2"><c r="A2" s="7" t="inlineStr"><is><t>${table:rows.qty}</t></is></c></row>'
             '</sheetData></worksheet>')

    def _fill(self):
        from ..utils import xlsx_placeholder
        return xlsx_placeholder.expand_and_fill(self.SHEET, {
            'pct': 0.2099, 'name': '磺港溪', 'page': 3, 'flag': True, 'missing': None,
            'rows': [{'qty': 1.5}, {'qty': '2 M3'}]})

    def test_single_number_token_written_as_number(self):
        xml = self._fill()
        self.assertIn('<c r="A1" s="7"><v>0.2099</v></c>', xml,
                      '百分比要寫成數值，0.00% 格式才會生效')
        self.assertIn('<c r="A2" s="7"><v>1.5</v></c>', xml, '表格列裡的數字一樣寫成數值')

    def test_text_and_mixed_cells_stay_text(self):
        """對照組：文字、「第${n}頁」這種混合、布林、None 都不能變成數值"""
        xml = self._fill()
        self.assertIn('<c r="B1" s="3" t="inlineStr"><is><t>磺港溪</t></is></c>', xml)
        self.assertIn('<c r="C1" s="3" t="inlineStr"><is><t>第3頁</t></is></c>', xml)
        self.assertIn('<c r="D1" s="3" t="inlineStr"><is><t>True</t></is></c>', xml)
        self.assertIn('<c r="E1" s="7"/>', xml, 'None 要留白，不能印 0')
        self.assertIn('<c r="A3" s="7" t="inlineStr"><is><t>2 M3</t></is></c>', xml)


@tagged('post_install', '-at_install', 'construction_template')
class TestPagedSheetPrintArea(TransactionCase):
    """③ 自主檢查總表（系統預設＋新北版）每隔一頁多一張只有一條直線的紙。

    分頁時複製出來的第 2、3… 張工作表沒有帶到列印範圍（只有第 1 張有 A:N），
    Excel 就印整個使用範圍 A:O，多出來的 O 欄自己成一頁。
    """

    WORKBOOK = ('<workbook><sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>'
                '<definedNames>'
                '<definedName name="_xlnm.Print_Area" localSheetId="0">%s!$A$1:$N$17</definedName>'
                '<definedName name="_xlnm.Print_Titles" localSheetId="0">%s!$1:$5</definedName>'
                '</definedNames></workbook>')
    RELS = ('<Relationships><Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
            '</Relationships>')

    def _pages(self, sheet_name, ref_name):
        from ..utils import xlsx_sheets
        parts = {'xl/workbook.xml': self.WORKBOOK % (sheet_name, ref_name, ref_name),
                 'xl/_rels/workbook.xml.rels': self.RELS, '[Content_Types].xml': '<Types></Types>'}
        updates, _additions = xlsx_sheets.build_pages(parts, ['<a/>', '<b/>', '<c/>'])
        return updates['xl/workbook.xml'].decode('utf-8')

    def test_every_page_sheet_gets_print_area(self):
        workbook = self._pages('第1頁', '第1頁')
        for pos, name in ((1, '第2頁'), (2, '第3頁')):
            self.assertIn('<definedName name="_xlnm.Print_Area" localSheetId="%s">%s!$A$1:$N$17'
                          '</definedName>' % (pos, name), workbook)
            self.assertIn('<definedName name="_xlnm.Print_Titles" localSheetId="%s">%s!$1:$5'
                          '</definedName>' % (pos, name), workbook)
        # 原本那條不能被改掉
        self.assertIn('localSheetId="0">第1頁!$A$1:$N$17', workbook)

    def test_formula_and_ref_error_names_untouched(self):
        """抗辯審查（skeptic F9、red-team F8）：OFFSET(…) 被通吃正規式改壞 → Excel 打不開；
        #REF!、自閉合的名稱也不能被改或丟掉"""
        from ..utils import xlsx_sheets
        wb = ('<workbook><sheets><sheet name="第1頁" sheetId="1" r:id="rId1"/></sheets><definedNames>'
              '<definedName name="dyn" localSheetId="0">OFFSET(第1頁!$A$1,0,0,COUNTA(第1頁!$A:$A),14)</definedName>'
              '<definedName name="bad" localSheetId="0">#REF!</definedName>'
              '<definedName name="empty"/></definedNames></workbook>')
        out = xlsx_sheets._copy_print_names(wb, 2, 1, '第1頁')
        self.assertIn('OFFSET(第1頁!$A$1,0,0,COUNTA(第1頁!$A:$A),14)', out)
        self.assertIn('<definedName name="bad" localSheetId="0">#REF!</definedName>', out)
        self.assertIn('<definedName name="empty"/>', out)
        self.assertNotIn('localSheetId="1"', out, '不是列印範圍、也不是單純參照的名稱不能複製')

    def test_renamed_first_sheet_reference_follows(self):
        """第一張改名成「第1頁」時，指到舊名稱的列印範圍也要跟著改（否則引用斷掉）"""
        workbook = self._pages('監工日報', "'監工日報'")
        self.assertNotIn('監工日報', workbook)
        self.assertIn('localSheetId="0">第1頁!$A$1:$N$17', workbook)
        self.assertIn('localSheetId="2">第3頁!$A$1:$N$17', workbook)


def _blank(name):
    from .common import blank_template
    with open(blank_template(name), 'rb') as fh:
        return fh.read()


def _zip_text(data, part):
    import zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(part).decode('utf-8')


@tagged('post_install', '-at_install', 'construction_template')
class TestBlankTemplateLayout(TransactionCase):
    """④ 空白樣板本身的版面設定（全部 xlsx 樣板一起檢查，不只出事的那一份）"""

    def _xlsx_names(self):
        import os
        from .common import blank_template
        folder = os.path.dirname(blank_template('daily_log_1.xlsx'))
        names = sorted(n for n in os.listdir(folder) if n.endswith('.xlsx'))
        self.assertGreater(len(names), 10, '找不到空白樣板目錄——這個檢查等於沒跑')
        return names

    def test_no_placeholder_hidden_by_merge(self):
        """監造日報表（二）：工程名稱的 ${project.name} 放在合併儲存格 A4:F4 裡的 B4，
        Excel 只顯示左上角 → 每一頁的工程名稱都印不出來"""
        import re
        from ..utils import xlsx_placeholder

        def col(s):
            n = 0
            for ch in s:
                n = n * 26 + ord(ch) - 64
            return n
        hidden = []
        for name in self._xlsx_names():
            data = _blank(name)
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                parts = zf.namelist()
                shared = (xlsx_placeholder.parse_shared_strings(zf.read('xl/sharedStrings.xml').decode('utf-8'))
                          if 'xl/sharedStrings.xml' in parts else [])
                for part in parts:
                    if not re.match(r'xl/worksheets/sheet\d+\.xml$', part):
                        continue
                    xml = zf.read(part).decode('utf-8')
                    merges = [re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', m).groups()
                              for m in re.findall(r'<mergeCell ref="([^"]+:[^"]+)"', xml)]
                    for c, r, attrs, body in xlsx_placeholder.CELL_RE.findall(xml):
                        if '${' not in xlsx_placeholder.cell_text(attrs, body, shared):
                            continue
                        ref = '%s%s' % (c, r)
                        for c1, r1, c2, r2 in merges:
                            inside = col(c1) <= col(c) <= col(c2) and int(r1) <= int(r) <= int(r2)
                            if inside and (col(c), int(r)) != (col(c1), int(r1)):
                                hidden.append('%s %s 在 %s%s:%s%s 裡' % (name, ref, c1, r1, c2, r2))
        self.assertEqual(hidden, [])

    def test_daily_log_c1_keeps_eagle_one_page(self):
        """營造版施工日誌（一）照 EAGLE 原檔「整張縮成一頁」（使用者 2026-11-05 裁示）。
        跑版檢查曾改成高度不限（fitToHeight=0、工項多時往下分頁），裁示後撤回；
        這支測試防止下次又被當成跑版「修」掉。要改先問使用者。"""
        import re
        xml = _zip_text(_blank('daily_log_c1.xlsx'), 'xl/worksheets/sheet1.xml')
        self.assertIn('<pageSetUpPr fitToPage="1"/>', xml)
        setup = re.search(r'<pageSetup[^>]*>', xml).group(0)
        # 沒寫 fitToWidth／fitToHeight＝兩者預設 1＝寬高都縮成一頁
        self.assertNotIn('fitToHeight=', setup)
        self.assertNotIn('fitToWidth=', setup)

    def test_daily_log_2_no_blank_row_under_header(self):
        """監造日報表（二）：表頭第 5 列與資料第 7 列之間沒有定義第 6 列，
        Excel 用預設列高印出一條空白列（只在第 1 頁出現，後面幾頁的表頭是「列印標題」）"""
        import re
        xml = _zip_text(_blank('daily_log_2.xlsx'), 'xl/worksheets/sheet1.xml')
        row6 = re.search(r'<row r="6"([^>]*)', xml)
        self.assertIsNotNone(row6, '第 6 列沒有定義 → 印成預設高度的空白列')
        self.assertIn('hidden="1"', row6.group(1))

    def test_control_tables_repeat_header_rows(self):
        """管制表跨頁時表頭不重複：第 2 頁起看不出每一欄是什麼"""
        import re
        for name, marker in (('review_control.docx', 'FOR item'),
                             ('defect_control.docx', 'FOR record'),
                             ('test_control.docx', 'FOR item')):
            xml = _zip_text(_blank(name), 'word/document.xml')
            table = re.search(r'<w:tbl>.*?</w:tbl>', xml, re.S).group(0)
            rows = re.findall(r'<w:tr[ >].*?</w:tr>', table, re.S)
            first_data = next(i for i, tr in enumerate(rows) if marker in ''.join(
                re.findall(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>', tr)).replace(' ', ' '))
            self.assertGreater(first_data, 0, name)
            for i in range(first_data):
                self.assertIn('<w:tblHeader/>', rows[i], '%s 第 %s 列（表頭）要跨頁重複' % (name, i))
            self.assertNotIn('<w:tblHeader/>', rows[first_data], '%s 資料列不能設成表頭' % name)


@tagged('post_install', '-at_install', 'construction_template')
class TestControlMappings(TransactionCase):

    def test_review_control_item_no_falls_back_to_sequence(self):
        """送審管制總表：送審單沒有編號時「項次」印名稱 → 長名稱塞進窄欄，一字一行"""
        from ..mappings import review_control
        app = self.env['supervision.review.application'].new({'name': '混凝土取樣(210)'})
        self.assertFalse(app.no)
        item = review_control._item(app, 3)
        self.assertEqual(item['no'], '3')
        self.assertEqual(item['name'], '混凝土取樣(210)')



@tagged('post_install', '-at_install', 'construction_template')
class TestMigration3100(TransactionCase):
    """⑤ 3.10.0 換預設樣板：清單要列出每一個舊版、不能含新版（否則下次升級又會被當成舊版）"""

    def _module(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'migrations', '18.0.3.10.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mig_3_10_0', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_replaceable_excludes_new_files(self):
        import hashlib
        from .common import blank_template
        mod = self._module()
        from ..hooks import TYPES
        ext = {t: e for t, _label, e, _note in TYPES}
        for ttype, sums in mod.REPLACEABLE.items():
            with open(blank_template('%s.%s' % (ttype, ext[ttype])), 'rb') as fh:
                new = hashlib.sha1(fh.read()).hexdigest()
            self.assertNotIn(new, sums, '%s：新版的 checksum 不能在「可覆蓋的舊版」清單裡' % ttype)

    def test_daily_log_c1_not_replaced(self):
        """營造版日誌一照 EAGLE 不改 → 不能出現在換檔清單裡（否則升級會把各站的檔換掉）"""
        self.assertNotIn('daily_log_c1', self._module().REPLACEABLE)

    def test_current_defaults_are_known_old_versions(self):
        """這個庫現在的系統預設，要嘛已是新版，要嘛在清單裡（否則升級會略過、不換）"""
        import hashlib
        from .common import blank_template
        mod = self._module()
        from ..hooks import TYPES
        ext = {t: e for t, _label, e, _note in TYPES}
        templates = self.env['document.template'].with_context(active_test=False).search(
            [('is_default', '=', True), ('template_type', 'in', list(mod.REPLACEABLE))])
        self.assertTrue(templates, '這個庫沒有系統預設樣板——檢查等於沒跑')
        for tpl in templates:
            with open(blank_template('%s.%s' % (tpl.template_type, ext[tpl.template_type])), 'rb') as fh:
                new = hashlib.sha1(fh.read()).hexdigest()
            checksum = tpl.attachment_id.checksum
            self.assertTrue(checksum == new or checksum in mod.REPLACEABLE[tpl.template_type],
                            '%s 目前的附件 %s 不是已知的出貨版本' % (tpl.template_type, checksum))


@tagged('post_install', '-at_install', 'construction_template')
class TestProbeStageGap(TransactionCase):
    """⑥ 自主檢查樣板「復舊工程」：樣板只用 stages[0] 與 stages[2]（跳過第 2 段），
    檢查類型只有兩段 → 守門算段數用 len(capacity)＝2，以為對得上，
    套印才爆 jinja2 的英文錯誤「list object has no element 2」。"""

    def _probe(self, stage_indexes):
        from ..utils import template_probe
        rows = [template_probe.Row(s, 0, frozenset({'situation'}), '段%s' % s, '項目%s' % s)
                for s in stage_indexes]
        return template_probe.Probe(template_probe.KIND_INDEXED, rows=rows)

    def test_skipped_stage_index_is_reported(self):
        from ..utils import template_probe
        problems = template_probe.check_fit(
            self._probe([0, 2]), [('施工前', ['項目0']), ('施工後', ['項目2'])], strict_names=False)
        self.assertTrue(problems, '樣板跳過第 2 段、還要第 3 段，守門卻放行')
        self.assertTrue(any('第 3 段' in p for p in problems), problems)
        self.assertTrue(any('第 2 段' in p for p in problems), problems)

    def test_skipped_stage_with_no_items_not_reported(self):
        """抗辯審查（skeptic F3）：被跳過的段在資料裡是 0 項（量測區塊併出來的空段）→ 不會漏印，不能擋"""
        from ..utils import template_probe
        problems = template_probe.check_fit(
            self._probe([0, 2]), [('施工前', ['項目0']), ('', []), ('施工後', ['項目2'])],
            strict_names=False)
        self.assertEqual(problems, [])

    def test_contiguous_stages_still_pass(self):
        """對照組：連號的樣板照舊放行"""
        from ..utils import template_probe
        problems = template_probe.check_fit(
            self._probe([0, 1]), [('施工前', ['項目0']), ('施工後', ['項目1'])], strict_names=False)
        self.assertEqual(problems, [])


@tagged('post_install', '-at_install', 'construction_template')
class TestProbeNoItemSlots(TransactionCase):
    """⑦ 40 種自主檢查上傳樣板只有表頭標記、檢查項目那幾列沒有任何結果欄位的標記
    （2026-06-24 生成程式把結果欄清空）。守門只核對名稱，結構判成 unknown 就直接放行，
    匯出的表「實際檢查情形／檢查結果／備註」整欄空白，看起來卻很正常。"""

    def test_template_without_item_tokens_is_reported(self):
        from ..utils import template_probe
        problems = template_probe.check_fit(
            template_probe.Probe(template_probe.KIND_UNKNOWN), [('施工前', ['項目'])])
        self.assertTrue(problems, '沒有結果欄位的樣板被放行 → 匯出的檢查結果整欄空白')
        self.assertTrue(any('整欄空白' in p for p in problems), problems)

    def _probe(self, kind, text):
        from ..utils import template_probe
        xml = '<w:document><w:body><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:body></w:document>' % text
        return template_probe.Probe(kind, xml=xml)

    def test_dynamic_template_still_passes(self):
        """對照組：動態表格樣板（系統預設）不限項目數，照舊放行"""
        from ..utils import template_probe
        probe = self._probe(template_probe.KIND_DYNAMIC, '{% for stage in inspection.stages %}')
        self.assertEqual(template_probe.check_fit(probe, [('施工前', ['項目'])]), [])

    def test_eagle_style_item_loop_passes(self):
        """抗辯審查（skeptic F2）：`+++FOR stage IN inspection.stages+++` 是合法的動態寫法，
        DYNAMIC_RE 認不得 → kind 是 unknown，舊判斷會誤擋"""
        from ..utils import template_probe
        for text in ('+++FOR stage IN inspection.stages+++', '{%p for item in stage.items %}'):
            probe = self._probe(template_probe.KIND_UNKNOWN, text)
            self.assertEqual(template_probe.check_fit(probe, [('施工前', ['項目'])]), [], text)

    def test_photo_loop_only_is_still_reported(self):
        """抗辯審查（red-team F7）：只有照片迴圈、沒有任何項目標記 → kind 判成 dynamic，舊判斷放行"""
        from ..utils import template_probe
        probe = self._probe(template_probe.KIND_DYNAMIC, '{% for page in inspection.imagePages %}')
        self.assertTrue(template_probe.check_fit(probe, [('施工前', ['項目'])]))


@tagged('post_install', '-at_install', 'construction_template')
class TestPageBreakParagraph(TransactionCase):
    """⑧ 管制表中間多一頁白紙：每一頁結尾是「只有分頁符號的段落」，前一頁剛好排滿到底時，
    這個段落被擠到新的一頁，再分一次頁 → 中間一張白紙（缺失管制表 15 頁裡的第 12 頁）。
    改成在下一段設「段落前分頁」：段落本來就在頁首時 Word 不會再多分一頁。"""

    def _render(self, build):
        return _body(docx_render.render(_docx(build), {}))

    def test_break_only_paragraph_becomes_page_break_before(self):
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('第二頁')
        blocks = _blocks(self._render(build))
        self.assertFalse(any(_has_page_break(el) for el in blocks), '只有分頁符號的段落還在')
        second = [el for el in blocks if _text(el) == '第二頁'][0]
        self.assertIsNotNone(second.find('%s/%s' % (_q('pPr'), _q('pageBreakBefore'))),
                             '下一段要改成「段落前分頁」')

    def test_break_followed_by_spacer_paragraph_converts(self):
        """缺失管制表的實際結構：分頁段落 → 空白間隔段 → 標題。下一段是空的也要轉
        （只有「下一段也只有分頁符號」＝刻意留的空白頁才不轉）"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('')
            doc.add_paragraph('矯正與預防紀錄管制表')
        blocks = _blocks(self._render(build))
        self.assertFalse(any(_has_page_break(el) for el in blocks), '只有分頁符號的段落還在 → 前一頁排滿時多一張白紙')
        self.assertTrue(any(el.find('%s/%s' % (_q('pPr'), _q('pageBreakBefore'))) is not None for el in blocks))

    def test_two_breaks_in_a_row_keep_the_blank_page(self):
        """抗辯審查（skeptic F6）：連續兩個分頁＝刻意留的空白頁（雙面列印），不能吃掉"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('第三頁')
        blocks = _blocks(self._render(build))
        pages = sum(1 for el in blocks if _has_page_break(el)) + sum(
            1 for el in blocks if el.find('%s/%s' % (_q('pPr'), _q('pageBreakBefore'))) is not None)
        self.assertEqual(pages, 2, '刻意留的空白頁被吃掉')

    def test_page_break_before_val_zero_is_turned_on(self):
        """抗辯審查（skeptic F5）：下一段已有 <w:pageBreakBefore w:val="0"/>（關）→ 要打開，不能讓分頁消失"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            second = doc.add_paragraph('第二頁')
            # python-docx 設 False 會直接拿掉元素，造不出 val="0"——直接寫 XML
            from docx.oxml import parse_xml
            ppr = second._p.get_or_add_pPr()
            ppr.insert(0, parse_xml('<w:pageBreakBefore xmlns:w="%s" w:val="0"/>' % W_NS))
            # 後面再接一段：「第二頁」不是最後一段，才不會跟「最後一段結尾處理」混在一起測
            doc.add_paragraph('第二頁之後')
        before = _body(_docx(build))
        self.assertEqual([el.get(_q('val')) for el in before.iter(_q('pageBreakBefore'))], ['0'],
                         '測試樣板本身要有 val="0"（否則這支測試是恆真的）')
        blocks = _blocks(self._render(build))
        second = [el for el in blocks if _text(el) == '第二頁'][0]
        pbb = second.find('%s/%s' % (_q('pPr'), _q('pageBreakBefore')))
        self.assertIsNotNone(pbb)
        self.assertNotIn((pbb.get(_q('val')) or '1').lower(), ('0', 'false', 'off'))

    def test_break_before_table_is_kept(self):
        """對照組：下一塊是表格（表格不能設段落前分頁）→ 分頁符號留著"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            doc.add_paragraph('第一頁')
            doc.add_paragraph('').add_run().add_break(WD_BREAK.PAGE)
            doc.add_table(rows=1, cols=1).cell(0, 0).text = '表格'
        blocks = _blocks(self._render(build))
        self.assertTrue(any(_has_page_break(el) for el in blocks))

    def test_break_inside_text_paragraph_is_kept(self):
        """對照組：有文字的段落裡的分頁符號不動"""
        from docx.enum.text import WD_BREAK

        def build(doc):
            para = doc.add_paragraph('第一頁結尾')
            para.add_run().add_break(WD_BREAK.PAGE)
            doc.add_paragraph('第二頁')
        blocks = _blocks(self._render(build))
        self.assertTrue(any(_has_page_break(el) for el in blocks))


@tagged('post_install', '-at_install', 'construction_template')
class TestUploadedTemplateUnreadable(TransactionCase):
    """⑨ 檢查類型上傳過樣板、但檔案讀不到（filestore 檔案遺失、附件被清掉）時，
    `_form_template()` 會靜默改用系統預設樣板——系統預設是動態表格、守門一律放行，
    「測試樣板」顯示成功，套的卻不是這個類型的樣板（2026-11-05 自主檢查修正時實際撞到）。"""

    def test_missing_upload_is_reported_not_replaced(self):
        from odoo.exceptions import UserError
        itype = self.env['self.inspection.type'].create({'name': '樣板讀不到測試'})
        itype.write({'template_file': False, 'template_filename': '鋼筋自主檢查表.docx'})
        self.assertFalse(itype.template_file)
        with self.assertRaises(UserError) as cm:
            itype._form_template()
        self.assertIn('讀不到', str(cm.exception))

    def test_no_upload_still_uses_system_default(self):
        """對照組：根本沒上傳過（沒有檔名）→ 照舊用系統預設樣板"""
        itype = self.env['self.inspection.type'].create({'name': '沒有上傳樣板'})
        _raw, _name, label = itype._form_template()
        self.assertIn('系統預設', label)
