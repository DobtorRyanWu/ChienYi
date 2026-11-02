# -*- coding: utf-8 -*-
"""案件沒填「業主/主辦機關」時，報表抬頭印空白，不印任何一家的機關名稱（T5-1）。

原本 authority_name() 在欄位空白時回退到某一家機關，其他客戶沒填機關的案件
（dev 252 案有 73 案沒填）抬頭全印成那一家。
"""

import base64
from datetime import date, timedelta

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import (
    estimate_progress_report, invoice_detail, invoice_photo, plan_review_stamp, progress_report)
from odoo.addons.construction_template.utils import docx_render, template_render

from .common import blank_template, docx_texts, xlsx_cells

# 舊的回退值：任何輸出都不該再出現這家機關
LEGACY_AUTHORITY = '臺北市政府工務局水利工程處'


def _strict_render(name, context):
    with open(blank_template(name), 'rb') as fp:
        raw = fp.read()
    original = docx_render.SandboxedEnvironment
    docx_render.SandboxedEnvironment = lambda **kw: SandboxedEnvironment(
        undefined=StrictUndefined, **kw)
    try:
        return docx_render.render(raw, context)
    finally:
        docx_render.SandboxedEnvironment = original


@tagged('post_install', '-at_install', 'construction_template')
class TestAuthorityBlank(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        start = fields.Date.today() - timedelta(days=40)
        cls.project = cls.env['project.project'].create({
            'name': '機關空白測試工程', 'code': 'TPL-AUTH-BLANK',
            'project_type': 'general', 'state': 'construction',
            'company_id': cls.env.company.id,
            'authority_name': '   ',   # 只有空白也要算沒填
            'contract_start_date': start,
            'contract_end_date': start + timedelta(days=299),
            'contract_duration': 300,
        })
        cls.estimate = cls.env['payment.estimate'].create({
            'project_id': cls.project.id, 'estimate_date': start + timedelta(days=9)})

    def test_authority_name_is_empty_string(self):
        self.assertEqual(progress_report.authority_name(self.project), '')

    def test_every_mapping_context_gets_empty_string(self):
        """四個使用處都拿到空字串（不是 False、不是舊機關）"""
        for label, ctx in (
            ('invoice_detail', invoice_detail.build_context(self.estimate)),
            ('invoice_photo', invoice_photo.build_context(self.estimate)),
            ('estimate_progress_report', estimate_progress_report.build_context(self.estimate)),
        ):
            self.assertEqual(ctx['authorityName'], '', label)
        if 'supervision.plan.control' in self.env:
            plan = self.env['supervision.plan.control'].create({
                'name': '整體施工計畫', 'project_id': self.project.id,
                'first_submit_date': date(2026, 10, 20)})
            self.assertEqual(plan_review_stamp.build_context(plan)['authorityName'], '')

    def test_filled_authority_still_printed(self):
        self.project.authority_name = '新北市政府高灘地工程管理處'
        self.assertEqual(progress_report.authority_name(self.project),
                         '新北市政府高灘地工程管理處')

    def test_docx_output_has_no_legacy_authority_or_none(self):
        out = _strict_render('estimate_progress_report.docx',
                             estimate_progress_report.build_context(self.estimate))
        for part, text in docx_texts(out).items():
            self.assertNotIn('臺北市', text, part)
            self.assertNotIn('False', text, part)
            self.assertNotIn('None', text, part)

    def test_xlsx_output_header_is_blank(self):
        # 用模組內的空白樣板建一份案件專屬樣板（庫裡既有預設樣板的檔不一定在 filestore）
        with open(blank_template('invoice_detail.xlsx'), 'rb') as fp:
            template = self.env['document.template'].create({
                'name': '機關空白測試樣板', 'template_type': 'invoice_detail',
                'project_id': self.project.id, 'file_name': 'invoice_detail.xlsx',
                'file_data': base64.b64encode(fp.read())})
        content, _name = template_render.render(template, self.estimate)
        cells = list(xlsx_cells(content).values())[0]
        self.assertEqual((cells.get('A1') or '').strip(), '')
        for ref, text in cells.items():
            self.assertNotIn(LEGACY_AUTHORITY, text or '', ref)
            self.assertNotIn('False', text or '', ref)
