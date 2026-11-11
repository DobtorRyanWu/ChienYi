# -*- coding: utf-8 -*-
"""session 旗標（合約 §2）：給前端公司服務與營造廠主管／後台角色帳號的提示用。"""
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        user = self.env.user
        signed_in = bool(user) and not user._is_public()
        # 營造方標記（營造廠主管、營造方角色帳號）：沒有 cids cookie 時前端改成開啟全部允許公司
        # （static/src/backend/company_service_patch.js）
        manager = signed_in and user._dash_is_contractor_manager()
        result['dash_show_all_allowed_companies'] = manager
        # 營造廠主管或後台角色帳號（含監造方）尚未啟用兩步驟驗證、而且強制兩步驟驗證時（_dash_totp_missing）：
        # 前端提示去「帳戶安全性」啟用。範圍不合格見 _dash_scope_ok
        result['dash_totp_missing'] = signed_in and (manager or user._is_role_account()) and user._dash_totp_missing()
        # 唯讀帳號（營造廠主管、控台讀取、後台角色帳號）：私訊／群組對話的 @ 建議名單另列讀得到的內部同事
        # （S2 fix2-U，使用者 11-11 暫定；static/src/backend/mention_colleagues_patch.js、restricted_mail.py 檔頭九）
        result['dash_mention_colleagues'] = signed_in and user._dash_is_restricted_internal()
        return result
