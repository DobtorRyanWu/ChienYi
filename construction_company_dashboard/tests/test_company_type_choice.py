# -*- coding: utf-8 -*-
"""合約 §0b-30（使用者 11-06「建公司時必選類型」）：畫面上新建公司不預帶類型、沒選存不了。

斷言打在使用者看得到的結果：表單一開沒有值、空著存檔被擋、選了才存得進去。
另記現況：程式建立（不經畫面）預設值照舊——避免日後以為程式路徑也擋住了。
"""
from odoo.tests import Form, TransactionCase, tagged

COMPANY_TYPE_SUPERVISION = 'supervision'
COMPANY_TYPE_CONTRACTOR = 'contractor'


@tagged('post_install', '-at_install', 'construction_company_dashboard')
class TestCompanyTypeChoice(TransactionCase):

    def test_new_company_form_requires_choice(self):
        form = Form(self.env['res.company'])
        self.assertFalse(form.company_type, '新建公司畫面不預帶公司類型')
        form.name = 'DASH 新建監造公司'
        with self.assertRaises(AssertionError, msg='沒選公司類型存不了'):
            form.save()
        form.company_type = COMPANY_TYPE_SUPERVISION
        company = form.save()
        self.assertEqual(company.company_type, COMPANY_TYPE_SUPERVISION)

    def test_explicit_default_from_context_is_kept(self):
        form = Form(self.env['res.company'].with_context(default_company_type=COMPANY_TYPE_CONTRACTOR))
        self.assertEqual(form.company_type, COMPANY_TYPE_CONTRACTOR, '呼叫端明確帶預設值時照用')

    def test_existing_company_form_keeps_value(self):
        company = self.env['res.company'].create({'name': 'DASH 既有監造公司',
                                                  'company_type': COMPANY_TYPE_SUPERVISION})
        form = Form(company)
        self.assertEqual(form.company_type, COMPANY_TYPE_SUPERVISION, '開既有公司不清掉類型')
        # 改一個有 onchange 的欄位（開既有紀錄時 Form 不呼叫第一次 onchange——只開表單證明不了什麼，
        # 第二輪抗辯 simplifier B 指出原本這支恆真）：只有新紀錄的第一次呼叫會清類型
        form.name = 'DASH 既有監造公司（改名）'
        self.assertEqual(form.company_type, COMPANY_TYPE_SUPERVISION, '改既有公司的其他欄位不清掉類型')
        self.assertEqual(form.save().company_type, COMPANY_TYPE_SUPERVISION)

    def test_programmatic_create_keeps_default(self):
        """現況紀錄：create() 不經畫面，預設值照舊（施工廠商）。"""
        company = self.env['res.company'].create({'name': 'DASH 程式建立'})
        self.assertEqual(company.company_type, COMPANY_TYPE_CONTRACTOR)
