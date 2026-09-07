# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "工程監造系統 - 進度表管理",
    "version": "18.0.1.3.0",
    "category": "Construction/Supervision",
    "summary": "工程進度表管理 - 支援每周/每兩周/自訂計算模式",
    "description": """
進度表管理模組
==============

此模組提供工程進度表管理功能。

主要功能
--------
* 進度表管理 (progress.schedule) - 每個專案可有多版進度表
* 進度表明細 (progress.schedule.line) - 時間區間進度規劃
* 支援每周、每兩周、自訂三種計算模式
* 累計進度自動計算
* 實際進度從施工日誌自動帶入
* 差異分析：超前/正常/落後狀態

業務流程
--------
1. 建立進度表，選擇計算模式
2. 自動產生時間區間（每周/每兩周）或手動新增（自訂）
3. 填寫各區間預定進度，系統自動計算累計進度
4. 從施工日誌同步實際進度
5. 系統自動計算差異與進度狀態
    """,
    "author": "Engineering Supervision System",
    "website": "https://github.com/engineering-supervision",
    "license": "LGPL-3",
    "depends": [
        "construction_supervision_base",
        "construction_daily_log",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/progress_activate_wizard_views.xml",
        "views/progress_schedule_views.xml",
        "views/progress_schedule_graph_views.xml",
        "views/supervision_project_views.xml",
        "views/daily_log_sheet_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "construction_progress/static/src/components/progress_chart/progress_chart.js",
            "construction_progress/static/src/components/progress_chart/progress_chart.xml",
            "construction_progress/static/src/components/progress_dashboard/progress_dashboard.js",
            "construction_progress/static/src/components/progress_dashboard/progress_dashboard.xml",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
    "sequence": 20,
}
