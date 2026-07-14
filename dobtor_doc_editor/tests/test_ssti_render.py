"""SSTI 回歸測試 — doc.render.mixin._render_template 的真實渲染路徑。

背景：舊 test_jinja_sandbox.py 自建裸 SandboxedEnvironment 且 ctx 不含 object/user，
因此測不到真正的攻擊面。真實 _render_template 會把「活的 ORM record」以
object=record、user=env.user 餵進 Jinja globals，導致 {{ object.env.cr... }} /
{{ object.sudo()... }} 可穿透 sandbox 讀寫整庫（已用 live PoC 證實）。

本檔走真正的 _render_template，斷言：
  1) 惡意表達式無法讀出 database.secret（穿透即失敗）。
  2) 惡意表達式無法讀出 DB cursor 資訊（dbname）。
  3) 修復後正常 UX（object.<field>）仍可渲染，未回歸。
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestSSTIRender(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mixin = self.env['doc.render.mixin']
        # 以真實 record 當渲染對象（有 env、有欄位），模擬 object=record 的攻擊面
        self.record = self.env.user

    def test_secret_not_exfiltrated_via_sudo(self):
        """{{ object.env['ir.config_parameter'].sudo().get_param('database.secret') }}
        不得回傳真正的 database.secret。"""
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        payload = ("{{ object.env['ir.config_parameter']"
                   ".sudo().get_param('database.secret') }}")
        result = self.Mixin._render_template(payload, self.record)
        self.assertTrue(secret, "database.secret 應存在才有測試意義")
        self.assertNotIn(secret, result,
                         "SSTI：database.secret 透過 object.env.sudo() 被讀出")

    def test_db_cursor_not_reachable(self):
        """{{ object.env.cr.dbname }} 不得回傳實際 DB 名稱。"""
        dbname = self.env.cr.dbname
        result = self.Mixin._render_template("{{ object.env.cr.dbname }}", self.record)
        self.assertNotIn(dbname, result,
                         "SSTI：DB cursor（object.env.cr）可從 template 觸及")

    def test_user_env_not_reachable(self):
        """{{ user.env.cr.dbname }} 同樣不得穿透。"""
        dbname = self.env.cr.dbname
        result = self.Mixin._render_template("{{ user.env.cr.dbname }}", self.record)
        self.assertNotIn(dbname, result,
                         "SSTI：user.env 可從 template 觸及")

    def test_legit_field_access_still_works(self):
        """UX 護欄：object.<field> 正常渲染（修復不得破壞正常欄位替換）。"""
        result = self.Mixin._render_template("[{{ object.login }}]", self.record)
        self.assertEqual(result, "[%s]" % self.record.login,
                         "正常欄位 object.login 渲染回歸")
