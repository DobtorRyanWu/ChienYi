# -*- coding: utf-8 -*-

from odoo.addons.web.controllers.home import Home as WebHome
from odoo.http import request


class Home(WebHome):

    def _login_redirect(self, uid, redirect=None):
        # portal user 登入後直接落 /construction(URL bar 漂亮)；後台角色帳號（S2）也先到手機首頁
        # （計畫的預設決定，手機選單有「電腦版後台」）。其他 internal user 不影響(仍走 Odoo 預設邏輯,通常落 /odoo)。
        # 判斷＝res.users._portal_uses_phone_home()（/my 首頁同一份）
        if not redirect and request.env['res.users'].sudo().browse(uid)._portal_uses_phone_home():
            redirect = '/construction'
        return super()._login_redirect(uid, redirect=redirect)
