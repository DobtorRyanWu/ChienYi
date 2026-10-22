"""前台上傳證明文件的上限與檔名清洗（計畫 §4「證書與照片上傳」）。

會員能往伺服器塞東西的只有這條路徑，所以三道閘門都要有測試：
宣告長度（先擋 body 再讀）、實際長度、待審筆數；檔名一律清洗後才落地與進標頭。
"""

import base64
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.assoc_portal.controllers import portal

from .common import PASSWORD, PortalCase

PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQ'
    'AAAABJRU5ErkJggg==')
MAX_MB = 'odoo.addons.assoc_portal.controllers.portal.DOC_MAX_MB'


@tagged('post_install', '-at_install')
class TestDocumentUpload(HttpCase, PortalCase):

    def setUp(self):
        super().setUp()
        self.user = self.grant()
        self.activate()
        self.env.cr.flush()
        self.authenticate(self.user.login, PASSWORD)

    def upload(self, content=PNG_1PX, filename='cert.png', doc_type='photo'):
        # 證明文件的上傳表單在「我的資料」頁（會員專區已併進 /my）
        page = self.url_open('/my/assoc/profile')
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        return self.url_open(
            '/my/assoc/documents/upload',
            data={'csrf_token': csrf, 'doc_type': doc_type},
            files={'file': (filename, content, 'application/octet-stream')})

    def pending(self):
        return self.env['assoc.member.document'].sudo().search([
            ('member_id', '=', self.member.id)])

    def test_upload_creates_pending_document(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertIn('/my/assoc/profile?upload=ok', response.url, '上傳完回到「我的資料」頁')
        self.assertIn('已上傳，等候公會審核', response.text, '使用者要看得到結果')
        doc = self.pending()
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc.state, 'submitted')
        self.assertEqual(doc.submitted_via, 'portal')

    def test_upload_rejects_wrong_type(self):
        """副檔名說是 png、內容是文字 → 看內容判定。"""
        response = self.upload(content=b'<script>alert(1)</script>', filename='evil.png')
        self.assertIn('upload=bad_type', response.url)
        self.assertFalse(self.pending())

    def test_upload_rejects_oversized_content(self):
        """超過上限的檔案要擋掉（讀取本身有上限，不會把整個檔吃進來）。"""
        with patch(MAX_MB, 1):
            response = self.upload(content=b'x' * (1024 * 1024 + 1024))
        self.assertIn('upload=too_big', response.url)
        self.assertFalse(self.pending())

    def test_corrupt_image_is_rejected_without_500(self):
        """magic bytes 像 PNG、內容截斷的檔不能讓路由爆掉。

        `ir.attachment._check_contents` 會對圖片跑 Pillow（ir_attachment.py:345），
        截斷的檔丟 `OSError: Truncated File Read` 而 Odoo 沒接住 → 500。
        """
        response = self.upload(content=PNG_1PX[:40], filename='broken.png')
        self.assertEqual(response.status_code, 200, '不能是 500')
        self.assertIn('upload=bad_image', response.url)
        self.assertFalse(self.pending())

    def test_backend_also_refuses_corrupt_image(self):
        """後台與匯入不走 controller，所以模型自己也要擋。"""
        with self.assertRaises(ValidationError):
            self.env['assoc.member.document'].sudo().create({
                'member_id': self.member.id, 'doc_type': 'engineer_cert',
                'file': base64.b64encode(PNG_1PX[:40]), 'file_name': 'broken.png'})

    def test_upload_stops_at_pending_cap(self):
        for index in range(portal.MAX_PENDING_DOCS):
            self.env['assoc.member.document'].sudo().create({
                'member_id': self.member.id, 'doc_type': 'other',
                'file': base64.b64encode(PNG_1PX), 'file_name': 'p%s.png' % index})
        self.env.cr.flush()
        response = self.upload()
        self.assertIn('upload=too_many', response.url)
        self.assertEqual(len(self.pending()), portal.MAX_PENDING_DOCS)

    def test_filename_is_sanitised_before_storage_and_header(self):
        """檔名會進 Content-Disposition：CRLF 讓 werkzeug 丟 500，引號可以偽裝副檔名。"""
        self.upload(filename='../a"b\r\nX-Evil: 1.png')
        doc = self.pending()
        self.assertEqual(len(doc), 1)
        for bad in ('..', '"', '\r', '\n', '/'):
            self.assertNotIn(bad, doc.file_name)
        response = self.url_open('/my/assoc/documents/%s/file' % doc.id)
        self.assertEqual(response.status_code, 200)
        disposition = response.headers['Content-Disposition']
        self.assertIn('attachment', disposition)
        for bad in ('"b', '\r', '\n'):
            self.assertNotIn(bad, disposition)

    def test_download_sanitises_filename_from_other_sources(self):
        """下載端要自己清一次：前台上傳已經清過，但後台上傳與匯入沒有經過這條路。

        帶 CRLF 的檔名直接進 `Content-Disposition` 會讓 werkzeug 丟 500
        （標頭注入的擋法），引號則可以在下載對話框裡偽裝副檔名。
        """
        doc = self.env['assoc.member.document'].sudo().create({
            'member_id': self.member.id, 'doc_type': 'other',
            'file': base64.b64encode(PNG_1PX), 'file_name': 'ok.png'})
        self.env.cr.execute(
            'UPDATE assoc_member_document SET file_name = %s WHERE id = %s',
            ['a"b\r\nX-Evil: 1.png', doc.id])
        self.env.cr.flush()
        response = self.url_open('/my/assoc/documents/%s/file' % doc.id)
        self.assertEqual(response.status_code, 200, '髒檔名不能變成 500')
        disposition = response.headers['Content-Disposition']
        # 判準是「不能跳出引號、不能換行」；殘留的 X-Evil 只是引號內的普通文字
        for bad in ('"b', '\r', '\n'):
            self.assertNotIn(bad, disposition)
        self.assertNotIn('X-Evil', dict(response.headers), '不能被注入成另一個標頭')

    def test_chinese_filename_downloads(self):
        """中文檔名是這個市場的常態，不能讓下載整條連線掛掉。

        自己拼 `filename="..."` 的話，非 latin-1 的標頭值會在 WSGI 寫標頭時丟
        UnicodeEncodeError——用戶端拿到的是連線中斷，連 500 都沒有，監控看不出來。
        """
        self.upload(filename='技師證書.png')
        doc = self.pending()
        self.assertEqual(doc.file_name, '技師證書.png', '中文檔名要原樣留著')
        response = self.url_open('/my/assoc/documents/%s/file' % doc.id)
        self.assertEqual(response.status_code, 200)
        disposition = response.headers['Content-Disposition']
        # 標頭本身必須是 latin-1 可編碼的（WSGI 就是這樣序列化的）
        disposition.encode('latin-1')
        self.assertIn("filename*=UTF-8''", disposition)
