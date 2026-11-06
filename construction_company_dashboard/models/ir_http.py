# -*- coding: utf-8 -*-
"""session 旗標（合約 §2）：給前端公司服務與營造廠主管的提示用。"""
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        user = self.env.user
        manager = bool(user) and not user._is_public() and user._dash_is_contractor_manager()
        # 營造廠主管：沒有 cids cookie 時前端改成開啟全部允許公司（static/src/backend/company_service_patch.js）
        result['dash_show_all_allowed_companies'] = manager
        # 營造廠主管尚未啟用兩步驟驗證：前端提示去「我的偏好」啟用（資料在啟用前一律看不到）
        result['dash_totp_missing'] = manager and user._dash_totp_missing()
        return result
