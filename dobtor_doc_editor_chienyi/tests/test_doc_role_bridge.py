# -*- coding: utf-8 -*-
"""ChienYi 角色 → dobtor 文件群組 橋接（security/doc_role_bridge.xml）測試。

驗證 implied_ids cascade：
- 前台主動角色（現場人員/主管/老闆）取得 group_doc_portal；唯讀 viewer 不取得。
- 內部角色（代操/系統管理者）取得 group_doc_editor。
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor', 'dobtor_doc_editor_chienyi')
class TestDocRoleBridge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.g_doc_portal = ref('dobtor_doc_editor.group_doc_portal')
        cls.g_doc_editor = ref('dobtor_doc_editor.group_doc_editor')
        cls.g_viewer = ref('construction_supervision_base.group_portal_viewer')
        cls.g_user = ref('construction_supervision_base.group_portal_user')
        cls.g_leader = ref('construction_supervision_base.group_portal_leader')
        cls.g_subscriber = ref('construction_supervision_base.group_portal_subscriber')
        cls.g_supervisor_admin = ref('construction_supervision_base.group_supervisor_admin')
        cls.g_operator = ref('construction_supervision_base.group_operator')

    # ─── 前台主動角色取得 group_doc_portal（cascade 自 group_portal_user）───

    def test_portal_user_implies_doc_portal(self):
        self.assertIn(self.g_doc_portal, self.g_user.trans_implied_ids,
                      "現場人員應 implied group_doc_portal")

    def test_leader_and_subscriber_inherit_doc_portal(self):
        self.assertIn(self.g_doc_portal, self.g_leader.trans_implied_ids,
                      "主管應 cascade 取得 group_doc_portal")
        self.assertIn(self.g_doc_portal, self.g_subscriber.trans_implied_ids,
                      "老闆應 cascade 取得 group_doc_portal")

    # ─── 唯讀 viewer 刻意被排除（避免取得寫入權）─────────────────────

    def test_viewer_excluded_from_doc_portal(self):
        self.assertNotIn(self.g_doc_portal, self.g_viewer.trans_implied_ids,
                         "定期閱覽者（唯讀）不應取得含寫入權的 group_doc_portal")

    # ─── 內部角色取得 group_doc_editor（cascade 自 group_supervisor_admin）───

    def test_supervisor_admin_implies_doc_editor(self):
        self.assertIn(self.g_doc_editor, self.g_supervisor_admin.trans_implied_ids,
                      "系統管理者應 implied group_doc_editor")

    def test_operator_inherits_doc_editor(self):
        self.assertIn(self.g_doc_editor, self.g_operator.trans_implied_ids,
                      "代操應 cascade 取得 group_doc_editor")
