# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 樣板設定',
    'version': '18.0.2.2.0',
    'category': 'Construction/Supervision',
    'summary': '文件樣板管理與設定',
    'description': """
工程監造系統 - 樣板設定模組
============================

此模組提供文件樣板管理功能：

主要功能
--------
* 文件樣板管理 (document.template)
* 支援多種樣板類型：施工日誌、自主檢查、缺失改善、進度表、估驗計價表等
* 系統預設樣板與專案自訂樣板
* 樣板上傳、下載、測試功能
* 欄位對照表設定 (JSON 格式)

技術特點
--------
* 多層級樣板優先順序：專案專屬 > 公司預設 > 系統預設
* 支援 Excel/Word 樣板格式
* 完整的權限控制
* 上傳樣板時檢查檔案格式與樣板類型是否相符（docx 類型不能傳 xlsx）
* 專案層級彙總表可由呼叫端用 context 指定日期區間；日期空白的記錄一律列入
  並回報，不會被靜默排除
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        # 樣板套印需要在施工日誌表單加匯出按鈕。
        # 反向不成立（daily_log 不依賴 template），無循環依賴。
        'construction_daily_log',
        'construction_notification_slip',
        'construction_payment',
        'construction_acceptance',
        'construction_test',
        # docx 樣板的 +++INS+++ → docxtpl Jinja2 轉換器在這個模組裡。
        # dobtor_doc_editor 只依賴 base/web/mail/html_editor/bus/portal，不會循環。
        'dobtor_doc_editor',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/document_template_views.xml',
        'views/daily_log_export_views.xml',
        'views/project_export_views.xml',
        'views/notification_slip_export_views.xml',
        'views/payment_estimate_export_views.xml',
        'views/acceptance_test_export_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    # 安裝時把 data/templates_blank/ 的 13 個空白範本灌成系統預設樣板
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 50,
}
