# -*- coding: utf-8 -*-
"""某工程某一天已完成的自主檢查清單（models/self_inspection_daily_summary.py）。

淞源 2026-11-10 需求 C1：檢查紀錄要帶進當天的施工日誌。日誌頁、後台表單、匯出都讀這一份，
所以「哪些算當天做過的檢查」只在這裡判斷：同工程、同一天、不是草稿，一般式與預約式都算。
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_quality.models.self_inspection_daily_summary import BLOCK_HEADING

GENERAL = 'general.self.inspection'
RESERVATION = 'reservation.self.inspection'


@tagged('post_install', '-at_install', 'construction_quality')
class TestSelfInspectionDailySummary(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        Project = cls.env['project.project']
        cls.project = Project.create({
            'name': '當日摘要測試', 'code': 'QA-DAYSUM',
            'project_type': 'general', 'company_id': company.id})
        cls.other_project = Project.create({
            'name': '當日摘要測試（別的工程）', 'code': 'QA-DAYSUM-2',
            'project_type': 'general', 'company_id': company.id})
        cls.res_project = Project.create({
            'name': '當日摘要測試（預約式）', 'code': 'QA-DAYSUM-R',
            'project_type': 'reservation', 'company_id': company.id})
        cls.slip = cls.env['reservation.notification.slip'].create({
            'project_id': cls.res_project.id, 'location': '當日摘要測試地點'})
        cls.slip.sudo().write({'state': 'in_progress'})
        cls.itype = cls.env['self.inspection.type'].create({'name': '模板組立'})
        cls.day = fields.Date.today()
        cls.Summary = cls.env['self.inspection.daily.summary']

    def _insp(self, state='inspected', day=None, project=None, model=GENERAL, result=None, **vals):
        values = {'inspection_type_id': self.itype.id, 'inspection_date': day or self.day,
                  'sub_project_name': '擋土牆'}
        if model == GENERAL:
            values['project_id'] = (project or self.project).id
        else:
            values['slip_id'] = self.slip.id
        values.update(vals)
        insp = self.env[model].create(values)
        insp.checklist_ids.unlink()
        if result:
            self.env[model + '.item'].create(
                {'inspection_id': insp.id, 'check_item': '題目', 'check_result': result})
        if state != 'draft':
            insp.write({'state': state})
        return insp

    def test_only_done_inspections_of_that_day_and_project(self):
        done = self._insp(result='pass')
        self._insp(state='draft')                                        # 草稿：還沒檢查完
        self._insp(day=self.day - timedelta(days=1))                     # 別天
        self._insp(project=self.other_project)                           # 別的工程
        rows = self.Summary._rows(self.project, self.day)
        self.assertEqual([(r['model'], r['id']) for r in rows], [(GENERAL, done.id)])
        self.assertEqual(rows[0]['number'], done.name)
        self.assertEqual(rows[0]['state'], 'inspected')

    def test_confirmed_and_closed_count_as_done(self):
        confirmed = self._insp(state='confirmed')
        closed = self._insp(state='closed')
        ids = [r['id'] for r in self.Summary._rows(self.project, self.day)]
        self.assertEqual(ids, [confirmed.id, closed.id])

    def test_reservation_inspection_included(self):
        insp = self._insp(model=RESERVATION, state='confirmed', result='pass')
        rows = self.Summary._rows(self.res_project, self.day)
        self.assertEqual([(r['model'], r['id']) for r in rows], [(RESERVATION, insp.id)])
        self.assertEqual(rows[0]['number'], insp.inspection_no)
        self.assertEqual(rows[0]['result_label'], '合格')

    def test_result_label(self):
        self._insp(result='pass')
        self._insp(result='defect')
        self._insp()                                                     # 沒有檢查項目 → 沒有整體結果
        labels = [r['result_label'] for r in self.Summary._rows(self.project, self.day)]
        self.assertEqual(labels, ['合格', '不合格', '已檢查'])

    def test_title(self):
        title = self.Summary._row_title
        self.assertEqual(title('模板組立', '擋土牆', 'A 區'), '模板組立（擋土牆 A 區）')
        self.assertEqual(title('模板組立', '模板組立', 'A 區'), '模板組立（A 區）')
        self.assertEqual(title('模板組立', '擋土牆', False), '模板組立（擋土牆）')
        self.assertEqual(title('模板組立', '模板組立', ''), '模板組立')
        self.assertEqual(title('', '擋土牆', 'A 區'), '擋土牆（A 區）')

    def test_block_text_and_limit(self):
        self.assertEqual(self.Summary._block_text(self.project, self.day), '')
        for _index in range(3):
            self._insp(result='pass', inspection_location='A 區')
        full = self.Summary._block_text(self.project, self.day)
        self.assertEqual(full.split('\n'), [
            BLOCK_HEADING,
            '1. 模板組立（擋土牆 A 區）：合格',
            '2. 模板組立（擋土牆 A 區）：合格',
            '3. 模板組立（擋土牆 A 區）：合格',
        ])
        limited = self.Summary._block_text(self.project, self.day, limit=2).split('\n')
        self.assertEqual(limited[:3], full.split('\n')[:3])
        self.assertEqual(len(limited), 4)
        self.assertIn('3', limited[3])                                   # 最後一行寫總筆數
        # 剛好等於上限：不加「共 N 筆」那一行
        self.assertEqual(self.Summary._block_text(self.project, self.day, limit=3), full)

    def test_empty_inputs(self):
        self.assertEqual(self.Summary._rows(self.env['project.project'], self.day), [])
        self.assertEqual(self.Summary._rows(self.project, False), [])
