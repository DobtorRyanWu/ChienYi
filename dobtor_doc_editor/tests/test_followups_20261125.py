# -*- coding: utf-8 -*-
"""W5 乙組：大文件存檔與版本備註（I1、I2，2026-11-25）。

I1 超過 CONTENT_SIZE_THRESHOLD 的內容要建 ir.attachment；前台協作者（營造方）對附件沒有權限時存不了。
   修法（若重現）：附件建立／更新改用 sudo，且前面先確認呼叫者對這份文件有寫入權。
I2 版本備註（label）：版本清單 get_version_list 有回 label，版本面板（doc_version_panel.xml）有印；
   這裡只鎖住「清單回得出備註」，受限帳號看不到 chatter 的問題交回主對話決定（不在本檔處理）。
"""
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

    # ── I2 ──
    def test_i2_version_list_returns_label(self):
        # 版本由內部編輯者存（前台受限帳號連在 chatter 留訊息都被擋，見公司儀表板 restricted_mail）；
        # 清單是讀 versions_data，前台協作者讀得到備註
        self.doc.write({'collaborator_ids': [(4, self.internal.id)]})
        self.doc.with_user(self.internal).action_save_version(label='會議結論定稿')
        versions = self.doc.with_user(self.portal).get_version_list()
        self.assertEqual([v['label'] for v in versions], ['會議結論定稿'])
