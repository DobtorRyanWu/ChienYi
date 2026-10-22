"""匯出 writer：公式注入跳脫、UTF-8-SIG、xlsx 不把字串當公式。"""

import io
import zipfile

from odoo.tests import TransactionCase, tagged

from ..tools_export import escape_formula, roc_date, write_rows

COLUMNS = (
    ('姓名', lambda r: r['name'], 'text'),
    ('金額', lambda r: r['amount'], 'int'),
    ('日期', lambda r: r['date'], 'date_roc'),
)


@tagged('post_install', '-at_install')
class TestExportWriter(TransactionCase):

    def _rows(self):
        import datetime
        return [
            {'name': '王小明', 'amount': 3000, 'date': datetime.date(2026, 9, 18)},
            {'name': '=cmd|\' /c calc\'!A1', 'amount': 1500, 'date': False},
            {'name': '喆堃峯', 'amount': 0, 'date': datetime.date(2026, 1, 1)},
        ]

    def test_escape_formula(self):
        for bad in ('=1+1', '+1', '-1', '@sum', '\tx', '\rx'):
            self.assertTrue(escape_formula(bad).startswith("'"))
        self.assertEqual(escape_formula('王小明'), '王小明')
        self.assertEqual(escape_formula(False), '')

    def test_roc_date(self):
        import datetime
        self.assertEqual(roc_date(datetime.date(2026, 9, 18)), '115/09/18')
        self.assertEqual(roc_date(False), '')

    def test_csv_is_utf8_sig_and_escaped(self):
        data = write_rows(COLUMNS, self._rows(), file_type='csv')
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'), 'Excel 要 BOM 才不會亂碼')
        text = data.decode('utf-8-sig')
        self.assertIn("'=cmd", text, '公式要被跳脫')
        self.assertIn('喆堃峯', text, 'cp950 編不出這些字，所以一律 UTF-8')
        self.assertIn('115/09/18', text)

    def test_xlsx_strings_are_not_formulas(self):
        data = write_rows(COLUMNS, self._rows(), file_type='xlsx')
        with zipfile.ZipFile(io.BytesIO(data)) as book:
            sheet = book.read('xl/worksheets/sheet1.xml').decode()
            shared = book.read('xl/sharedStrings.xml').decode()
        self.assertNotIn('<f>', sheet, 'xlsx 不可出現公式節點（要用 write_string）')
        self.assertIn('喆堃峯', shared)
        # xlsx 不加 ' 前綴：那個引號在 Excel 儲存格裡看得到；防公式靠 write_string
        self.assertIn('=cmd', shared)
        self.assertNotIn("&apos;=cmd", shared)
        self.assertNotIn("'=cmd", shared)
