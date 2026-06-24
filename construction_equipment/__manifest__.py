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
* 人機項目主檔 (daily.log.man.machine)
* 施工日誌人機使用明細 (daily.log.man.machine.detail)
* 人機項目批次複製精靈
* 工程級人機項目管理與使用量自動累計

進階功能（付費版）
------------------
* 機具設備分類 (supervision.equipment.category)
* 機具設備主檔管理 (supervision.equipment)
* MTBF/MTTR 效能指標自動計算
* 設備維護請求與看板工作流 (supervision.equipment.request)

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
        # 注意：ir.model.access.csv 必須先載入，才能刪除舊群組
        "security/ir.model.access.csv",
        "security/security.xml",
        # Data - 人員類型預設資料必須在視圖之前載入
        "data/personnel_type_data.xml",
        "data/ir_sequence_data.xml",
        "data/equipment_request_stage_data.xml",
        # Views - 基礎功能
        "views/personnel_type_views.xml",
        "views/daily_log_man_machine_views.xml",
        "views/daily_log_sheet_views.xml",
        "views/wizard_copy_man_machine_views.xml",
        "views/daily_log_add_man_machine_wizard_views.xml",
        # Views - 進階功能（機具設備管理，已啟用）
        "views/equipment_category_views.xml",
        "views/equipment_views.xml",
        "views/equipment_request_views.xml",
        # Menu
        "views/menu.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": False,
    "sequence": 15,
}
