# -*- coding: utf-8 -*-

from odoo.addons.web.controllers.home import Home as WebHome
from odoo.addons.web.controllers.utils import is_user_internal


class Home(WebHome):

    def _login_redirect(self, uid, redirect=None):
        # portal user 登入後直接落 /construction(URL bar 漂亮),
        # internal user 不影響(仍走 Odoo 預設邏輯,通常落 /odoo)
        if not redirect and not is_user_internal(uid):
            redirect = '/construction'
        return super()._login_redirect(uid, redirect=redirect)
