# -*- coding: utf-8 -*-
"""檢查類型的「結果欄位」（models/self_inspection_mark.py，2026-10-28 新北契約檢查表）。

使用者裁示：
- 工地環境清潔及交通維持安全措施檢查表：勾什麼、沒勾都算通過（表上有反著問的題目，照實勾）。
- 生態保育措施自主檢查表：是／不足／否，「不足」「否」算缺失，但不擋勾選、不擋列印、也不擋結案。
既有的 check_result 語意不變——缺失精靈、報表、通報單合格率都讀它，所以由勾選換算出來。
"""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_quality')
class TestResultLayout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '結果欄位測試', 'code': 'QA-LAYOUT',
            'project_type': 'general', 'company_id': cls.env.company.id})
        Type = cls.env['self.inspection.type']
        cls.t_std = Type.create({'name': '標準'})
        cls.t_rec = Type.create({'name': '環境清潔', 'result_layout': 'yes_no'})
        cls.t_eco = Type.create({'name': '生態保育', 'result_layout': 'yes_partial_no',
                                 'allow_close_with_defect': True})
        # 預約式檢查要掛通報單（比照 dobtor_doc_editor_chienyi 測試的建法）
        cls.res_project = cls.env['project.project'].create({
            'name': '結果欄位測試（預約式）', 'code': 'QA-LAYOUT-R',
            'project_type': 'reservation', 'company_id': cls.env.company.id})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.res_project.id, 'location': '結果欄位測試地點'})
        cls.slip.sudo().write({'state': 'in_progress'})

    def _insp(self, itype, model='general.self.inspection'):
        vals = {'inspection_type_id': itype.id, 'inspection_date': fields.Date.today(),
                'sub_project_name': '結果欄位測試'}
        if model == 'general.self.inspection':
            vals.update(project_id=self.project.id, name='QA-LAYOUT')
        else:
            vals.update(slip_id=self.slip.id)
        insp = self.env[model].create(vals)
        insp.checklist_ids.unlink()
        return insp

    def _item(self, insp, model, **vals):
        return self.env[model].create(dict({'inspection_id': insp.id, 'check_item': '題目'}, **vals))

    def test_record_layout_always_passes(self):
        insp = self._insp(self.t_rec)
        Item = 'general.self.inspection.item'
        items = [self._item(insp, Item, mark=m) for m in ('yes', 'no', 'na', False)]
        self.assertEqual([i.check_result for i in items], ['pass', 'pass', 'na', 'pass'])
        self.assertEqual((insp.defect_count, insp.has_defect, insp.overall_result), (0, False, 'pass'))
        # 改勾選也照換算（「否」不會變成缺失）
        items[0].write({'mark': 'no'})
        self.assertEqual((items[0].check_result, insp.overall_result), ('pass', 'pass'))

    def test_partial_layout_counts_defects(self):
        insp = self._insp(self.t_eco)
        Item = 'general.self.inspection.item'
        yes, partial, no, blank = (self._item(insp, Item, mark=m) for m in ('yes', 'partial', 'no', False))
        self.assertEqual([i.check_result for i in (yes, partial, no, blank)], ['pass', 'defect', 'defect', False])
        self.assertEqual((insp.defect_count, insp.overall_result), (2, 'fail'))
        partial.write({'mark': 'yes'})
        self.assertEqual((partial.check_result, insp.defect_count), ('pass', 1))

    def test_standard_layout_unchanged(self):
        insp = self._insp(self.t_std)
        item = self._item(insp, 'general.self.inspection.item', check_result='defect')
        item.write({'mark': 'yes'})          # 標準樣式不換算：勾選欄沒有作用
        self.assertEqual(item.check_result, 'defect')
        self.assertEqual(insp.overall_result, 'fail')

    def test_reservation_items_follow_layout(self):
        insp = self._insp(self.t_eco, 'reservation.self.inspection')
        item = self._item(insp, 'reservation.self.inspection.item', mark='partial')
        self.assertEqual((item.check_result, insp.has_defect), ('defect', True))
        insp2 = self._insp(self.t_rec, 'reservation.self.inspection')
        item2 = self._item(insp2, 'reservation.self.inspection.item', mark='no')
        self.assertEqual((item2.check_result, insp2.has_defect), ('pass', False))

    def _close(self, insp):
        insp.action_inspect()
        insp.action_confirm()
        insp.action_close()

    def test_close_with_defect_only_when_allowed(self):
        eco = self._insp(self.t_eco)
        self._item(eco, 'general.self.inspection.item', mark='no')
        self._close(eco)
        self.assertEqual(eco.state, 'closed')
        std = self._insp(self.t_std)
        self._item(std, 'general.self.inspection.item', check_result='defect')
        with self.assertRaises(UserError):
            self._close(std)

    def test_default_items_follow_layout(self):
        # 從類型預設項目載入（前台建立走這條）：紀錄型沒勾算通過，是不足否沒勾沒有結果
        for itype, want in ((self.t_rec, 'pass'), (self.t_eco, False)):
            self.env['self.inspection.type.item'].create({'type_id': itype.id, 'name': '預設題'})
            insp = self.env['general.self.inspection'].create({
                'project_id': self.project.id, 'name': 'QA-LOAD', 'inspection_type_id': itype.id,
                'sub_project_name': itype.name, 'inspection_date': fields.Date.today()})
            if not insp.checklist_ids:
                insp.action_load_default_items()
            self.assertEqual(insp.checklist_ids.mapped('check_result'), [want], itype.name)

    def test_reverse_question_flips_the_judgement(self):
        # 生態保育表「其他」：是否有民眾陳情——答「是」才是有狀況；勾選照實記，換算反過來
        q = self.env['self.inspection.type.item'].create(
            {'type_id': self.t_eco.id, 'name': '是否有民眾陳情', 'reverse_question': True})
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'name': 'QA-REV', 'inspection_type_id': self.t_eco.id,
            'sub_project_name': '生態保育', 'inspection_date': fields.Date.today()})
        if not insp.checklist_ids:
            insp.action_load_default_items()
        item = insp.checklist_ids.filtered(lambda i: i.type_item_id == q)
        item.write({'mark': 'yes'})
        self.assertEqual(item.check_result, 'defect')
        item.write({'mark': 'no'})
        self.assertEqual(item.check_result, 'pass')
        # 紀錄型不判定：反向題照樣通過
        q2 = self.env['self.inspection.type.item'].create(
            {'type_id': self.t_rec.id, 'name': '是否有塵土外溢道路', 'reverse_question': True})
        rec = self._insp(self.t_rec)
        it2 = self._item(rec, 'general.self.inspection.item', type_item_id=q2.id, mark='yes')
        self.assertEqual(it2.check_result, 'pass')
