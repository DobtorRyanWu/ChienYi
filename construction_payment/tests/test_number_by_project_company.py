# -*- coding: utf-8 -*-
"""估驗請款、工作驗收的單號依工程所屬公司取號。

這兩種單原本沒有 create()，單號只靠欄位預設值（next_by_code，依目前公司）在開表單時取；
預設值改成「/」後由 create() 依工程的公司取號（ir.sequence._next_by_code_for_project）。
"""
from odoo.tests import TransactionCase, tagged

PADDING = 4
CLAIM_AMOUNT = 1000


@tagged('post_install', '-at_install', 'construction_payment')
class TestNumberByProjectCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env['res.company']
        cls.company_b = Company.create({'name': '請款單號測試 B 監造'})
        cls.contractor = Company.create({'name': '請款單號測試營造', 'company_type': 'contractor'})
        Seq = cls.env['ir.sequence']
        for code, prefix in (('payment.claim', 'CLM-B-'), ('work.acceptance', 'WA-B-')):
            Seq.create({'name': '單號測試 %s' % code, 'code': code, 'prefix': prefix,
                        'padding': PADDING, 'company_id': cls.company_b.id})
        cls.project_b = cls.env['project.project'].create({
            'name': '請款單號測試工程', 'code': 'CLM-NUM-B', 'project_type': 'general',
            'company_id': cls.company_b.id})

    def test_form_default_is_slash(self):
        self.assertEqual(self.env['payment.claim'].default_get(['name'])['name'], '/')
        self.assertEqual(self.env['work.acceptance'].default_get(['name'])['name'], '/')

    def test_claim_uses_project_company(self):
        claim = self.env['payment.claim'].create({
            'project_id': self.project_b.id, 'company_id': self.company_b.id,
            'claim_amount': CLAIM_AMOUNT})
        self.assertTrue(claim.name.startswith('CLM-B-'), claim.name)

    def test_work_acceptance_uses_project_company(self):
        acceptance = self.env['work.acceptance'].create({
            'project_id': self.project_b.id, 'contractor_company_id': self.contractor.id})
        self.assertTrue(acceptance.name.startswith('WA-B-'), acceptance.name)

    def test_explicit_name_is_kept(self):
        claim = self.env['payment.claim'].create({
            'project_id': self.project_b.id, 'company_id': self.company_b.id,
            'claim_amount': CLAIM_AMOUNT, 'name': '手動單號-001'})
        self.assertEqual(claim.name, '手動單號-001')
