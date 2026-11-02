"""「插入 Odoo 欄位」清單：一般內部帳號（含代操作員）要拿得到欄位。

原 bug：_get_fields_for_model 用使用者環境 search ir.model.fields，
該表一般帳號沒有讀權 → 清單空白。放行與拒絕都要驗：
模型範圍仍由目標模型的 check_access_rights('read') 決定。
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_doc_editor')
class TestAvailableFieldsAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        groups = [self.env.ref('base.group_user').id]
        # 代操作員群組在 construction_supervision_base（非本模組依賴），有裝才帶
        operator = self.env.ref(
            'construction_supervision_base.group_operator',
            raise_if_not_found=False)
        if operator:
            groups.append(operator.id)
        self.user = self.env['res.users'].create({
            'name': 'fields_operator',
            'login': 'fields_operator',
            'groups_id': [(6, 0, groups)],
        })

    def test_precondition_user_cannot_read_ir_model_fields(self):
        """前提：此帳號直接 search ir.model.fields 會被擋（否則測試恆真）。"""
        with self.assertRaises(AccessError):
            self.env['ir.model.fields'].with_user(self.user).search(
                [('model', '=', 'res.partner')], limit=1)

    def test_allowed_model_returns_nonempty_list(self):
        mixin = self.env['doc.render.mixin'].with_user(self.user)
        result = mixin.get_available_fields('res.partner')
        names = {f['name'] for f in result}
        self.assertIn('name', names)

    def test_model_without_read_access_still_denied(self):
        mixin = self.env['doc.render.mixin'].with_user(self.user)
        with self.assertRaises(AccessError) as cm:
            mixin.get_available_fields('ir.cron')
        self.assertIn('ir.cron', str(cm.exception))
