# -*- coding: utf-8 -*-
"""日誌標題（name）不得隨建立者的語言而不同。

name 是 stored compute，原本用建立當下的 context lang／使用者語言格式化日期：
zh_TW 使用者建的是「11月3日 週二」，en_US 使用者建的是「Tue, Nov 3」，
同一份清單裡標題兩種格式混在一起（拷貝庫 6834 筆中 4655 筆是英文格式）。
"""
from datetime import date

from odoo.tests import TransactionCase, tagged

LOG_DATE = date(2026, 11, 3)
# 固定的中文格式（11 月 3 日，星期二）
EXPECTED_NAME = '11月3日 週二'


@tagged('post_install', '-at_install', 'construction_daily_log')
class TestSheetTitleLanguage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('zh_TW')
        cls.env['res.lang']._activate_lang('en_US')
        # 同專案同一天只能一張日誌，所以每位使用者各用一個專案
        cls.projects = {}
        for code in ('zh_TW', 'en_US'):
            project = cls.env['project.project'].create({
                'name': '標題語言測試工程 %s' % code, 'code': 'TTL-%s' % code,
                'project_type': 'general',
            })
            cls.env['progress.schedule'].create({
                'project_id': project.id, 'version': 1,
                'calculation_mode': 'weekly', 'change_date': '2026-08-01',
                'state': 'active',
            })
            cls.projects[code] = project
        cls.employee = cls.env['hr.employee'].create({'name': '標題測試填表人'})

    def _user(self, login, lang):
        return self.env['res.users'].create({
            'name': login, 'login': login, 'lang': lang,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('construction_supervision_base.group_operator').id,
            ])],
        })

    def _create_as(self, user):
        # 與使用者實際操作一致：context 的 lang 跟著使用者語言
        sheet = self.env['daily.log.sheet'].with_user(user).with_context(
            lang=user.lang).create({
                'supervision_project_id': self.projects[user.lang].id,
                'employee_id': self.employee.id,
                'log_date': LOG_DATE,
            })
        return sheet.sudo()

    def test_title_same_for_zh_and_en_users(self):
        zh = self._create_as(self._user('ttl_zh', 'zh_TW'))
        en = self._create_as(self._user('ttl_en', 'en_US'))
        self.assertEqual(zh.name, EXPECTED_NAME)
        self.assertEqual(en.name, EXPECTED_NAME, '英文使用者建的日誌標題不該是英文格式')
