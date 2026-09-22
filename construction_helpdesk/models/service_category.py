# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionServiceCategory(models.Model):
    _name = 'construction.service.category'
    _description = '服務單類別'
    _order = 'sequence, id'

    name = fields.Char(string='名稱', required=True, translate=False)
    sequence = fields.Integer(string='排序', default=10)
    active = fields.Boolean(string='啟用', default=True)
    ask_functional_module = fields.Boolean(
        string='詢問發生功能',
        help='勾選的類別，前台「意見回饋」會多問一題「在哪個功能遇到問題？」（選填）。'
             '只對跟軟體操作有關的類別有意義（操作疑問、系統問題）；'
             '帳務、硬體、銷售等類別問這題只會讓客戶困惑。')
    is_system_problem = fields.Boolean(
        string='系統問題類',
        help='勾選的類別才能「轉問題單」。全系統只能有一個，且不可刪除、不可封存。',
    )

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', '服務單類別名稱不可重複。'),
    ]

    @api.constrains('is_system_problem')
    def _check_single_system_problem(self):
        # 封存的也要算進來，否則「封存舊的、再勾一個新的」就繞過了唯一性
        count = self.with_context(active_test=False).search_count(
            [('is_system_problem', '=', True)])
        if count > 1:
            raise ValidationError(_('「系統問題」類別只能有一個。'))

    def write(self, vals):
        # 不可把「系統問題」類別封存，也不可把它的系統問題旗標拿掉
        # （拿掉等於變相刪除：全系統會沒有任何類別能轉問題單）
        protected = self.filtered('is_system_problem')
        if protected:
            if 'active' in vals and not vals['active']:
                raise UserError(_('「系統問題」類別不可封存。'))
            if 'is_system_problem' in vals and not vals['is_system_problem']:
                raise UserError(_('不可取消「系統問題」類別的系統問題旗標。'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_system_problem(self):
        # at_uninstall=False：解除安裝本模組時仍可正常清除
        if self.filtered('is_system_problem'):
            raise UserError(_('「系統問題」類別不可刪除。'))
