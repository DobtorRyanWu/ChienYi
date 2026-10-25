# -*- coding: utf-8 -*-
"""營造版施工日誌第一聯（daily_log_c1）：第四項、第五項(一)的勾選要跟著資料走。

2026-10-24 對新北契約附表9-1 時發現：空白樣板 A23（技術士）寫死「□有■無」、A27（勤前教育）
與 A29（個人防護具）寫死「■有 □無」，A28（新進勞工）用 ${value9-1/2/3} 但對照表沒供值
——不管日誌填什麼，印出來永遠是同一個答案（或三格都空白）。資料欄位一直都在
daily.log.sheet 上，是對照表沒接。

這裡用模組裡真正的空白樣板套印，斷言產出的儲存格文字，而不是只看 build_context：
樣板寫死的勾選在 context 層看不出來。
"""

import os
import tempfile

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_template.mappings import daily_log_c1
from odoo.addons.construction_template.utils.template_render import _render_placeholder

from .common import blank_template, leftovers_xlsx, xlsx_cells

SHEET = 'xl/worksheets/sheet1.xml'


@tagged('post_install', '-at_install', 'construction_template')
class TestDailyLogC1Checkboxes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '日誌勾選測試', 'code': 'TPL-DLC1CHK',
            'project_type': 'general', 'state': 'construction',
            'company_id': company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        employee = cls.env['hr.employee'].create(
            {'name': '日誌勾選測試員工', 'company_id': company.id})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': company.id,
            'employee_id': employee.id,
            'log_date': fields.Date.today(),
        })

    def _render(self, **vals):
        self.sheet.write(vals)
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, 'out.xlsx')
            data = _render_placeholder(
                blank_template('daily_log_c1.xlsx'), dst, daily_log_c1, self.sheet)
        return data, xlsx_cells(data)[SHEET]

    def test_checkboxes_follow_data(self):
        # 刻意選「和寫死的勾選相反」的值：寫死時這組一定對不上
        data, cells = self._render(
            has_technician_requirement='yes',
            safety_pre_work_education='no',
            safety_labor_insurance_check='no_new_worker',
            safety_ppe_check='no',
        )
        self.assertIn('■有', cells['A23'])
        self.assertIn('□無', cells['A23'])
        self.assertIn('□有', cells['A27'])
        self.assertIn('■無', cells['A27'])
        self.assertIn('□有', cells['A28'])
        self.assertIn('□無', cells['A28'])
        self.assertIn('■無新進勞工', cells['A28'])
        self.assertIn('□有', cells['A29'])
        self.assertIn('■無', cells['A29'])
        self.assertEqual(leftovers_xlsx(data), [])

    def test_unfilled_prints_both_unchecked(self):
        # 沒填的題目兩格都是 □：不能替現場人員勾一個答案
        data, cells = self._render(
            has_technician_requirement=False,
            safety_pre_work_education=False,
            safety_labor_insurance_check=False,
            safety_ppe_check=False,
        )
        for ref in ('A23', 'A27', 'A28', 'A29'):
            self.assertNotIn('■', cells[ref], ref)
            self.assertIn('□', cells[ref], ref)
        self.assertEqual(leftovers_xlsx(data), [])

    def test_serial_label_and_note_8(self):
        # 工程會格式的「表報編號：」與註 8（樣板原本只有註 1～7、編號沒有標籤）
        _data, cells = self._render(safety_ppe_check='yes')
        self.assertTrue(cells['S2'].startswith('表報編號：'), cells['S2'])
        self.assertIn(self.sheet.name, cells['S2'])
        self.assertIn('8.本表單係公共工程委員會頒訂格式', cells['A37'])
