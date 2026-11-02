# -*- coding: utf-8 -*-
"""B2：進度表明細的麵包屑要是「進度表名稱 區間」，不是 progress.schedule.line,N / NewId。"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'construction_progress')
class TestScheduleLineDisplayName(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': '明細顯示名稱測試', 'code': 'DISP-SL', 'project_type': 'general'})
        cls.schedule = cls.env['progress.schedule'].create({
            'project_id': cls.project.id, 'calculation_mode': 'weekly',
            'change_date': '2026-08-01'})

    def test_saved_line_shows_schedule_and_period(self):
        line = self.env['progress.schedule.line'].create({
            'schedule_id': self.schedule.id, 'sequence': 1,
            'date_start': '2026-08-01', 'date_end': '2026-08-07'})
        self.assertEqual(
            line.display_name, '%s %s' % (self.schedule.name, '08/01 - 08/07'))
        self.assertNotIn('progress.schedule.line', line.display_name)

    def test_new_line_does_not_show_newid(self):
        line = self.env['progress.schedule.line'].new({'schedule_id': self.schedule.id})
        self.assertNotIn('NewId', line.display_name)
        self.assertEqual(line.display_name, self.schedule.name)
        blank = self.env['progress.schedule.line'].new({})
        self.assertNotIn('NewId', blank.display_name)
