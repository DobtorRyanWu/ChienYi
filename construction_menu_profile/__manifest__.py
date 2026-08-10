# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 選單設定檔',
    'version': '18.0.1.0.0',
    'category': 'Construction/Configuration',
    'summary': '集中管理後台選單的顯示與隱藏',
    'description': """
工程監造系統 - 選單設定檔
==========================

把「哪些選單要出現在後台」集中成一份清單，取代散在各模組 menu.xml 裡的
零星停用設定。

為什麼不直接註解掉各模組的 menuitem
------------------------------------
* 註解掉父選單會讓引用它的子模組載入失敗（External ID not found）
* Odoo 原生 App（聯絡人、保養、Spreadsheets…）的 XML 不在本專案，
  根本無法用註解關閉，一定要另外寫 active=False
* 兩套做法混用之後，「現在到底開了哪些」要翻 15+ 個檔案才知道

改用本模組後，完整的開關表就是 models/ir_ui_menu.py 的 MENUS_OFF，
要把某個選單開回來，把那一行刪掉再升級即可。

運作方式
--------
data/menu_profile.xml 用 <function> 而不是 <record>。<function> 在每次模組
install 與 upgrade 都會執行，所以「升級一次 = 重新套用整份設定檔」。
清單以 env.ref(..., raise_if_not_found=False) 查詢，未安裝的模組直接略過。

完整的「保留 vs 關閉」對照表見 README.md。
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    # 只需涵蓋 MENUS_OFF 裡被關選單的擁有模組，確保本模組在它們之後載入。
    # contacts / maintenance 已分別由 construction_supervision_base /
    # construction_equipment 間接帶入，不必重複列。
    'depends': [
        'construction_supervision_base',
        'construction_daily_log',
        'construction_equipment',
        'construction_meeting_record',
        'construction_progress',
        'construction_timeline',
        'base_geoengine',
        'spreadsheet_oca',
    ],
    'data': [
        'data/menu_profile.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 99,
}
