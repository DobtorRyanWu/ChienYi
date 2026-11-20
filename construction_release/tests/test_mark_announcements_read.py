# -*- coding: utf-8 -*-
"""按「知道了」只能標已發布且有公告內容的版本（R2 low：呼叫端給的 id 原本不限範圍）。"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'release_mark_read')
class TestMarkAnnouncementsRead(TransactionCase):

    def setUp(self):
        super().setUp()
        Rel = self.env['construction.release']
        # 同時只能有一個草稿版本：先建兩個、立刻改成已發布，最後才建草稿
        self.published = Rel.create({'name': 'v9.9.1', 'announce_title': '公告', 'announce_body': '內容'})
        self.published.sudo().state = 'published'
        self.no_title = Rel.create({'name': 'v9.9.3'})
        self.no_title.sudo().state = 'published'
        self.draft = Rel.create({'name': 'v9.9.2', 'announce_title': '草稿公告', 'announce_body': '內容'})
        self.user = self.env.ref('base.user_admin')   # 要用啟用中的真實帳號（env.user 可能是停用的 OdooBot，read_user_ids 會濾掉它）

    def test_only_published_with_title_is_marked(self):
        Rel = self.env['construction.release'].with_user(self.user)
        Rel.mark_announcements_read([self.published.id, self.draft.id, self.no_title.id])
        self.assertIn(self.user, self.published.read_user_ids)            # 正常案例
        self.assertNotIn(self.user, self.draft.read_user_ids)             # 修前會失敗：草稿也被標
        self.assertNotIn(self.user, self.no_title.read_user_ids)
