# -*- coding: utf-8 -*-
"""參觀帳號的網址白名單（淞源 C11）：單一攔截點、預設拒絕。

參觀帳號登入後，除了 VISIT_ALLOWED 列的網址，其餘一律不給：
* 一般頁面（GET）導回參觀首頁；其他方法與 JSON／RPC 請求回 403。
* 帳號過期（或沒設有效期）：當下登出、導到登入頁（每日排程之後會把帳號停用，這裡是不等排程）。
掛在 ir.http._pre_dispatch：每個「有對到路由」的請求在進 controller 之前都會經過，不分 auth 型別
（公開頁帶著參觀帳號的 session 來也一樣擋）。靜態檔（/模組/static/…）不經路由，本來就是公開的。
不是參觀帳號的請求完全不受影響（只多一次群組判斷）。
"""
import logging

import werkzeug.exceptions

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

VISIT_HOME = '/construction/visit'
LOGIN_URL = '/web/login'
# 參觀帳號可以打的網址：完全相同，或以「這個＋/」開頭
VISIT_ALLOWED = (
    VISIT_HOME,                 # 參觀專用頁面（各自再對照授權表）
    '/web/assets',              # 頁面的 CSS／JS 資產包（公開路由）
    '/web/session/logout',      # 登出
    LOGIN_URL,                  # 登入頁（登出後、過期後會到這裡）
)


def visit_path_allowed(path):
    return any(path == allowed or path.startswith(allowed + '/') for allowed in VISIT_ALLOWED)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._visit_account_gate()

    @classmethod
    def _visit_account_gate(cls):
        user = request.env.user if request.env.uid else None
        if not user or not user._is_visit_account():
            return
        path = request.httprequest.path
        if user._visit_expired():
            if path == LOGIN_URL or path.startswith('/web/assets/'):
                return
            _logger.info('參觀帳號 %s（id %s）已過期，登出', user.login, user.id)
            request.session.logout(keep_db=True)
            werkzeug.exceptions.abort(request.redirect(LOGIN_URL, 303))
        if visit_path_allowed(path):
            return
        _logger.info('參觀帳號 %s（id %s）被擋：%s %s', user.login, user.id, request.httprequest.method, path)
        if request.dispatcher.routing_type != 'http' or request.httprequest.method != 'GET':
            raise werkzeug.exceptions.Forbidden('參觀帳號不能使用這個功能。')
        werkzeug.exceptions.abort(request.redirect(VISIT_HOME, 303))
