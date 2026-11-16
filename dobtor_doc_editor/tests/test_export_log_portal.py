# -*- coding: utf-8 -*-
"""前台帳號讀不到匯出紀錄 doc.editor.export.log（2026-11-16）。

背景：匯出紀錄是後台稽核資料（誰在何時匯出哪份文件、檔案大小、匯出當下綁定的「模型,id」），
前台文件協作者群組（group_doc_portal）卻有讀取 ACL、又沒有任何 ir.rule
→ 前台帳號經 RPC（/web/dataset/call_kw）讀得到全庫每個人的匯出紀錄。
寫紀錄一律走 record_export() 的 sudo，前台沒有任何畫面要讀它，所以前台讀取權直接收回
（ACL 那一列改成 0,0,0,0，與 error_log／perf_metric 的前台列「不給讀」同一風格）。

裝了公司儀表板的庫：營造方前台帳號本來就被範圍規則擋（不在白名單的模型全拒）；
監造方前台帳號走核心規則——洞在那裡，所以這裡的前台帳號是監造方（沒有那個欄位的庫就是一般前台帳號）。
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

EXPORT_LOG = 'doc.editor.export.log'
# 測試用的檔案大小（bytes），只用來確認紀錄有寫進去
FAKE_FILE_SIZE = 1024


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestExportLogPortalAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        Users = self.env['res.users']
        # 監造方前台帳號（不被公司儀表板的營造方範圍規則擋，走的是核心規則）
        side_vals = {'is_supervision_org': True} if 'is_supervision_org' in Users._fields else {}
        self.portal = new_test_user(
            self.env, login='exportlog_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal', **side_vals)
        self.internal = new_test_user(
            self.env, login='exportlog_internal',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user')
        self.doc = self.env['doc.document'].create({
            'name': '匯出紀錄測試文件', 'content_html': '<p>x</p>',
            'collaborator_ids': [(6, 0, [self.portal.id])]})
        # 別人（內部帳號）的一筆匯出紀錄
        self.others_log = self.env[EXPORT_LOG].with_user(self.internal).record_export(
            self.doc, 'pdf', with_alias=False, file_size=FAKE_FILE_SIZE, source='editor')

    def test_portal_cannot_read_export_logs(self):
        """前台帳號經 RPC 讀不到匯出紀錄（含別人的）。"""
        self.assertTrue(self.others_log, '前提：別人的匯出紀錄有寫進去')
        self.assertTrue(self.portal.share, '前提：測試帳號是前台帳號')
        self.env.invalidate_all()
        self.assertFalse(self.others_log.with_user(self.portal).has_access('read'),
                         '前台帳號不可讀別人的匯出紀錄')
        with self.assertRaises(AccessError):
            self.env[EXPORT_LOG].with_user(self.portal).search_read([], ['record_ref', 'user_id'])

    def test_portal_export_still_records_log(self):
        """正當入口：前台協作者匯出照常留紀錄（record_export 以 sudo 寫，不靠前台的權限）；後台照常讀。"""
        log = self.env[EXPORT_LOG].with_user(self.portal).record_export(
            self.doc, 'docx', with_alias=False, file_size=FAKE_FILE_SIZE, source='editor')
        self.assertTrue(log, 'record_export 失敗會吞例外回 False——前台匯出不可因此少一筆紀錄')
        self.assertEqual(self.env[EXPORT_LOG].search_count([('user_id', '=', self.portal.id)]), 1)
        self.assertTrue(self.others_log.with_user(self.internal).has_access('read'),
                        '後台內部帳號照常讀得到匯出紀錄（稽核選單）')
