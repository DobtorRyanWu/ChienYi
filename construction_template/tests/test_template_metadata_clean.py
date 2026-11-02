# -*- coding: utf-8 -*-
"""系統預設空白樣板不能夾帶出貨者的內網路徑、個人帳號、舊案外部連結（T5-3）。

只看 metadata 與路徑；版面、公式、token 不在這裡驗（其他測試套印時會驗）。
"""

import glob
import os
import re
import zipfile

from odoo.tests.common import TransactionCase, tagged

from .common import blank_template

BLANK_DIR = os.path.dirname(blank_template('material_test.docx'))
# 建立者／最後修改者允許的值：空，或產品名稱
ALLOWED_AUTHORS = ('', 'ChienYi')
AUTHOR_RE = re.compile(r'<(dc:creator|cp:lastModifiedBy)(?:\s[^>]*)?>([^<]*)</\1>')
# 內網磁碟路徑、舊案資料夾（UNC 路徑或 file:/// 外部連結）
NETWORK_PATH_RE = re.compile(r'\\\\[^\\"<]+\\|file:///')


@tagged('post_install', '-at_install', 'construction_template')
class TestTemplateMetadataClean(TransactionCase):

    def _files(self):
        files = sorted(glob.glob(os.path.join(BLANK_DIR, '*.xlsx'))
                       + glob.glob(os.path.join(BLANK_DIR, '*.docx')))
        self.assertTrue(files)
        return files

    def test_no_personal_author_in_core_properties(self):
        bad = []
        for path in self._files():
            with zipfile.ZipFile(path) as zf:
                if 'docProps/core.xml' not in zf.namelist():
                    continue
                xml = zf.read('docProps/core.xml').decode('utf-8')
            for tag, value in AUTHOR_RE.findall(xml):
                if value not in ALLOWED_AUTHORS:
                    bad.append((os.path.basename(path), tag, value))
        self.assertEqual(bad, [])

    def test_no_company_in_app_properties(self):
        bad = []
        for path in self._files():
            with zipfile.ZipFile(path) as zf:
                if 'docProps/app.xml' not in zf.namelist():
                    continue
                xml = zf.read('docProps/app.xml').decode('utf-8')
            for tag, value in re.findall(r'<(Company|Manager)>([^<]+)</\1>', xml):
                bad.append((os.path.basename(path), tag, value))
        self.assertEqual(bad, [])

    def test_no_network_paths_in_workbook_or_external_links(self):
        bad = []
        for path in self._files():
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name == 'xl/workbook.xml' or name.startswith('xl/externalLinks/'):
                        xml = zf.read(name).decode('utf-8')
                        if NETWORK_PATH_RE.search(xml) or '192.168.' in xml:
                            bad.append((os.path.basename(path), name))
        self.assertEqual(bad, [])
