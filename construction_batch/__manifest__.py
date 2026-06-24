# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    'name': '工程監造系統 - 批次操作',
    'version': '18.0.1.0.0',
    'category': 'Construction/Supervision',
    'summary': '批次下載施工日誌、估驗計價表等文件',
    'description': """
批次操作模組
============

此模組提供工程監造系統的批次操作功能。

主要功能
--------
* 批次下載精靈 (batch.download.wizard)
    - 施工日誌批次下載
    - 自主檢查表批次下載
    - 估驗計價表批次下載
    - 檢試驗記錄批次下載

* 支援功能
    - 日期區間篩選
    - 格式選擇 (PDF/Excel)
    - ZIP 壓縮打包下載

設計說明
--------
* 整合 construction_daily_log 與 construction_payment 模組
* 使用 TransientModel 精靈模式
* 支援多公司資料隔離
    """,
    'author': 'Engineering Supervision System',
    'website': 'https://github.com/engineering-supervision',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_daily_log',
        'construction_payment',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Wizards
        'wizard/batch_download_wizard_views.xml',
        # Views
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 50,
}
