# -*- coding: utf-8 -*-
"""手機施工日誌頁：當天已完成的自主檢查要列出來（淞源 2026-11-10 需求 C1）。

淞源技師：「這筆紀錄也要跑回施工日誌，寫明今天做的抽查」。修改前日誌詳情頁完全沒有檢查的資料
（只有列表頁提示「待完成檢查」）。清單由 construction_quality 的 self.inspection.daily.summary 產生，
匯出第一聯與後台表單讀同一份；這裡驗手機兩個頁面真的拿得到、畫得出來。

真實前台帳號跑真實路由，模板實際渲染成 HTML 再斷言。
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.construction_portal.tests.dash_fixtures import (
    contractor_project_vals, contractor_user_vals, make_contractor)

FIELD = 'construction_supervision_base.group_portal_user'
SECTION_TITLE = '本日自主檢查'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalDailyLogDayInspections(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.ctrl = ConstructionPortal()
        # 夾具：前台現場人員是營造方帳號（範圍公司＝工程的承攬廠商）
        cls.contractor = make_contractor(env, '日誌帶入檢查測試營造')
        cls.project = env['project.project'].create({
            'name': '日誌帶入檢查測試工程', 'code': 'PM-DAYINSP', 'project_type': 'general',
            'state': 'construction', 'company_id': env.company.id,
            **contractor_project_vals(cls.contractor)})
        env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today()}).write({'state': 'active'})
        cls.worker = env['res.users'].create({
            'name': 'dayinsp_worker', 'login': 'dayinsp_worker',
            'groups_id': [(6, 0, [env.ref(FIELD).id])],
            **contractor_user_vals(cls.contractor)})
        env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.worker.id})
        cls.employee = env['hr.employee'].search([('user_id', '=', cls.worker.id)], limit=1) \
            or env['hr.employee'].create({
                'name': 'dayinsp_worker_emp', 'company_id': env.company.id, 'user_id': cls.worker.id})
        cls.itype = env['self.inspection.type'].create({'name': '模板組立'})
        cls.today = fields.Date.today()
        cls.log = env['daily.log.sheet'].create({
            'supervision_project_id': cls.project.id,
            'company_id': env.company.id,
            'employee_id': cls.employee.id,
            'log_date': cls.today,
        })

    def _insp(self, state='inspected', day=None):
        insp = self.env['general.self.inspection'].create({
            'project_id': self.project.id, 'inspection_type_id': self.itype.id,
            'inspection_date': day or self.today, 'sub_project_name': '擋土牆',
            'inspection_location': 'A 區',
        })
        insp.checklist_ids.unlink()
        self.env['general.self.inspection.item'].create(
            {'inspection_id': insp.id, 'check_item': '題目', 'check_result': 'pass'})
        if state != 'draft':
            insp.write({'state': state})
        return insp

    def _drive(self, method, *args):
        """現場人員跑真實路由，路由 render 的模板實際渲染成 HTML。回傳 (values, html)。"""
        self.env.flush_all()
        self.env.invalidate_all()
        env = self.env(user=self.worker)
        seen = {}
        with MockRequest(env) as req:
            req.httprequest.files.getlist.return_value = []
            req.httprequest.args = {}
            req.params = {}
            req.render = lambda tpl, vals=None, **k: seen.update(tpl=tpl, vals=vals) or '<render>'
            res = method(*args)
            self.assertIn('tpl', seen, '路由沒有 render（被導走了）：%s' % getattr(res, 'headers', res))
            html = env['ir.ui.view']._render_template(seen['tpl'], dict(seen['vals']))
        return seen['vals'], html.decode() if isinstance(html, bytes) else html

    def test_detail_lists_done_inspections_of_the_day(self):
        done = self._insp()
        draft = self._insp(state='draft')
        yesterday = self._insp(day=self.today - timedelta(days=1))
        values, html = self._drive(
            self.ctrl.portal_construction_daily_log_detail, self.project.id, self.log.id)
        self.assertEqual([row['id'] for row in values['day_inspections']], [done.id])
        self.assertIn(SECTION_TITLE, html)
        self.assertIn('/construction/inspection/%s"' % done.id, html)
        self.assertIn('模板組立（擋土牆 A 區）', html)
        self.assertIn('合格', html)
        for other in (draft, yesterday):
            self.assertNotIn('/construction/inspection/%s"' % other.id, html)

    def test_detail_without_inspection_has_no_section(self):
        self._insp(state='draft')
        values, html = self._drive(
            self.ctrl.portal_construction_daily_log_detail, self.project.id, self.log.id)
        self.assertEqual(values['day_inspections'], [])
        self.assertNotIn(SECTION_TITLE, html)

    def test_edit_form_shows_count_hint(self):
        self._insp()
        self._insp(state='confirmed')
        values, html = self._drive(
            self.ctrl.portal_construction_daily_log_edit, self.project.id, self.log.id)
        self.assertEqual(values['day_inspection_count'], 2)
        self.assertIn('目前 2 筆', html)

    def test_new_form_renders_without_count(self):
        _values, html = self._drive(self.ctrl.portal_construction_daily_log_new, self.project.id)
        self.assertIn('匯出時會自動附在這一欄後面', html)
        self.assertNotIn('目前', html.split('匯出時會自動附在這一欄後面')[1].split('</div>')[0])
