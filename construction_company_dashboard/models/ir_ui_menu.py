# -*- coding: utf-8 -*-
"""營造廠主管的選單允許清單（合約 §3.7）。

只看得到「公司儀表板」「進度表圖表」與它們的上層選單（不給工程案件選單：工程表單的數量按鈕會讀到看不到的模型而報錯）。
選單 xmlid 先定成常數：menu_company_dashboard 由線 C 建立，沒裝／還沒建時略過。
"""
from odoo import api, models

ALLOWED_MENU_XMLIDS = (
    'construction_company_dashboard.menu_company_dashboard',
    'construction_progress.menu_progress_chart_dashboard',
)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _dash_allowed_menu_ids(self):
        """允許清單選單＋它們的上層（parent_path 取）＋底下的子選單。"""
        Menu = self.sudo().with_context(**{'ir.ui.menu.full_list': True, 'active_test': False})
        ids = set()
        for xmlid in ALLOWED_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            menu = menu.sudo()
            ids.update(int(i) for i in (menu.parent_path or '').split('/') if i)
            ids.update(Menu.search([('id', 'child_of', menu.id)]).ids)
        return ids

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug)
        user = self.env.user
        if user and not user._is_public() and user._dash_is_contractor_manager():
            return visible & self._dash_allowed_menu_ids()
        return visible
