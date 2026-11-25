# -*- coding: utf-8 -*-
"""W5 乙組：自主檢查勾選換算與報表（E2-2、E2-5，2026-11-25）。

E2-2 改題目（type_item_id）或同時改勾選與題目時，換算要用「寫入後」的反向題設定
E2-5 通用 QWeb 自檢報表：勾選樣式的表要印實際勾選（是／否…），不可每題都印成合格 ✓
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged

GENERAL_REPORT = 'construction_quality.report_general_self_inspection'
RESERVATION_REPORT = 'construction_quality.report_reservation_self_inspection'
# 明細列的合格記號（頁首的總結果另有「✓ 合格」，不算）
PASS_TICK = '<span style="color: #28a745;">✓</span>'


@tagged('post_install', '-at_install', 'construction_quality')
class TestMarkFollowups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '勾選追修測試', 'code': 'QA-MARKFU',
            'project_type': 'general', 'company_id': cls.env.company.id})
        Type = cls.env['self.inspection.type']
        cls.t_eco = Type.create({'name': '追修生態保育', 'result_layout': 'yes_partial_no'})
        cls.t_rec = Type.create({'name': '追修環境清潔', 'result_layout': 'yes_no'})
        Question = cls.env['self.inspection.type.item']
        cls.q_normal = Question.create({'type_id': cls.t_eco.id, 'name': '一般題'})
        cls.q_reverse = Question.create({'type_id': cls.t_eco.id, 'name': '是否有民眾陳情', 'reverse_question': True})

    def _insp(self, itype):
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'name': 'QA-MARKFU', 'inspection_type_id': itype.id,
            'sub_project_name': '勾選追修', 'inspection_date': fields.Date.today()})
        insp.checklist_ids.unlink()
        return insp

    def _item(self, insp, **vals):
        return self.env['general.self.inspection.item'].create(
            dict({'inspection_id': insp.id, 'check_item': '題目'}, **vals))

    # ── E2-2 ──
    def test_e2_2_changing_question_recomputes_result(self):
        item = self._item(self._insp(self.t_eco), type_item_id=self.q_normal.id, mark='yes')
        self.assertEqual(item.check_result, 'pass')
        item.write({'type_item_id': self.q_reverse.id})
        self.assertEqual(item.check_result, 'defect', '改成反向題後，答「是」要算缺失')
        item.write({'type_item_id': self.q_normal.id})
        self.assertEqual(item.check_result, 'pass')

    def test_e2_2_mark_and_question_written_together_use_new_question(self):
        item = self._item(self._insp(self.t_eco), type_item_id=self.q_reverse.id, mark='no')
        self.assertEqual(item.check_result, 'pass')
        item.write({'mark': 'yes', 'type_item_id': self.q_normal.id})
        self.assertEqual(item.check_result, 'pass', '一般題答「是」是通過；不可用舊的反向題設定換算')

    def test_e2_2_standard_layout_untouched(self):
        std = self.env['self.inspection.type'].create({'name': '追修標準'})
        item = self._item(self._insp(std), check_result='defect')
        item.write({'check_result': 'pass'})
        self.assertEqual(item.check_result, 'pass')

    # ── E2-5 ──
    def _html(self, report, insp):
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(report, insp.ids)
        return html.decode('utf-8') if isinstance(html, bytes) else str(html)

    def test_e2_5_general_report_prints_actual_mark(self):
        insp = self._insp(self.t_rec)
        self._item(insp, mark='no', check_item='有塵土外溢道路')
        html = self._html(GENERAL_REPORT, insp)
        self.assertIn('有塵土外溢道路', html)
        self.assertNotIn(PASS_TICK, html, '勾選樣式的表不可把「否」印成合格 ✓')
        self.assertIn('>否<', html.replace(' ', '').replace('\n', ''))

    def test_e2_5_standard_report_still_ticks(self):
        std = self.env['self.inspection.type'].create({'name': '追修標準報表'})
        insp = self._insp(std)
        self._item(insp, check_result='pass', check_item='標準題')
        self.assertIn(PASS_TICK, self._html(GENERAL_REPORT, insp))
