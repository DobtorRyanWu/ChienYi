# -*- coding: utf-8 -*-
"""docx 套印要用沙箱化的 Jinja2。

樣板 docx 是使用者上傳的（document.template、自主檢查類型的 template_file，任何
後台帳號都有寫入權），docxtpl 預設的 jinja2.Environment 沒有沙箱：樣板裡寫
`{{ x.__class__.__mro__ }}` 這類運算式就能沿著物件走到 Python 內部、在主機上執行
（2026-10-25 紅隊審查 critical）。SandboxedEnvironment 擋掉底線開頭的屬性與不安全的
呼叫，一般的 {{ a.b }}、{% for %}、{% if %} 照常運作。
"""

import io
import zipfile

from jinja2.exceptions import SecurityError

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.utils import docx_render

from .common import blank_template, docx_texts


def _docx_with(text):
    """拿模組內一份空白 docx，把本文換成一段含 text 的段落"""
    with open(blank_template('material_test.docx'), 'rb') as fp:
        raw = fp.read()
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == 'word/document.xml':
                xml = data.decode('utf-8')
                head, rest = xml.split('<w:body>', 1)
                tail = rest[rest.rindex('<w:sectPr'):]
                data = (head + '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>'
                        + tail).encode('utf-8')
            dst.writestr(info, data)
    return out.getvalue()


@tagged('post_install', '-at_install', 'construction_template')
class TestDocxSandbox(TransactionCase):

    def test_dunder_access_is_blocked(self):
        raw = _docx_with('{{ projectName.__class__.__mro__ }}')
        with self.assertRaises(SecurityError):
            docx_render.render(raw, {'projectName': '工程'})

    def test_normal_template_still_renders(self):
        raw = _docx_with('{{ projectName }}{% for r in rows %}[{{ r.no }}]{% endfor %}'
                         '{% if flag %}有{% else %}無{% endif %}')
        out = docx_render.render(raw, {'projectName': '八里工程&水設施',
                                       'rows': [{'no': 1}, {'no': 2}], 'flag': True})
        text = docx_texts(out)['word/document.xml']
        self.assertIn('八里工程&水設施', text)      # autoescape 照舊（& 不會變成壞掉的 XML）
        self.assertIn('[1][2]有', text)

    def test_recordset_attributes_are_blocked(self):
        # 對照表的 context 目前都是純值；萬一有人把 recordset 放進去，樣板也不能碰到 ORM
        # （SandboxedEnvironment 預設允許呼叫公開方法，record.unlink() 會過）
        raw = _docx_with('{{ rec.name }}')
        with self.assertRaises(SecurityError):
            docx_render.render(raw, {'rec': self.env.user})

    def test_recordset_item_access_is_blocked(self):
        # rec['name'] 走 Jinja 的 getitem，不經 is_safe_attribute（2026-10-25 第二輪審查 L2）
        raw = _docx_with("{{ rec['name'] }}")
        with self.assertRaises(SecurityError):
            docx_render.render(raw, {'rec': self.env.user})

