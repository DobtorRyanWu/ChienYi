# -*- coding: utf-8 -*-
"""公司設定：期限提醒的兩個天數（淞源 2026-11-10 會議 C8）。

老闆在會中說「七天前通知現場、剩三天還沒安排就亮紅燈」是舉例，所以各公司可以自己調。
這兩個數字同時決定：每日提醒什麼時候發（models/deadline_reminder.py）、
公司儀表板與手機首頁「期限待辦」的燈號（models/project_deadline.py）。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .project_deadline import DEFAULT_MANAGER_DAYS, DEFAULT_SITE_DAYS

MAX_REMIND_DAYS = 60        # 提醒天數的上限（再早提醒就沒有意義，也避免打錯多一個零）


class ResCompany(models.Model):
    _inherit = 'res.company'

    deadline_site_days = fields.Integer(
        string='到期前幾天提醒現場', default=DEFAULT_SITE_DAYS, required=True,
        help='有期限的事項（送審、應交文件、缺失改善、公文、送件期限）還剩這麼多天時，通知權責人；'
             '沒有權責人就通知該工程的現場人員。這幾天內的事項在「期限待辦」亮黃燈。')
    deadline_manager_days = fields.Integer(
        string='剩幾天還沒辦完就提醒主管', default=DEFAULT_MANAGER_DAYS, required=True,
        help='還剩這麼多天仍未辦完時，通知該工程的老闆與主管；這幾天內的事項在「期限待辦」亮紅燈。')

    @api.constrains('deadline_site_days', 'deadline_manager_days')
    def _check_deadline_days(self):
        for company in self:
            site, manager = company.deadline_site_days, company.deadline_manager_days
            if not 0 <= manager <= site <= MAX_REMIND_DAYS:
                raise ValidationError(
                    '期限提醒天數不正確：「提醒主管」的天數不能比「提醒現場」多，兩個都要在 0 到 %s 天之間。'
                    % MAX_REMIND_DAYS)

    def _cy_deadline_days(self):
        """(提醒現場的天數, 提醒主管的天數)；沒有公司（空的 recordset）用預設值。"""
        if not self:
            return DEFAULT_SITE_DAYS, DEFAULT_MANAGER_DAYS
        self.ensure_one()
        company = self.sudo()
        return company.deadline_site_days, company.deadline_manager_days
