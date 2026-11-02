# -*- coding: utf-8 -*-
"""回歸測試 —— 代操作員（group_operator，非 admin）批次下載照片。

原始 bug：上傳精靈把附件改成 res_id=0，核心 ir.attachment.check() 對
res_id 為空的附件只讓建立者與 group_system 讀；下載精靈的 summary / 預覽 /
下載讀 attachment_id.file_size、.name 時，代操作員被擋，跳「存取錯誤」。
附件刻意由 superuser 建立（建立者 != 代操作員）。
"""
import base64

from odoo.tests.common import TransactionCase, tagged

PAYLOAD = b'x' * 300000  # 約 0.29 MB，total_size 才不會四捨五入成 0


@tagged('post_install', '-at_install', 'construction_photo')
class TestDownloadWizardOperator(TransactionCase):

    def setUp(self):
        super().setUp()
        project = self.env['project.project'].create({
            'name': '下載精靈代操測試工程',
            'code': 'DL-OP',
            'company_id': self.env.company.id,
        })
        att = self.env['ir.attachment'].create({
            'name': 'orphan_dl.jpg',
            'raw': PAYLOAD,
            'mimetype': 'image/jpeg',
            'res_model': 'supervision.photo',
            'res_id': 0,
        })
        self.photo = self.env['supervision.photo'].create({
            'project_id': project.id,
            'attachment_id': att.id,
        })
        self.project = project
        self.operator = self.env['res.users'].create({
            'name': 'dl_operator',
            'login': 'dl_operator',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('construction_supervision_base.group_operator').id,
            ])],
        })

    def _wizard(self):
        return self.env['supervision.photo.download.wizard'].with_user(
            self.operator).create({
                'project_id': self.project.id,
                'selected_photo_ids': [(6, 0, self.photo.ids)],
            })

    def test_precondition_operator_cannot_read_attachment(self):
        """前提：代操作員直接讀該附件確實會被擋（否則下面的測試是恆真）。"""
        att = self.photo.attachment_id.with_user(self.operator)
        with self.assertRaises(Exception) as cm:
            att.invalidate_recordset()
            att.file_size
        self.assertIn('ir.attachment', str(cm.exception))

    def test_summary_shows_count_and_size(self):
        wiz = self._wizard()
        self.assertEqual(wiz.photo_count, 1)
        self.assertGreater(wiz.total_size, 0)

    def test_preview_opens(self):
        action = self._wizard().action_preview()
        self.assertEqual(action['res_model'],
                         'supervision.photo.download.preview')

    def test_download_builds_zip_with_original_name(self):
        wiz = self._wizard()
        wiz.action_download()
        self.assertEqual(wiz.state, 'done')
        self.assertTrue(wiz.result_file)
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(
                base64.b64decode(wiz.result_file))) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 1)
            self.assertIn('orphan_dl', names[0])
            self.assertEqual(zf.read(names[0]), PAYLOAD)

    def test_result_and_reopen_actions_have_title(self):
        wiz = self._wizard()
        self.assertEqual(wiz._reopen()['name'], '批次下載照片')
        self.assertEqual(wiz._get_download_action()['name'], '批次下載照片')
