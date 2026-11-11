# -*- coding: utf-8 -*-
"""營造廠主管與後台角色帳號的選單允許清單（合約 §3.7；角色帳號 S1，2026-11-10）。

* 營造廠主管：只看得到「公司儀表板」「進度表圖表」與它們的上層選單（不給工程案件選單：工程表單的數量按鈕會讀到看不到的模型而報錯）。
* 後台角色帳號：公司儀表板、估驗計價、成本分析、即時損益、契約工項、契約變更單、進度表／進度明細／進度表圖表／進度報告、
  手機版（S2：回手機首頁）。
  判斷排在營造廠主管之前（營造方角色帳號也帶營造廠主管群組）。
選單 xmlid 先定成常數：沒裝的模組（成本分析是選裝）或還沒建的選單略過。
"""
from odoo import api, models

ALLOWED_MENU_XMLIDS = (
    'construction_company_dashboard.menu_company_dashboard',
    'construction_progress.menu_progress_chart_dashboard',
)
# 後台角色帳號（xmlid 逐一讀 views/menu.xml 確認）
ROLE_MENU_XMLIDS = (
    'construction_company_dashboard.menu_company_dashboard',        # 工程管理 > 工程總覽 > 公司儀表板
    'construction_supervision_base.menu_estimate',                  # 計價請款 > 估驗計價（construction_payment 掛上 action）
    'construction_cost_analysis.menu_cost_analysis',                # 計價請款 > 成本分析（選裝）
    'construction_general.menu_general_realtime_profit',            # 計價請款 > 即時損益
    'construction_supervision_base.menu_supervision_task',          # 工程管理 > 工程總覽 > 契約工項
    'construction_contract_change.menu_contract_change_order',      # 工程管理 > 契約管理 > 契約變更單
    'construction_progress.menu_progress_schedule',                 # 工程管理 > 進度管理 > 進度表
    'construction_progress.menu_progress_schedule_line',            # 進度明細
    'construction_progress.menu_progress_chart_dashboard',          # 進度表圖表
    'construction_general.menu_general_progress_report',            # 進度報告
    'construction_company_dashboard.menu_role_phone_home',          # 手機版（回 /construction；S2）
)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _dash_allowed_menu_ids(self, xmlids=ALLOWED_MENU_XMLIDS):
        """允許清單選單＋它們的上層（parent_path 取）＋底下的子選單。"""
        Menu = self.sudo().with_context(**{'ir.ui.menu.full_list': True, 'active_test': False})
        ids = set()
        for xmlid in xmlids:
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
        if not user or user._is_public():
            return visible
        if user._is_role_account():
            return visible & self._dash_allowed_menu_ids(ROLE_MENU_XMLIDS)
        if user._dash_is_contractor_manager():
            return visible & self._dash_allowed_menu_ids()
        return visible
