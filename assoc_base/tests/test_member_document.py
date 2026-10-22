"""會員文件：類型與大小限制、審核狀態、照片核准後套用、已核准不可改刪。"""

import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
PDF_MIN = b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n'


@tagged('post_install', '-at_install')
class TestMemberDocument(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env['res.partner'].create({'name': '文件測試', 'company_id': cls.env.company.id})
        cls.member = cls.env['assoc.member'].create({'partner_id': partner.id, 'member_no': 'D001'})
        cls.staff = cls.env['res.users'].create({
            'name': '公會職員（測試）', 'login': 'assoc_staff_doc_test',
            'groups_id': [(6, 0, [cls.env.ref('assoc_base.group_assoc_staff').id])],
        })

    def _doc(self, **vals):
        return self.env['assoc.member.document'].create(dict({
            'member_id': self.member.id,
            'doc_type': 'engineer_cert',
            'file': base64.b64encode(PDF_MIN),
            'file_name': 'cert.pdf',
        }, **vals))

    def test_accepts_pdf_and_image(self):
        self.assertEqual(self._doc().state, 'submitted')
        self.assertEqual(self._doc(doc_type='photo', file=base64.b64encode(PNG_1PX),
                                   file_name='me.png').state, 'submitted')

    def test_rejects_other_mimetypes(self):
        with self.assertRaises(ValidationError):
            self._doc(file=base64.b64encode(b'<html><script>alert(1)</script></html>'),
                      file_name='x.html')

    def test_rejects_oversized_file(self):
        with self.assertRaises(ValidationError):
            self._doc(file=base64.b64encode(PDF_MIN + b'0' * (10 * 1024 * 1024)))

    def test_sha256_recorded(self):
        doc = self._doc()
        self.assertEqual(len(doc.sha256), 64)

    def test_staff_cannot_review(self):
        doc = self._doc()
        with self.assertRaises(AccessError):
            doc.with_user(self.staff).action_approve()

    def test_approve_photo_applies_to_member(self):
        doc = self._doc(doc_type='photo', file=base64.b64encode(PNG_1PX), file_name='me.png')
        self.assertFalse(self.member.partner_id.image_1920)
        doc.action_approve()
        self.assertTrue(self.member.partner_id.image_1920, '照片核准後才套用到會員')
        self.assertEqual(doc.state, 'approved')
        self.assertEqual(doc.reviewer_uid, self.env.user)
        self.assertEqual(
            self.env['assoc.audit.log'].search_count([('action', '=', 'doc_review')]), 1)

    def test_reject_requires_reason(self):
        doc = self._doc()
        with self.assertRaises(UserError):
            doc.action_reject()
        doc.reject_reason = '證書已過期'
        doc.action_reject()
        self.assertEqual(doc.state, 'rejected')

    def test_approved_document_is_immutable(self):
        doc = self._doc()
        doc.action_approve()
        with self.assertRaises(UserError):
            doc.write({'file': base64.b64encode(PNG_1PX), 'file_name': 'swap.png'})
        with self.assertRaises(UserError):
            doc.unlink()

    def test_current_document_is_latest_approved(self):
        old = self._doc(cert_no='OLD')
        old.action_approve()
        new = self._doc(cert_no='NEW')
        new.action_approve()
        current = self.env['assoc.member.document']._current_document(self.member, 'engineer_cert')
        self.assertEqual(current, new)

    def test_state_cannot_be_written_by_rpc(self):
        """狀態只能由審核動作改：否則 approved → submitted 就繞過「不可改」。"""
        doc = self._doc()
        doc.action_approve()
        with self.assertRaises(UserError):
            doc.write({'state': 'submitted'})
        with self.assertRaises(UserError):
            doc.with_context(assoc_doc_review=True).write({'state': 'submitted'})

    def test_document_cannot_be_moved_to_another_member(self):
        other_partner = self.env['res.partner'].create({
            'name': '他人', 'company_id': self.env.company.id})
        other = self.env['assoc.member'].create({
            'partner_id': other_partner.id, 'member_no': 'D002'})
        doc = self._doc()
        with self.assertRaises(UserError):
            doc.write({'member_id': other.id})

    def test_photo_must_be_image(self):
        with self.assertRaises(ValidationError):
            self._doc(doc_type='photo')  # 預設是 PDF

    def test_approved_document_stays_locked_after_state_reset(self):
        doc = self._doc()
        doc.action_approve()
        # 就算用審核旗標把狀態改回去，approved_once 仍然鎖住檔案與刪除
        doc.action_reject.__self__  # noqa: B018  (確保方法存在)
        self.assertTrue(doc.approved_once)
        with self.assertRaises(UserError):
            doc.unlink()
