# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 更新紀錄、系統版本與公告',
    # 1.0.0: 第一階段 —— 更新紀錄（原因／改變／做法三欄必填、是否公告無預設、
    #        受影響模組逐一記改前／改後版號且改後必須大於改前、關聯系統問題單）
    #        第二階段 —— 系統版本（同時最多一個草稿、登記時自動放進草稿、確認時才編版號並
    #        拍版本清單、確認即鎖紀錄）、部署檢查（升到一半／不相符／本庫未安裝）、
    #        相符才能發布、發布後自動建下一版草稿、問題單「修復版本」自動推得
    #        （首次推送前的開發期間維持 1.0.0）
    'version': '18.0.1.0.0',
    'category': 'Construction/Supervision',
    'summary': '模組更新紀錄、系統版本發布、部署檢查、更新公告與維護預告',
    'description': """
工程監造系統 - 更新紀錄、系統版本與公告
========================================

* 更新紀錄：一次推送到主分支登記一筆，人工填寫
* 系統版本（YYYY.MM.N）：草稿 → 確認 → 部署檢查 → 發布（＝更新公告）
* 部署檢查：比對資料庫實際安裝版號與版本清單
* 更新公告（跳窗一次）與維護預告（橫幅）

管理功能只給 Odoo 管理員（base.group_system）。
規格：流程圖\\files\\prompt_B_更新紀錄與公告模組_construction_release.md
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'construction_helpdesk',
        # 前台公告與維護橫幅（第四階段）
        'construction_portal',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/release_security.xml',
        'data/ir_sequence_data.xml',
        'views/release_entry_views.xml',
        'views/release_views.xml',
        'views/deployment_views.xml',
        'views/problem_views.xml',
        'views/announcement_views.xml',
        'views/portal_announcement_templates.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_release/static/src/js/release_notice.js',
            'construction_release/static/src/xml/release_notice.xml',
        ],
        'web.assets_frontend': [
            'construction_release/static/src/css/portal_announcement.css',
            'construction_release/static/src/js/portal_announcement.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
