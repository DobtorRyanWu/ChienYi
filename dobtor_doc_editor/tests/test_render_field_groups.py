# -*- coding: utf-8 -*-
"""匯出／預覽的 Jinja 沙箱（_SafeRecordProxy）要守欄位的 groups。

2026-11-08 抗辯：代理直接 rec[name]，而非儲存的 compute 欄位讀取時 ORM 不檢查 groups，
所以 {{ user.totp_secret }}（groups=NO_ACCESS，compute 用 SQL 撈）在匯出時會印出匯出者的 TOTP 金鑰。
"""
from odoo.tests.common import TransactionCase, tagged, new_test_user


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestRenderFieldGroups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='render_groups_u', groups='base.group_user')

    def _render(self, expr):
        Doc = self.env['doc.document'].with_user(self.user)
        # 尾巴加 6*7：證明 Jinja 真的有跑（渲染失敗會原樣回傳，斷言就恆真）
        return Doc._render_template(expr + '|{{ 6*7 }}', self.user)

    def test_no_access_field_not_rendered(self):
        if 'totp_secret' not in self.env['res.users']._fields:
            self.skipTest('auth_totp 未安裝')
        self.env.cr.execute('UPDATE res_users SET totp_secret=%s WHERE id=%s',
                            ('JBSWY3DPEHPK3PXP', self.user.id))
        self.env.invalidate_all()
        self.assertEqual(self.user.sudo().totp_secret, 'JBSWY3DPEHPK3PXP', 'rig：金鑰要真的有值')
        out = self._render('{{ user.totp_secret }}{{ object.totp_secret }}')
        self.assertIn('|42', out)
        self.assertNotIn('JBSWY3DPEHPK3PXP', out)

    def test_plain_field_still_rendered(self):
        out = self._render('{{ object.login }}')
        self.assertEqual(out, 'render_groups_u|42')
