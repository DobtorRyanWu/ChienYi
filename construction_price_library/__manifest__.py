# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 價格庫管理',
    'version': '18.0.1.0.0',
    'category': 'Construction/Supervision',
    'summary': '工程常用工項標準單價資料庫管理',
    'description': """
工程監造系統 - 價格庫管理模組
==============================

此模組提供工程常用工項的標準單價資料庫功能：

主要功能
--------
* 價格庫分類管理 (樹狀結構)
* 價格庫項目管理 (標準工項單價)
* 價格變更歷史記錄
* 價格庫匯入精靈 (快速匯入契約工項)

技術特點
--------
* 樹狀分類結構 (_parent_store)
* 自動記錄價格變更歷史
* 成本組成驗證
* 批次匯入契約工項
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'uom',
    ],
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Views - item views must load before category (action reference)
        'views/price_library_item_views.xml',
        'views/price_library_category_views.xml',
        'views/price_library_import_wizard_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 30,
    'post_init_hook': 'post_init_hook',
}
