# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：估驗日期要照順序核定，只留在一般式；預約式不檢查。

舊系統（EAGLE）只有一般式會檢查估驗日期有沒有被其他期別涵蓋
（後端 routes/payItem.js、前端 views/PC/PayRecord.vue「所選日期已被涵蓋在其他次估驗計價」）；
預約式的日期欄沒有綁任何檢查。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（PE-03）。
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_payment')
class TestEagleParityEstimateDate(TransactionCase):

    def _approved_later_estimate(self, project_type):
        project = self.env['project.project'].create({
            'name': '回復原版估驗 %s' % project_type, 'code': 'EP-PE-%s' % project_type.upper(),
            'project_type': project_type, 'state': 'construction', 'company_id': self.env.company.id})
        later = self.env['payment.estimate'].create({'project_id': project.id, 'estimate_date': fields.Date.today()})
        later.action_approve()
        self.assertEqual(later.state, 'approved', '前提：已經有一期日期較晚、已核定的估驗')
        return project

    def test_reservation_estimate_before_approved_one_allowed(self):
        project = self._approved_later_estimate('reservation')
        earlier = self.env['payment.estimate'].create({
            'project_id': project.id, 'estimate_date': fields.Date.today() - timedelta(days=10)})
        earlier.action_approve()
        self.assertEqual(earlier.state, 'approved')

    def test_general_estimate_before_approved_one_still_refused(self):
        project = self._approved_later_estimate('general')
        with self.assertRaises(UserError):
            self.env['payment.estimate'].create({
                'project_id': project.id, 'estimate_date': fields.Date.today() - timedelta(days=10)})
