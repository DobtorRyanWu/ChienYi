# -*- coding: utf-8 -*-
"""全工區的預約式自主檢查建缺失（2026-11-22，construction_quality 18.0.6.14.0）。

全工區的檢查沒有通報單；精靈以前只帶 inspection.slip_id，建出來的缺失會因為沒有通報單被擋。
現在帶工程與全工區：全工區的檢查 → 全工區的缺失；掛通報單的照舊掛同一張。
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_reservation')
class TestWholeSiteDefectWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '全工區精靈', 'code': 'WS-WIZ',
            'project_type': 'reservation', 'company_id': cls.env.company.id})
        cls.env['defect.improvement.prefix.config'].create({
            'project_id': cls.project.id,
            'supervision_prefix': 'WSS', 'contractor_prefix': 'WSC'})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.project.id, 'location': '全工區精靈地點'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.itype = cls.env['self.inspection.type'].create({'name': '全工區精靈類型'})

    def _insp(self, **kw):
        vals = {'inspection_type_id': self.itype.id, 'sub_project_name': '全工區精靈',
                'inspection_date': date(2026, 11, 22),
                'checklist_ids': [(0, 0, {'check_item': '護欄', 'check_result': 'defect'})]}
        vals.update(kw)
        return self.env['reservation.self.inspection'].create(vals)

    def _run_wizard(self, insp):
        self.env['create.reservation.defect.wizard'].create({
            'inspection_id': insp.id, 'record_type': 'supervision',
            'item_ids': [(6, 0, insp.checklist_ids.ids)],
        }).action_confirm()
        return insp.checklist_ids.defect_improvement_id

    def test_whole_site_inspection_makes_whole_site_defect(self):
        insp = self._insp(project_id=self.project.id, is_whole_site=True)
        defect = self._run_wizard(insp)
        self.assertTrue(defect)
        self.assertTrue(defect.is_whole_site)
        self.assertFalse(defect.slip_id)
        self.assertEqual(defect.project_id, self.project)

    def test_slip_inspection_keeps_slip(self):
        insp = self._insp(slip_id=self.slip.id)
        defect = self._run_wizard(insp)
        self.assertFalse(defect.is_whole_site)
        self.assertEqual(defect.slip_id, self.slip)
