# -*- coding: utf-8 -*-
"""契約附表 10 種（3.7.0）：每一份空白樣板都套得起來、帶得到該帶的表頭。

用 StrictUndefined 套印：樣板寫了對照表沒給的欄位直接拋錯（docxtpl 預設會靜靜印空白）。
附表6-2、附表7 另外驗從計畫送審／材料送審帶出來的勾選與日期。
"""

from datetime import date

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.utils import docx_render, record_filter, template_render

from .common import blank_template, docx_texts, leftovers_docx

HEADER_TYPES = (
    'plan_review_opinion_construction', 'plan_review_opinion_quality', 'qc_staff_register',
    'site_staff_register', 'quality_evaluation', 'engineer_supervision_record',
    'technician_sign_sheet', 'soil_transport_attachments',
)


def _strict_render(name, context):
    with open(blank_template(name), 'rb') as fp:
        raw = fp.read()
    original = docx_render.SandboxedEnvironment
    docx_render.SandboxedEnvironment = lambda **kw: SandboxedEnvironment(undefined=StrictUndefined, **kw)
    try:
        return docx_render.render(raw, context)
    finally:
        docx_render.SandboxedEnvironment = original


@tagged('post_install', '-at_install', 'construction_template')
class TestNtpcContractForms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '契約附表測試工程', 'code': 'TPL-CF-0806', 'company_id': cls.env.company.id,
            'contract_no': 'NTPC-115-0806', 'location': '新北市八里區',
            'authority_name': '新北市政府高灘地工程管理處', 'authority_contact_name': '王承辦',
            'management_company_name': '測試監造顧問', 'contractor_company_name': '測試營造',
            'original_contract_amount': 48785000.0,
            'contract_start_date': date(2026, 11, 1), 'contract_end_date': date(2027, 8, 27),
        })

    def test_every_header_form_renders(self):
        for ttype in HEADER_TYPES:
            mapping = template_render.get_mapping(ttype)
            self.assertIsNotNone(mapping, ttype)
            self.assertEqual(mapping.MODEL, 'project.project', ttype)
            ctx = mapping.build_context(self.project)
            out = _strict_render('%s.docx' % ttype, ctx)
            self.assertEqual(leftovers_docx(out), [], ttype)

    def test_header_values(self):
        mapping = template_render.get_mapping('qc_staff_register')
        ctx = mapping.build_context(self.project.with_context(
            **{record_filter.CTX_TO: date(2026, 11, 15)}))
        self.assertEqual(ctx['awardAmountK'], '48,785')       # 決標金額以千元計
        self.assertEqual(ctx['projectCode'], 'TPL-CF-0806')
        self.assertEqual(ctx['fillDate'], '115年11月15日')     # 批次下載的截止日
        text = docx_texts(_strict_render('qc_staff_register.docx', ctx))['word/document.xml']
        for value in ('契約附表測試工程', '新北市八里區', '48,785', '王承辦', '測試監造顧問', '測試營造'):
            self.assertIn(value, text)
        self.assertNotIn('附表8-1', text)                      # 系統預設版不帶新北的附表編號

    def test_plan_review_stamp(self):
        if 'supervision.plan.control' not in self.env:
            self.skipTest('construction_review 沒有安裝')
        plan = self.env['supervision.plan.control'].create({
            'name': '整體施工計畫', 'project_id': self.project.id,
            'first_submit_date': date(2026, 10, 20), 'second_submit_date': date(2026, 10, 28),
            'supervisor_review_date': date(2026, 10, 30), 'supervisor_review_doc_no': '和監字第001號',
        })
        approved = self.env['supervision.plan.control'].create({
            'name': '品質計畫', 'project_id': self.project.id,
            'authority_approve_date': date(2026, 11, 5), 'authority_approve_doc_no': '新北高施字第002號',
        })
        mapping = template_render.get_mapping('plan_review_stamp')
        ctx = mapping.build_context(plan)
        self.assertEqual((ctx['submitCount'], ctx['submitDate']), (2, '115年10月28日'))
        self.assertEqual((ctx['passBox'], ctx['approveBox']), ('■', '□'))
        text = docx_texts(_strict_render('plan_review_stamp.docx', ctx))['word/document.xml']
        self.assertIn('■審查合格', text)
        self.assertIn('和監字第001號', text)
        self.assertIn('□同意核定', text)
        ctx = mapping.build_context(approved)
        self.assertEqual((ctx['submitCount'], ctx['approveBox']), ('', '■'))
        text = docx_texts(_strict_render('plan_review_stamp.docx', ctx))['word/document.xml']
        self.assertIn('■同意核定', text)
        self.assertIn('新北高施字第002號', text)

    def test_material_review_record(self):
        if 'supervision.review.application' not in self.env:
            self.skipTest('construction_review 沒有安裝')
        app = self.env['supervision.review.application'].create({
            'name': '預拌混凝土', 'project_id': self.project.id,
            'is_factory_inspection': True, 'has_catalog': True, 'has_related_test_report': True,
            'review_comment': '配比符合規範', 'final_review_result': 'pass',
        })
        ctx = template_render.get_mapping('material_review_record').build_context(app)
        self.assertEqual((ctx['boxFactory'], ctx['boxCatalog'], ctx['boxLab']), ('■', '■', '□'))
        text = docx_texts(_strict_render('material_review_record.docx', ctx))['word/document.xml']
        for value in ('■駐廠檢驗', '■型錄樣品審查', '□材料試驗室檢驗', '■駐廠檢驗試驗報告', '配比符合規範', '合格'):
            self.assertIn(value, text)
        # 還沒編號（預設 '/'）印空白；沒有送審日期印回手填提示
        self.assertEqual(ctx['no'], '')
        self.assertIn('年', ctx['submitDate'])
