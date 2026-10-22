"""存取軌跡：不可改、不可刪、公會隔離、不記個資值。"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAuditLog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log = cls.env['assoc.audit.log']
        partner = cls.env['res.partner'].create({'name': '軌跡測試', 'company_id': cls.env.company.id})
        cls.member = cls.env['assoc.member'].create({'partner_id': partner.id, 'member_no': 'A001'})

    def test_log_records_actor_and_count(self):
        entry = self.log._log('reveal_pii', records=self.member)
        self.assertEqual(entry.create_uid, self.env.user)
        self.assertEqual(entry.res_model, 'assoc.member')
        self.assertEqual(entry.res_ids_text, str(self.member.id))
        self.assertEqual(entry.record_count, 1)
        self.assertEqual(entry.company_id, self.member.company_id)

    def test_immutable(self):
        entry = self.log._log('reveal_pii', records=self.member)
        with self.assertRaises(UserError):
            entry.action = 'export_pii'
        with self.assertRaises(UserError):
            entry.unlink()
        with self.assertRaises(UserError):
            entry.sudo().unlink()

    def test_staff_cannot_read(self):
        entry = self.log._log('reveal_pii', records=self.member)
        staff = self.env['res.users'].create({
            'name': '職員', 'login': 'assoc_staff_audit_test',
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_staff').id])],
        })
        with self.assertRaises(AccessError):
            entry.with_user(staff).read(['action'])

    def test_company_isolation(self):
        other_company = self.env['res.company'].create({'name': '他公會（軌跡測試）'})
        entry = self.log._log('reveal_pii', records=self.member, company=other_company)
        admin = self.env['res.users'].create({
            'name': '本公會管理員', 'login': 'assoc_admin_audit_test',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('assoc_base.group_assoc_admin').id])],
        })
        found = self.log.with_user(admin).search([('id', '=', entry.id)])
        self.assertFalse(found, '別的公會的軌跡看不到')
