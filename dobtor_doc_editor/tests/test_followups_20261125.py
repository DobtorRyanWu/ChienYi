# -*- coding: utf-8 -*-
"""W5 乙組：大文件存檔與版本備註（I1、I2，2026-11-25）。

I1 超過 CONTENT_SIZE_THRESHOLD 的內容要建 ir.attachment；前台協作者（營造方）對附件沒有權限時存不了。
   修法（若重現）：附件建立／更新改用 sudo，且前面先確認呼叫者對這份文件有寫入權。
I2 版本備註（label）：版本清單 get_version_list 有回 label，版本面板（doc_version_panel.xml）有印；
   這裡只鎖住「清單回得出備註」，受限帳號看不到 chatter 的問題交回主對話決定（不在本檔處理）。
"""
import base64

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.dobtor_doc_editor.models.doc_document import CONTENT_SIZE_THRESHOLD

from .scope_fixture import scope_portal_as_contractor

# 比門檻多一點的內容（位元組 → 字元數：半形字元一字一位元組）
OVERSIZE_HTML = '<p>' + 'x' * (CONTENT_SIZE_THRESHOLD + 1024) + '</p>'


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestLargeDocumentSave(TransactionCase):

    def setUp(self):
        super().setUp()
        self.portal = new_test_user(
            self.env, login='doc_large_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal')
        scope_portal_as_contractor(self.env, self.portal)
        self.internal = new_test_user(
            self.env, login='doc_large_internal',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        self.stranger = new_test_user(
            self.env, login='doc_large_stranger',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal')
        scope_portal_as_contractor(self.env, self.stranger)
        self.doc = self.env['doc.document'].create({
            'name': '大文件', 'content_html': '<p>小</p>',
            'collaborator_ids': [(6, 0, [self.portal.id])]})

    def _assert_stored_as_attachment(self, doc):
        doc.invalidate_recordset()
        self.assertTrue(doc.is_large_document)
        self.assertTrue(doc.content_attachment_id)
        self.assertEqual(doc.get_content_html(), OVERSIZE_HTML)

    def test_i1_portal_collaborator_can_save_oversize_content(self):
        self.doc.with_user(self.portal).write({'content_html': OVERSIZE_HTML})
        self._assert_stored_as_attachment(self.doc)
        # 存完之後協作者自己也讀得回來（編輯器重開）
        self.assertEqual(self.doc.with_user(self.portal).get_content_html(), OVERSIZE_HTML)

    def test_i1_portal_collaborator_can_update_existing_large_content(self):
        self.doc.with_user(self.portal).write({'content_html': OVERSIZE_HTML})
        self.doc.with_user(self.portal).write({'content_html': OVERSIZE_HTML + '<p>再加</p>'})
        self.doc.invalidate_recordset()
        self.assertTrue(self.doc.get_content_html().endswith('<p>再加</p>'))

    def test_i1_internal_editor_can_save_oversize_content(self):
        self.doc.write({'collaborator_ids': [(4, self.internal.id)]})
        self.doc.with_user(self.internal).write({'content_html': OVERSIZE_HTML})
        self._assert_stored_as_attachment(self.doc)

    def test_i1_non_collaborator_still_cannot_write_large_content(self):
        """沒有這份文件寫入權的人，不可藉由附件 sudo 路徑寫進去。"""
        with self.assertRaises(AccessError):
            self.doc.with_user(self.stranger).write({'content_html': OVERSIZE_HTML})
        self.doc.invalidate_recordset()
        self.assertFalse(self.doc.is_large_document)
        self.assertEqual(self.doc.content_html, '<p>小</p>')

    def test_i1_non_collaborator_cannot_call_store_helper_directly(self):
        """附件輔助方法本身也要先確認寫入權（它可被 RPC 以外的程式呼叫）。"""
        with self.assertRaises(AccessError):
            self.doc.with_user(self.stranger)._store_content_as_attachment(OVERSIZE_HTML)
        self.assertFalse(self.doc.content_attachment_id)

    # ── I1 審查（2026-11-25）：sudo 只能用在這份文件自己的內容附件上 ──
    def _victim_attachment(self):
        """掛在內部編輯者讀不到的記錄上的附件（系統參數只有系統管理者讀得到）"""
        param = self.env['ir.config_parameter'].sudo().search([], limit=1)
        return self.env['ir.attachment'].sudo().create({
            'name': 'secret.txt', 'type': 'binary', 'datas': base64.b64encode('機密內容'.encode()),
            'res_model': 'ir.config_parameter', 'res_id': param.id})

    def test_i1_foreign_attachment_is_not_overwritten_via_sudo(self):
        """content_attachment_id 內部帳號寫得到：把它指到別的附件再存大文件，不可以用 sudo 覆寫那個附件。"""
        victim = self._victim_attachment()
        with self.assertRaises(AccessError):                       # 基準：直接寫那個附件本來就被拒
            victim.with_user(self.internal).write({'datas': base64.b64encode(b'x')})
        doc = self.env['doc.document'].with_user(self.internal).create({'name': '指到別的附件'})
        doc.write({'content_attachment_id': victim.id})
        doc.write({'content_html': OVERSIZE_HTML})
        victim.invalidate_recordset()
        self.assertEqual(base64.b64decode(victim.datas).decode(), '機密內容', '別的附件不可被覆寫')
        doc.invalidate_recordset()
        self.assertNotEqual(doc.sudo().content_attachment_id, victim, '大文件要另建自己的內容附件')
        self.assertEqual(doc.sudo().content_attachment_id.res_id, doc.id)
        self.assertEqual(doc.get_content_html(), OVERSIZE_HTML)

    def test_i1_foreign_attachment_is_not_read_via_sudo(self):
        """把 content_attachment_id 指到自己讀不到的附件，不可以經 get_content_html 用 sudo 讀出來。"""
        victim = self._victim_attachment()
        with self.assertRaises(AccessError):                       # 基準：直接讀那個附件本來就被拒
            victim.with_user(self.internal).read(['datas'])
        doc = self.env['doc.document'].with_user(self.internal).create({'name': '指到別的附件（讀）'})
        doc.write({'content_attachment_id': victim.id, 'is_large_document': True})
        doc.invalidate_recordset()
        with self.assertRaises(AccessError):
            doc.get_content_html()

    # ── I1 補審（2026-11-25）：複製大文件，副本要有自己的內容附件 ──
    def test_i1_copy_of_large_document_gets_own_attachment(self):
        """副本原本指到原文件的內容附件：前台協作者開副本被拒、改原文件會連副本一起變。"""
        self.doc.with_user(self.portal).write({'content_html': OVERSIZE_HTML})
        self.doc.invalidate_recordset()
        origin_attachment = self.doc.content_attachment_id
        copy = self.doc.copy({'name': '大文件（副本）'})
        copy.write({'collaborator_ids': [(6, 0, [self.portal.id])]})
        copy.invalidate_recordset()
        self.assertTrue(copy.content_attachment_id, '副本要有內容附件')
        self.assertNotEqual(copy.content_attachment_id, origin_attachment, '副本不可共用原文件的內容附件')
        self.assertEqual(copy.content_attachment_id.res_id, copy.id)
        # 前台協作者讀得到副本（編輯器打得開）
        self.assertEqual(copy.with_user(self.portal).get_content_html(), OVERSIZE_HTML)
        # 原文件再改，副本內容不變
        self.doc.write({'content_html': OVERSIZE_HTML + '<p>原文件再改</p>'})
        copy.invalidate_recordset()
        self.assertEqual(copy.get_content_html(), OVERSIZE_HTML)

    # ── I2 ──
    def test_i2_version_list_returns_label(self):
        # 版本由內部編輯者存（前台受限帳號連在 chatter 留訊息都被擋，見公司儀表板 restricted_mail）；
        # 清單是讀 versions_data，前台協作者讀得到備註
        self.doc.write({'collaborator_ids': [(4, self.internal.id)]})
        self.doc.with_user(self.internal).action_save_version(label='會議結論定稿')
        versions = self.doc.with_user(self.portal).get_version_list()
        self.assertEqual([v['label'] for v in versions], ['會議結論定稿'])
