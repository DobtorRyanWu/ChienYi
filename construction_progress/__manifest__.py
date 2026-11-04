# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "工程監造系統 - 進度表管理",
    # 1.4.0: 施工日誌表單「進度」區顯示「累計實際進度(%)」（actual_progress，原本隱藏；
    #        列印取當天或之前最後一次有填的值，見 construction_template 3.6.0）
    # 1.5.0: 撤回 1.4.0——實際進度照說明書填「本日實際進度」（每日增量），累計由進度表加總；
    #        actual_progress 回到只給舊系統 xlsm 匯入存累計值（後台不顯示），見 construction_template 3.8.0
    # 1.5.3: 進度圖表、進度看板的 Chart.js 外掛改用 construction_supervision_base 內建檔，客戶擋外網也畫得出來
    # 1.5.4: 前台三個角色（老闆／主管／現場）的 ORM 寫入權收回（ir.model.access.csv 改 1,0,0,0）。前台頁面一律走 sudo＋controller 守衛寫入，不受影響；營造廠帳號不能再繞過前台直接打 RPC 改資料
    # 1.5.5: 前台成員讀取規則補到掛在工程底下的業務資料（老闆另加公司範圍）：原本前台讀得到、沒有任何前台規則，非成員經 RPC 讀得到別案：進度表與區間
    "version": "18.0.1.5.5",
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
