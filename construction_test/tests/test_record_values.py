# -*- coding: utf-8 -*-
"""檢(試)驗紀錄的「試驗項目及數據」子表（supervision.test.record.value）。

新北契約附表11「材料設備品質抽(查)驗紀錄表」要印每一項的合格值與試驗值，
所以加了子表（2026-10-25）。紀錄規則不會從母表繼承，母表在 jt 這種多家監造公司
共用的庫裡又是靠規則隔離的，所以子表自己要有公司隔離；前台沒有檢試驗填寫頁，
不給前台角色任何權限。
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

PORTAL_GROUPS = (
    'construction_supervision_base.group_portal_subscriber',
    'construction_supervision_base.group_portal_leader',
    'construction_supervision_base.group_portal_user',
    'construction_supervision_base.group_portal_viewer',
)


@tagged('post_install', '-at_install', 'construction_test')
class TestRecordValues(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': '甲監造公司（測試）'})
        cls.company_b = cls.env['res.company'].create({'name': '乙監造公司（測試）'})
        cls.user_a = cls.env['res.users'].create({
            'name': '甲公司後台', 'login': 'tr_value_a',
            'company_id': cls.company_a.id, 'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('construction_supervision_base.group_supervisor_admin').id])],
        })
        project_b = cls.env['project.project'].create({
            'name': '乙公司工程', 'code': 'TR-VAL-B', 'company_id': cls.company_b.id})
        standard_b = cls.env['supervision.test.standard'].create({
            'name': '混凝土抗壓強度', 'material': '預拌混凝土', 'project_id': project_b.id})
        cls.record_b = cls.env['supervision.test.record'].create({
            'project_id': project_b.id, 'standard_id': standard_b.id,
            'supplier_name': '乙預拌廠', 'test_report_no': 'R-115-001',
            'value_ids': [(0, 0, {'item_name': '抗壓強度', 'standard_value': '≥280 kgf/cm²',
                                  'test_value': '312 kgf/cm²'})],
        })

    def test_new_fields_stored(self):
        rec = self.record_b
        self.assertEqual((rec.supplier_name, rec.test_report_no), ('乙預拌廠', 'R-115-001'))
        self.assertEqual(rec.value_ids.mapped('test_value'), ['312 kgf/cm²'])
        self.assertEqual(rec.value_ids.company_id, self.company_b)

    def test_other_company_cannot_read_values(self):
        Value = self.env['supervision.test.record.value'].with_user(self.user_a)
        self.assertFalse(Value.search([('id', 'in', self.record_b.value_ids.ids)]))
        with self.assertRaises(AccessError):
            Value.browse(self.record_b.value_ids.ids).read(['test_value'])

    def test_portal_roles_have_no_access(self):
        Value = self.env['supervision.test.record.value']
        for xmlid in PORTAL_GROUPS:
            user = self.env['res.users'].create({
                'name': xmlid, 'login': 'tr_value_' + xmlid.rsplit('.', 1)[-1],
                'groups_id': [(6, 0, [self.env.ref(xmlid).id])]})
            self.assertFalse(Value.with_user(user).has_access('read'), xmlid)
