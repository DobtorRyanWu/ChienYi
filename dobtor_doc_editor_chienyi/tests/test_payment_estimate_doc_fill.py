# -*- coding: utf-8 -*-
"""估驗計價線上文件：建立／重新套用範本時，表頭與「本期完成工項」要填成這張估驗的實際值。

背景（2026-11-07 使用者在 jt 實看「完全是沒內容」）：
範本 dobtor_doc_editor.template_payment_estimate 出廠沒有欄位對映，
「顯示實際值」沒有對映就回錯誤；工項表只有一列空白。
改成與自主檢查同一套：doc.linked.mixin._doc_prepare_content_html 在 server 端把值寫進 content_html。

金額定義與「工程估驗計價單」匯出的「合計（僅合約項）」一致——有裝 construction_template
時直接拿它的 build_context() 當第二把尺比對（兩種獨立算法要得出同一個數字）。
"""
import re
from datetime import date

from lxml import html as lxml_html

from odoo.tests.common import TransactionCase, tagged

# 範本裡六個表頭變數；建立後一個都不能留下
_HEADER_VAR_RE = (r'\{\{\s*(project_name|estimate_date|contractor|estimate_no|'
                  r'current_amount|cumulative_amount)\s*\}\}')


def _item_rows(content_html):
    """回傳「本期完成工項」表（範本裡唯一有 thead 的表）tbody 每列的儲存格文字。"""
    root = lxml_html.fragment_fromstring(content_html, create_parent='div')
    tables = [t for t in root.iter('table') if t.find('thead') is not None]
    assert len(tables) == 1, '找不到唯一一張有 thead 的工項表：%d 張' % len(tables)
    return [[(td.text_content() or '').strip() for td in tr.iter('td')]
            for tr in tables[0].find('tbody').iter('tr')]


def _money_to_int(text):
    return int(text.replace(',', ''))


@tagged('post_install', '-at_install', 'dobtor_doc_editor_chienyi')
class TestPaymentEstimateDocFill(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '估驗文件填值 A&B <x>',
            'code': 'EST-DOCFILL',
            'state': 'construction',
            'company_id': cls.env.company.id,
            'contractor_company_name': '測試營造 <有限>',
        })
        Task = cls.env['project.task']
        cls.root = Task.create({
            'name': '發包工程費', 'project_id': cls.project.id, 'item_no': '壹',
            'unit': '式', 'planned_qty': 1.0, 'unit_price': 0.0,
        })

        def leaf(no, name, unit, price):
            return Task.create({
                'name': name, 'project_id': cls.project.id, 'parent_id': cls.root.id,
                'item_no': no, 'unit': unit, 'planned_qty': 100.0, 'unit_price': price,
            })
        cls.a = leaf('一', '混凝土 210kgf/cm²', 'M3', 10.1)
        cls.b = leaf('二', '鋼筋', 'T', 0.5)
        cls.c = leaf('三', '模板', 'M2', 0.5)
        cls.d = leaf('四', '本期沒估的工項', 'M', 7.0)
        cls.e = leaf('五', '雜項', '式', 0.5)

    # === 工具 ===
    def _estimate(self, day, lines):
        """lines：[(task, qty), …]；彙總項（root）一律帶一列，跟正式資料一樣。"""
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id,
            'estimate_date': date(2024, 9, day),
        })
        Line = self.env['payment.estimate.line']
        vals = Line._prepare_line_vals(self.root, 1)
        vals['estimate_id'] = est.id
        Line.create(vals)
        for seq, (task, qty) in enumerate(lines, 10):
            vals = Line._prepare_line_vals(task, seq)
            vals.update({'estimate_id': est.id, 'estimate_qty': qty})
            Line.create(vals)
        return est

    def _approve(self, *ests):
        for est in ests:
            est.action_submit_estimate()
            est.action_approve()
        self.env.invalidate_all()

    def _doc_html(self, est):
        est.action_open_linked_doc()
        return est.linked_doc_id.content_html

    # === 表頭 ===
    def test_header_vars_filled(self):
        est = self._estimate(23, [(self.a, 3.5)])
        content = self._doc_html(est)
        self.assertNotRegex(content, _HEADER_VAR_RE)
        self.assertIn('113.09.23', content)             # 民國日期，與估驗計價單匯出同格式
        self.assertIn('第 %s 期' % est.estimate_no, content)
        self.assertIn('測試營造 &lt;有限&gt;', content)  # 承包商取工程案件的廠商名稱

    def test_values_are_escaped(self):
        """名稱裡的 < & 要跳脫：否則會變成真的 HTML 標籤，顯示的字跟資料不一樣。"""
        est = self._estimate(23, [(self.a, 1)])
        content = self._doc_html(est)
        self.assertIn('估驗文件填值 A&amp;B &lt;x&gt;', content)
        self.assertNotIn('<x>', content)

    # === 本期完成工項 ===
    def test_items_are_current_period_leaves_in_order(self):
        """只列本期有估的葉節點，依明細順序；彙總項與本期 0 數量的工項不列。"""
        est = self._estimate(23, [(self.a, 3.5), (self.d, 0), (self.b, 2)])
        rows = _item_rows(self._doc_html(est))
        self.assertEqual([r[:3] for r in rows], [
            ['一', '混凝土 210kgf/cm²', 'M3'],
            ['二', '鋼筋', 'T'],
        ])
        # 數量、單價照原值（去掉多餘的 0），小計是整數元
        self.assertEqual(rows[0][3:], ['3.5', '10.1', '35'])
        self.assertEqual(rows[1][3:], ['2', '0.5', '1'])

    def test_item_amounts_sum_to_header_current_amount(self):
        """三列各 0.5 元：逐列四捨五入是 1+1+1＝3，表頭本期是 contract_subtotal＝2
        （Monetary 依幣別精度存成整數元，1.5 → 2）。小計欄要做尾差調整，加起來等於表頭，
        不然紙本對不起來。"""
        est = self._estimate(23, [(self.b, 1), (self.c, 1), (self.e, 1)])
        leaves = est.line_ids.filtered(lambda ln: not ln.is_summary_item)
        self.assertEqual(sum(leaves.mapped('estimate_amount')), 1.5)
        self.assertEqual(est.contract_subtotal, 2.0)
        rows = _item_rows(self._doc_html(est))
        amounts = [_money_to_int(r[5]) for r in rows]
        self.assertEqual(len(amounts), 3)
        self.assertNotEqual(amounts, [1, 1, 1], '這組輸入要能分辨「有沒有尾差調整」')
        self.assertEqual(sum(amounts), 2)

    def test_no_lines_keeps_template_blank_row(self):
        """沒有明細：工項表保留範本那一列空白（安全降級），表頭照樣填。"""
        est = self.env['payment.estimate'].create({
            'project_id': self.project.id, 'estimate_date': date(2024, 9, 23)})
        content = self._doc_html(est)
        self.assertNotRegex(content, _HEADER_VAR_RE)
        rows = _item_rows(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 6)

    # === 累計：本期＋前面已核定各期（草稿不算）===
    def test_cumulative_counts_earlier_approved_only(self):
        e1 = self._estimate(1, [(self.a, 2)])      # 20.2，已核定 → 算
        e2 = self._estimate(2, [(self.a, 1)])      # 10.1，草稿 → 不算
        self._approve(e1)
        e3 = self._estimate(3, [(self.a, 3.5)])    # 35.35
        content = self._doc_html(e3)
        self.assertEqual(e2.state, 'draft')
        # 本期 35（contract_subtotal：35.35 依幣別精度存成 35）；
        # 累計 round(20.2＋35.35)＝56——明細金額相加後才捨入，與估驗計價單匯出同一套
        # （不是各期 contract_subtotal 相加的 20＋35＝55）
        root = lxml_html.fragment_fromstring(content, create_parent='div')
        header = [t for t in root.iter('table') if t.find('thead') is None][0]
        cells = [(td.text_content() or '').strip() for td in header.iter('td')]
        self.assertEqual(cells[cells.index('本期估驗金額') + 1], '35')
        self.assertEqual(cells[cells.index('累計金額') + 1], '56')

    def test_amounts_match_estimate_report_export(self):
        """第二把尺：同一張估驗，跟「工程估驗計價單」匯出的合計（僅合約項）要同一個數字。"""
        try:
            from odoo.addons.construction_template.mappings.estimate_report import build_context
        except ImportError:
            self.skipTest('construction_template 不在 addons path')
        if self.env['ir.module.module'].search_count([
                ('name', '=', 'construction_template'), ('state', '=', 'installed')]) != 1:
            self.skipTest('construction_template 未安裝')
        e1 = self._estimate(1, [(self.a, 2), (self.b, 3)])
        self._approve(e1)
        e2 = self._estimate(3, [(self.a, 3.5), (self.c, 1), (self.b, 1)])
        ctx = build_context(e2)
        root = lxml_html.fragment_fromstring(self._doc_html(e2), create_parent='div')
        header = [t for t in root.iter('table') if t.find('thead') is None][0]
        cells = [(td.text_content() or '').strip() for td in header.iter('td')]
        self.assertEqual(cells[cells.index('本期估驗金額') + 1], ctx['totalCurrentAmount'])
        self.assertEqual(cells[cells.index('累計金額') + 1], ctx['totalCumulativeAmount'])

    def test_cumulative_includes_earlier_items_not_listed_this_period(self):
        """前期估過、本期沒列的工項也要算進累計（匯入建的估驗單只列本期有填的工項）。

        這支用來分辨兩種口徑：「本張各列的前期＋本期」會漏掉工項二，得 56；
        匯出用的「本張＋前期全部葉節點」得 round(20.2＋1.5＋35.35)＝57。
        """
        e1 = self._estimate(1, [(self.a, 2), (self.b, 3)])     # 20.2＋1.5
        self._approve(e1)
        e2 = self._estimate(3, [(self.a, 3.5)])                 # 35.35，本期沒列工項二
        root = lxml_html.fragment_fromstring(self._doc_html(e2), create_parent='div')
        header = [t for t in root.iter('table') if t.find('thead') is None][0]
        cells = [(td.text_content() or '').strip() for td in header.iter('td')]
        self.assertEqual(cells[cells.index('累計金額') + 1], '57')

    # === 範本被後台 HTML 編輯器存過：表頭表會被瀏覽器補上 <tbody> ===
    def _browser_saved_template(self):
        """模擬範本在後台 widget="html" 存過一次：瀏覽器替沒有 tbody 的表頭表補上 <tbody>。"""
        html = self.env.ref('dobtor_doc_editor.template_payment_estimate').content_html
        saved, n = re.subn(r'(<table[^>]*>)(.*?)(</table>)',
                           lambda m: m[1] + '<tbody>' + m[2] + '</tbody>' + m[3],
                           str(html), count=1, flags=re.DOTALL)
        self.assertEqual(n, 1)
        self.assertGreaterEqual(saved.count('<tbody>'), 2, 'rig 要真的多出一個 tbody')
        return saved

    def test_header_table_with_tbody_is_not_replaced(self):
        est = self._estimate(23, [(self.a, 3.5), (self.b, 2)])
        content = est._doc_prepare_content_html(self._browser_saved_template())
        self.assertNotRegex(content, _HEADER_VAR_RE)
        self.assertIn('本期估驗金額', content)
        self.assertIn('估驗文件填值 A&amp;B &lt;x&gt;', content)
        self.assertEqual([r[0] for r in _item_rows(content)], ['一', '二'])

    def test_ambiguous_item_table_left_untouched(self):
        """有兩張帶 thead 的表：分不出哪張是工項表，就不動（表頭照填）。"""
        est = self._estimate(23, [(self.a, 3.5)])
        tpl = str(self.env.ref('dobtor_doc_editor.template_payment_estimate').content_html)
        start = tpl.index('<table', tpl.index('<thead') - 400)
        item_table = tpl[start:tpl.index('</table>', start) + len('</table>')]
        content = est._doc_prepare_content_html(tpl + item_table)
        self.assertNotRegex(content, _HEADER_VAR_RE)
        self.assertNotIn('混凝土', content)

    # === 資料不能變成 Jinja 原始碼：匯出 PDF／DOCX 與快速預覽會把 content_html 整份丟給 Jinja ===
    def test_jinja_delimiters_in_values_are_not_evaluated(self):
        evil = self.env['project.task'].create({
            'name': '{{ 7*7 }}{% for i in range(3) %}迴圈{% endfor %}{# 吃掉 #}',
            'project_id': self.project.id, 'parent_id': self.root.id,
            'item_no': '六', 'unit': '式', 'planned_qty': 1.0, 'unit_price': 1.0,
        })
        est = self._estimate(23, [(evil, 1)])
        est.action_open_linked_doc()
        doc = est.linked_doc_id
        for opener in ('{{', '{%', '{#'):
            self.assertNotIn(opener, doc.content_html)
        # 用匯出同一支渲染器跑一次；尾巴加 6*7 證明 Jinja 真的有跑（渲染失敗會原樣回傳，那樣斷言恆真）
        rendered = doc._render_template(str(doc.content_html) + '{{ 6*7 }}', est)
        self.assertIn('42', rendered)
        self.assertNotIn('49', rendered)
        self.assertNotIn('迴圈迴圈', rendered)
        self.assertIn('吃掉', rendered)

    # === 重新套用範本：抓現在的值 ===
    def test_reapply_template_refreshes_values(self):
        est = self._estimate(23, [(self.a, 1)])
        est.action_open_linked_doc()
        doc = est.linked_doc_id
        self.assertEqual(_item_rows(doc.content_html)[0][3], '1')
        est.line_ids.filtered(lambda ln: ln.task_id == self.a).estimate_qty = 4
        doc.action_reapply_template()
        rows = _item_rows(doc.content_html)
        self.assertEqual(rows[0][3], '4')
        self.assertEqual(rows[0][5], '40')       # 4 × 10.1 = 40.4 → 40

    # === 2026-11-08 修法複審留下的 low ===
    def test_nested_item_table_left_untouched(self):
        """工項表包在排版表裡（DOCX 匯入的範本常見）：分不清楚就不動，並記 warning。"""
        est = self._estimate(23, [(self.a, 3.5)])
        tpl = str(self.env.ref('dobtor_doc_editor.template_payment_estimate').content_html)
        start = tpl.index('<table', tpl.index('<thead') - 400)
        end = tpl.index('</table>', start) + len('</table>')
        nested = (tpl[:start] + '<table><tbody><tr><td>' + tpl[start:end]
                  + '</td></tr></tbody></table>' + tpl[end:])
        with self.assertLogs('odoo.addons.dobtor_doc_editor_chienyi', level='WARNING'):
            content = est._doc_prepare_content_html(nested)
        self.assertNotRegex(content, _HEADER_VAR_RE)
        self.assertNotIn('混凝土', content)
        self.assertEqual(content.count('<thead'), nested.count('<thead'))
        self.assertEqual(content.count('<tbody'), nested.count('<tbody'))

    def test_contractor_partner_without_name(self):
        """承包廠商聯絡人裡有沒名字的地址（name=False）：不能讓「開啟線上文件」整個失敗。"""
        project = self.project.copy({'name': '無廠商名稱工程', 'code': 'EST-NONAME',
                                     'contractor_company_name': False})
        if 'contractor_partner_ids' not in project._fields:
            self.skipTest('contractor_partner_ids 由 construction_portal 提供，未安裝')
        company = self.env['res.partner'].create({'name': '乙營造', 'is_company': True})
        nameless = self.env['res.partner'].create({'type': 'delivery', 'parent_id': company.id})
        self.assertFalse(nameless.name, 'rig：要真的有一個沒名字的聯絡人')
        project.contractor_partner_ids = [(6, 0, (company | nameless).ids)]
        est = self.env['payment.estimate'].create({
            'project_id': project.id, 'estimate_date': date(2024, 9, 23)})
        self.assertEqual(est._doc_contractor_name(), '乙營造')

    def test_adjacent_values_cannot_form_jinja_opener(self):
        """兩個變數緊貼時，前一個值結尾的 { 與後一個值開頭的 { 不能拼成 {{。"""
        from ..models import payment_estimate_doc_helper as helper
        out = helper.fill_vars('<p>{{ a }}{{ b }}</p>', {'a': 'X{', 'b': '{ 7*7 }}'})
        self.assertNotIn('{{', out)
        self.assertIn('7*7', out)
