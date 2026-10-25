# -*- coding: utf-8 -*-
"""前台施工日誌可填「累計實際進度(%)」（daily.log.sheet.actual_progress）。

2026-10-25 使用者裁示：日誌與工程施工進度報告表上的實際進度，取「當天或之前最後一次
有填的累計值」（construction_template/utils/progress.py）。這個欄位以前只有 xlsm 匯入
會寫，後台表單隱藏、前台沒有欄位——現場沒地方填，印出來永遠是空白。

空白＝這天沒更新（存 0），列印時沿用前一次；不合法的值整筆不寫、導回編輯頁。
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
class TestPortalDailyLogActualProgress(TransactionCase):

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

    def test_update_writes_actual_progress(self):
        sheet = self._sheet()
        res = self._update(sheet, actual_progress='35.5')
        self.assertIn('message=updated', self._location(res))
        self.assertEqual(sheet.actual_progress, 35.5)

    def test_blank_means_not_updated(self):
        sheet = self._sheet()
        sheet.write({'actual_progress': 20.0})
        self._update(sheet, actual_progress='')
        self.assertEqual(sheet.actual_progress, 0.0)

    def test_invalid_redirects_and_writes_nothing(self):
        sheet = self._sheet()
        bads = ('-1', '100.01', 'abc', 'nan', 'inf',
                FileStorage(BytesIO(b'5'), filename='x.txt'))
        for bad in bads:
            res = self._update(sheet, work_summary='不該寫入', actual_progress=bad)
            self.assertIn('/edit?error=invalid_progress', self._location(res), bad)
            self.assertEqual(sheet.actual_progress, 0.0, bad)
            self.assertFalse(sheet.work_summary, bad)

    def test_create_with_actual_progress(self):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            res = self.ctrl.portal_construction_daily_log_create(
                project_id=str(self.project.id),
                log_date=str(fields.Date.today() - timedelta(days=1)),
                actual_progress='12')
        self.assertIn('message=created', self._location(res))
        log = self.env['daily.log.sheet'].search(
            [('supervision_project_id', '=', self.project.id)], limit=1)
        self.assertEqual(log.actual_progress, 12.0)

    def test_create_invalid_redirects_without_creating(self):
        with MockRequest(self.env(user=self.leader)) as req:
            req.httprequest.files.getlist.return_value = []
            res = self.ctrl.portal_construction_daily_log_create(
                project_id=str(self.project.id),
                log_date=str(fields.Date.today() - timedelta(days=1)),
                actual_progress='abc')
        self.assertIn('/daily-log/new?error=invalid_progress', self._location(res))
        self.assertFalse(self.env['daily.log.sheet'].search(
            [('supervision_project_id', '=', self.project.id)]))
