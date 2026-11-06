# -*- coding: utf-8 -*-
"""前台自主檢查依檢查類型的「結果欄位」畫按鈕、送勾選值（construction_quality self_inspection_mark.py）。

環境清潔表（是／否／不適用，只紀錄）：勾什麼、沒勾都通過；生態保育表（是／不足／否）：不足、否算缺失，
反向題（是否有民眾陳情）答「是」才是缺失。標準樣式的行為不變（沒送＝合格）。
"""

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

LEADER = 'construction_supervision_base.group_portal_leader'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalInspectionResultLayout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        # 夾具：前台主管是營造方帳號（範圍公司＝工程的承攬廠商）
        cls.contractor = make_contractor(cls.env, '前台結果欄位測試營造')
        cls.project = cls.env['project.project'].create({
            'name': '前台結果欄位測試', 'code': 'PM-LAYOUT', 'project_type': 'general',
            'state': 'construction', 'company_id': cls.env.company.id,
            **contractor_project_vals(cls.contractor)})
        cls.leader = cls.env['res.users'].create({
            'name': 'pl_leader', 'login': 'pl_leader',
            'groups_id': [(6, 0, [cls.env.ref(LEADER).id])],
            **contractor_user_vals(cls.contractor)})
        cls.env['supervision.project.member'].create(
            {'project_id': cls.project.id, 'user_id': cls.leader.id})
        Type, Item = cls.env['self.inspection.type'], cls.env['self.inspection.type.item']
        cls.t_rec = Type.create({'name': '環境清潔（測試）', 'result_layout': 'yes_no'})
        cls.t_eco = Type.create({'name': '生態保育（測試）', 'result_layout': 'yes_partial_no'})
        cls.t_std = Type.create({'name': '標準（測試）'})
        cls.rec_items = [Item.create({'type_id': cls.t_rec.id, 'name': n, 'sequence': s})
                         for s, n in ((10, '是否無積水'), (20, '是否有塵土外溢道路'))]
        cls.eco_items = [Item.create({'type_id': cls.t_eco.id, 'name': '保全物種保護', 'sequence': 10}),
                         Item.create({'type_id': cls.t_eco.id, 'name': '是否有民眾陳情', 'sequence': 20,
                                      'reverse_question': True})]
        cls.std_items = [Item.create({'type_id': cls.t_std.id, 'name': '鋼筋間距', 'sequence': 10})]

    def _get_items(self, itype):
        with MockRequest(self.env(user=self.leader)):
            return self.ctrl.portal_construction_inspection_get_items(type_id=itype.id)

    def _create(self, itype, type_items, results):
        post = {'project_id': str(self.project.id), 'inspection_type_id': str(itype.id),
                'inspection_date': str(fields.Date.today()), 'sub_project_name': itype.name}
        for idx, (ti, res) in enumerate(zip(type_items, results)):
            post['checklist_item_id_%d' % idx] = str(ti.id)
            if res is not None:
                post['checklist_result_%d' % idx] = res
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            self.ctrl.portal_construction_inspection_create(**post)
        insp = self.env['general.self.inspection'].search(
            [('project_id', '=', self.project.id), ('inspection_type_id', '=', itype.id)], order='id desc', limit=1)
        return insp, [insp.checklist_ids.filtered(lambda l: l.type_item_id == ti) for ti in type_items]

    def test_get_items_returns_layout_buttons(self):
        rec = self._get_items(self.t_rec)
        self.assertEqual(rec['layout'], 'yes_no')
        self.assertEqual([m['label'] for m in rec['marks']], ['是', '否', '不適用'])
        self.assertEqual({m['result'] for m in rec['marks']}, {'pass', 'na'})       # 只紀錄：沒有缺失
        eco = self._get_items(self.t_eco)
        self.assertEqual([m['label'] for m in eco['marks']], ['是', '不足', '否'])
        reverse = [i for i in eco['items'] if i['name'] == '是否有民眾陳情'][0]
        self.assertEqual([m['result'] for m in reverse['marks']], ['defect', 'defect', 'pass'])
        std = self._get_items(self.t_std)
        self.assertEqual((std['layout'], std['marks']), ('standard', []))

    def test_record_layout_passes_whatever_is_ticked(self):
        insp, (a, b) = self._create(self.t_rec, self.rec_items, ['no', None])
        self.assertEqual((a.mark, a.check_result), ('no', 'pass'))
        self.assertEqual((b.mark, b.check_result), (False, 'pass'))      # 沒勾也通過
        self.assertEqual((insp.has_defect, insp.overall_result), (False, 'pass'))

    def test_partial_layout_and_reverse_question(self):
        insp, (a, b) = self._create(self.t_eco, self.eco_items, ['partial', 'yes'])
        self.assertEqual((a.mark, a.check_result), ('partial', 'defect'))
        self.assertEqual((b.mark, b.check_result), ('yes', 'defect'))   # 反向題：有民眾陳情＝缺失
        self.assertEqual(insp.defect_count, 2)

    def test_forged_mark_is_ignored(self):
        # 不在這個樣式選項裡的值（例如標準樣式的 defect）當沒勾，不寫進去
        insp, (a, _b) = self._create(self.t_rec, self.rec_items, ['defect', 'yes'])
        self.assertEqual((a.mark, a.check_result), (False, 'pass'))

    def test_standard_layout_unchanged(self):
        insp, (a,) = self._create(self.t_std, self.std_items, [None])
        self.assertEqual((a.mark, a.check_result), (False, 'pass'))      # 原本就是沒送＝合格
        insp2, (b,) = self._create(self.t_std, self.std_items, ['defect'])
        self.assertEqual(b.check_result, 'defect')
