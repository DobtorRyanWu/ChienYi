# -*- coding: utf-8 -*-
"""本庫主公司不算營造廠（合約 §0b-27；線 F2 乾淨庫全模組測試實測）。

公司類型的預設值是「施工廠商」（construction_supervision_base/models/res_company.py，18.0 既有），
新庫的 1 號公司（base.main_company）一開始就是施工廠商。判定「主要公司是營造廠＝營造方」（§0b-5）若不排除主公司，
裝上儀表板後所有主要公司是 1 號公司的帳號（含管理員、監造人員）都被當成營造方、什麼都看不到——乾淨庫上候選 126 支紅、基準 0 支。

鎖住：主公司被設成施工廠商時，
1. 主要公司是主公司、沒有其他營造標記的內部帳號：不是營造方、是監造方，看得到全部工程；
2. 建帳號不把範圍公司預帶成主公司；範圍公司不能設成主公司；
3. 對照：主要公司是另一家營造廠的帳號仍是營造方（排除只限主公司，不是把這條判定拿掉）。
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

COMPANY_TYPE_CONTRACTOR = 'contractor'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestMainCompanyNotContractor(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.main = env.ref('base.main_company')
        # 模擬新庫：主公司是預設的施工廠商
        cls.main.write({'company_type': COMPANY_TYPE_CONTRACTOR})
        cls.other_contractor = env['res.company'].create({'name': 'DASH 主公司測試 營造', 'company_type': COMPANY_TYPE_CONTRACTOR})
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.staff = Users.create({
            'name': 'dash_main_staff', 'login': 'dash_main_staff',
            'groups_id': [(6, 0, [env.ref('base.group_user').id])],
            'company_id': cls.main.id, 'company_ids': [(6, 0, cls.main.ids)]})
        cls.contractor_staff = Users.create({
            'name': 'dash_main_ctr', 'login': 'dash_main_ctr',
            'groups_id': [(6, 0, [env.ref('base.group_user').id])],
            'company_id': cls.other_contractor.id,
            'company_ids': [(6, 0, (cls.main | cls.other_contractor).ids)]})
        cls.project = env['project.project'].create({
            'name': 'DASH 主公司測試工程', 'code': 'DASH-MAIN', 'project_type': 'general', 'company_id': cls.main.id})

    def test_main_company_user_is_supervision_side(self):
        self.assertFalse(self.staff._dash_is_contractor_side(), '主要公司是主公司的帳號不可被當成營造方')
        self.assertTrue(self.staff._is_supervision_side())
        seen = self.env['project.project'].with_user(self.staff).search([('id', '=', self.project.id)])
        self.assertEqual(seen, self.project, '監造方看得到主公司的工程（不被範圍規則收窄）')

    def test_other_contractor_still_contractor_side(self):
        self.assertTrue(self.contractor_staff._dash_is_contractor_side(), '別家營造廠的帳號仍是營造方')
        self.assertEqual(self.contractor_staff.dash_scope_company_id, self.other_contractor, '預帶範圍公司照舊')

    def test_no_scope_prefill_or_scope_on_main_company(self):
        self.assertFalse(self.staff.dash_scope_company_id, '不可把範圍公司預帶成主公司')
        with self.assertRaises(ValidationError):
            self.staff.write({'dash_scope_company_id': self.main.id})
