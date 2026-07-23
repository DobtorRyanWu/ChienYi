# -*- coding: utf-8 -*-
"""/my 首頁「我的文件」counter 的權限保護測試。

Bug：`_get_documents_domain_count` 直接 search_count(doc.document)，
缺 group_doc_portal 的前台帳號一觸發 /my/counters 的 doc_count 就拋 AccessError，
整個 /my 首頁 counter 掛掉。

修法：counter 先 check_access_rights('read', raise_exception=False)，無權限回 0。
本測試同時證明 (a) bug 條件真的存在（未保護的 search_count 會爆），
(b) controller 有保護（/my/counters 回 doc_count=0，不噴錯）。
"""

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestPortalHomeDocCounter(HttpCase):

    def test_doc_count_without_access_returns_zero(self):
        """只有 base.group_portal（無任何文件群組）的帳號：
        - 直接 search_count 會拋 AccessError（重現 bug 根因）
        - /my/counters 的 doc_count 回 0、不 500（證明 guard 生效）
        """
        user = new_test_user(
            self.env,
            login='dobtor_counter_noacc',
            password='dobtor_counter_noacc',
            groups='base.group_portal',
        )

        # (a) 根因：這種帳號在 model ACL 層就被擋，未保護的 search_count 會爆
        with self.assertRaises(AccessError):
            self.env['doc.document'].with_user(user).search_count([])

        # (b) guard：透過真實 /my/counters JSON 路由取 doc_count，應 graceful 回 0
        self.authenticate('dobtor_counter_noacc', 'dobtor_counter_noacc')
        resp = self.opener.post(
            f"{self.base_url()}/my/counters",
            json={
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {'counters': ['doc_count']},
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn('error', body,
                         f"/my/counters 不該回 error（guard 應吞掉 AccessError）: {body}")
        self.assertEqual(body.get('result', {}).get('doc_count'), 0,
                         "缺文件群組的帳號 doc_count 應為 0")

    def test_doc_count_with_access_counts_collaborator_docs(self):
        """有 group_doc_portal 的帳號：doc_count 反映自己被邀為協作者的文件數。"""
        owner = new_test_user(
            self.env,
            login='dobtor_counter_owner',
            groups='dobtor_doc_editor.group_doc_editor,base.group_user',
        )
        portal = new_test_user(
            self.env,
            login='dobtor_counter_portal',
            password='dobtor_counter_portal',
            groups='dobtor_doc_editor.group_doc_portal,base.group_portal',
        )
        Doc = self.env['doc.document']
        doc_invited = Doc.with_user(owner).create({
            'name': '受邀文件', 'content_html': '<p>x</p>',
        })
        Doc.with_user(owner).create({
            'name': '未受邀文件', 'content_html': '<p>y</p>',
        })
        doc_invited.collaborator_ids = [(4, portal.id)]

        self.authenticate('dobtor_counter_portal', 'dobtor_counter_portal')
        resp = self.opener.post(
            f"{self.base_url()}/my/counters",
            json={
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {'counters': ['doc_count']},
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get('result', {}).get('doc_count'), 1,
                         "只應計入被邀為協作者的 1 份文件")
