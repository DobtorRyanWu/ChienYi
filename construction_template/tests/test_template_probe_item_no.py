# -*- coding: utf-8 -*-
"""硬編自主檢查樣板：第二欄是「項次」數字時，項目名稱取下一欄。

template_probe 逐列比對「樣板上印的項目名稱」與檢查類型的項目（防錯位），它假設第一欄是
段落、第二欄是項目名稱——79 份 EAGLE 樣板都是這樣。工程會／新北的表常多一欄「項次」
（生態保育措施自主檢查表：項目｜項次｜檢查項目｜是｜不足｜否｜缺失說明），第二欄是 1、2、3，
守門就拿「1」去比項目名稱而擋下套印。
"""

import io
import zipfile

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.utils import template_probe

from .common import blank_template


def _cell(text, vmerge=None):
    pr = '<w:tcPr><w:vMerge%s/></w:tcPr>' % (' w:val="restart"' if vmerge == 'restart' else '') \
        if vmerge else ''
    return '<w:tc>%s<w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>' % (pr, text)


def _docx(rows):
    body = '<w:tbl>%s</w:tbl>' % ''.join('<w:tr>%s</w:tr>' % ''.join(r) for r in rows)
    with open(blank_template('material_test.docx'), 'rb') as fp:
        src = zipfile.ZipFile(io.BytesIO(fp.read()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == 'word/document.xml':
                xml = data.decode('utf-8')
                head, rest = xml.split('<w:body>', 1)
                data = (head + '<w:body>' + body + rest[rest.rindex('<w:sectPr'):]).encode('utf-8')
            dst.writestr(info, data)
    return out.getvalue()


def _mark(s, i):
    return '{{ inspection.stages[%d].items[%d].passMark }}' % (s, i)


@tagged('post_install', '-at_install', 'construction_template')
class TestTemplateProbeItemNo(TransactionCase):

    def test_item_number_column_is_skipped(self):
        raw = _docx([
            [_cell('生態保育措施', 'restart'), _cell('1'), _cell('保全物種保護'), _cell(_mark(0, 0))],
            [_cell('', 'cont'), _cell('2'), _cell('減少整地範圍'), _cell(_mark(0, 1))],
        ])
        probe = template_probe.probe(raw)
        self.assertTrue(probe.is_indexed)
        self.assertEqual([r.item_name for r in probe.rows], ['保全物種保護', '減少整地範圍'])
        self.assertEqual(template_probe.check_fit(
            probe, [('生態保育措施', ['保全物種保護', '減少整地範圍'])]), [])
        # 名稱真的不同時仍要擋
        self.assertTrue(template_probe.check_fit(
            probe, [('生態保育措施', ['減少整地範圍', '保全物種保護'])]))

    def test_normal_layout_unchanged(self):
        raw = _docx([[_cell('施工前'), _cell('模板組立'), _cell(_mark(0, 0))]])
        self.assertEqual([r.item_name for r in template_probe.probe(raw).rows], ['模板組立'])
