# -*- coding: utf-8 -*-
{
    'name': 'Dobtor Spreadsheet Editor — ChienYi Bridge',
    # 1.0.1: 「從工項產生試算表」J 欄（累計估驗金額）葉節點改成 =前期已核定累計金額(常數)+H，
    #        跟後台 construction_payment 18.0.1.8.1 同一套算法；原本 =單價×累計數量，
    #        前期手動金額／單價 0 的整包項／單價中途改過時對不上（111-20-AEF-V 第13期 8 列）。
    #        彙總列維持 =F×I（算出 0，小計 SUM 才不會重複加總）。需要 construction_payment 18.0.1.8.1。
    # 1.0.3: 估驗單「匯入估驗試算表」「從工項產生試算表」加 Spreadsheet 群組，沒權限的人不再看到按了被擋的按鈕
    # 1.1.0: 資料夾／檔案總覽的 xlsx 加「在瀏覽器預覽」唯讀按鈕（需 dobtor_spreadsheet_editor 18.0.1.1.0）
    # 1.2.0: 「工程後台使用者」自動帶 Spreadsheet 使用者群組（2026-11-11 使用者決定所有工程後台使用者都能用試算表；
    #        頂層 App 由 construction_menu_profile 18.0.1.1.0 開回）。代操作員 imply 工程後台使用者，一併生效
    'version': '18.0.1.2.0',
    'summary': '把 xlsx 高保真匯入／可編輯試算表接到 ChienYi 估驗計價',
    'description': 'dobtor_spreadsheet_editor 與 ChienYi 業務模組橋接：'
    'payment.estimate（估驗計價）表單加「匯入估驗試算表」按鈕，開 Xlsx 高保真匯入'
    '（解析→可編輯 o-spreadsheet→下載 xlsx）。通用編輯器保持與業務無關，整合集中於本 bridge。',
    'category': 'Productivity',
    'author': 'Dobtor / ChienYi',
    'license': 'LGPL-3',
    'depends': [
        'dobtor_spreadsheet_editor',
        'construction_payment',
    ],
    'data': [
        'security/groups.xml',
        'views/payment_estimate_views.xml',
        'views/attachment_preview_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
