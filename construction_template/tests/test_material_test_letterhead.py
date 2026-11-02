# -*- coding: utf-8 -*-
"""材料試驗報告（送審函）的公文抬頭不能印死某一家公司的人與信箱（T5-2）。

空白樣板原本寫死「負責人：游貽任」與 jt.corp@msa.hinet.net，每一家客戶的送審函都印任泰的。
現在 email 接案件監造公司（res.company）的 email；負責人系統裡沒有對應欄位，留空白給人手填。
"""

import zipfile
from types import SimpleNamespace

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import material_test
from odoo.addons.construction_template.utils import docx_render

from .common import blank_template, docx_texts, leftovers_docx

LEGACY_STRINGS = ('游貽任', 'jt.corp', 'msa.hinet')
SUPERVISOR_EMAIL = 'supervisor@example.test'


@tagged('post_install', '-at_install', 'construction_template')
class TestMaterialTestLetterhead(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '送審函抬頭測試工程', 'code': 'TPL-MT-HEAD', 'company_id': cls.company.id})
        cls.record = SimpleNamespace(
            standard_id=False, test_report_no='22RT153', archive_number='A-1', name='N-1',
            project_id=cls.project)

    def _render(self):
        with open(blank_template('material_test.docx'), 'rb') as fp:
            raw = fp.read()
        out = docx_render.render(raw, material_test.build_context(self.record))
        return docx_texts(out)['word/document.xml']

    def test_blank_template_has_no_legacy_strings(self):
        with zipfile.ZipFile(blank_template('material_test.docx')) as zf:
            for name in zf.namelist():
                if name.endswith('.xml'):
                    xml = zf.read(name).decode('utf-8')
                    for legacy in LEGACY_STRINGS:
                        self.assertNotIn(legacy, xml, '%s 還留著 %s' % (name, legacy))

    def test_render_uses_supervisor_company_email(self):
        self.company.email = SUPERVISOR_EMAIL
        text = self._render()
        self.assertIn('email：' + SUPERVISOR_EMAIL, text)
        for legacy in LEGACY_STRINGS:
            self.assertNotIn(legacy, text)
        self.assertIn('報告編號：22RT153', text)

    def test_render_blank_when_company_has_no_email(self):
        self.company.email = False
        text = self._render()
        self.assertIn('email：', text)
        self.assertNotIn('False', text)
        self.assertNotIn('None', text)
        for legacy in LEGACY_STRINGS:
            self.assertNotIn(legacy, text)

    def test_render_has_no_leftover_tokens(self):
        with open(blank_template('material_test.docx'), 'rb') as fp:
            raw = fp.read()
        out = docx_render.render(raw, material_test.build_context(self.record))
        self.assertEqual(leftovers_docx(out), [])
