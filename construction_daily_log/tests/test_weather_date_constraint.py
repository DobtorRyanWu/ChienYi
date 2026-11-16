# -*- coding: utf-8 -*-
"""天氣列日期檢查回歸測試：日誌已是單日記錄，原檢查讀不存在的 date_start／date_end 而 AttributeError。"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestWeatherDateConstraint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        project = cls.env['project.project'].create({
            'name': '天氣日期測試工程', 'code': 'WEATHER-1', 'project_type': 'general',
            'state': 'construction', 'company_id': company.id})
        employee = cls.env['hr.employee'].create({'name': '天氣測試填表人', 'company_id': company.id})
        schedule = cls.env['progress.schedule'].create({
            'project_id': project.id, 'change_date': fields.Date.today()})
        schedule.write({'state': 'active'})
        cls.sheet = cls.env['daily.log.sheet'].create({
            'supervision_project_id': project.id, 'company_id': company.id,
            'employee_id': employee.id, 'log_date': fields.Date.today()})

    def test_same_date_ok(self):
        weather = self.env['daily.log.weather'].create({
            'sheet_id': self.sheet.id, 'date': self.sheet.log_date})
        self.assertEqual(weather.date, self.sheet.log_date)

    def test_other_date_rejected(self):
        for delta in (-1, 1):
            with self.subTest(delta=delta), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.env['daily.log.weather'].create({
                        'sheet_id': self.sheet.id,
                        'date': self.sheet.log_date + timedelta(days=delta)})
