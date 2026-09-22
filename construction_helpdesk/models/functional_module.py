# -*- coding: utf-8 -*-
from odoo import fields, models


class ConstructionFunctionalModule(models.Model):
    """發生功能：客戶在使用哪一個功能時遇到問題。

    就是一份可編輯的名稱清單，刻意不關聯 ir.module.module：技術模組≠使用者看到的功能
    （前台全部都在 construction_portal 一個模組裡，統計會失真）。
    寫成清單而非寫死在程式：前台新增功能時在後台加一筆即可，不必改程式。

    同一份清單服務兩邊：
    - 前台「意見回饋」只列出勾了「前台顯示」的項目（客戶看得到的功能）；
    - 後台服務單／問題單可選全部（含契約工項、估驗計價這類只在後台的功能）。
    """
    _name = 'construction.functional.module'
    _description = '發生功能'
    _order = 'sequence, id'

    name = fields.Char(string='名稱', required=True)
    sequence = fields.Integer(string='排序', default=10)
    active = fields.Boolean(string='啟用', default=True)
    portal_name = fields.Char(
        string='前台顯示名稱',
        help='前台與後台對同一個功能叫法不同時填這裡（例：後台「進度管理」在前台叫「工程進度」）。'
             '留空＝前台也顯示「名稱」。')
    show_in_portal = fields.Boolean(
        string='前台顯示', default=True,
        help='勾選的項目才會出現在前台「意見回饋」的「在哪個功能遇到問題？」選單。'
             '只在後台才有的功能（例如契約管理、估驗計價、成本分析）不要勾。')

    def get_portal_label(self):
        self.ensure_one()
        return self.portal_name or self.name

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '發生功能名稱不可重複。'),
    ]
