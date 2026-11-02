# -*- coding: utf-8 -*-
"""沒有 spreadsheet_oca.group_user 的內部帳號要能開估驗單。

原 bug：spreadsheet_count 的 compute 直接讀 spreadsheet_ids，帳號對
spreadsheet.spreadsheet 沒有 ACL → 整張估驗單打不開。
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'dobtor_spreadsheet_editor_chienyi')
class TestEstimateNoSpreadsheetGroup(TransactionCase):

    def setUp(self):
        super().setUp()
        project = self.env['project.project'].create({
            'name': '無試算表群組測試工程',
            'code': 'SSE-NOGRP',
            'company_id': self.env.company.id,
        })
        self.est = self.env['payment.estimate'].create({
            'project_id': project.id,
            'estimate_date': '2026-01-01',
        })
        # 掛一張關聯試算表，計數才有非零可驗
        self.env['spreadsheet.spreadsheet'].create({
            'name': 'linked', 'payment_estimate_id': self.est.id})
        sse_group = self.env.ref('spreadsheet_oca.group_user')
        self.user = self.env['res.users'].create({
            'name': 'no_sse_group',
            'login': 'no_sse_group',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('construction_supervision_base.group_operator').id,
            ])],
        })
        self.assertNotIn(sse_group, self.user.groups_id)

    def test_precondition_user_has_no_spreadsheet_acl(self):
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env['spreadsheet.spreadsheet'].with_user(self.user).search([])

    def test_spreadsheet_count_readable(self):
        est = self.est.with_user(self.user)
        self.assertEqual(est.spreadsheet_count, 1)

    def test_form_view_builds_and_hides_button(self):
        est = self.est.with_user(self.user)
        res = est.get_views([(False, 'form')])
        arch = res['views']['form']['arch']
        self.assertIn('spreadsheet_count', arch)
        self.assertNotIn('action_open_spreadsheets', arch)
        # 並且真的能讀表單用到的欄位
        est.read(['spreadsheet_count'])
