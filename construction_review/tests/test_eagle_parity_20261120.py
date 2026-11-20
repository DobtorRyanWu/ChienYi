# -*- coding: utf-8 -*-
"""回復原版（1118 會議）：送審管制裡舊系統沒有的限制拿掉後，這些動作要做得成。

舊系統（EAGLE）的送審沒有狀態欄位，刪除鈕連確認視窗都沒有
（後端 routes/reviewApplication.js DELETE 直接刪、前端 views/PC/ReviewApplications.vue）。
對照清單：odoo18-docker/docs/新舊系統限制差異_20261120.md（RV-01、RV-04）。
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_review')
class TestEagleParityReview(TransactionCase):

    def _project(self, state):
        return self.env['project.project'].create({
            'name': '回復原版送審 %s' % state, 'code': 'EP-RV-%s' % state.upper(), 'project_type': 'general',
            'state': state, 'company_id': self.env.company.id})

    def _review(self, project):
        return self.env['supervision.review.application'].create({'name': '回復原版測試材料', 'project_id': project.id})

    def test_done_review_can_be_deleted(self):
        """RV-01：已完成的送審記錄可以直接刪。"""
        review = self._review(self._project('construction'))
        review.action_done()
        self.assertEqual(review.state, 'done', '前提：送審已完成')
        review.unlink()
        self.assertFalse(review.exists())
