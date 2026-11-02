# -*- coding: utf-8 -*-
"""B12 — 預約式自主檢查建立缺失時要帶來源資訊（2026-11-02）。

原本只帶通報單與描述：缺失來源預設成「通報單」、發現人空白、
發現日期是建立當天（不是檢查日期）。比照一般式
construction_general/models/create_defect_wizard.py。
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged

INSPECTION_DATE = date(2026, 10, 15)


@tagged('post_install', '-at_install', 'construction_reservation')
class TestReservationDefectWizardSource(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'B12 預約式來源', 'code': 'B12-RSV',
            'project_type': 'reservation', 'company_id': cls.env.company.id})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'B12S', 'contractor_prefix': 'B12C'})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': 'B12 地點'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.itype = cls.env['self.inspection.type'].create({'name': 'B12 類型'})
        cls.inspector = cls.env['res.users'].create({
            'name': 'b12_inspector', 'login': 'b12_inspector'})
        cls.inspection = cls.env['reservation.self.inspection'].create({
            'slip_id': cls.slip.id,
            'inspection_type_id': cls.itype.id,
            'sub_project_name': 'B12 分項',
            'inspection_date': INSPECTION_DATE,
            'inspector_id': cls.inspector.id,
            'checklist_ids': [(0, 0, {
                'check_item': '鋼筋間距', 'check_result': 'defect',
                'actual_result': '偏大'})],
        })

    def test_wizard_defect_carries_source_info(self):
        wiz = self.env['create.reservation.defect.wizard'].create({
            'inspection_id': self.inspection.id,
            'record_type': 'supervision',
            'item_ids': [(6, 0, self.inspection.checklist_ids.ids)],
        })
        wiz.action_confirm()
        defect = self.inspection.checklist_ids.defect_improvement_id
        self.assertTrue(defect, '應建立缺失改善單')
        self.assertEqual(defect.source_type, 'self_inspection')
        self.assertEqual(defect.found_date, INSPECTION_DATE)
        self.assertEqual(defect.discovery_user_id, self.inspector)
