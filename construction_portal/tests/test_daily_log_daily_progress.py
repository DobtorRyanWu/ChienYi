# -*- coding: utf-8 -*-
"""前台施工日誌填「本日實際進度(%)」（daily.log.sheet.daily_actual_progress，每日增量）。

說明書（施工日誌、進度表、進度報告）的設計：日誌填本日增量、進度表加總成累計。
2026-10-25 那一版前台另開「累計實際進度」寫進 actual_progress——那個欄位存的是舊系統 xlsm 匯入的累計值，
jt 有 3,391 張日誌只靠它；使用者 2026-10-28 選「照說明書＋保留舊資料」，前台改填增量、不再碰 actual_progress。

空白＝今天沒有進度（存 0）；不合法的值整筆不寫、導回編輯頁。
"""

from datetime import timedelta
from io import BytesIO

from werkzeug.datastructures import FileStorage

from odoo import fields
from odoo.addons.website.tools import MockRequest
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

LEADER = 'construction_supervision_base.group_portal_leader'


@tagged('post_install', '-at_install', 'construction_portal')
class TestPortalDailyLogDailyProgress(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ctrl = ConstructionPortal()
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': '前台實際進度測試工程', 'code': 'PM-ACTPROG',
            'state': 'construction', 'company_id': cls.company.id,
        })
        cls.env['progress.schedule'].create({
            'project_id': cls.project.id,
            'change_date': fields.Date.today(),
        }).write({'state': 'active'})
        cls.leader = cls.env['res.users'].create({
            'name': 'pa_leader', 'login': 'pa_leader',
            'groups_id': [(6, 0, [cls.env.ref(LEADER).id])],
        })
        cls.env['supervision.project.member'].create({
            'project_id': cls.project.id, 'user_id': cls.leader.id})
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.leader.id)], limit=1) or cls.env['hr.employee'].create({
                'name': '前台實際進度測試員工', 'company_id': cls.company.id,
                'user_id': cls.leader.id})

    def _sheet(self, days_ago=1):
        return self.env['daily.log.sheet'].create({
            'supervision_project_id': self.project.id,
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'log_date': fields.Date.today() - timedelta(days=days_ago),
        })

    def _update(self, sheet, **post):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            return self.ctrl.portal_construction_daily_log_update(
                self.project.id, sheet.id, **post)

    @staticmethod
    def _location(response):
        return response.headers.get('Location', '')

    def test_update_writes_daily_increment(self):
        sheet = self._sheet()
        res = self._update(sheet, daily_actual_progress='0.35')
        self.assertIn('message=updated', self._location(res))
        self.assertEqual(sheet.daily_actual_progress, 0.35)

    def test_blank_means_no_progress_today(self):
        sheet = self._sheet()
        sheet.write({'daily_actual_progress': 2.0})
        self._update(sheet, daily_actual_progress='')
        self.assertEqual(sheet.daily_actual_progress, 0.0)

    def test_update_never_touches_imported_cumulative(self):
        # 舊系統 xlsm 匯入的累計值：前台編輯（包括舊表單殘留的 actual_progress 參數）都不可以改到它
        sheet = self._sheet()
        sheet.write({'actual_progress': 40.0})
        self._update(sheet, daily_actual_progress='1', actual_progress='0')
        self.assertEqual(sheet.actual_progress, 40.0)
        self.assertEqual(sheet.daily_actual_progress, 1.0)

    def test_form_without_the_field_keeps_the_value(self):
        # 換版前打開、換版後才送出的舊編輯頁沒有這一欄：不可以當成 0 蓋掉
        sheet = self._sheet()
        sheet.write({'daily_actual_progress': 0.8})
        self._update(sheet, work_summary='舊頁送出')
        self.assertEqual(sheet.daily_actual_progress, 0.8)
        self.assertEqual(sheet.work_summary, '舊頁送出')

    def test_invalid_redirects_and_writes_nothing(self):
        sheet = self._sheet()
        bads = ('-1', '100.01', 'abc', 'nan', 'inf',
                FileStorage(BytesIO(b'5'), filename='x.txt'))
        for bad in bads:
            res = self._update(sheet, work_summary='不該寫入', daily_actual_progress=bad)
            self.assertIn('/edit?error=invalid_progress', self._location(res), bad)
            self.assertEqual(sheet.daily_actual_progress, 0.0, bad)
            self.assertFalse(sheet.work_summary, bad)

    def test_create_with_daily_increment(self):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            res = self.ctrl.portal_construction_daily_log_create(
                project_id=str(self.project.id),
                log_date=str(fields.Date.today() - timedelta(days=1)),
                daily_actual_progress='1.2')
        self.assertIn('message=created', self._location(res))
        log = self.env['daily.log.sheet'].search(
            [('supervision_project_id', '=', self.project.id)], limit=1)
        self.assertEqual(log.daily_actual_progress, 1.2)
        self.assertFalse(log.actual_progress)

    def test_create_invalid_redirects_without_creating(self):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            res = self.ctrl.portal_construction_daily_log_create(
                project_id=str(self.project.id),
                log_date=str(fields.Date.today() - timedelta(days=1)),
                daily_actual_progress='abc')
        self.assertIn('/daily-log/new?error=invalid_progress', self._location(res))
        self.assertFalse(self.env['daily.log.sheet'].search(
            [('supervision_project_id', '=', self.project.id)]))
