# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': '試算表工作區',
    # 1.0.0: 在 OCA 試算表（spreadsheet_oca）上加資料夾與左側導覽、模板庫、版本紀錄與對比、
    #        清單優先操作與繁中介面。純擴充：不另立 App、不新增第二張試算表資料表。
    # 1.0.1: 一般試算表（spreadsheet.spreadsheet）的協作操作列也納入寫入守衛（原本只保護模板）：
    #        要對該試算表有寫入權才能建／改／刪它的操作列。OCA 原本對所有內部帳號全開。
    # 1.0.2: 2026-11-25 低風險四條：拿掉「跳過自動版本」的 context 旗標，直接寫 spreadsheet_binary_data 也留版本；
    #        資料夾改掛別家公司在修改時也擋；另存為模板要有寫入權；刪試算表／模板時一併清掉它的協作操作列。
    #        不需要 migration（沒有欄位或資料變動；既有的孤兒操作列不處理）。
    'version': '18.0.1.0.2',
    'summary': '在 OCA 試算表上加資料夾、模板庫、版本紀錄與對比',
    'description': """
試算表工作區
============
以 ``_inherit`` 擴充 OCA ``spreadsheet.spreadsheet``，OCA 原檔不動：

* 階層資料夾＋清單左側導覽（資料夾、標籤）
* 模板庫：從模板建立試算表、試算表另存為模板
* 版本紀錄：手動「存成版本」＋存檔時自動存版本（內容有變才存），並可「對比最新版」
* 清單優先：點一列直接開啟、列尾齒輪改資訊、「新增」直接建立並開啟、表單「下載 XLSX」

畫面與功能分組參考 Dobtor Spreadsheet 平台（dobtor_spreadsheet）的操作方式重新實作，
未使用其原始碼。
    """,
    'category': 'Productivity',
    'author': 'ChienYi',
    # 繼承的 spreadsheet_oca 是 AGPL-3，衍生模組用同一個授權
    'license': 'AGPL-3',
    'depends': [
        'spreadsheet_oca',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/spreadsheet_version_save_views.xml',
        'views/spreadsheet_folder_views.xml',
        'views/spreadsheet_template_views.xml',
        'views/spreadsheet_version_views.xml',
        'views/spreadsheet_spreadsheet_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'spreadsheet_workspace/static/src/views/workspace_views.js',
            'spreadsheet_workspace/static/src/views/workspace_views.xml',
            'spreadsheet_workspace/static/src/action_loader.js',
        ],
        # o-spreadsheet 引擎所在的延遲載入 bundle：版本對比要在瀏覽器端把「底稿＋操作」算成實際內容
        'spreadsheet.o_spreadsheet': [
            'spreadsheet_workspace/static/src/bundle/version_diff.js',
            'spreadsheet_workspace/static/src/bundle/version_compare_action.js',
            'spreadsheet_workspace/static/src/bundle/version_compare_action.xml',
            'spreadsheet_workspace/static/src/bundle/control_panel_patch.js',
            'spreadsheet_workspace/static/src/bundle/control_panel_patch.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
