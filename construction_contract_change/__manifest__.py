# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 契約變更管理',
    # 1.1.0: 契約工項清單注入的「變更紀錄」欄改為預設隱藏，配合
    #        construction_supervision_base 18.0.5.1.0 把顯示欄位定為 7 欄
    'version': '18.0.1.1.0',
    'category': 'Construction/Supervision',
    'summary': '工程契約變更單管理 (參考 OCA project_version 設計)',
    'description': """
工程監造系統 - 契約變更管理
============================

此模組提供工程契約變更追蹤與管理功能：

主要功能
--------
* 契約變更單 (contract.change.order)
* 變更明細 (contract.change.order.line)
* 支援金額/數量/工期變更追蹤
* 工項新增、修改、刪除變更類型
* 自動更新專案契約資訊

狀態流程
--------
* draft (草稿) -> submitted (已提送)
* submitted -> reviewing (審查中)
* reviewing -> approved (已核定) / rejected (已駁回)
* approved -> applied (已套用)

技術特點
--------
* 參考 OCA project_version 設計模式
* 完整的變更金額與比率計算
* 自動套用變更至工項與專案
* 累計變更追蹤
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'mail',  # 關鍵！支援 Chatter 功能
        'construction_supervision_base',
    ],
    # openpyxl ← pip openpyxl（契約變更 XLSX 匯入精靈解析用）
    'external_dependencies': {
        'python': ['openpyxl'],
    },
    'data': [
        # Security
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        'security/ir.model.access.csv',
        'security/security.xml',
        # Data
        'data/ir_sequence_data.xml',
        # Views
        'views/contract_change_order_views.xml',
        'views/contract_change_wizard_views.xml',
        'views/contract_change_file_import_wizard_views.xml',
        'views/project_task_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 15,
}
