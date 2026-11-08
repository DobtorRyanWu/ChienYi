# -*- coding: utf-8 -*-
"""xlsx 匯入與附件唯讀預覽（18.0.1.1.0，2026-11-08）。

起因：jt 產出的監造日報表在試算表裡打開，JT 浮水印（其實是 Excel 的「頁首圖」，
只在列印時出現）被當成一般圖片貼在左上角、整片蓋住表頭；「實際進度」文字
'45.60' 配 0.00% 格式顯示成 4560.00%；「740 天」「3 次」的單位不見。
"""

import base64
import io
import zipfile

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.dobtor_spreadsheet_editor.models import xlsx_to_workbook as x2w
from odoo.addons.dobtor_spreadsheet_editor.models.ir_attachment import XLSX_MIMETYPE

# 1×1 PNG
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def _xlsx_with_vml_image(sheet_tag):
    """最小 xlsx：一個工作表、一張 VML 圖，只差工作表用哪個標籤掛它。

    sheet_tag='legacyDrawingHF' → 頁首／頁尾圖（&C&G）；'legacyDrawing' → 貼在表上的圖。
    兩份只差這一個字，所以結果不同只能是這個標籤造成的。
    """
    ns_main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    rel_vml = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing'
    rel_img = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
    rel_ws = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet'
    rels_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/workbook.xml',
                   '<workbook xmlns="%s" xmlns:r="%s"><sheets>'
                   '<sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>' % (ns_main, ns_r))
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s" '
                   'Target="worksheets/sheet1.xml"/></Relationships>' % (rels_ns, rel_ws))
        z.writestr('xl/worksheets/sheet1.xml',
                   '<worksheet xmlns="%s" xmlns:r="%s"><sheetData/>'
                   '<headerFooter><oddHeader>&amp;C&amp;G</oddHeader></headerFooter>'
                   '<%s r:id="rId1"/></worksheet>' % (ns_main, ns_r, sheet_tag))
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels',
                   '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s" '
                   'Target="../drawings/vmlDrawing1.vml"/></Relationships>' % (rels_ns, rel_vml))
        z.writestr('xl/drawings/vmlDrawing1.vml',
                   '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
                   'xmlns:o="urn:schemas-microsoft-com:office:office">'
                   '<v:shape id="CH" style="position:absolute;margin-left:0;margin-top:0;'
                   'width:259pt;height:242pt"><v:imagedata o:relid="rId1"/></v:shape></xml>')
        z.writestr('xl/drawings/_rels/vmlDrawing1.vml.rels',
                   '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s" '
                   'Target="../media/image1.png"/></Relationships>' % (rels_ns, rel_img))
        z.writestr('xl/media/image1.png', PNG)
    return buf.getvalue()


def _xlsx_with_cells():
    """openpyxl 寫一份：文字 '45.60' 配 0.00%、740 配 0_ "天"、正常數字配 0.00%"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws['A1'] = '45.60'
    ws['A1'].number_format = '0.00%'
    ws['A2'] = 740
    ws['A2'].number_format = '0_ "天"'
    ws['A3'] = 0.456
    ws['A3'].number_format = '0.00%'
    ws['A4'] = '第一聯'
    ws['A5'] = '258,923,496'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@tagged('post_install', '-at_install', 'dobtor_spreadsheet_editor')
class TestXlsxImportFidelity(TransactionCase):

    def test_header_footer_image_is_not_a_sheet_image(self):
        hf = x2w.extract_images(_xlsx_with_vml_image('legacyDrawingHF'))
        on_sheet = x2w.extract_images(_xlsx_with_vml_image('legacyDrawing'))
        self.assertEqual(hf, [], '頁首圖不能被當成貼在儲存格上的圖')
        # 對照組：同一份檔只換標籤，貼在表上的 VML 圖照樣要抓得到（不是整個 VML 都不讀了）
        self.assertEqual(len(on_sheet), 1)

    def test_number_formats(self):
        cases = {
            '0_ "天"': '0 "天"',
            '#,##0_);[Red]\\(#,##0\\)': '#,##0 ;\\(#,##0\\)',
            '"契約變更次數:第  "0"  次"': '"契約變更次數:第  "0"  次"',
            '[$NT$-404]#,##0': '"NT$"#,##0',
            '#,##0.00_ ': '#,##0.00 ',
            '0.00%': '0.00%',
            # o-spreadsheet 不認得／語意會變 → 不帶格式（照舊）
            '[$-404]e"年"m"月"d"日";@': None,
            '[>=100]0;0': None,
            '0.00E+00': None,
            '[h]:mm': None,
            'General': None,
        }
        for excel, expected in cases.items():
            with self.subTest(excel=excel):
                self.assertEqual(x2w._safe_format(excel), expected)

    def test_numeric_looking_text_stays_literal(self):
        base = self.env['spreadsheet.spreadsheet']._empty_spreadsheet_data()
        data, _log, _images = x2w.xlsx_bytes_to_workbook_data(_xlsx_with_cells(), base)
        cells = data['sheets'][0]['cells']
        # 文字 '45.60' 不能被當數字套 0.00%（會顯示 4560.00%）
        self.assertEqual(cells['A1']['format'], x2w.TEXT_FORMAT)
        self.assertEqual(cells['A5']['format'], x2w.TEXT_FORMAT)
        # 真的數字照樣套原本的格式
        self.assertEqual(cells['A2']['format'], '0 "天"')
        self.assertEqual(cells['A3']['format'], '0.00%')
        # 一般文字不加格式
        self.assertNotIn('format', cells['A4'])


@tagged('post_install', '-at_install', 'dobtor_spreadsheet_editor')
class TestAttachmentPreview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 一般內部帳號，刻意不在試算表群組（jt 只有 2 個帳號在群組裡）
        cls.internal = new_test_user(cls.env, login='xlsx_preview_internal',
                                     groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='xlsx_preview_portal',
                                   groups='base.group_portal')
        assert not cls.internal.has_group('spreadsheet_oca.group_user')
        partner = cls.env['res.partner'].create({'name': '預覽測試'})
        cls.att = cls.env['ir.attachment'].create({
            'name': '表單.xlsx', 'raw': _xlsx_with_cells(), 'mimetype': XLSX_MIMETYPE,
            'res_model': 'res.partner', 'res_id': partner.id,
        })

    def test_internal_user_gets_readonly_preview(self):
        att = self.att.with_user(self.internal)
        action = att.action_open_spreadsheet_preview()
        self.assertEqual(action['tag'], 'action_spreadsheet_oca')
        self.assertEqual(action['params'], {'spreadsheet_id': self.att.id, 'model': 'ir.attachment'})
        data = att.get_spreadsheet_data()
        self.assertEqual(data['mode'], 'readonly')
        self.assertEqual(data['revisions'], [])
        self.assertEqual(data['dobtor_preview']['download_url'],
                         '/web/content/%d?download=true' % self.att.id)
        self.assertEqual(data['spreadsheet_raw']['sheets'][0]['cells']['A4']['content'], '第一聯')
        # 唯讀模式下前端照樣會送協作訊息（CLIENT_JOINED…）：要有這個方法、而且一律不接受
        self.assertIs(att.send_spreadsheet_message({'type': 'CLIENT_JOINED'}), False)
        # 不留副本：預覽不建 spreadsheet.spreadsheet 記錄
        self.assertFalse(self.env['spreadsheet.spreadsheet'].search(
            [('source_filename', '=', '表單.xlsx')]))

    def test_access_follows_the_attachment(self):
        # 掛在一般內部帳號讀不到的單據上（系統參數只有管理員讀得到）
        param = self.env['ir.config_parameter'].search([], limit=1)
        hidden = self.env['ir.attachment'].create({
            'name': '機密.xlsx', 'raw': _xlsx_with_cells(), 'mimetype': XLSX_MIMETYPE,
            'res_model': 'ir.config_parameter', 'res_id': param.id,
        })
        with self.assertRaises(AccessError):
            hidden.with_user(self.internal).get_spreadsheet_data()
        with self.assertRaises(AccessError):
            hidden.with_user(self.internal).action_open_spreadsheet_preview()
        # 前台帳號一律不行（核心 ir.attachment.check）
        with self.assertRaises(AccessError):
            self.att.with_user(self.portal).get_spreadsheet_data()

    def test_zip_bomb_is_refused_before_parsing(self):
        # 一份壓縮後幾十 KB、宣稱解開超過上限的 xlsx：要在 openpyxl 讀之前就擋
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('xl/worksheets/sheet1.xml', b' ' * (x2w.MAX_UNZIPPED_XML_BYTES + 1))
        bomb = buf.getvalue()
        self.assertLess(len(bomb), 1024 * 1024)       # 檔案本身很小，PREVIEW_MAX_BYTES 擋不到
        with self.assertRaises(x2w.XlsxTooLarge):
            x2w.xlsx_bytes_to_workbook_data(bomb, {})
        att = self.env['ir.attachment'].create({
            'name': '炸彈.xlsx', 'raw': bomb, 'mimetype': XLSX_MIMETYPE})
        with self.assertRaisesRegex(UserError, '太大'):
            att.get_spreadsheet_data()

    def test_non_xlsx_and_broken_files(self):
        txt = self.env['ir.attachment'].create({'name': 'a.txt', 'raw': b'hello', 'mimetype': 'text/plain'})
        with self.assertRaises(UserError):
            txt.get_spreadsheet_data()
        broken = self.env['ir.attachment'].create({
            'name': '壞檔.xlsx', 'raw': b'not a zip', 'mimetype': XLSX_MIMETYPE})
        # 壞檔的細節記 ERROR log（給維運看）——用 assertLogs 接住，同時證明真的有記
        with self.assertLogs('odoo.addons.dobtor_spreadsheet_editor.models.ir_attachment', 'ERROR'), \
                self.assertRaisesRegex(UserError, '無法在瀏覽器預覽'):
            broken.get_spreadsheet_data()
