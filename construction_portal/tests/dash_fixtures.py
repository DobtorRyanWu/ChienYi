# -*- coding: utf-8 -*-
"""前台測試的帳號／工程夾具（公司儀表板合約 §2、§3.6 之後）。

前台帳號沒勾監造組織時，既有程式會自動設成營造組織（res.users._apply_default_contractor_org），
也就是「營造方」：可見範圍＝工程的營造廠含自己的範圍公司，範圍公司空白＝什麼都看不到（預設拒絕）。
所以既有前台測試要明寫帳號是哪一方：

- 營造方前台帳號：contractor_user_vals(營造廠)，測試工程要用 contractor_project_vals(營造廠)
  把這家營造廠填進「承攬廠商」（在建單據之前填，單據的營造廠歸屬才會自動帶入）；
- 監造方前台帳號（代表監造單位的前台人員，審核類動作只有監造方能做）：SUPERVISION_USER_VALS。

本檔不是測試模組（檔名不是 test_ 開頭），只給各測試檔匯入。
"""

COMPANY_TYPE_CONTRACTOR = 'contractor'

# 監造方前台帳號：勾監造組織，不會被預設成營造組織
SUPERVISION_USER_VALS = {'is_supervision_org': True}

# 營造廠主管夾具的 TOTP 密鑰（base32，只用來讓 totp_enabled 為真）。
# 營造廠主管沒啟用兩步驟驗證＝範圍不合格、框架以外全拒（合約 §0b-8，線 A1'），
# 測「有資料可看的主管」時夾具要先啟用；沒啟用的情境由 construction_company_dashboard 的測試單獨驗。
MANAGER_TOTP_SECRET = 'JBSWY3DPEHPK3PXP'


def make_contractor(env, name):
    """建一家營造廠（公司類型＝施工廠商）。"""
    return env['res.company'].create({'name': name, 'company_type': COMPANY_TYPE_CONTRACTOR})


def contractor_project_vals(contractor):
    """併進 project.project create 的值：承攬廠商＝這家營造廠。"""
    return {'contractor_company_ids': [(6, 0, contractor.ids)]}


def contractor_user_vals(contractor):
    """併進 res.users create 的值：營造組織＋範圍公司＝這家營造廠。"""
    return {'is_contractor_org': True, 'dash_scope_company_id': contractor.id}
