# -*- coding: utf-8 -*-
"""新北契約新增的兩種樣板類型（2026-10-25）。

material_inspection_record  附表11「材料設備品質抽(查)驗紀錄表」——一筆檢(試)驗紀錄一張
estimate_progress_report    第五條附件一「品質管理文件查對表」＋附件二「工程施工進度報告表」
                            ——一張估驗一份（兩張表都是估驗時要附的）

測的是對照表給的值，以及用模組裡的空白樣板實際套印後沒有殘留標記、
樣板用到的每一個欄位對照表都有給（StrictUndefined：拼錯一個字就拋錯，不會印空白）。
"""

from datetime import timedelta

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import (
    estimate_progress_report, material_inspection_record)
from odoo.addons.construction_template.utils import docx_render

from .common import blank_template, docx_texts, leftovers_docx


def _strict_render(name, context):
    """用 StrictUndefined 套印：樣板寫了對照表沒給的欄位就拋 UndefinedError"""
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
class TestNtpcNewForms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        today = fields.Date.today()
        cls.start = today - timedelta(days=40)
        cls.project = cls.env['project.project'].create({
            'name': '新北表單測試工程', 'code': 'TPL-NTPCNEW',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
            'authority_name': '新北市政府高灘地工程管理處',
            'management_company_name': '測試監造顧問',
            'contractor_company_name': '測試營造',
            'contract_no': '1150806A',
            'contract_start_date': cls.start,
            'contract_end_date': cls.start + timedelta(days=299),
            'contract_duration': 300,
        })
        schedule = cls.env['progress.schedule'].create({
            'project_id': cls.project.id, 'change_date': cls.start - timedelta(days=1)})
        cls.env['progress.schedule.line'].create({
            'schedule_id': schedule.id, 'sequence': 10, 'date_start': cls.start,
            'date_end': cls.start + timedelta(days=99), 'planned_progress': 50.0})
        schedule.write({'state': 'active'})
        employee = cls.env['hr.employee'].create({'name': '新北表單測試員工', 'company_id': company.id})
        cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id, 'company_id': company.id,
            'employee_id': employee.id, 'log_date': cls.start + timedelta(days=15),
            'actual_progress': 6.0})
        Estimate = cls.env['payment.estimate']
        cls.e1 = Estimate.create({'project_id': cls.project.id,
                                  'estimate_date': cls.start + timedelta(days=9)})
        cls.e2 = Estimate.create({'project_id': cls.project.id,
                                  'estimate_date': cls.start + timedelta(days=19)})

    # ------------------------------------------------------------ 進度報告表
    def test_progress_report_values(self):
        ctx = estimate_progress_report.build_context(self.e2)
        self.assertEqual(ctx['projectName'], '新北表單測試工程')
        self.assertEqual(ctx['authorityName'], '新北市政府高灘地工程管理處')
        self.assertEqual(ctx['contractNo'], '1150806A')
        self.assertEqual(ctx['contractor'], '測試營造')
        self.assertEqual(ctx['supervisorName'], '測試監造顧問')
        # 起：上一張估驗日的隔天；迄：本張估驗日
        fmt = estimate_progress_report.roc_date_cn
        self.assertEqual(ctx['periodStart'], fmt(self.start + timedelta(days=10)))
        self.assertEqual(ctx['periodEnd'], fmt(self.start + timedelta(days=19)))
        # 預定：50% × 20/100 天＝10%；實際：第 16 天填的 6%
        self.assertEqual(ctx['plannedProgress'], '10.00')
        self.assertEqual(ctx['actualProgress'], '6.00')
        self.assertEqual((ctx['aheadBox'], ctx['behindBox']), ('□', '■'))
        self.assertEqual((ctx['aheadValue'], ctx['behindValue']), ('', '4.00'))
        self.assertEqual(ctx['remainingDays'], '280')   # 300 − 20

    def test_first_period_starts_at_project_start(self):
        ctx = estimate_progress_report.build_context(self.e1)
        self.assertEqual(ctx['periodStart'], estimate_progress_report.roc_date_cn(self.start))
        self.assertEqual(ctx['actualProgress'], '')          # 第 10 天以前沒人填過
        self.assertEqual((ctx['aheadBox'], ctx['behindBox']), ('□', '□'))

    def test_progress_report_template_renders(self):
        out = _strict_render('estimate_progress_report.docx',
                             estimate_progress_report.build_context(self.e2))
        self.assertEqual(leftovers_docx(out), [])
        text = docx_texts(out)['word/document.xml']
        self.assertIn('新北市政府高灘地工程管理處', text)       # 系統預設版從案件帶機關名稱
        self.assertIn('1150806A', text)

    # ------------------------------------------------------------ 附表11
    def _test_record(self, **vals):
        standard = self.env['supervision.test.standard'].create({
            'name': '混凝土抗壓試驗', 'material': '預拌混凝土', 'project_id': self.project.id})
        base = {'project_id': self.project.id, 'standard_id': standard.id,
                'in_site_date': fields.Date.today(), 'in_site_quantity': 30.0,
                'supplier_name': '測試預拌廠', 'method_site': True, 'method_lab': True,
                'lab_name': '測試試驗所', 'test_report_no': 'R-001', 'result': 'pass'}
        base.update(vals)
        return self.env['supervision.test.record'].create(base)

    def test_inspection_record_values(self):
        rec = self._test_record(value_ids=[
            (0, 0, {'item_name': '抗壓強度', 'standard_value': '≥280', 'test_value': '305'})])
        ctx = material_inspection_record.build_context(rec)
        self.assertEqual(ctx['supplier'], '測試預拌廠')
        self.assertEqual((ctx['methodSite'], ctx['methodLab'], ctx['methodFactory']), ('■', '■', '□'))
        self.assertEqual(ctx['methodOther'], '□')
        self.assertEqual((ctx['passBox'], ctx['failBox']), ('■', '□'))
        self.assertEqual(ctx['reportNo'], 'R-001')
        self.assertEqual(len(ctx['values']), 3)             # 紙本預印 3 組，不足補空白
        self.assertEqual(ctx['values'][0]['test'], '305')
        self.assertEqual(ctx['values'][2]['item'], '')
        self.assertEqual(ctx['asReportBox'], '□')           # 有數據列就不勾「如試驗報告」

    def test_inspection_record_more_than_three_values(self):
        rec = self._test_record(value_ids=[
            (0, 0, {'item_name': '項目%d' % n, 'test_value': str(n)}) for n in range(5)])
        ctx = material_inspection_record.build_context(rec)
        self.assertIn('項目3', ctx['valuesMore'])          # 第 4 組起不能靜靜消失
        self.assertIn('項目4', ctx['valuesMore'])

    def test_inspection_record_template_renders(self):
        rec = self._test_record(method_other_note='廠商自主試驗')
        ctx = material_inspection_record.build_context(rec)
        self.assertEqual(ctx['methodOther'], '■')
        out = _strict_render('material_inspection_record.docx', ctx)
        self.assertEqual(leftovers_docx(out), [])
        text = docx_texts(out)['word/document.xml']
        self.assertIn('測試預拌廠', text)
        self.assertIn('■工地現場檢驗', text)
        self.assertNotIn('附表11', text)                    # 系統預設版不帶新北的附表編號

    def test_fill_date_is_taipei_date(self):
        # 提出時間存 UTC：台北 10/25 07:00 提出＝UTC 10/24 23:00，填表日期要印台北的日期
        self.e2.submitted_date = fields.Datetime.to_datetime('2026-10-24 23:00:00')
        ctx = estimate_progress_report.build_context(self.e2)
        self.assertEqual(ctx['fillDate'], '115年10月25日')

    def test_planned_does_not_depend_on_line_sequence(self):
        # 同一張進度表兩條明細序號相同（預設都是 10）時，累計要照日期累加，不能重複計算。
        # 使用中的進度表不能改明細，所以另建一個案件、明細建好再啟用
        project = self.env['project.project'].create({
            'name': '序號相同測試', 'code': 'TPL-NTPCSEQ', 'company_id': self.env.company.id})
        schedule = self.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': self.start - timedelta(days=1)})
        Line = self.env['progress.schedule.line']
        for start, end, pct in ((0, 49, 50.0), (50, 99, 20.0)):
            Line.create({'schedule_id': schedule.id, 'sequence': 10,
                         'date_start': self.start + timedelta(days=start),
                         'date_end': self.start + timedelta(days=end), 'planned_progress': pct})
        schedule.write({'state': 'active'})
        from odoo.addons.construction_template.utils import progress
        # 第 60 天：前一區間 50% ＋ 20% × 10/50
        self.assertAlmostEqual(
            progress.planned_cumulative_on(project, self.start + timedelta(days=59)), 54.0)
