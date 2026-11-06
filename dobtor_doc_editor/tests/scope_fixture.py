# -*- coding: utf-8 -*-
"""測試夾具：前台協作者在「裝了公司儀表板範圍欄位」的庫裡要像真的營造方帳號。

背景（construction_company_dashboard 合約 §0b-4、§0b-29）：
- construction_supervision_base 會把沒勾營造／監造組織的前台帳號預設成營造組織
  （res_users.py `_apply_default_contractor_org`）→ 這種帳號是營造方。
- 營造方的範圍公司空白＝預設拒絕（什麼都看不到）；範圍公司是營造廠時，
  dobtor 文件只讀、寫得到協作者含自己的那幾份（受邀協作）。
真實的營造方前台帳號一定設了範圍公司（換版前用 contractor_fill_report.py 補齊），
所以夾具照真實設定給範圍公司；沒有這個欄位的庫（沒裝 construction_supervision_base）什麼都不做。
期望值不變：這些測試驗的本來就是「受邀的讀寫得到、沒受邀的讀不到」。
"""

COMPANY_TYPE_CONTRACTOR = 'contractor'


def scope_portal_as_contractor(env, user, company=None):
    """給前台帳號一個營造廠範圍公司；回傳那家公司（沒有範圍欄位的庫回 None）。"""
    if 'dash_scope_company_id' not in env['res.users']._fields:
        return None
    if company is None:
        company = env['res.company'].sudo().create({
            'name': f'{user.login} 營造廠',
            'company_type': COMPANY_TYPE_CONTRACTOR,
        })
    user.sudo().dash_scope_company_id = company
    return company
