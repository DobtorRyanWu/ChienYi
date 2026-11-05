# -*- coding: utf-8 -*-
"""前台建立自主檢查：一次勾好幾個檢查時機，每一個都要存進去（2026-11-06）。

Odoo 18 的 `get_http_params()` 用 `{**httprequest.form}` 合併表單——werkzeug MultiDict
以 ** 展開時同名欄位只留第一個值，所以 `**post` 裡的 inspection_timing_ids 永遠只有一個。
紙本上「施工中＋施工完成」同時勾是常態（self.inspection.type.timing_ids 的說明），
只存第一個的話表單印出來就少一格勾，而且沒有任何錯誤訊息。
"""

from odoo import fields, http
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'construction_portal')
class TestInspectionTimingMultiSelect(HttpCase):

    def test_two_timings_both_saved(self):
        password = 'timing-multi-pw'
        user = self.env['res.users'].create({
            'name': '時機多選測試', 'login': 'timing_multi_tester', 'password': password,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('construction_supervision_base.group_supervisor_admin').id,
            ])],
        })
        project = self.env['project.project'].create({
            'name': '時機多選測試工程', 'code': 'PTL-TIMING',
            'project_type': 'general', 'company_id': self.env.company.id,
        })
        itype = self.env['self.inspection.type'].create({
            'name': '鋼筋組立檢查', 'project_id': project.id})
        picked = itype.timing_ids.filtered(lambda t: t.name in ('施工中檢查', '施工完成檢查'))
        self.assertEqual(len(picked), 2, '測資前提：類型上有這兩個時機')

        self.authenticate(user.login, password)
        response = self.url_open('/construction/inspection/create', data={
            'csrf_token': http.Request.csrf_token(self),
            'project_id': project.id,
            'inspection_type_id': itype.id,
            'inspection_date': fields.Date.today().isoformat(),
            'sub_project_name': '北段鋼筋',
            # requests 會把 list 編成同名欄位重複送出——就是瀏覽器送勾選框的樣子
            'inspection_timing_ids': [str(t) for t in picked.ids],
        })
        self.assertEqual(response.status_code, 200)
        inspection = self.env['general.self.inspection'].search(
            [('project_id', '=', project.id)])
        self.assertEqual(len(inspection), 1, '測資前提：建立了一張檢查')
        self.assertEqual(inspection.inspection_timing_ids, picked,
                         '勾了兩個檢查時機，只存進去 %s 個' % len(inspection.inspection_timing_ids))
