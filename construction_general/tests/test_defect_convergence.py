# -*- coding: utf-8 -*-
"""M4-b 回歸測試 — 自主檢查「建立缺失」精靈改建 supervision.defect（一般式唯一模型）。

原本 create_defect_wizard 建 general.defect.improvement（已淘汰、資料已清）。收斂後應建
supervision.defect，並把來源自主檢查/檢查項欄位帶上、item 反向連 supervision_defect_id。
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_general')
class TestDefectConvergence(TransactionCase):

    def test_wizard_creates_supervision_defect(self):
        project = self.env['project.project'].create({
            'name': 'M4-b 收斂測試工程', 'code': 'M4B-CONV',
            'state': 'construction', 'company_id': self.env.company.id,
        })
        itype = self.env['self.inspection.type'].search([], limit=1)
        insp = self.env['general.self.inspection'].create({
            'name': 'INSP-M4B', 'project_id': project.id,
            'inspection_type_id': itype.id, 'sub_project_name': '子項',
            'inspection_date': fields.Date.today(),
        })
        item = self.env['general.self.inspection.item'].create({
            'inspection_id': insp.id, 'check_item': '牆面',
            'check_result': 'defect', 'actual_result': '裂縫',
        })

        wiz = self.env['create.defect.improvement.wizard'].create({
            'inspection_id': insp.id, 'record_type': 'supervision',
            'item_ids': [(6, 0, [item.id])],
        })
        wiz.action_confirm()

        # 建的是 supervision.defect（非 general），且雙向連結 + 來源欄位帶上
        self.assertTrue(item.supervision_defect_id,
                        'M4-b：檢查項未連到 supervision.defect')
        d = item.supervision_defect_id
        self.assertEqual(d._name, 'supervision.defect')
        self.assertEqual(d.self_inspection_id, insp)
        self.assertEqual(d.self_inspection_item_id, item)
        self.assertEqual(d.source, 'self_inspection')
        self.assertEqual(d.record_type, 'supervision')
        self.assertEqual(d.description, '[牆面] 裂縫')
        # inspection 的關聯缺失 One2many 也指向它
        self.assertIn(d, insp.defect_improvement_ids)
        # general.defect.improvement 完全沒被建
        self.assertEqual(
            self.env['general.defect.improvement'].search_count(
                [('project_id', '=', project.id)]), 0,
            'M4-b：不應再建 general.defect.improvement')

    def test_wizard_skips_already_created(self):
        """已連 supervision_defect_id 的項目不重複建。"""
        project = self.env['project.project'].create({
            'name': 'M4-b skip', 'code': 'M4B-SKIP',
            'state': 'construction', 'company_id': self.env.company.id,
        })
        itype = self.env['self.inspection.type'].search([], limit=1)
        insp = self.env['general.self.inspection'].create({
            'name': 'INSP2', 'project_id': project.id,
            'inspection_type_id': itype.id, 'sub_project_name': 's',
            'inspection_date': fields.Date.today(),
        })
        item = self.env['general.self.inspection.item'].create({
            'inspection_id': insp.id, 'check_item': 'x',
            'check_result': 'defect', 'actual_result': 'y',
        })
        wiz = self.env['create.defect.improvement.wizard'].create({
            'inspection_id': insp.id, 'record_type': 'supervision',
            'item_ids': [(6, 0, [item.id])]})
        wiz.action_confirm()
        first = item.supervision_defect_id
        # 再跑一次同項目 → 已建立，應 raise（不重複）
        wiz2 = self.env['create.defect.improvement.wizard'].create({
            'inspection_id': insp.id, 'record_type': 'supervision',
            'item_ids': [(6, 0, [item.id])]})
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            wiz2.action_confirm()
        self.assertEqual(item.supervision_defect_id, first)
