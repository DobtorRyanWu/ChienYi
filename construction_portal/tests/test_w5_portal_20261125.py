# -*- coding: utf-8 -*-
"""W5 甲組（2026-11-25）：預約式自主檢查建立時 POST 結果對應項目的鍵（E2-4）、
前台 JS 段落名稱要跳脫（E2-6）。

E2-4：前端依「段落分群後的順序」編 checklist_item_id_N（值＝樣板項目 id），後端預約式路徑原本卻把
checklist_result_N 依「位置」對到 inspection.checklist_ids，兩邊順序不同時結果寫到錯的題目。
改成跟一般式同一個鍵：用 checklist_item_id_N 找 type_item_id 相同的那一題。
E2-6：portal_v10.js 把 stage.label 直接接進 HTML；JS 沒有單元測試架構，以 Python 靜態斷言讀原始碼
（這是靜態檢查，不執行 JS）。
"""

import os

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers import portal_inspection
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, make_contractor)


@tagged('post_install', '-at_install', 'construction_portal')
class TestChecklistPostKey(TransactionCase):

    def test_posted_results_follow_item_id_not_position(self):
        """前端送的順序（B 先、A 後）與 checklist_ids 的位置順序（A 先、B 後）不同：
        結果必須落在 item id 指到的那一題，不是位置對到的那一題。"""
        env = self.env
        contractor = make_contractor(env, 'W5 對應鍵營造')
        project = env['project.project'].create({
            'name': 'W5 預約式', 'code': 'W5-RSV', 'project_type': 'reservation',
            'state': 'construction', 'company_id': env.company.id,
            **contractor_project_vals(contractor)})
        itype = env['self.inspection.type'].create({'name': 'W5 兩段樣板'})
        stage_a, stage_b = itype.stage_ids[:1], env['self.inspection.type.stage'].create({
            'type_id': itype.id, 'name': 'W5 第二段', 'sequence': stage_ids_seq(itype) + 10})
        item_a = env['self.inspection.type.item'].create({
            'type_id': itype.id, 'name': 'W5 題A', 'stage_id': stage_a.id})
        item_b = env['self.inspection.type.item'].create({
            'type_id': itype.id, 'name': 'W5 題B', 'stage_id': stage_b.id})
        slip = env['reservation.notification.slip'].create({
            'project_id': project.id, 'location': 'W5 地點', 'slip_no': 1})
        slip.sudo().write({'state': 'in_progress'})
        insp = env['reservation.self.inspection'].create({
            'slip_id': slip.id, 'inspection_type_id': itype.id, 'sub_project_name': 'W5'})
        insp.action_load_default_items()
        self.assertEqual(insp.checklist_ids.mapped('type_item_id'), item_a | item_b,
                         '前提：checklist 位置順序是 A、B（防恆真）')
        post = {
            'checklist_item_id_0': str(item_b.id), 'checklist_result_0': 'defect',
            'checklist_actual_0': '乙情形',
            'checklist_item_id_1': str(item_a.id), 'checklist_result_1': 'pass',
            'checklist_actual_1': '甲情形',
        }
        portal_inspection._apply_posted_checklist(insp, post)
        by_item = {line.type_item_id: line for line in insp.checklist_ids}
        self.assertEqual(by_item[item_b].check_result, 'defect')
        self.assertEqual(by_item[item_b].actual_result, '乙情形')
        self.assertEqual(by_item[item_a].check_result, 'pass')
        self.assertEqual(by_item[item_a].actual_result, '甲情形')


def stage_ids_seq(itype):
    return max(itype.stage_ids.mapped('sequence') or [0])


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalJsStageLabelEscaped(TransactionCase):

    def test_stage_label_is_escaped_in_html(self):
        """靜態檢查：portal_v10.js 不可把 stage.label 直接接進 HTML 字串，要包 escHtml()。"""
        path = os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'js', 'portal_v10.js')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        self.assertIn('function escHtml(', source, '前提：檔內有跳脫函式')
        self.assertIn('stage.label', source, '前提：檔內有用到 stage.label（防恆真）')
        self.assertNotIn("+ stage.label +", source)
        self.assertIn('escHtml(stage.label)', source)
