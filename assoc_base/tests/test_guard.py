"""守衛哨兵（§16 通則 1–2）。

要證明的事：
- RPC 送得進來的 context（JSON：True、字串…）不能當守衛通過。
- create 的守衛要驗「產出的紀錄」，不是驗傳進來的 vals——context 的 default_*
  與使用者自建的 ir.default 都會在 super().create() 內部補進初值。
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..tools import GUARD, check_created, guarded


@tagged('post_install', '-at_install')
class TestGuard(TransactionCase):

    def test_guarded_only_accepts_sentinel(self):
        env = self.env
        self.assertFalse(guarded(env, 'assoc_demo'))
        for forged in (True, 1, 'GUARD', '<assoc.GUARD>', {'x': 1}):
            # env(context=...) 才是 Environment 的用法（with_context 是 recordset 的）
            self.assertFalse(
                guarded(env(context={'assoc_demo': forged}), 'assoc_demo'),
                'RPC 送得進來的值不可以被當成哨兵：%r' % (forged,))
        self.assertTrue(guarded(env(context={'assoc_demo': GUARD}), 'assoc_demo'))

    def test_check_created_compares_result(self):
        partner = self.env['res.partner'].create({'name': '守衛測試', 'company_id': self.env.company.id})
        member = self.env['assoc.member'].create({
            'partner_id': partner.id, 'member_no': 'G001', 'active': True})
        # 初值相符 → 通過
        check_created(member, {'active': True}, 'assoc_demo')
        # 初值不符且沒有哨兵 → 擋下
        with self.assertRaises(ValidationError):
            check_created(member, {'active': False}, 'assoc_demo')
        # 帶哨兵 → 放行（系統自己的流程）
        check_created(member.with_context(assoc_demo=GUARD), {'active': False}, 'assoc_demo')

    def test_check_created_catches_context_default(self):
        """default_* 會在 super().create() 內部補值，只驗 vals 會漏掉。"""
        partner = self.env['res.partner'].create({'name': '預設值測試', 'company_id': self.env.company.id})
        member = self.env['assoc.member'].with_context(default_active=False).create({
            'partner_id': partner.id, 'member_no': 'G002'})
        self.assertFalse(member.active, '前提：default_* 確實改得動初值')
        with self.assertRaises(ValidationError):
            check_created(member, {'active': True}, 'assoc_demo')

    def test_check_created_catches_ir_default(self):
        """使用者自建的 ir.default 一樣會改初值（RPC 就能建）。"""
        self.env['ir.default'].set('assoc.member', 'active', False, user_id=self.env.uid)
        partner = self.env['res.partner'].create({'name': 'ir.default 測試', 'company_id': self.env.company.id})
        member = self.env['assoc.member'].create({'partner_id': partner.id, 'member_no': 'G003'})
        self.assertFalse(member.active, '前提：ir.default 確實改得動初值')
        with self.assertRaises(ValidationError):
            check_created(member, {'active': True}, 'assoc_demo')
