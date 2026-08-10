# -*- coding: utf-8 -*-
# Copyright 2024-2025 Engineering Supervision System
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "工程監造系統 - 施工日誌",
    # 2.0.0: 照片收斂 —— photo_ids 從 M2M(ir.attachment) 改成 One2many(supervision.photo)
    # 2.1.0: 後台照片頁籤加上批次上傳精靈按鈕（鎖定且未解鎖時隱藏）
    # 2.2.0: 照片頁籤改用共用看板
    # 2.3.0: 同上，關掉照片頁籤的「加入」按鈕
    # 2.4.0: 契約工項 actual_qty 改由施工日誌自動計算（只計已確認日誌）
    # 2.6.0: 同上，補 post-migration 重算既有工項的 actual_qty 與下游金額/完成率
    #        （欄位早就存在，Odoo 不會自動排程重算）
    "version": "18.0.2.7.0",
    "category": "Construction/Supervision",
    "summary": "施工日誌管理 - 參考 hr_timesheet_sheet 設計模式",
    "description": """
施工日誌模組
============

此模組提供施工日誌管理功能，參考 hr_timesheet_sheet 的 Sheet 聚合模式設計。

主要功能
--------
* 施工日誌表單 (daily.log.sheet) - 聚合多日日誌
* 施工日誌明細 (daily.log.line) - 繼承 account.analytic.line
* 每日天氣紀錄 (daily.log.weather)
* 四態工作流程：新建 -> 草稿 -> 待審核 -> 已核准
* 多公司資料隔離 (施工廠商只能看自己公司的日誌)
* 與 hr_timesheet 整合

參考設計
--------
* hr_timesheet_sheet: Sheet 聚合模式 + 審核流程
* account.analytic.line: 工時表行整合
    """,
    "author": "Engineering Supervision System",
    "website": "https://github.com/engineering-supervision",
    "license": "LGPL-3",
    "depends": [
        "construction_supervision_base",
        "construction_notification_slip",
        "construction_photo",
        "hr_timesheet",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/mail_activity_data.xml",
        "data/daily_log_cron.xml",
        "wizard/daily_log_unlock_wizard_views.xml",
        "wizard/daily_log_add_items_wizard_views.xml",
        "wizard/weekly_schedule_add_items_wizard_views.xml",
        "views/daily_log_views.xml",
        "views/construction_weekly_schedule_views.xml",
        "views/menu.xml",
        "report/daily_log_report.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "sequence": 10,
}
