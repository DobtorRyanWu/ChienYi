# -*- coding: utf-8 -*-
from odoo import api, models

# Odoo 核心 mail 模組給系統帳號（base.partner_root）的預設名稱
ODOOBOT_DEFAULT_NAME = 'OdooBot'
# 訊息記錄（chatter）中系統動作的作者名稱
SYSTEM_PARTNER_NAME = '系統'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _rename_system_partner(self):
        """把系統帳號的顯示名稱由 OdooBot 改成「系統」。

        只在名稱「剛好是 OdooBot」時才改；使用者自己改過的名稱不覆蓋。
        由非 noupdate 的 data 檔呼叫，全新安裝與每次 -u 都會執行（冪等）。
        sudo 說明：只讀寫 base.partner_root 一筆，由程式固定，不接受外部輸入；
        只在安裝／升級（資料載入）時呼叫，不經任何使用者操作路徑。
        """
        partner = self.env.ref('base.partner_root', raise_if_not_found=False)
        if partner and partner.sudo().name == ODOOBOT_DEFAULT_NAME:
            partner.sudo().write({'name': SYSTEM_PARTNER_NAME})
        return True
