# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # 前台通知中心「上次查看時間」浮水印：用來算未讀數（前台帳號的 mail.notification
    # 天生 is_read=True，無法用原生未讀機制，故自建此浮水印）。
    portal_notif_last_seen = fields.Datetime(
        string='前台通知上次查看時間',
        help='前台通知中心用：晚於此時間的通知計為未讀；開啟通知頁時更新為當下。')
