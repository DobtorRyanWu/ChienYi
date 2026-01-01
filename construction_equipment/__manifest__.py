# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "工程監造系統 - 人機管理",
    "version": "18.0.1.0.0",
    "category": "Construction/Equipment",
    "summary": "機具設備管理、維護請求與 MTBF/MTTR 效能指標",
    "description": """
工程監造系統 - 人機管理模組
============================

此模組提供施工機具設備管理功能，參考 Odoo 18 maintenance 模組設計。

主要功能
--------
* 機具設備分類 (supervision.equipment.category)
* 機具設備主檔管理 (supervision.equipment)
* MTBF/MTTR 效能指標自動計算
* 設備維護請求與看板工作流 (supervision.equipment.request)
* 施工日誌人機記錄 (daily.log.man.machine)

技術特點
--------
* 參考 maintenance 模組設計模式
* 支援 Odoo 18 動態屬性 (Properties)
* 糾正性維護與預防性維護
* 循環維護排程支援
* 多公司資料隔離
    """,
    "author": "Engineering Supervision System",
    "website": "https://github.com/engineering-supervision",
    "license": "LGPL-3",
    "depends": [
        "maintenance",
        "construction_supervision_base",
        "construction_daily_log",
    ],
    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/ir_sequence_data.xml",
        "data/equipment_request_stage_data.xml",
        # Views
        "views/equipment_category_views.xml",
        "views/equipment_views.xml",
        "views/equipment_request_views.xml",
        "views/daily_log_man_machine_views.xml",
        "views/daily_log_sheet_views.xml",
        "views/menu.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": False,
    "sequence": 15,
}
